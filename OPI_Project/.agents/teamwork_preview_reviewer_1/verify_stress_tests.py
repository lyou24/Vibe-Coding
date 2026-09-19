import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
APP_PATH = os.path.join(PROJECT_ROOT, "app.py")

# 1. 存在しないユーザーID (999999) 入力時の挙動
at = AppTest.from_file(APP_PATH, default_timeout=30).run()
at.sidebar.text_input[0].set_value("999999").run()
assert len(at.exception) == 0, f"Exception on user 999999: {[e.message for e in at.exception]}"
warnings = [w.value for w in at.warning]
assert any("見つかりません" in w for w in warnings), f"Expected not found warning, got {warnings}"
print("Stress Test 1 Passed: Non-existent user ID gracefully handled.")

# 2. スライダー同値 (50.0, 50.0)
at = AppTest.from_file(APP_PATH, default_timeout=30).run()
at.slider(key="filter_clear_rate_range").set_value((50.0, 50.0)).run()
assert len(at.exception) == 0, f"Exception on slider (50, 50): {[e.message for e in at.exception]}"
print("Stress Test 2 Passed: Equal slider min/max (50%, 50%) handled safely.")

# 3. 0件ヒットのフィルタ条件設定（例: 定数15.7〜15.7で未プレイかつAB+目標など）
at.multiselect(key="filter_target_rank").set_value(["AB+"]).run()
at.slider(key="filter_clear_rate_range").set_value((90.0, 100.0)).run()
assert len(at.exception) == 0
info_messages = [i.value for i in at.info]
assert any("適正範囲の楽曲が見つかりませんでした" in m or "データが不足" in m for m in info_messages)
print("Stress Test 3 Passed: 0-hit filter displays user friendly info message without crashing.")

# 4. 難易度表タブでの各ランク切り替え
for rank in ["S", "SS", "SSS", "SSS+", "AB+"]:
    at.selectbox(key="diff_target_rank_select").set_value(rank).run()
    assert len(at.exception) == 0
    at.selectbox(key="my_diff_target_rank_select").set_value(rank).run()
    assert len(at.exception) == 0
print("Stress Test 4 Passed: All 5 ranks selectable in difficulty and my-difficulty tables without error.")

print("\n>>> ALL STRESS TESTS PASSED! <<<")
