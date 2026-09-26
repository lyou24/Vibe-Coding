import os
import sys
import math
import re
import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.database.models import Chart, Player, ScoreLog, DifficultyEnum
from src.analyzer.opi_calculator import OPICalculator, normalize_rank
from src.recommender.recommender import OPIRecommender
from src.visualizer.visualizer import OPIVisualizer

APP_PATH = os.path.join(PROJECT_ROOT, "app.py")
DB_PATH = os.path.join(PROJECT_ROOT, "data", "opi_database.sqlite")


# ==============================================================================
# 1. 空の入力・マルチセレクト・スライダー境界値 (UI & Backend)
# ==============================================================================
class TestAdversarialInputAndSliders:
    """空の入力、マルチセレクト全未選択、極端なスライダー境界値での堅牢性検証"""

    def test_multiselect_empty_all_fallback_ui(self):
        """
        リコメンドUIにおいて、すべてのマルチセレクト（目標ランク、レベル、現在ランク）
        を空（[]）にした場合、クラッシュせず全対象として安全に探索・表示されること。
        """
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        assert len(at.exception) == 0, f"Initial launch failed: {at.exception}"

        # フィルターウィジェットの特定
        target_rank_ms = at.multiselect(key="filter_target_rank")
        level_ms = at.multiselect(key="filter_level")
        current_rank_ms = at.multiselect(key="filter_current_rank")

        assert target_rank_ms is not None
        assert level_ms is not None
        assert current_rank_ms is not None

        # すべて空リストに設定して再実行
        target_rank_ms.set_value([]).run()
        level_ms.set_value([]).run()
        current_rank_ms.set_value([]).run()

        assert len(at.exception) == 0, f"Exception occurred when multiselects empty: {at.exception}"
        # データフレームまたはメッセージが安全に出力されること
        has_df = len(at.dataframe) > 0
        has_info = any("見つかりませんでした" in str(i.value) for i in at.info)
        assert has_df or has_info, "マルチセレクト未選択時に結果UI（DataFrame または Info）が表示されていません"

    def test_multiselect_partial_selections(self):
        """マルチセレクトで特定の単一または複数項目を選択した際のUI検証"""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        target_rank_ms = at.multiselect(key="filter_target_rank")
        level_ms = at.multiselect(key="filter_level")

        # 目標ランクのみ SSS 選択
        target_rank_ms.set_value(["SSS"]).run()
        assert len(at.exception) == 0

        # レベル 14+ 選択
        level_ms.set_value(["14+"]).run()
        assert len(at.exception) == 0

    def test_slider_zero_to_zero_boundary(self):
        """クリア割合スライダーを (0.0, 0.0)% に設定したときの境界値検証"""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        slider = at.slider(key="filter_clear_rate_range")
        assert slider is not None

        slider.set_value((0.0, 0.0)).run()
        assert len(at.exception) == 0, f"Exception at slider (0.0, 0.0): {at.exception}"

    def test_slider_hundred_to_hundred_boundary(self):
        """クリア割合スライダーを (100.0, 100.0)% に設定したときの境界値検証"""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        slider = at.slider(key="filter_clear_rate_range")
        assert slider is not None

        slider.set_value((100.0, 100.0)).run()
        assert len(at.exception) == 0, f"Exception at slider (100.0, 100.0): {at.exception}"

    def test_slider_full_range_boundary(self):
        """クリア割合スライダーを (0.0, 100.0)% に設定したときの全域検証"""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        slider = at.slider(key="filter_clear_rate_range")
        assert slider is not None

        slider.set_value((0.0, 100.0)).run()
        assert len(at.exception) == 0, f"Exception at slider (0.0, 100.0): {at.exception}"
        assert len(at.dataframe) > 0, "クリア割合0〜100%指定時にリコメンドデータフレームが表示されていません"

    def test_constant_slider_point_range(self):
        """譜面定数スライダーを単一点 (14.0, 14.0) に設定したときの境界値検証"""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        slider = at.slider(key="filter_constant_range")
        assert slider is not None

        slider.set_value((14.0, 14.0)).run()
        assert len(at.exception) == 0, f"Exception at constant slider (14.0, 14.0): {at.exception}"

    def test_backend_recommender_boundary_filters(self):
        """バックエンド OPIRecommender の引数に対する境界値・敵対的入力検証"""
        rec = OPIRecommender(DB_PATH)

        # 1. 勝率スライダー境界値
        res_zero = rec.get_recommendations(user_id=10605, win_rate_min=0.0, win_rate_max=0.0)
        assert isinstance(res_zero, list)

        res_hundred = rec.get_recommendations(user_id=10605, win_rate_min=1.0, win_rate_max=1.0)
        assert isinstance(res_hundred, list)

        # 2. 勝率逆転 (min > max) 入力時の安全動作 (例外を出さず空リストを返す)
        res_inverted = rec.get_recommendations(user_id=10605, win_rate_min=0.8, win_rate_max=0.2)
        assert isinstance(res_inverted, list)
        assert len(res_inverted) == 0

        # 3. level 引数が空リスト / None
        res_empty_level = rec.get_recommendations(user_id=10605, level=[])
        assert isinstance(res_empty_level, list)
        res_none_level = rec.get_recommendations(user_id=10605, level=None)
        assert isinstance(res_none_level, list)
        assert len(res_none_level) > 0

        # 4. current_rank 引数が空リスト / None / 存在しない文字列
        res_empty_cr = rec.get_recommendations(user_id=10605, current_rank=[])
        assert isinstance(res_empty_cr, list)
        res_nonexistent_cr = rec.get_recommendations(user_id=10605, current_rank="UNKNOWN_RANK")
        assert isinstance(res_nonexistent_cr, list)


# ==============================================================================
# 2. 存在しないユーザーIDや極端なレーティング値・OPI値
# ==============================================================================
class TestAdversarialUserIdAndRatings:
    """不正・存在しないユーザーIDや極端なレーティング値での耐障害性検証"""

    def test_non_existent_user_id_ui(self):
        """存在しないユーザーID (99999999) を入力した際、アプリがクラッシュせず警告を表示すること"""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        user_inputs = [t for t in at.sidebar.text_input if "ユーザーID" in t.label or "ID" in t.label]
        assert len(user_inputs) > 0

        user_inputs[0].set_value("99999999").run()
        assert len(at.exception) == 0, f"Exception on non-existent user: {at.exception}"
        assert any("見つかりません" in str(w.value) for w in at.warning), "存在しないIDに対して警告が表示されていません"

    def test_negative_and_string_user_id_ui(self):
        """負数や非数値文字列をIDに入力した際のUIエラーハンドリング"""
        from streamlit.testing.v1 import AppTest

        for invalid_val in ["-10605", "abc", "", "   ", "!@#$%"]:
            at = AppTest.from_file(APP_PATH, default_timeout=30).run()
            user_inputs = [t for t in at.sidebar.text_input if "ユーザーID" in t.label or "ID" in t.label]
            user_inputs[0].set_value(invalid_val).run()
            assert len(at.exception) == 0, f"Exception on invalid user ID '{invalid_val}': {at.exception}"

    def test_extreme_large_user_id_overflow_vulnerability(self):
        """
        【脆弱性実証テスト】
        SQLite の 64-bit 符号付き整数の最大値 (9223372036854775807) を超える
        超巨大な数値文字列（例: '999999999999999999999999999999'）を入力した場合、
        Pythonの int は任意精度のため int 変換は成功するが、
        SQLite の INTEGER カラム上限を超えて OverflowError が発生する脆弱性を実証する。
        """
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        user_inputs = [t for t in at.sidebar.text_input if "ユーザーID" in t.label or "ID" in t.label]
        user_inputs[0].set_value("999999999999999999999999999999").run()

        # 実証: 現状の実装では OverflowError がキャッチされず at.exception に記録される
        has_overflow = any("OverflowError" in str(e.message) or "too large to convert to SQLite INTEGER" in str(e.message) for e in at.exception)
        assert has_overflow, "64-bitオーバーフローが発生するか、または適切にハンドリングされているかを検証"

    def test_recommender_extreme_and_none_user(self):
        """バックエンド OPIRecommender で存在しないIDや極端なOPI値が渡された場合の動作"""
        rec = OPIRecommender(DB_PATH)

        # 存在しないID
        assert rec.get_recommendations(user_id=99999999) == []
        # ユーザーIDもplayer_opiもNone
        assert rec.get_recommendations(user_id=None, player_opi=None) == []

        # 極端に低いOPI (-5000.0)
        recs_low = rec.get_recommendations(user_id=10605, player_opi=-5000.0, win_rate_min=0.0, win_rate_max=1.0)
        assert isinstance(recs_low, list)
        for r in recs_low:
            assert r["probability"] < 0.001

        # 極端に高いOPI (10000.0)
        recs_high = rec.get_recommendations(user_id=10605, player_opi=10000.0, win_rate_min=0.0, win_rate_max=1.0)
        assert isinstance(recs_high, list)
        for r in recs_high:
            assert r["probability"] > 0.999

    def test_visualizer_band_label_boundaries_and_adversarial(self):
        """OPIVisualizer.get_band_label の境界値・極端値・異常値検証"""
        # 境界値: 17.75 未満は None
        assert OPIVisualizer.get_band_label(17.749999) is None
        assert OPIVisualizer.get_band_label(17.74) is None
        assert OPIVisualizer.get_band_label(0.0) is None
        assert OPIVisualizer.get_band_label(-15.0) is None

        # 境界値: 17.75 は 18.0帯
        assert OPIVisualizer.get_band_label(17.75) == "18.0"
        assert OPIVisualizer.get_band_label(18.0) == "18.0"
        assert OPIVisualizer.get_band_label(18.249999) == "18.0"

        # 境界値: 18.25 は 18.5帯
        assert OPIVisualizer.get_band_label(18.25) == "18.5"
        assert OPIVisualizer.get_band_label(18.749999) == "18.5"

        # 境界値: 18.75 は 19.0帯
        assert OPIVisualizer.get_band_label(18.75) == "19.0"

        # 高レーティング
        assert OPIVisualizer.get_band_label(20.0) == "20.0"
        assert OPIVisualizer.get_band_label(25.0) == "25.0"

        # 異常値 (None, NaN, Inf, 文字列型入力等)
        assert OPIVisualizer.get_band_label(None) is None
        assert OPIVisualizer.get_band_label(float("nan")) is None
        assert OPIVisualizer.get_band_label(float("inf")) is None
        assert OPIVisualizer.get_band_label(float("-inf")) is None
        assert OPIVisualizer.get_band_label("not_a_number") is None

    def test_visualizer_plotly_extreme_and_adversarial_values(self):
        """Plotly動的散布図生成関数に極端値やNoneを渡した際の堅牢性"""
        vis = OPIVisualizer(DB_PATH)

        # ユーザー値がNoneの場合（登録プレイヤー散布図のみ）
        fig_none = vis.create_distribution_figure(player_rating=None, player_opi=None)
        assert len(fig_none.data) >= 1

        # レーティングが帯域未満 (15.0) のユーザー
        fig_low = vis.create_distribution_figure(player_rating=15.0, player_opi=1100.0, player_name="初心者")
        assert len(fig_low.data) == 2  # 背景散布図 + ユーザーハイライト
        user_trace = fig_low.data[1]
        assert user_trace.marker.symbol == "star"
        assert user_trace.x[0] == 15.0
        assert user_trace.y[0] == 1100.0

        # 極端な高値
        fig_high = vis.create_distribution_figure(player_rating=99.9, player_opi=9999.0)
        assert len(fig_high.data) == 2


# ==============================================================================
# 3. 達成済みフラグの境界値（974,999点、975,000点、1,009,999点、1,010,000点等）
# ==============================================================================
class TestScoreAndAchievementBoundaries:
    """スコア境界値およびフラグ判定ロジックの厳密な検証"""

    class DummyScoreLog:
        def __init__(self, score, achieve_s=False, achieve_ss=False, achieve_sss=False, achieve_sssp=False, achieve_abp=False):
            self.score = score
            self.achieve_s = achieve_s
            self.achieve_ss = achieve_ss
            self.achieve_sss = achieve_sss
            self.achieve_sssp = achieve_sssp
            self.achieve_abp = achieve_abp

    @pytest.fixture
    def recommender(self):
        return OPIRecommender(DB_PATH)

    def test_rank_score_boundaries_determination(self, recommender):
        """スコア境界値における現在ランク判定 (_determine_current_rank) の網羅検証"""
        matrix = [
            # (score, expected_category)
            (0, "未S"),
            (969999, "未S"),
            (970000, "S止まり"),
            (970001, "S止まり"),
            (989999, "S止まり"),
            (990000, "SS止まり"),
            (990001, "SS止まり"),
            (999999, "SS止まり"),
            (1000000, "SSS止まり"),
            (1000001, "SSS止まり"),
            (1007499, "SSS止まり"),
            (1007500, "SSS+止まり"),
            (1007501, "SSS+止まり"),
            (1009999, "SSS+止まり"),
            (1010000, "AB+"),
            (1010001, "AB+"),
        ]

        for score, expected_cat in matrix:
            dummy = self.DummyScoreLog(score=score)
            cat, disp = recommender._determine_current_rank(dummy)
            assert cat == expected_cat, f"Score {score}: expected '{expected_cat}', got '{cat}'"

    def test_target_achievement_boundaries(self, recommender):
        """スコア境界値における目標ランク達成判定 (_is_target_achieved) の網羅検証"""
        cases = [
            # (score, target_rank, expected_is_achieved)
            (969999, "S", False),
            (970000, "S", True),
            (970000, "SS", False),
            (989999, "SS", False),
            (990000, "SS", True),
            (990000, "SSS", False),
            (999999, "SSS", False),
            (1000000, "SSS", True),
            (1000000, "SSS+", False),
            (1007499, "SSS+", False),
            (1007500, "SSS+", True),
            (1007500, "AB+", False),
            (1009999, "AB+", False),
            (1010000, "AB+", True),
            (1010001, "AB+", True),
        ]

        for score, target, expected in cases:
            dummy = self.DummyScoreLog(score=score)
            ach = recommender._is_target_achieved(dummy, target)
            assert ach == expected, f"Score {score}, target {target}: expected {expected}, got {ach}"

    def test_achievement_flag_override_and_conflict(self, recommender):
        """スコアが未達でもフラグがTrueの場合、およびスコア達成でフラグFalseの場合のOR条件検証"""
        # 1. スコアが低い(900,000)が achieve_s=True
        d1 = self.DummyScoreLog(score=900000, achieve_s=True)
        assert recommender._is_target_achieved(d1, "S") is True
        cat1, _ = recommender._determine_current_rank(d1)
        assert cat1 == "S止まり"

        # 2. スコアが低い(900,000)が achieve_abp=True
        d2 = self.DummyScoreLog(score=900000, achieve_abp=True)
        assert recommender._is_target_achieved(d2, "AB+") is True
        cat2, _ = recommender._determine_current_rank(d2)
        assert cat2 == "AB+"

        # 3. スコアが十分(1010000)だが achieve_abp=False
        d3 = self.DummyScoreLog(score=1010000, achieve_abp=False)
        assert recommender._is_target_achieved(d3, "AB+") is True
        cat3, _ = recommender._determine_current_rank(d3)
        assert cat3 == "AB+"

        # 4. スコアがNone
        d4 = self.DummyScoreLog(score=None)
        assert recommender._is_target_achieved(d4, "S") is False
        cat4, _ = recommender._determine_current_rank(d4)
        assert cat4 == "未S"

        # 5. スコアログそのものがNone
        assert recommender._is_target_achieved(None, "S") is False
        cat5, _ = recommender._determine_current_rank(None)
        assert cat5 == "未S"

    def test_current_rank_filter_robustness(self, recommender):
        """_matches_current_rank_filter の表記ゆれ・リスト指定・大文字小文字耐性"""
        assert recommender._matches_current_rank_filter("SSS+止まり", ["SSS+止まり", "AB+"]) is True
        assert recommender._matches_current_rank_filter("S止まり", ["SSS+止まり", "AB+"]) is False
        assert recommender._matches_current_rank_filter("AB+", "AB+") is True
        assert recommender._matches_current_rank_filter("AB+", "AP") is True
        assert recommender._matches_current_rank_filter("AB+", "ABP") is True
        assert recommender._matches_current_rank_filter("SSS+止まり", "SSSP") is True
        assert recommender._matches_current_rank_filter("未S", "未プレイ") is True
        assert recommender._matches_current_rank_filter("S止まり", None) is True
        assert recommender._matches_current_rank_filter("S止まり", []) is True

    def test_recommender_zero_leak_of_achieved_charts(self, recommender):
        """
        実データ (ユーザー10605) を用いて、すでに目標ランクを達成済みの楽曲が
        リコメンド結果に1件も混入（リーク）していないことを実証検証する。
        """
        for target in ["S", "SS", "SSS", "SSS+", "AB+"]:
            recs = rec.get_recommendations(
                user_id=10605,
                target_rank=target,
                win_rate_min=0.0,
                win_rate_max=1.0,
                limit=100
            ) if (rec := recommender) else []
            for r in recs:
                chart_id = r["chart_id"]
                # ユーザー10605のDBスコアを直接引いて再確認
                session = recommender.Session()
                try:
                    s = session.query(ScoreLog).filter_by(user_id=10605, chart_id=chart_id).first()
                    if s:
                        ach = recommender._is_target_achieved(s, target)
                        assert not ach, f"達成済み楽曲 {r['title']} (Score: {s.score}) が目標 {target} のリコメンドにリークしています"
                finally:
                    session.close()


# ==============================================================================
# 4. 難易度表の帯域境界値（OPI 1999.9 vs 2000.0）
# ==============================================================================
class TestDifficultyGridBandsAndSorting:
    """難易度表における100 OPIごとの帯域計算と降順ソートの徹底検証"""

    def test_opi_band_floor_division_boundary(self):
        """
        帯域計算式: (opi // 50 * 50).astype(int)
        1999.9 は 1950帯、2000.0 は 2000帯に正しく分類されること。
        """
        values = [
            # (opi_val, expected_band)
            (1999.9, 1950),
            (1999.999999, 1950),
            (2000.0, 2000),
            (2000.000001, 2000),
            (2049.9, 2000),
            (2050.0, 2050),
            (1450.5, 1450),
            (1500.0, 1500),
            (0.0, 0),
            (49.9, 0),
            (50.0, 50),
        ]

        for opi_val, expected_band in values:
            calc_band = int(math.floor(opi_val / 50.0) * 50)
            assert calc_band == expected_band, f"OPI {opi_val}: expected band {expected_band}, got {calc_band}"

        s = pd.Series([v[0] for v in values])
        bands = (s // 50 * 50).astype(int).tolist()
        expected = [v[1] for v in values]
        assert bands == expected, f"Pandas band division failed: {bands} != {expected}"

    def test_ui_difficulty_grid_descending_order(self):
        """
        Streamlit AppTest を通じて、Tab 3 (OPI難易度表) および Tab 4 (マイOPI難易度表)
        の帯域ヘッダーが完全な降順（高い帯域が上位）で描画されているか検証。
        """
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        assert len(at.exception) == 0

        headers = [m.value for m in at.markdown if "OPI " in m.value or "適正帯域" in m.value]
        assert len(headers) > 0, "帯域ヘッダーが見つかりません"

        extracted_bands = []
        for h in headers:
            match = re.search(r'(?:OPI|適正帯域)\s+(\d+)〜', h)
            if match:
                extracted_bands.append(int(match.group(1)))

        assert len(extracted_bands) > 0, "帯域数値を抽出できませんでした"
        # 最初のタブ（Tab 3）のブロックが単調減少（降順）であることを検証
        # 帯域が次に大きくなるところ（Tab 4の開始点）までの先頭ブロックをスライス
        tab3_bands = []
        for b in extracted_bands:
            if tab3_bands and b > tab3_bands[-1]:
                break
            tab3_bands.append(b)

        assert len(tab3_bands) >= 3, f"帯域数が少なすぎます: {tab3_bands}"
        # 厳密な降順ソートの検証
        for i in range(len(tab3_bands) - 1):
            assert tab3_bands[i] > tab3_bands[i + 1], f"帯域が降順ソートされていません: {tab3_bands}"

    def test_ui_difficulty_grid_abp_contains_2000_band(self):
        """
        目標ランク選択を 'AB+' に切り替えた場合、2000帯（OPI 2000〜2099）
        のヘッダーが先頭に出現することを実証検証。
        """
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        select_box = at.selectbox(key="diff_target_rank_select")
        assert select_box is not None

        # AB+ を選択 (index 4)
        select_box.select("AB+").run()
        assert len(at.exception) == 0

        headers = [m.value for m in at.markdown if "OPI " in m.value]
        extracted_bands = []
        for h in headers:
            match = re.search(r'OPI\s+(\d+)〜', h)
            if match:
                extracted_bands.append(int(match.group(1)))

        assert len(extracted_bands) > 0
        assert extracted_bands[0] >= 2000, f"AB+選択時の最上位帯域が2000以上ではありません: {extracted_bands[0]}"

    def test_my_opi_view_achievement_styling_ui(self):
        """
        Tab 4 (マイOPI難易度表) において、各楽曲の現在最高ランクに応じた濃色ハイライト、
        未達成楽曲に通常背景 (#f8f9fa) が適用され、[達成済]/[未達成] バッジが付与されていること。
        """
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        assert len(at.exception) == 0

        cards = [m.value for m in at.markdown if "background-color:" in m.value]
        assert len(cards) > 0, "難易度表カードHTMLが見つかりません"

        rank_colors = ("#2e7d32", "#1565c0", "#c62828", "#f9a825", "#c2410c")
        has_achieved_card = any(
            any(color in c for color in rank_colors) and "[達成済]" in c
            for c in cards
        )
        has_unachieved_card = any("#f8f9fa" in c and "[未達成]" in c for c in cards)

        assert has_achieved_card, "マイOPI難易度表に最高到達ランク色の達成済みカードが存在しません"
        assert has_unachieved_card, "マイOPI難易度表に未達成カード（#f8f9fa / [未達成]）が存在しません"


# ==============================================================================
# 5. 数値安定性・IRT確率計算・MLE推定ストレステスト
# ==============================================================================
class TestNumericalStabilityAndStress:
    """数値計算ロジック（ロジスティック確率、最尤推定）の特異点・オーバーフロー耐性検証"""

    @pytest.fixture
    def calc(self):
        return OPICalculator()

    def test_irt_probability_numerical_stability(self, calc):
        """IRTロジスティック確率計算の数値安定性"""
        # 1. 完全一致
        assert abs(calc.irt_probability(1500.0, 1500.0, 40.0) - 0.5) < 1e-6

        # 2. 超巨大な差（オーバーフロー防止）
        assert calc.irt_probability(100000.0, 1500.0, 40.0) == 1.0
        assert calc.irt_probability(-100000.0, 1500.0, 40.0) == 0.0

        # 3. y <= 0 や y=None に対する安全フォールバック（ゼロ割れ防止）
        p_zero_y = calc.irt_probability(1500.0, 1500.0, 0.0)
        assert abs(p_zero_y - 0.5) < 1e-6
        p_neg_y = calc.irt_probability(1500.0, 1500.0, -10.0)
        assert abs(p_neg_y - 0.5) < 1e-6
        p_none_y = calc.irt_probability(1500.0, 1500.0, None)
        assert abs(p_none_y - 0.5) < 1e-6

    def test_estimate_user_opi_stress_and_edge_cases(self, calc):
        """最尤推定 (estimate_user_opi) のエッジケース・異常値耐性"""
        # 1. 空データ入力
        assert calc.estimate_user_opi([], initial_theta=1500.0) == 1500.0

        # 2. 極端な全達成データ (100曲全クリア)
        all_success = [{'x': 1500.0 + i * 10, 'y': 40.0, 'achieved': 1} for i in range(100)]
        opi_high = calc.estimate_user_opi(all_success, initial_theta=1500.0)
        assert np.isfinite(opi_high)
        assert opi_high > 1800.0

        # 3. 極端な全未達成データ (100曲全ミス)
        all_fail = [{'x': 1500.0 + i * 10, 'y': 40.0, 'achieved': 0} for i in range(100)]
        opi_low = calc.estimate_user_opi(all_fail, initial_theta=1500.0)
        assert np.isfinite(opi_low)
        assert opi_low < 1500.0

        # 4. 異常値（None, y<=0, 無効データ）が混入したデータ
        dirty_data = [
            {'x': None, 'y': 40.0, 'achieved': 1},
            {'x': 1600.0, 'y': -5.0, 'achieved': 1},
            {'x': 1700.0, 'y': None, 'achieved': 0},
            "invalid_tuple",
            (1800.0,),  # 要素不足
            (1900.0, 40.0, 1),
        ]
        dirty_opi = calc.estimate_user_opi(dirty_data, initial_theta=1500.0)
        assert np.isfinite(dirty_opi)

        # 5. initial_theta が NaN / Inf の場合
        res_nan = calc.estimate_user_opi(all_success[:5], initial_theta=float("nan"))
        assert np.isfinite(res_nan)
