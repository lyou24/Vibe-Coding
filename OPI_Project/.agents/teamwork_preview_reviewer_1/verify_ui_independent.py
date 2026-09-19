import sys
import os
import io

# 出力文字コード設定
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
APP_PATH = os.path.join(PROJECT_ROOT, "app.py")
at = AppTest.from_file(APP_PATH, default_timeout=30).run()
assert len(at.exception) == 0, f"Exceptions: {[e.message for e in at.exception]}"

# 1. 目標ランクに ['S'] を選択
at.multiselect(key="filter_target_rank").set_value(["S"]).run()
assert len(at.exception) == 0
df_s = at.dataframe[0].value
assert len(df_s) > 0, "S target recs should not be empty"
unique_ranks = set(df_s["目標ランク"].unique())
assert unique_ranks == {"S"}, f"Unexpected target ranks: {unique_ranks}"
print("Test 1 Passed: S target rank correctly filtered.")

# 2. 目標ランクに ['S', 'SS'] を選択
at.multiselect(key="filter_target_rank").set_value(["S", "SS"]).run()
assert len(at.exception) == 0
df_s_ss = at.dataframe[0].value
assert len(df_s_ss) > 0
unique_s_ss = set(df_s_ss["目標ランク"].unique())
assert unique_s_ss.issubset({"S", "SS"}), f"Unexpected ranks: {unique_s_ss}"
print("Test 2 Passed: S and SS target ranks correctly filtered.")

# 3. レベルに ['14'] を選択
at.multiselect(key="filter_level").set_value(["14"]).run()
assert len(at.exception) == 0
df_lv14 = at.dataframe[0].value
assert len(df_lv14) > 0
unique_levels = set(df_lv14["レベル"].unique())
assert unique_levels == {"14"}, f"Unexpected levels: {unique_levels}"
print("Test 3 Passed: Level 14 correctly filtered.")

# 4. 目標ランク・レベルを未選択（[]）に戻す（フォールバック検証）
at.multiselect(key="filter_target_rank").set_value([]).run()
at.multiselect(key="filter_level").set_value([]).run()
assert len(at.exception) == 0
df_all = at.dataframe[0].value
assert len(df_all) > 0
print(f"Test 4 Passed: Unselected fallback to all targets works perfectly ({len(df_all)} items).")

# 5. スライダーを 0.0〜100.0 にし、目標ランクを ['AB+'] に設定
at.slider(key="filter_clear_rate_range").set_value((0.0, 100.0)).run()
at.multiselect(key="filter_target_rank").set_value(["AB+"]).run()
assert len(at.exception) == 0
df_abp = at.dataframe[0].value
assert len(df_abp) > 0
unique_abp = set(df_abp["目標ランク"].unique())
assert unique_abp == {"AB+"}, f"Unexpected target ranks: {unique_abp}"
print(f"Test 5 Passed: Slider 0-100% and AB+ target rank work perfectly ({len(df_abp)} items).")

# 6. 現在ランク絞り込み（['未S']）の検証
at.multiselect(key="filter_target_rank").set_value([]).run()
at.slider(key="filter_clear_rate_range").set_value((30.0, 70.0)).run()
at.multiselect(key="filter_current_rank").set_value(["未S"]).run()
assert len(at.exception) == 0
df_cur_uns = at.dataframe[0].value
assert len(df_cur_uns) > 0
for status in df_cur_uns["現在の達成状況"].unique():
    assert ("未S" in status or "未プレイ" in status), f"Unexpected current status: {status}"
print(f"Test 6 Passed: Current rank '未S' filtering works perfectly ({len(df_cur_uns)} items).")

print("\n>>> ALL INDEPENDENT VERIFICATIONS PASSED SUCCESSFULLY! <<<")
