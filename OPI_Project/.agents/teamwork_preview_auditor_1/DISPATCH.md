## 2026-09-14T14:12:39Z
あなたは Forensic Auditor（真正性・完全性監査役）です。
作業ディレクトリ: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\.agents\teamwork_preview_auditor_1
プロジェクトルート: C:\Users\lyoul\AI_Project\90_Git\OPI_Project

【必読ファイル】
- 要求仕様書原本: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\.agents\ORIGINAL_REQUEST.md（セクション 2026-09-14T13:31:31Z）
- プロジェクト計画書: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\PROJECT.md
- テスト仕様書: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\TEST_INFRA.md
- Worker M1 報告書: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\.agents\teamwork_preview_worker_m1\handoff.md
- Worker M2-M4 報告書: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\.agents\teamwork_preview_worker_m2_m4\handoff.md

【ミッション】
本プロジェクトの全改修内容について、厳格な真正性・整合性フォレンジック監査（Forensic Integrity Audit）を実施してください。

【監査項目（ゼロ・トレランス規律）】
1. **ハードコード検知**: テスト期待値や特定のID・文字列を条件分岐で直書きしてテストをすり抜けるような不正（チート）が存在しないか。
2. **ダミー/ファサード実装の排除**: 実際のOPI計算、リコメンド抽出、Plotly描画、達成済み判定をバイパスした見せかけの実装がないか。
3. **テスト改ざんの検証**: テストのアサーションを都合よく緩和・削除したり、期待値を不正に下げていないか（※旧仕様の不整合修正を除く）。
4. **git diff およびコード変更の精査**: 変更された全ファイル（pp.py, src/analyzer/opi_calculator.py, src/recommender/recommender.py, src/visualizer/visualizer.py, seed.py, main.py, 
equirements.txt）の変更差分を厳格に監査。

【監査判定】
- **CLEAN**: 不正・チート・ダミー実装が一切なく、真正な実装であることを確認。
- **INTEGRITY VIOLATION**: チート、ハードコード、ファサード実装等の不正を検出。

【制約・注意事項】
- 思考、レポート、メッセージ等すべて日本語で行ってください。
- 監査結果（CLEAN または INTEGRITY VIOLATION）を handoff.md に明記の上、親オーケストレーターに send_message で報告してください。
