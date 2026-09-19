import sys
sys.stdout.reconfigure(encoding='utf-8')
from streamlit.testing.v1 import AppTest

# 1. 初期状態（未認証）
at = AppTest.from_file("app.py", default_timeout=30).run()
assert len(at.exception) == 0, f"Exceptions: {[e.message for e in at.exception]}"
pass_inputs = [t for t in at.text_input if "合言葉" in t.label]
assert len(pass_inputs) > 0, "合言葉入力欄が見つかりません"
assert len(at.sidebar.text_input) == 0, "未認証時にサイドバーが表示されています"
print("[TEST 1] Password input exists and main UI is blocked: PASS")

# 2. 誤った合言葉
pass_inputs[0].set_value("wrong_password")
at.button[0].click()
at.run()
assert any("正しくありません" in err.value for err in at.error), "誤ったパスワードでエラーが表示されませんでした"
assert not at.session_state.get("authenticated", False) if hasattr(at.session_state, "get") else ("authenticated" not in at.session_state or not at.session_state["authenticated"]), "誤ったパスワードで認証されてしまいました"
print("[TEST 2] Wrong password rejected with error: PASS")

# 3. 正しい合言葉 (123123)
pass_inputs[0].set_value("123123")
at.button[0].click()
at.run()
assert at.session_state["authenticated"] is True, "正しい合言葉で認証されていません"
user_inputs = [t for t in at.sidebar.text_input if "ユーザーID" in t.label]
assert len(user_inputs) > 0, "認証後にサイドバーが表示されていません"
print("[TEST 3] Correct password (123123) authenticated and app unlocked: PASS")

print("\nALL AUTHENTICATION TESTS PASSED SUCCESSFULLY!")
