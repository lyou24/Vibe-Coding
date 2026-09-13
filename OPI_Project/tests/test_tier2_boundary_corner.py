import math
import numpy as np
import pytest
import pandas as pd
from src.visualizer.visualizer import OPIVisualizer
from src.database.models import Player


class TestTier2BoundaryCorner:
    """Tier 2: NaN / inf / -inf / None および境界値・異常系に対するロバスト性テスト"""

    @pytest.mark.parametrize("invalid_rating", [
        None,
        float('nan'),
        np.nan,
        float('inf'),
        float('-inf'),
        "invalid_string",
        [],
        {},
    ])
    def test_get_band_label_nan_inf_none_robustness(self, invalid_rating):
        """
        NaN, np.nan, inf, -inf, None, および非数値型に対して、
        ValueError や OverflowError 等でクラッシュせず、安全に None を返却すること。
        """
        result = OPIVisualizer.get_band_label(invalid_rating)
        assert result is None, f"Input {invalid_rating} should safely return None, got {result}"

    @pytest.mark.parametrize("rating, expected_label", [
        (0.0, None),
        (17.74, None),
        (17.7499, None),
        (17.750, "18.0"),
        (17.7501, "18.0"),
        (18.0, "18.0"),
        (18.249, "18.0"),
        (18.2499, "18.0"),
        (18.250, "18.5"),
        (18.7499, "18.5"),
        (18.750, "19.0"),
        (19.250, "19.5"),
        (19.750, "20.0"),
        (20.250, "20.5"),
        (20.750, "21.0"),
        (21.250, "21.5"),
        (99.9, "100.0"),
    ])
    def test_get_band_label_exact_boundaries(self, rating, expected_label):
        """
        要件定義書 1.3 F-06 / 3.2:
        レーティング18.0以上のユーザーを0.5刻みの基準値とし、
        各基準値 ±0.25 の帯域（[center - 0.25, center + 0.25)）に厳密に分類されること。
        """
        result = OPIVisualizer.get_band_label(rating)
        assert result == expected_label, f"Rating {rating} should be labeled {expected_label}, got {result}"

    def test_distribution_methods_with_nan_inf_database_records(self, test_db_path, test_session, tmp_path):
        """
        データベース内に rating や total_opi が NaN / inf / -inf / None のレコードが存在しても、
        calculate_current_distribution_table および create_distribution_plot / plot_distribution が
        例外でクラッシュすることなく安全に除外・集計・描画できること。
        """
        # 正常レコードと異常レコードを混合して登録
        mixed_players = [
            Player(user_id=8001, player_name="ValidUser1", rating=18.0, total_opi=1480.0),
            Player(user_id=8002, player_name="ValidUser2", rating=18.5, total_opi=1630.0),
            Player(user_id=8003, player_name="ValidUser3", rating=19.0, total_opi=1790.0),
            Player(user_id=8010, player_name="NaNUser", rating=float('nan'), total_opi=1800.0),
            Player(user_id=8011, player_name="InfUser", rating=float('inf'), total_opi=1800.0),
            Player(user_id=8012, player_name="NegInfUser", rating=float('-inf'), total_opi=1800.0),
            Player(user_id=8013, player_name="NaNOpiUser", rating=18.0, total_opi=float('nan')),
            Player(user_id=8014, player_name="InfOpiUser", rating=18.0, total_opi=float('inf')),
        ]
        test_session.add_all(mixed_players)
        test_session.commit()

        vis = OPIVisualizer(test_db_path)

        # 1. calculate_current_distribution_table の検証
        df_table = vis.calculate_current_distribution_table()
        assert not df_table.empty, "正常なプレイヤーデータに基づく統計テーブルが生成されること"
        rates = df_table["対象レート"].tolist()
        assert "18.0" in rates
        assert "18.5" in rates
        assert "19.0" in rates

        # 2. create_distribution_plot の検証
        plot_file = str(tmp_path / "test_nan_distribution.png")
        vis.create_distribution_plot(plot_file)
        import os
        assert os.path.exists(plot_file), "分布図画像が生成されていること"

        # 3. plot_distribution エイリアスの検証
        plot_alias_file = str(tmp_path / "test_nan_distribution_alias.png")
        vis.plot_distribution(plot_alias_file)
        assert os.path.exists(plot_alias_file), "エイリアスメソッドでも分布図画像が生成されていること"

    def test_distribution_methods_with_only_invalid_records(self, test_db_path, test_session, tmp_path):
        """
        データベース内に無効・異常値レコードしか存在しない場合でも、安全に空の表を返しクラッシュしないこと。
        """
        invalid_players = [
            Player(user_id=8020, player_name="NaNOnly", rating=float('nan'), total_opi=float('nan')),
            Player(user_id=8021, player_name="InfOnly", rating=float('inf'), total_opi=float('inf')),
            Player(user_id=8022, player_name="LowRating", rating=15.0, total_opi=1000.0),
        ]
        test_session.add_all(invalid_players)
        test_session.commit()

        vis = OPIVisualizer(test_db_path)
        df_table = vis.calculate_current_distribution_table()
        assert df_table.empty, "有効な対象データがない場合は空のDataFrameを返すこと"

        plot_file = str(tmp_path / "test_empty_distribution.png")
        # 例外を起こさず安全に終了すること
        vis.create_distribution_plot(plot_file)
