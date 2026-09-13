"""
M3 イテレーション2 敵対的検証スクリプト
NaN / inf / None / 極値 / 浮動小数点誤差 / 異常データ混入に対する徹底的ストレステスト
"""

import os
import sys
import math
import tempfile
import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# プロジェクトルートのインポートパス解決
sys.path.insert(0, os.path.abspath("."))

from src.database.models import Base, Player, Chart, ScoreLog
from src.visualizer.visualizer import OPIVisualizer

def test_single_band_label():
    print("=== [TEST 1] get_band_label 単体敵対的ストレステスト ===")
    
    test_cases = [
        # (Case Name, Input, Expected, AllowCrash)
        ("None", None, None, False),
        ("float('nan')", float('nan'), None, False),
        ("np.nan", np.nan, None, False),
        ("float('inf')", float('inf'), None, False),
        ("float('-inf')", float('-inf'), None, False),
        ("invalid string", "invalid", None, False),
        ("empty string", "", None, False),
        ("string 'nan'", "nan", None, False),
        ("string 'inf'", "inf", None, False),
        ("string '-inf'", "-inf", None, False),
        ("string valid '18.0'", "18.0", "18.0", False),
        ("string valid '18.25'", "18.25", "18.5", False),
        ("empty list", [], None, False),
        ("empty dict", {}, None, False),
        ("object instance", object(), None, False),
        ("complex number", 18.0 + 1j, None, False),
        ("negative rating -100.0", -100.0, None, False),
        ("negative huge -1e9", -1e9, None, False),
        ("zero 0.0", 0.0, None, False),
        ("sub-threshold 17.0", 17.0, None, False),
        ("sub-threshold 17.74", 17.74, None, False),
        ("sub-threshold 17.749", 17.749, None, False),
        ("sub-threshold 17.7499", 17.7499, None, False),
        ("sub-threshold 17.74999999", 17.74999999, None, False),
        # 18.0 band: [17.75, 18.25)
        ("band 18.0 lower 17.750", 17.750, "18.0", False),
        ("band 18.0 lower+eps 17.75000001", 17.75000001, "18.0", False),
        ("band 18.0 center 18.000", 18.000, "18.0", False),
        ("band 18.0 upper-margin 18.249", 18.249, "18.0", False),
        ("band 18.0 upper-margin 18.2499", 18.2499, "18.0", False),
        ("band 18.0 upper-margin 18.24999999", 18.24999999, "18.0", False),
        # 18.5 band: [18.25, 18.75)
        ("band 18.5 lower 18.250", 18.250, "18.5", False),
        ("band 18.5 lower+eps 18.25000001", 18.25000001, "18.5", False),
        ("band 18.5 center 18.500", 18.500, "18.5", False),
        ("band 18.5 upper-margin 18.7499", 18.7499, "18.5", False),
        # 19.0 band: [18.75, 19.25)
        ("band 19.0 lower 18.750", 18.750, "19.0", False),
        ("band 19.0 center 19.000", 19.000, "19.0", False),
        # 19.5 band: [19.25, 19.75)
        ("band 19.5 lower 19.250", 19.250, "19.5", False),
        # 20.0 band: [19.75, 20.25)
        ("band 20.0 lower 19.750", 19.750, "20.0", False),
        # 20.5 band: [20.25, 20.75)
        ("band 20.5 lower 20.250", 20.250, "20.5", False),
        # 21.0 band: [20.75, 21.25)
        ("band 21.0 lower 20.750", 20.750, "21.0", False),
        # 21.5 band: [21.25, 21.75)
        ("band 21.5 lower 21.250", 21.250, "21.5", False),
        # Extreme upper
        ("extreme 99.9", 99.9, "100.0", False),
        ("extreme 1000.0", 1000.0, "1000.0", False),
        ("huge float 1e15", 1e15, None, False), # 1e15 might overflow or calculate huge band
    ]

    all_passed = True
    for name, val, expected, allow_crash in test_cases:
        try:
            actual = OPIVisualizer.get_band_label(val)
            if expected is not None:
                if actual == expected:
                    print(f"  [PASS] {name:32} -> {actual}")
                else:
                    print(f"  [FAIL] {name:32} -> Got {actual}, Expected {expected}")
                    all_passed = False
            else:
                # expected is None
                if name == "huge float 1e15":
                    # 1e15 is a float, check if it crashed or safely returned something
                    print(f"  [INFO] {name:32} -> Returned {actual} (No crash)")
                elif actual is None:
                    print(f"  [PASS] {name:32} -> None")
                else:
                    print(f"  [FAIL] {name:32} -> Got {actual}, Expected None")
                    all_passed = False
        except Exception as e:
            print(f"  [CRASH] {name:32} -> Exception: {type(e).__name__}: {e}")
            all_passed = False

    assert all_passed, "get_band_label 単体テストで失敗がありました。"
    print(">>> get_band_label 単体敵対的テスト: ALL PASSED!\n")


def test_distribution_methods_adversarial():
    print("=== [TEST 2] 集計・描画メソッド敵対的ストレステスト ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "adversarial_test.sqlite")
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        vis = OPIVisualizer(db_path)

        # 1. 完全空DBでの実行
        print("  1. 空DBテスト...")
        t_empty = vis.calculate_current_distribution_table()
        assert t_empty.empty, "空DBでは空DataFrameが返るべき"
        plot_empty = os.path.join(tmpdir, "plot_empty.png")
        vis.create_distribution_plot(plot_empty)
        assert not os.path.exists(plot_empty), "データなしではプロットファイルは生成されない（安全リターン）"
        vis.plot_distribution(plot_empty)
        print("     [PASS] 空DB安全処理確認")

        # 2. 全レコードが異常値・極値のDB
        print("  2. 全レコード異常値テスト...")
        invalid_players = [
            Player(user_id=1, player_name="P1", rating=float('nan'), total_opi=1500.0),
            Player(user_id=2, player_name="P2", rating=18.0, total_opi=float('nan')),
            Player(user_id=3, player_name="P3", rating=float('inf'), total_opi=1500.0),
            Player(user_id=4, player_name="P4", rating=18.0, total_opi=float('inf')),
            Player(user_id=5, player_name="P5", rating=float('-inf'), total_opi=1500.0),
            Player(user_id=6, player_name="P6", rating=18.0, total_opi=float('-inf')),
            Player(user_id=7, player_name="P7", rating=None, total_opi=1500.0),
            Player(user_id=8, player_name="P8", rating=18.0, total_opi=None),
            Player(user_id=9, player_name="P9", rating=10.0, total_opi=1000.0), # 17.75未満
            Player(user_id=10, player_name="P10", rating=17.7499, total_opi=1000.0), # 17.75未満
        ]
        session.add_all(invalid_players)
        session.commit()

        t_invalid = vis.calculate_current_distribution_table()
        assert t_invalid.empty, "異常レコードのみの場合は空DataFrameが返るべき"
        plot_invalid = os.path.join(tmpdir, "plot_invalid.png")
        vis.create_distribution_plot(plot_invalid)
        assert not os.path.exists(plot_invalid), "有効データなしではプロットファイル生成されず安全終了"
        print("     [PASS] 全レコード異常値耐性確認")

        # 3. 正常1件のみ（N=1 サンプル）
        print("  3. N=1 サンプルテスト（分布集計・バイオリンプロット特異点）...")
        single_player = Player(user_id=100, player_name="SingleP", rating=18.0, total_opi=1480.0)
        session.add(single_player)
        session.commit()

        t_single = vis.calculate_current_distribution_table()
        assert len(t_single) == 1, f"1件の集計が得られるべき: {len(t_single)}"
        assert t_single.iloc[0]["対象レート"] == "18.0"
        assert t_single.iloc[0]["目標総合OPI（中央値）"] == 1480.0
        assert t_single.iloc[0]["サンプル人数"] == "1人"
        
        plot_single = os.path.join(tmpdir, "plot_single.png")
        vis.create_distribution_plot(plot_single)
        assert os.path.exists(plot_single), "N=1でもプロットファイルが正常に生成されること"
        print("     [PASS] N=1 特異点耐性確認")

        # 4. 正常多件数 + 異常データ大量混入（カオスデータセット）
        print("  4. カオスデータセットテスト（正常群 + 大量異常データ）...")
        chaos_players = []
        # 各帯域に正常データを配置
        centers = [18.0, 18.5, 19.0, 19.5, 20.0, 20.5, 21.0]
        uid = 200
        for c in centers:
            for delta in [-0.24, -0.1, 0.0, 0.1, 0.24]:
                chaos_players.append(Player(
                    user_id=uid,
                    player_name=f"Norm_{uid}",
                    rating=round(c + delta, 3),
                    total_opi=1000.0 + c * 50 + delta * 20
                ))
                uid += 1
        
        # 異常系を大量注入
        for _ in range(50):
            chaos_players.append(Player(
                user_id=uid,
                player_name=f"Chaos_{uid}",
                rating=float('nan') if uid % 3 == 0 else (float('inf') if uid % 3 == 1 else float('-inf')),
                total_opi=float('nan') if uid % 2 == 0 else 1500.0
            ))
            uid += 1

        session.add_all(chaos_players)
        session.commit()

        t_chaos = vis.calculate_current_distribution_table()
        assert not t_chaos.empty, "カオスデータでも正常レコードが集計されること"
        bands = t_chaos["対象レート"].tolist()
        for c in centers:
            assert f"{c:.1f}" in bands, f"帯域 {c:.1f} が集計結果に含まれていること"

        plot_chaos = os.path.join(tmpdir, "plot_chaos.png")
        vis.create_distribution_plot(plot_chaos)
        assert os.path.exists(plot_chaos), "カオスデータでもプロットファイルが生成されること"
        print("     [PASS] カオスデータ耐性確認")

        # 5. エイリアス plot_distribution の検証
        plot_alias = os.path.join(tmpdir, "plot_alias.png")
        vis.plot_distribution(plot_alias)
        assert os.path.exists(plot_alias), "plot_distribution エイリアスで画像が正常生成されること"
        print("     [PASS] plot_distribution エイリアス動作確認")

        # 6. 要件定義書3.2 目標値テーブル get_target_distribution_table の検証
        t_target = vis.get_target_distribution_table()
        assert len(t_target) == 7, f"目標値テーブルは7行であること: {len(t_target)}"
        assert "18.0" in t_target["対象レート"].values
        assert "21.0" in t_target["対象レート"].values
        print("     [PASS] get_target_distribution_table 整合性確認")

        session.close()
        engine.dispose()
        vis.engine.dispose()

    print(">>> 集計・描画メソッド敵対的テスト: ALL PASSED!\n")

if __name__ == "__main__":
    try:
        test_single_band_label()
        test_distribution_methods_adversarial()
        print("==========================================================")
        print("  ALL EMPIRICAL ADVERSARIAL STRESS TESTS COMPLETED (PASS)")
        print("==========================================================")
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
