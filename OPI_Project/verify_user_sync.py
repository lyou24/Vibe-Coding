import sys
sys.stdout.reconfigure(encoding='utf-8')
from streamlit.testing.v1 import AppTest

print("Launching AppTest...")
at = AppTest.from_file("app.py", default_timeout=30).run()

# 1. ログイン
pass_input = at.text_input[0]
pass_input.set_value("123123")
at.button[0].click()
at.run()
assert at.session_state["authenticated"] is True, "Login failed!"
print("[TEST 1] Authenticated: PASS")

# 2. ユーザーID入力（Enter押下による自動取得）
user_input = at.sidebar.text_input[0]
user_input.set_value("10605")
at.run()

# 自動でプレイヤーデータがロード・同期されているか確認
assert len(at.exception) == 0, f"Exceptions: {[e.message for e in at.exception]}"
metrics = at.metric
print("Metrics rendered:", [f"{m.label}: {m.value}" for m in metrics])
assert any("レーティング" in m.label for m in metrics), "Rating metric not found!"
print("[TEST 2] Automatic user sync on search: PASS")

# 3. メイン画面の「最新スコアに更新」ボタンの存在確認
refresh_buttons = [b for b in at.button if "最新スコアに更新" in b.label]
print("Refresh buttons found:", len(refresh_buttons))
assert len(refresh_buttons) > 0, "Main refresh button not found!"
print("[TEST 3] Main refresh button exists: PASS")

print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")
