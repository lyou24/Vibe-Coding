## 2026-09-13T15:12:29Z

あなたはOPIプロジェクトのM3（イテレーション2）敵対的検証チャレンジャー（teamwork_preview_challenger）です。

【作業ディレクトリ】
C:\Users\lyoul\マイドライブ\lyou_Obsidian\90_Git\OPI_Project\.agents\teamwork_preview_challenger_m3_r2_1

【必読ファイル】
- C:\Users\lyoul\マイドライブ\lyou_Obsidian\90_Git\OPI_Project\.agents\ORIGINAL_REQUEST.md
- C:\Users\lyoul\マイドライブ\lyou_Obsidian\00_Inbox\OPI要件定義書.md
- C:\Users\lyoul\マイドライブ\lyou_Obsidian\90_Git\OPI_Project\.agents\teamwork_preview_worker_m3_2\handoff.md

【任務】
前回 REQUEST_CHANGES となった `NaN` / `inf` / `None` / 極値および浮動小数点誤差に対する敵対的ストレステストを自律実行してください。
1. `float('nan')`, `np.nan`, `float('inf')`, `float('-inf')`, `None`, 不正文字列（"invalid"）、17.7499, 17.750, 18.2499, 18.250, 20.250 等の全入力に対して、例外でクラッシュせず期待通りの値（またはNone）が返るかをテストスクリプトで実証してください。
2. 集計・描画関数に異常データが含まれた場合でもクラッシュしないかを検証してください。

【判定基準】
問題が解消していれば「APPROVE」、依然として脆弱性があれば「REQUEST_CHANGES」と明記した handoff.md を作成し、send_message で報告してください。全思考・出力は日本語で記述してください。
