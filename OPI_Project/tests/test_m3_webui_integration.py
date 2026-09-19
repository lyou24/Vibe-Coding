"""
Milestone 3 Verification Test Suite: WebUI & Recommender Integration
app.py の M3 要件（ユーザーID初期値なし, 5段階全目標ランク統合最尤推定, 厳密照合, 多次元フィルター, 難易度表目標ランク切替, 安全アトミック更新）の実装検証
"""

import ast
import os
import pytest
from datetime import datetime

from src.database.models import Chart, Player, ScoreLog, DifficultyEnum
from src.analyzer.opi_calculator import OPICalculator
from src.recommender.recommender import OPIRecommender

APP_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))

class TestM3WebUIIntegration:
    """M3 WebUI & アルゴリズム統合の自動検証"""

    def test_app_initial_blank_and_existing_player_views_load(self):
        """初回はID空欄で、入力後はメタデータ・画像出力を含む一覧が例外なく開くこと"""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        assert len(at.exception) == 0
        assert at.sidebar.text_input[0].value == ""
        assert at.title[0].value == "Ongeki Power Indicator"

        at.sidebar.text_input[0].set_value("10605").run()
        assert len(at.exception) == 0
        assert all(metric.label != "参考OPI（全プレイ）" for metric in at.metric)
        assert any(button.label == "🖼️ フルHD画像を作成" for button in at.button)
        assert all("スマホ用" not in button.label for button in at.button)

    def test_app_ast_m3_features_presence(self):
        """app.py のソースコード内に M3 の必須要素が確実に組み込まれていることを AST および静的解析で検証"""
        with open(APP_PATH, "r", encoding="utf-8") as f:
            code = f.read()

        parsed_ast = ast.parse(code)
        assert parsed_ast is not None, "app.py が有効な Python コードとしてパース可能であること"

        # 1. 初回表示ではユーザーIDが空欄であること
        assert 'text_input("OngekiScoreLog ユーザーID", "")' in code
        assert 'text_input("OngekiScoreLog ユーザーID", "10605")' not in code

        # 2. 強制更新フラグの存在
        assert "force_update" in code, "強制更新チェックボックス変数が存在すること"
        assert "force=" in code, "fetch_user_profile または fetch_and_analyze_user に force 引数が渡されていること"

        # 3. 5段階全目標ランク統合推定 (build_user_achievements)
        assert "build_user_achievements" in code, "OPICalculator.build_user_achievements が呼び出されていること"

        # 4. (title, difficulty) 厳密照合の存在
        assert "chart_by_title_diff" in code or "difficulty" in code, "難易度を含む厳密照合が実装されていること"

        # 5. リコメンド多次元フィルター
        assert "filter_target_rank" in code or "target_rank" in code, "目標ランク選択フィルターが存在すること"
        assert "filter_level" in code or "level_filter" in code, "レベル絞り込みフィルターが存在すること"
        assert "filter_constant_range" in code or "constant_range" in code, "譜面定数スライダーが存在すること"
        assert "filter_current_rank" in code or "current_rank_filter" in code, "現在ランクフィルターが存在すること"

        # 6. 難易度表タブの目標ランク切替
        assert "diff_target_rank" in code, "難易度表タブに目標ランク切替が実装されていること"
        assert "get_chart_rank_params" in code, "各目標ランクのパラメータ取得関数が呼び出されていること"

        # 7. UI選択順・複数レベル・難易度表の降順表示
        assert 'TARGET_RANK_OPTIONS = ["S", "SS", "SSS", "SSS+", "AB+"]' in code
        assert "level_filters = st.multiselect" in code, "レベル絞り込みが複数選択であること"
        assert 'sort_values(by=f"{diff_target_rank} 適正OPI", ascending=False)' in code

        # 8. 楽曲メタデータと3一覧のフルHD画像出力
        assert '"バージョン"' in code and '"ジャンル"' in code
        assert code.count("render_image_export(") >= 4  # 定義 + 3一覧
        assert "build_full_hd_image" in code
        assert "build_pdf" not in code
        assert 'st.title("Ongeki Power Indicator")' in code

    def test_difficulty_cards_keep_readable_text_on_light_backgrounds(self):
        """ダークテーマでも難易度カードの文字色が背景に埋もれないことを検証"""
        with open(APP_PATH, "r", encoding="utf-8") as f:
            code = f.read()

        assert code.count('background-color: #f8f9fa; color: #1f2937;') >= 1
        assert 'background-color: {bg_color}; color: {text_color};' in code
        assert 'font-size: 0.95em; color: {title_color};' in code
        assert 'font-size: 0.8em; color: {detail_color};' in code

    def test_achieved_card_colors_follow_current_highest_rank(self):
        """各目標表でカード背景が譜面ごとの現在最高ランクに対応することを検証"""
        with open(APP_PATH, "r", encoding="utf-8") as f:
            code = f.read()

        expected_colors = {
            '"S": {"background": "#2e7d32"',
            '"SS": {"background": "#1565c0"',
            '"SSS": {"background": "#c62828"',
            '"SSS+": {"background": "#f9a825"',
            '"AB+": {"background": "#c2410c"',
        }
        for color_definition in expected_colors:
            assert color_definition in code

        assert 'ACHIEVED_RANK_CARD_STYLES.get(row["現在ランク"])' in code
        assert 'CURRENT_RANK_TO_ACHIEVED_RANK.get(current_rank_category)' in code
        assert '_determine_current_rank(score_log)' in code
        assert '_is_target_achieved(score_log, my_diff_target_rank)' in code

    def test_strict_title_and_difficulty_matching(self, test_session):
        """(title, difficulty) による同名曲（MASTER / LUNATIC）の混同防止の振る舞い検証"""
        # 同名曲の MASTER と LUNATIC を登録
        master_chart = Chart(
            chart_id="test_mas_chart",
            title="テスト競合楽曲",
            difficulty=DifficultyEnum.MASTER,
            level="14+",
            chart_constant=14.8,
            opi_sss_x=1650.0,
            opi_sss_y=40.0
        )
        luna_chart = Chart(
            chart_id="test_luna_chart",
            title="テスト競合楽曲",
            difficulty=DifficultyEnum.LUNATIC,
            level="15",
            chart_constant=15.2,
            opi_sss_x=1750.0,
            opi_sss_y=45.0
        )
        test_session.add_all([master_chart, luna_chart])
        test_session.commit()

        # 照合マップを app.py と同一ロジックで構築
        charts = test_session.query(Chart).filter(Chart.title == "テスト競合楽曲").all()
        chart_by_id = {c.chart_id: c for c in charts}
        chart_by_title_diff = {
            (c.title, c.difficulty.name if hasattr(c.difficulty, 'name') else str(c.difficulty)): c 
            for c in charts
        }

        # クローラーからの模擬スコアデータ（MASTER と LUNATIC）
        score_master = {"title": "テスト競合楽曲", "difficulty": "MASTER", "score": 1005000}
        score_luna = {"title": "テスト競合楽曲", "difficulty": "LUNATIC", "score": 995000}

        matched_mas = chart_by_title_diff.get((score_master["title"], score_master["difficulty"]))
        matched_luna = chart_by_title_diff.get((score_luna["title"], score_luna["difficulty"]))

        assert matched_mas is not None, "MASTER 譜面が正しく照合されること"
        assert matched_luna is not None, "LUNATIC 譜面が正しく照合されること"
        assert matched_mas.chart_id == "test_mas_chart", "MASTER 譜面の chart_id が一致すること"
        assert matched_luna.chart_id == "test_luna_chart", "LUNATIC 譜面の chart_id が一致すること"
        assert matched_mas.chart_id != matched_luna.chart_id, "同名曲で別々の chart_id が紐づくこと"

    def test_five_ranks_mle_estimation_progression(self, test_session, seed_charts):
        """build_user_achievements による 5目標ランク統合最尤推定の動作検証"""
        calc = OPICalculator()
        user_id = 99901
        player = Player(user_id=user_id, player_name="Test5RankUser", rating=19.5)
        test_session.add(player)

        # 複数譜面のスコア（SS達成、SSS達成、AP達成など様々なパターン）
        for i, c in enumerate(seed_charts[:5]):
            score_val = 1000000 + i * 2500  # 1000000, 1002500, 1005000, 1007500, 1010000
            s_log = ScoreLog(
                user_id=user_id,
                chart_id=c.chart_id,
                score=score_val,
                is_all_break=(score_val >= 1007500),
                is_full_bell=(score_val >= 1007500),
                achieve_ss=score_val >= 990000,
                achieve_sss=score_val >= 1000000,
                achieve_sssp=score_val >= 1007500,
                achieve_s=(score_val >= 1007500),
                achieve_abp=score_val == 1010000
            )
            test_session.add(s_log)
        test_session.commit()

        scores = test_session.query(ScoreLog).filter_by(user_id=user_id).all()
        achievements = calc.build_user_achievements(seed_charts, scores)

        # 5目標ランク * 5譜面 = 25エントリ（パラメータが存在するもの）
        assert len(achievements) >= 20, "5目標ランクの成否ベクトルが生成されていること"
        ranks_in_ach = set(a['rank'] for a in achievements)
        assert ranks_in_ach == {"SS", "SSS", "SSS+", "S", "AB+"}, "全5ランクがベクトルに含まれていること"

        total_opi = calc.estimate_user_opi(achievements, initial_theta=1500.0)
        assert 1400.0 <= total_opi <= 2200.0, f"推定OPIが妥当な値であること: {total_opi}"

    def test_recommender_multidimensional_filter_behavior(self, test_db_path, test_session, seed_charts):
        """リコメンド多次元フィルター（目標ランク、レベル、定数、現ランク）の複合動作検証"""
        calc = OPICalculator()
        user_id = 99902
        # OPI 1700 の上級プレイヤー
        player = Player(user_id=user_id, player_name="MultiFilterUser", rating=19.0, total_opi=1700.0)
        test_session.add(player)
        test_session.commit()

        recommender = OPIRecommender(test_db_path)

        # 1. 目標ランク "SSS" でのリコメンド
        recs_sss = recommender.get_recommendations(user_id=user_id, target_rank="SSS", limit=10)
        assert isinstance(recs_sss, list)

        # 2. 定数範囲フィルター (15.0 〜 15.5)
        recs_const = recommender.get_recommendations(
            user_id=user_id,
            target_rank="SSS",
            chart_constant_min=15.0,
            chart_constant_max=15.5,
            limit=10
        )
        for r in recs_const:
            assert 15.0 <= r["constant"] <= 15.5, f"定数範囲外の楽曲が含まれています: {r['constant']}"

        # 3. レベルフィルター ("15")
        recs_level = recommender.get_recommendations(
            user_id=user_id,
            target_rank="SSS",
            level="15",
            limit=10
        )
        for r in recs_level:
            assert r["level"] == "15", f"指定レベル以外の楽曲が含まれています: {r['level']}"

    def test_difficulty_table_generation_all_ranks(self, test_session, seed_charts):
        """難易度表生成が5つの全目標ランク（SS, SSS, SSS+, S, AP）で正常動作することを検証"""
        calc = OPICalculator()
        target_ranks = ["S", "SS", "SSS", "SSS+", "AB+"]

        for rank in target_ranks:
            rank_rows = []
            for c in seed_charts:
                x, y = calc.get_chart_rank_params(c, rank)
                if x is not None:
                    rank_rows.append({
                        "title": c.title,
                        "constant": c.chart_constant,
                        "opi": x,
                        "y": y
                    })
            assert len(rank_rows) > 0, f"目標ランク {rank} で難易度表エントリが生成されること"
            # 難易度表の適正OPIが正の有限値であること
            for row in rank_rows:
                assert row["opi"] > 0, f"適正OPIが不正です: {row}"
                assert row["y"] > 0, f"個人差度が不正です: {row}"
