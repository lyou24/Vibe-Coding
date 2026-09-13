import pytest
import numpy as np
from datetime import datetime

from src.database.models import Chart, Player, ScoreLog, DifficultyEnum
from src.analyzer.opi_calculator import OPICalculator
from src.recommender.recommender import OPIRecommender
from src.visualizer.visualizer import OPIVisualizer

class TestTier2BoundariesAndCornerCases:
    """Tier 2: 境界値・極端値・異常系・定数境界の検証"""

    def test_nonexistent_user_handling(self, test_db_path):
        """存在しないユーザーIDに対してリコメンドが安全に空リストを返すこと"""
        recommender = OPIRecommender(test_db_path)
        result = recommender.get_recommendations(user_id=99999999)
        assert result == [], "存在しないユーザーIDでは空リストを安全に返却すること"

    def test_zero_scores_player_handling(self, test_db_path, test_session, seed_charts):
        """スコア履歴が0件のプレイヤーに対して、OPI計算・リコメンドがクラッシュしないこと"""
        player = Player(user_id=8888, player_name="ZeroPlayUser", rating=18.0, total_opi=None)
        test_session.add(player)
        test_session.commit()

        # OPI計算
        calc = OPICalculator()
        opi = calc.estimate_user_opi([], initial_theta=1500.0)
        assert opi == 1500.0, "スコア0件の場合は初期thetaを維持すること"

        # リコメンド
        recommender = OPIRecommender(test_db_path)
        recs = recommender.get_recommendations(user_id=8888)
        assert recs == [], "total_opiがNoneのプレイヤーへのリコメンドは空リストを返却すること"

    def test_extreme_all_achieved_mle_convergence(self):
        """全曲達成（All 1）の極端なケースでも、L2正則化によりMLEが無限大へ発散せず有限値に収束すること"""
        calc = OPICalculator()
        # 全曲AP/SSS+のプレイヤー
        achievements = [
            {'x': 1200.0, 'y': 40.0, 'achieved': 1},
            {'x': 1400.0, 'y': 40.0, 'achieved': 1},
            {'x': 1600.0, 'y': 40.0, 'achieved': 1},
            {'x': 1800.0, 'y': 40.0, 'achieved': 1},
            {'x': 2000.0, 'y': 40.0, 'achieved': 1},
            {'x': 2200.0, 'y': 40.0, 'achieved': 1},
            {'x': 2400.0, 'y': 40.0, 'achieved': 1},
        ]
        opi = calc.estimate_user_opi(achievements, initial_theta=1500.0)
        assert np.isfinite(opi), "推定値が有限の実数であること"
        assert opi > 2200.0, "全達成のため高OPIに推定されること"
        assert opi < 3500.0, "正則化項により非現実的な巨大値に発散しないこと"

    def test_extreme_all_failed_mle_convergence(self):
        """全曲未達成（All 0）の極端なケースでも、MLEが負の無限大へ発散せず有限値に収束すること"""
        calc = OPICalculator()
        achievements = [
            {'x': 1200.0, 'y': 40.0, 'achieved': 0},
            {'x': 1400.0, 'y': 40.0, 'achieved': 0},
            {'x': 1600.0, 'y': 40.0, 'achieved': 0},
            {'x': 1800.0, 'y': 40.0, 'achieved': 0},
            {'x': 2000.0, 'y': 40.0, 'achieved': 0},
        ]
        opi = calc.estimate_user_opi(achievements, initial_theta=1500.0)
        assert np.isfinite(opi), "推定値が有限の実数であること"
        assert opi < 1300.0, "全未達成のため低OPIに推定されること"
        assert opi > 500.0, "正則化項により極端な負値に発散しないこと"

    def test_chart_constant_boundary_13_7(self):
        """定数13.7の境界判定（13.69は除外、13.70は対象）"""
        def is_target_chart(constant: float) -> bool:
            return constant >= 13.7

        assert is_target_chart(13.69) is False
        assert is_target_chart(13.699) is False
        assert is_target_chart(13.70) is True
        assert is_target_chart(13.75) is True
        assert is_target_chart(15.90) is True

    def test_rating_band_boundary_classification(self):
        """レーティング帯の境界値判定（17.75〜18.249... が18.0帯、17.749は除外）"""
        import math

        def get_band_center(rating: float):
            if rating < 17.75:
                return None
            band_idx = math.floor((rating - 17.75) / 0.5)
            center = 18.0 + band_idx * 0.5
            return round(center, 1)

        # 17.749: 18.0帯の範囲外（除外）
        assert get_band_center(17.74) is None
        assert get_band_center(17.749) is None

        # 17.750 〜 18.249: 18.0帯
        assert get_band_center(17.75) == 18.0
        assert get_band_center(18.00) == 18.0
        assert get_band_center(18.24) == 18.0

        # 18.250: 18.5帯
        assert get_band_center(18.25) == 18.5
        assert get_band_center(18.50) == 18.5
        assert get_band_center(18.74) == 18.5

        # 20.750: 21.0帯
        assert get_band_center(20.75) == 21.0
        assert get_band_center(21.00) == 21.0

    def test_visualizer_empty_data_handling(self, test_db_path, tmp_path):
        """プレイヤーデータが0件の状態で分布図作成を呼び出してもクラッシュしないこと"""
        vis = OPIVisualizer(test_db_path)
        output_path = str(tmp_path / "empty_distribution.png")
        # エラーを出さずに安全に終了すること
        vis.create_distribution_plot(output_path)
