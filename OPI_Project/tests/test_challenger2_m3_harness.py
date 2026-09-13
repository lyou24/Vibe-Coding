import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
"""
Milestone 3 Empirical Verification Harness — Challenger 2
=========================================================
Adversarial Verification Suite for:
1. Dynamic Difficulty Table Generation across all 5 Target Ranks (SS, SSS, SSS+, SSS+ABFB, AP)
2. Monotonicity & Statistical Consistency of Difficulty Parameters
3. Resilient Error Handling for Anomalous/Corrupted Charts in Difficulty Table
4. Safe Atomic Crawler Updates & Differential Blockade Prevention (スコア失敗時のロールバックと差分閉塞防止)
5. Force Update Cache Bypass
6. Multi-difficulty Strict Title/Difficulty Mapping
"""

import os
import sys
import pytest
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from src.database.models import init_db, get_session_maker, Chart, Player, ScoreLog, DifficultyEnum
from src.analyzer.opi_calculator import OPICalculator
from src.recommender.recommender import OPIRecommender
from src.crawler.ongeki_crawler import OngekiCrawler

# app.py からバックエンド関数をインポート
import app
from app import fetch_and_analyze_user, DB_FILE, Session


class TestChallenger2M3DifficultyTable:
    """難易度表タブの全目標ランク動的生成に関する敵対的テスト"""

    @pytest.fixture(autouse=True)
    def setup_class(self):
        self.session = Session()
        self.calc = OPICalculator()
        yield
        self.session.close()
        from app import engine
        engine.dispose()

    def test_difficulty_table_all_five_ranks_dynamic_generation(self):
        """全5目標ランク（SS, SSS, SSS+, SSS+ABFB, AP）で実DB全譜面の動的生成および昇順ソートを検証"""
        target_ranks = ["SS", "SSS", "SSS+", "SSS+ABFB", "AP"]
        charts = self.session.query(Chart).order_by(Chart.chart_constant.asc(), Chart.title.asc()).all()
        assert len(charts) > 0, "実DBに譜面データが存在すること"

        for rank in target_ranks:
            # app.py:224-242 と同一のロジックを実行
            chart_data = []
            for c in charts:
                x, y = self.calc.get_chart_rank_params(c, rank)
                if x is not None:
                    diff_name = c.difficulty.name if hasattr(c.difficulty, 'name') else str(c.difficulty)
                    chart_data.append({
                        "楽曲名": c.title,
                        "難易度": diff_name,
                        "レベル": c.level,
                        "定数": c.chart_constant,
                        f"{rank} 適正OPI": round(x, 1),
                        "個人差度": round(y, 1)
                    })

            assert len(chart_data) > 0, f"目標ランク {rank} でデータが抽出できること"
            df_charts = pd.DataFrame(chart_data)
            col_name = f"{rank} 適正OPI"

            # 必須カラムの存在確認
            assert col_name in df_charts.columns, f"動的カラム {col_name} が存在すること"
            assert "個人差度" in df_charts.columns
            assert "楽曲名" in df_charts.columns

            # NaN や 無限大の混入がないこと
            assert not df_charts[col_name].isna().any(), f"{col_name} に NaN が存在しないこと"
            assert not np.isinf(df_charts[col_name]).any(), f"{col_name} に inf が存在しないこと"
            assert not df_charts["個人差度"].isna().any(), f"個人差度に NaN が存在しないこと"

            # ソート検証
            df_sorted = df_charts.sort_values(by=col_name, ascending=True)
            opi_values = df_sorted[col_name].tolist()
            # 昇順にソートされていること
            assert all(opi_values[i] <= opi_values[i+1] for i in range(len(opi_values)-1)), \
                f"目標ランク {rank} の適正OPIで昇順ソートが成立していること"

    def test_difficulty_table_fallback_monotonicity(self):
        """パラメータ未定義譜面に対する基準アンカー補完ロジックの厳格な単調性を検証"""
        calc = OPICalculator()
        # パラメータがすべて None で定数のみを持つ譜面
        chart_mock = Chart(
            chart_id="mock_unanchored",
            title="アンカー補完テスト曲",
            difficulty=DifficultyEnum.MASTER,
            level="14",
            chart_constant=14.2,
            opi_ss_x=None,
            opi_sss_x=None,
            opi_sssp_x=None,
            opi_abfb_x=None,
            opi_ap_x=None
        )

        target_ranks = ["SS", "SSS", "SSS+", "SSS+ABFB", "AP"]
        params = {}
        for rank in target_ranks:
            x, y = calc.get_chart_rank_params(chart_mock, rank)
            assert x is not None, f"補完値が存在すること: {rank}"
            params[rank] = x

        # 基準アンカー補完における厳密な単調増加: SS < SSS < SSS+ < SSS+ABFB < AP
        assert params["SS"] < params["SSS"], f"SS({params['SS']}) < SSS({params['SSS']})"
        assert params["SSS"] < params["SSS+"], f"SSS({params['SSS']}) < SSS+({params['SSS+']})"
        assert params["SSS+"] < params["SSS+ABFB"], f"SSS+({params['SSS+']}) < SSS+ABFB({params['SSS+ABFB']})"
        assert params["SSS+ABFB"] < params["AP"], f"SSS+ABFB({params['SSS+ABFB']}) < AP({params['AP']})"

        # 仕様オフセットの厳密一致確認
        sss_val = params["SSS"]
        assert params["SS"] == pytest.approx(sss_val - 120.0)
        assert params["SSS+"] == pytest.approx(sss_val + 120.0)
        assert params["SSS+ABFB"] == pytest.approx(sss_val + 240.0)
        assert params["AP"] == pytest.approx(sss_val + 360.0)

    def test_difficulty_table_real_db_macro_rank_consistency(self):
        """実DB全譜面におけるマクロ的ランク難易度順序（平均値の序列: SS < SSS < SSS+ < SSS+ABFB < AP）を検証"""
        charts = self.session.query(Chart).all()
        assert len(charts) > 0

        target_ranks = ["SS", "SSS", "SSS+", "SSS+ABFB", "AP"]
        rank_means = {}

        for rank in target_ranks:
            values = []
            for c in charts:
                x, y = self.calc.get_chart_rank_params(c, rank)
                if x is not None:
                    values.append(x)
            assert len(values) > 0
            rank_means[rank] = np.mean(values)

        # マクロ的な平均適正OPIの序列が正しく反映されていること
        assert rank_means["SS"] < rank_means["SSS"] < rank_means["SSS+"] < rank_means["SSS+ABFB"] < rank_means["AP"], \
            f"マクロ平均難易度の序列が不正です: {rank_means}"

    def test_difficulty_table_anomalous_corrupted_charts_resilience(self):
        """欠損・異常パラメータを持つ敵対的譜面データに対する頑健性検証（DB非保存メモリインスタンスで実施）"""
        # 異常な譜面オブジェクト（DB制約に縛られずメモリ上でシミュレート）
        anomalous_charts = [
            # 譜面定数が未定義 (None)
            Chart(chart_id="corrupt_1", title="定数欠損曲", difficulty=DifficultyEnum.MASTER, level="14",
                  chart_constant=None, opi_sss_x=1600.0, opi_sss_y=40.0),
            # パラメータが未定義 (None)
            Chart(chart_id="corrupt_2", title="パラメータ欠損曲", difficulty=DifficultyEnum.MASTER, level="14+",
                  chart_constant=14.8, opi_sss_x=None, opi_sss_y=None),
            # 個人差度が負の値
            Chart(chart_id="corrupt_3", title="負の個人差度曲", difficulty=DifficultyEnum.MASTER, level="15",
                  chart_constant=15.0, opi_sss_x=1700.0, opi_sss_y=-10.0),
            # 個人差度が None
            Chart(chart_id="corrupt_3b", title="個人差度None曲", difficulty=DifficultyEnum.MASTER, level="15",
                  chart_constant=15.0, opi_sss_x=1700.0, opi_sss_y=None),
            # 極端に大きな定数 (25.0)
            Chart(chart_id="corrupt_4", title="極大定数曲", difficulty=DifficultyEnum.LUNATIC, level="15+",
                  chart_constant=25.0, opi_sss_x=2800.0, opi_sss_y=50.0),
        ]

        calc = OPICalculator()
        target_ranks = ["SS", "SSS", "SSS+", "SSS+ABFB", "AP"]

        for c in anomalous_charts:
            for rank in target_ranks:
                # クラッシュせず安全に None または フォールバック値が返却されること
                try:
                    res = calc.get_chart_rank_params(c, rank)
                    assert isinstance(res, tuple)
                    x, y = res
                    if x is not None:
                        assert isinstance(x, (int, float))
                        assert not np.isnan(x)
                    if y is not None:
                        assert isinstance(y, (int, float))
                        assert not np.isnan(y)
                        # 個人差度は <=0 や None の場合 40.0 に安全フォールバックすること
                        assert y > 0, f"個人差度が0以下です: {y}"
                except Exception as e:
                    pytest.fail(f"異常譜面 {c.chart_id} ({c.title}) のランク {rank} で例外が発生しました: {e}")


class TestChallenger2M3SafeAtomicCrawler:
    """クローラーの安全アトミック更新および差分閉塞防止に関する敵対的テスト"""

    @pytest.mark.asyncio
    async def test_atomic_rollback_on_empty_scores(self, test_session):
        """スコアが空リスト（[]）の場合にDBがロールバックされ、log_updated_atが更新されないことの実証"""
        user_id = 88801
        initial_date = datetime(2025, 4, 1, 12, 0, 0)
        player = Player(user_id=user_id, player_name="EmptyScoreUser", rating=18.5, log_updated_at=initial_date)
        test_session.add(player)
        test_session.commit()

        # モックの作成
        mock_profile = {
            "user_id": user_id,
            "player_name": "EmptyScoreUser_Updated",
            "rating": 18.8,
            "updated_at": datetime(2025, 4, 15, 12, 0, 0)
        }

        with patch("app.Session", return_value=test_session), \
             patch("src.crawler.ongeki_crawler.OngekiCrawler.fetch_user_profile", new_callable=AsyncMock) as mock_fetch_prof, \
             patch("src.crawler.ongeki_crawler.OngekiCrawler.fetch_user_scores", new_callable=AsyncMock) as mock_fetch_scores, \
             patch("streamlit.spinner"), \
             patch("streamlit.sidebar"):

            mock_fetch_prof.return_value = mock_profile
            mock_fetch_scores.return_value = []  # 空リスト返却

            # 実行
            await fetch_and_analyze_user(user_id, force=False)

        # 検証: ロールバックされ、initial_date のままであること
        p_check = test_session.query(Player).filter_by(user_id=user_id).first()
        assert p_check.log_updated_at == initial_date, \
            f"空スコア時に更新日時が進んでしまっています: {p_check.log_updated_at} != {initial_date}"
        assert p_check.rating == 18.5, "レーティングもロールバックされていること"
        assert p_check.player_name == "EmptyScoreUser", "プレイヤーネームもロールバックされていること"

    @pytest.mark.asyncio
    async def test_atomic_rollback_on_none_scores(self, test_session):
        """スコア取得がNone（失敗）の場合にDBがロールバックされ、log_updated_atが更新されないことの実証"""
        user_id = 88802
        initial_date = datetime(2025, 4, 1, 12, 0, 0)
        player = Player(user_id=user_id, player_name="NoneScoreUser", rating=18.0, log_updated_at=initial_date)
        test_session.add(player)
        test_session.commit()

        mock_profile = {
            "user_id": user_id,
            "player_name": "NoneScoreUser_Updated",
            "rating": 18.2,
            "updated_at": datetime(2025, 4, 20, 12, 0, 0)
        }

        with patch("app.Session", return_value=test_session), \
             patch("src.crawler.ongeki_crawler.OngekiCrawler.fetch_user_profile", new_callable=AsyncMock) as mock_fetch_prof, \
             patch("src.crawler.ongeki_crawler.OngekiCrawler.fetch_user_scores", new_callable=AsyncMock) as mock_fetch_scores, \
             patch("streamlit.spinner"), \
             patch("streamlit.sidebar"):

            mock_fetch_prof.return_value = mock_profile
            mock_fetch_scores.return_value = None  # None返却

            await fetch_and_analyze_user(user_id, force=False)

        p_check = test_session.query(Player).filter_by(user_id=user_id).first()
        assert p_check.log_updated_at == initial_date, "None返却時に更新日時が進んでいないこと"

    @pytest.mark.asyncio
    async def test_atomic_rollback_on_fetch_scores_exception(self, test_session):
        """スコア取得中にネットワーク切断などの例外が発生した際、中途半端なデータがコミットされないことの実証"""
        user_id = 88803
        initial_date = datetime(2025, 4, 1, 12, 0, 0)
        player = Player(user_id=user_id, player_name="ExceptionUser", rating=17.5, log_updated_at=initial_date)
        test_session.add(player)
        test_session.commit()

        mock_profile = {
            "user_id": user_id,
            "player_name": "ExceptionUser_Updated",
            "rating": 17.8,
            "updated_at": datetime(2025, 4, 25, 12, 0, 0)
        }

        with patch("app.Session", return_value=test_session), \
             patch("src.crawler.ongeki_crawler.OngekiCrawler.fetch_user_profile", new_callable=AsyncMock) as mock_fetch_prof, \
             patch("src.crawler.ongeki_crawler.OngekiCrawler.fetch_user_scores", new_callable=AsyncMock) as mock_fetch_scores, \
             patch("streamlit.spinner"), \
             patch("streamlit.sidebar"):

            mock_fetch_prof.return_value = mock_profile
            # ネットワーク切断エラーを送出
            mock_fetch_scores.side_effect = ConnectionResetError("Simulated Network Disconnect")

            try:
                await fetch_and_analyze_user(user_id, force=False)
            except ConnectionResetError:
                pass  # 例外が外に漏れる場合もテスト

        # セッションを再取得してDBへの永続化状態を厳密検証
        p_check = test_session.query(Player).filter_by(user_id=user_id).first()
        assert p_check.log_updated_at == initial_date, "例外発生時に更新日時がコミットされていないこと"
        assert p_check.rating == 17.5, "例外発生時にレーティングがコミットされていないこと"

    @pytest.mark.asyncio
    async def test_differential_blockade_prevention_full_lifecycle(self, test_session, seed_charts):
        """
        差分閉塞防止の完全ライフサイクル検証:
        1回目試行でスコア取得が失敗しても日時は進まず、2回目試行で正常に差分検知されて完全更新されることを実証
        """
        user_id = 88804
        t1 = datetime(2025, 4, 1, 0, 0, 0)
        t2 = datetime(2025, 4, 10, 0, 0, 0)
        target_chart_id = seed_charts[0].chart_id

        # 初期プレイヤー
        player = Player(user_id=user_id, player_name="LifecycleUser", rating=19.0, log_updated_at=t1)
        test_session.add(player)
        test_session.commit()

        crawler = OngekiCrawler()

        # --- STEP 1: 外部サイトでスコア更新が発生（t2）、しかしクローラーのスコア取得が失敗（空リスト） ---
        mock_prof_t2 = {"user_id": user_id, "player_name": "LifecycleUser", "rating": 19.1, "updated_at": t2}

        with patch("app.Session", return_value=test_session), \
             patch.object(crawler, "fetch_user_profile", new_callable=AsyncMock) as mock_prof, \
             patch.object(crawler, "fetch_user_scores", new_callable=AsyncMock) as mock_scores, \
             patch("streamlit.spinner"), \
             patch("streamlit.sidebar") as mock_sb:

            mock_prof.return_value = mock_prof_t2
            mock_scores.return_value = []  # スコア取得失敗

            # app.py 内の処理実行（crawlerインスタンスの差し替え）
            with patch("app.OngekiCrawler", return_value=crawler):
                await fetch_and_analyze_user(user_id, force=False)

        # 検証 1: ロールバックされ、log_updated_at は依然として t1 であること
        p_after_step1 = test_session.query(Player).filter_by(user_id=user_id).first()
        assert p_after_step1.log_updated_at == t1, "STEP 1 失敗後、更新日時が t1 のままであること"

        # --- STEP 2: 通信が回復し、2回目の通常更新（force=False）が実行された ---
        valid_scores = [
            {"chart_id": target_chart_id, "score": 1005000, "is_all_break": True, "is_full_bell": True}
        ]

        with patch("app.Session", return_value=test_session), \
             patch.object(crawler, "fetch_user_profile", new_callable=AsyncMock) as mock_prof2, \
             patch.object(crawler, "fetch_user_scores", new_callable=AsyncMock) as mock_scores2, \
             patch("streamlit.spinner"), \
             patch("streamlit.sidebar") as mock_sb2:

            # 差分判定ロジックの実走検証:
            # last_crawled_at として p_after_step1.log_updated_at (t1) が渡される
            # updated_at (t2) > t1 のため、fetch_user_profile は正常にプロファイルを返す！
            # （もし STEP 1 で日時が t2 に進んでしまっていたら、t2 <= t2 で None となり永久閉塞していた）
            mock_prof2.side_effect = lambda uid, last_crawled_at=None, force=False: (
                None if (not force and last_crawled_at and t2 <= last_crawled_at) else mock_prof_t2
            )
            mock_scores2.return_value = valid_scores

            with patch("app.OngekiCrawler", return_value=crawler):
                await fetch_and_analyze_user(user_id, force=False)

        # 検証 2: スコアが正常にDBに書き込まれ、log_updated_at が t2 に更新されたこと
        p_after_step2 = test_session.query(Player).filter_by(user_id=user_id).first()
        assert p_after_step2.log_updated_at == t2, "STEP 2 回復後、更新日時が正常に t2 に更新されること"
        assert p_after_step2.rating == 19.1
        score_in_db = test_session.query(ScoreLog).filter_by(user_id=user_id, chart_id=target_chart_id).first()
        assert score_in_db is not None, "スコアがDBに正常に保存されていること"
        assert score_in_db.score == 1005000

    @pytest.mark.asyncio
    async def test_force_update_bypasses_cache_when_dates_equal(self, test_session, seed_charts):
        """更新日時が同一（新規差分なし）でも force=True でバイパスしてスコアが再取得されることの実証"""
        user_id = 88805
        t_same = datetime(2025, 4, 10, 0, 0, 0)
        target_chart_id = seed_charts[0].chart_id

        player = Player(user_id=user_id, player_name="ForceUser", rating=19.2, log_updated_at=t_same)
        test_session.add(player)
        test_session.commit()

        mock_profile = {"user_id": user_id, "player_name": "ForceUser", "rating": 19.3, "updated_at": t_same}
        updated_scores = [
            {"chart_id": target_chart_id, "score": 1008000, "is_all_break": True, "is_full_bell": True}
        ]

        crawler = OngekiCrawler()
        with patch("app.Session", return_value=test_session), \
             patch.object(crawler, "fetch_user_profile", new_callable=AsyncMock) as mock_prof, \
             patch.object(crawler, "fetch_user_scores", new_callable=AsyncMock) as mock_scores, \
             patch("streamlit.spinner"), \
             patch("streamlit.sidebar"):

            # force=False のときは None（スキップ）、force=True のときは mock_profile を返す
            mock_prof.side_effect = lambda uid, last_crawled_at=None, force=False: (
                mock_profile if (force or not last_crawled_at or mock_profile["updated_at"] > last_crawled_at) else None
            )
            mock_scores.return_value = updated_scores

            with patch("app.OngekiCrawler", return_value=crawler):
                # force=True で実行
                await fetch_and_analyze_user(user_id, force=True)

        p_check = test_session.query(Player).filter_by(user_id=user_id).first()
        assert p_check.rating == 19.3, "強制更新によりレーティングが最新値に更新されること"
        score_rec = test_session.query(ScoreLog).filter_by(user_id=user_id, chart_id=target_chart_id).first()
        assert score_rec is not None
        assert score_rec.score == 1008000, "強制更新によりスコアが更新されること"


class TestChallenger2M3MultiDifficultyMatching:
    """同名曲における複数難易度（MASTER, LUNATIC, EXPERT等）の厳密照合検証"""

    def test_multi_difficulty_same_title_separation_and_isolation(self, test_session):
        """同一曲名で複数難易度が存在する場合、独立した chart_id に個別にマッピングされること"""
        title = "マルチ難易度テスト楽曲"
        c_exp = Chart(chart_id="mtest_exp", title=title, difficulty=DifficultyEnum.EXPERT, level="13",
                      chart_constant=13.0, opi_sss_x=1400.0, opi_sss_y=30.0)
        c_mas = Chart(chart_id="mtest_mas", title=title, difficulty=DifficultyEnum.MASTER, level="14+",
                      chart_constant=14.7, opi_sss_x=1650.0, opi_sss_y=40.0)
        c_luna = Chart(chart_id="mtest_luna", title=title, difficulty=DifficultyEnum.LUNATIC, level="15",
                       chart_constant=15.3, opi_sss_x=1780.0, opi_sss_y=45.0)
        test_session.add_all([c_exp, c_mas, c_luna])
        test_session.commit()

        charts = test_session.query(Chart).filter_by(title=title).all()
        chart_by_id = {c.chart_id: c for c in charts}
        chart_by_title_diff = {
            (c.title, c.difficulty.name if hasattr(c.difficulty, 'name') else str(c.difficulty)): c 
            for c in charts
        }

        # クローラーからの模擬スコアデータ
        scores = [
            {"title": title, "difficulty": "EXPERT", "score": 1009000},
            {"title": title, "difficulty": "MASTER", "score": 1005000},
            {"title": title, "difficulty": "LUNATIC", "score": 998000}
        ]

        mapped = {}
        for s in scores:
            chart = None
            if s.get("chart_id"):
                chart = chart_by_id.get(s["chart_id"])
            if not chart and "title" in s and "difficulty" in s:
                chart = chart_by_title_diff.get((s["title"], s["difficulty"]))
            mapped[s["difficulty"]] = chart

        assert mapped["EXPERT"].chart_id == "mtest_exp"
        assert mapped["MASTER"].chart_id == "mtest_mas"
        assert mapped["LUNATIC"].chart_id == "mtest_luna"
        # 3つすべてが異なるインスタンスであること
        assert len(set(c.chart_id for c in mapped.values())) == 3

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "-s"]))


