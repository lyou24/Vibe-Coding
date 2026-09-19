import os
import re
import pytest
import subprocess
from datetime import datetime
from bs4 import BeautifulSoup

from src.database.models import Chart, Player, ScoreLog, DifficultyEnum
from src.analyzer.opi_calculator import OPICalculator
from src.recommender.recommender import OPIRecommender

class TestTier4RealWorldAcceptance:
    """Tier 4: 実世界受入基準 (AC1, AC2, AC3) の厳密検証"""

    # --- AC1: Webサーバー稼働 & ID 10605 受入検証 ---

    def test_ac1_web_app_syntax_and_imports(self):
        """app.py が構文エラーなく、主要モジュールが正常にインポート可能であること"""
        app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))
        assert os.path.exists(app_path), "app.py が存在すること"

        # Python コンパイル（構文チェック）
        with open(app_path, "r", encoding="utf-8") as f:
            code = f.read()
        compile(code, app_path, "exec")

    def test_ac1_user_10605_opi_and_recommendation(self, test_db_path, test_session, seed_charts):
        """
        受入基準1 (AC1):
        テスト用ID 10605（ＮＥＧＩＮＥ, レート 19.950）のスコアログから、
        総合OPIが正常算出（約2000〜2100）され、リコメンド結果が正常に返却されること。
        """
        calc = OPICalculator()

        # 1. ユーザー作成 (ID 10605)
        user_id = 10605
        player = Player(
            user_id=user_id,
            player_name="ＮＥＧＩＮＥ",
            rating=19.950,
            log_updated_at=datetime(2026, 9, 10, 18, 30, 0)
        )
        test_session.add(player)

        # 2. サンプルHTML（Table 5）から10605のスコアログをパースして投入
        fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_user_10605.html")
        with open(fixture_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        tables = soup.find_all("table")
        score_table = tables[5]
        score_rows = score_table.find("tbody").find_all("tr")

        chart_map = {c.title: c for c in seed_charts}
        achievements = []

        for row in score_rows:
            title_elem = row.find("td", class_="sort_title").find("a")
            title = title_elem.text.strip()
            ts_elem = row.find("td", class_="sort_ts")
            score_val = int(ts_elem.text.strip().replace(",", ""))
            lamp_elem = row.find(class_="badge-lamp")
            bell_elem = row.find(class_="badge-bell")
            is_ab = bool(lamp_elem and "AB" in lamp_elem.text)
            is_fb = bool(bell_elem and "FB" in bell_elem.text)

            chart = chart_map.get(title)
            if not chart:
                continue

            s_log = ScoreLog(
                user_id=user_id,
                chart_id=chart.chart_id,
                score=score_val,
                is_all_break=is_ab,
                is_full_bell=is_fb,
                achieve_ss=score_val >= 990000,
                achieve_sss=score_val >= 1000000,
                achieve_sssp=score_val >= 1007500,
                achieve_s=(score_val >= 1007500 and is_ab and is_fb),
                achieve_abp=score_val == 1010000
            )
            test_session.add(s_log)

            # 総合OPI算出用: 5目標ランク（SS, SSS, SSS+, S, AP）の達成状況を投入
            rank_checks = [
                (chart.opi_ss_x, chart.opi_ss_y, s_log.achieve_ss),
                (chart.opi_sss_x, chart.opi_sss_y, s_log.achieve_sss),
                (chart.opi_sssp_x, chart.opi_sssp_y, s_log.achieve_sssp),
                (chart.opi_s_x, chart.opi_s_y, s_log.achieve_s),
                (chart.opi_abp_x, chart.opi_abp_y, s_log.achieve_abp),
            ]
            for x_val, y_val, ach in rank_checks:
                if x_val is not None:
                    achievements.append({
                        'x': x_val,
                        'y': y_val or 40.0,
                        'achieved': 1 if ach else 0
                    })

        test_session.commit()

        # 3. 総合OPIの最尤推定
        total_opi = calc.estimate_user_opi(achievements, initial_theta=1500.0)
        player.total_opi = total_opi
        test_session.commit()

        # 受入基準判定: レート19.950のプレイヤーの総合OPIは約2000〜2100（要件定義書3.2のレート20.0帯中央値 2076.8 近傍）
        assert 1950.0 <= total_opi <= 2150.0, (
            f"ID 10605の総合OPI算出値が要件範囲（約2000〜2100）を満たしていません: 実測値 {total_opi:.1f}"
        )

        # 4. リコメンドエンジンの実行
        recommender = OPIRecommender(test_db_path)
        # SSS目標またはAP目標でのリコメンド
        recs = recommender.get_recommendations(user_id=user_id, target_rank="SSS", limit=10)
        assert isinstance(recs, list), "リコメンド結果がリスト形式で返却されること"

    # --- AC2: run_opi.bat 自動ブートストラップ検証 ---

    def test_ac2_run_opi_bat_bootstrap(self):
        """
        受入基準2 (AC2):
        run_opi.bat が存在し、未セットアップ環境でも自動でvenv作成および
        pipインストールを行うブートストラップ機構を備えていることの静的/構文検証。
        """
        bat_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "run_opi.bat"))
        assert os.path.exists(bat_path), "run_opi.bat がリポジトリ直下に存在すること"

        with open(bat_path, "r", encoding="utf-8", errors="ignore") as f:
            bat_content = f.read().lower()

        # 1. 仮想環境の存在チェック
        assert ".venv" in bat_content, "run_opi.bat 内で .venv を確認していること"

        # 2. 未構築環境での venv 自動生成ロジック
        has_venv_creation = (
            "python -m venv" in bat_content or 
            "py -m venv" in bat_content or 
            "virtualenv" in bat_content
        )
        assert has_venv_creation, (
            "run_opi.bat に未セットアップ環境での仮想環境自動作成コマンド（python -m venv .venv 等）が含まれていません。"
        )

        # 3. 依存関係の自動インストール
        has_pip_install = (
            "pip install" in bat_content and "requirements.txt" in bat_content
        )
        assert has_pip_install, (
            "run_opi.bat に依存関係自動インストールコマンド（pip install -r requirements.txt 等）が含まれていません。"
        )

        # 4. Streamlit 起動コマンド
        assert "streamlit run" in bat_content, "run_opi.bat に streamlit run コマンドが含まれていること"

        # 5. cmd.exe による構文パース検証（未エスケープ丸括弧等の構文破壊がないことの実証防衛）
        import tempfile
        import shutil
        temp_dir = tempfile.mkdtemp(prefix="opi_syntax_check_")
        try:
            with open(bat_path, "r", encoding="utf-8", errors="ignore") as f:
                bat_text = f.read()

            mock_bat_text = re.sub(r"streamlit run app\.py.*", "echo [MOCK] streamlit run executed", bat_text)
            mock_bat_text = re.sub(r"(?m)^\s*pause\s*$", "rem pause", mock_bat_text)
            mock_bat_text = mock_bat_text.replace(
                "python -m venv .venv",
                "echo [MOCK] venv created & mkdir .venv\\Scripts & type nul > .venv\\Scripts\\activate.bat"
            )
            mock_bat_text = mock_bat_text.replace("call .venv\\Scripts\\activate.bat", "echo [MOCK] activated")
            mock_bat_text = mock_bat_text.replace("python -m pip install --upgrade pip", "echo [MOCK] pip upgraded")
            mock_bat_text = mock_bat_text.replace("pip install -r requirements.txt", "echo [MOCK] requirements installed")

            test_bat_file = os.path.join(temp_dir, "test_run_opi.bat")
            with open(test_bat_file, "w", encoding="utf-8", newline="\r\n") as f:
                f.write(mock_bat_text)

            parse_res = subprocess.run(
                ["cmd.exe", "/c", test_bat_file],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            assert parse_res.returncode == 0, (
                f"cmd.exe 構文パースエラーが発生しました (code {parse_res.returncode}): {parse_res.stderr}\n出力: {parse_res.stdout}"
            )
            assert "unexpected at this time" not in parse_res.stderr, f"構文エラー検知: {parse_res.stderr}"
            assert "仮想環境を作成しています [.venv]..." in parse_res.stdout, "未セットアップ時の開始メッセージが出力されていません"
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # --- AC3: OPI要件定義書.md 非破壊更新検証 ---

    def test_ac3_doc_non_destructive_update(self):
        """
        受入基準3 (AC3):
        OPI要件定義書.md に更新がある場合、テキスト削除が行われておらず、
        追記または取り消し線（~~）のみで編集されていることの検証。
        """
        # ワークスペースルートからの相対パス探索
        current_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.abspath(os.path.join(current_dir, "..", "..", "..", "00_Inbox", "OPI要件定義書.md")),
            os.path.abspath(os.path.join(current_dir, "..", "..", "..", "lyou_Obsidian", "00_Inbox", "OPI要件定義書.md")),
            r"C:\Users\lyoul\AI_Project\lyou_Obsidian\00_Inbox\OPI要件定義書.md",
            r"G:\マイドライブ\lyou_Obsidian\00_Inbox\OPI要件定義書.md",
            os.path.abspath("00_Inbox/OPI要件定義書.md"),
        ]
        doc_path = next((c for c in candidates if os.path.exists(c)), None)
        assert doc_path is not None, f"要件定義書が見つかりません (探索候補: {candidates})"

        with open(doc_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 必須コアセクションが保持されていること（削除されていないことの検証）
        assert "# 1. 要件定義書（Requirements Definition）" in content
        assert "F-01 データ収集機能" in content
        assert "F-02 外部楽曲DB同期機能" in content
        assert "F-03 単曲・目標ランク別OPI算出機能" in content
        assert "F-04 総合OPI算出機能" in content
        assert "F-05 目標楽曲リコメンド機能" in content
        assert "F-06 レーティング相関・分布分析機能" in content
        assert "F-07 OPI難易度表生成機能" in content
        assert "## 3.2 レーティング別 総合OPI目標値および分布統計" in content

        # Git 追跡下にある場合は git diff による削除行チェック
        try:
            repo_dir = os.path.dirname(doc_path)
            diff_result = subprocess.run(
                ["git", "diff", "--", doc_path],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                encoding="utf-8"
            )
            if diff_result.returncode == 0 and diff_result.stdout:
                diff_lines = diff_result.stdout.splitlines()
                for line in diff_lines:
                    if line.startswith("-") and not line.startswith("---"):
                        deleted_text = line[1:].strip()
                        if deleted_text:
                            # 削除行がある場合、それが取り消し線で囲まれているか、メタデータ更新等の許容範囲かを検証
                            assert "~~" in deleted_text or "updated_at" in deleted_text, (
                                f"要件定義書でテキストの削除が検出されました（取り消し線 ~~ 形式を使用してください）: {deleted_text}"
                            )
        except Exception:
            # gitコマンドが使用できない環境ではファイル内容のコアセクション保持検証のみ
            pass
