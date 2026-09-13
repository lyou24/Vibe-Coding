## 2026-09-13T15:07:45Z

<USER_REQUEST>
あなたはOPIプロジェクトのM3マイルストーン（イテレーション2：ロバスト性向上・NaN/infガード実装）を担当する実装Worker（teamwork_preview_worker）です。

【作業ディレクトリ】
C:\Users\lyoul\マイドライブ\lyou_Obsidian\90_Git\OPI_Project\.agents\teamwork_preview_worker_m3_2

【必読ファイル】
- C:\Users\lyoul\マイドライブ\lyou_Obsidian\90_Git\OPI_Project\.agents\ORIGINAL_REQUEST.md
- C:\Users\lyoul\マイドライブ\lyou_Obsidian\00_Inbox\OPI要件定義書.md
- C:\Users\lyoul\マイドライブ\lyou_Obsidian\90_Git\OPI_Project\PROJECT.md
- C:\Users\lyoul\マイドライブ\lyou_Obsidian\90_Git\OPI_Project\.agents\teamwork_preview_challenger_m3_1\handoff.md
- C:\Users\lyoul\マイドライブ\lyou_Obsidian\90_Git\OPI_Project\.agents\teamwork_preview_worker_m3_1\handoff.md

【MANDATORY INTEGRITY WARNING】
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

【担当・変更可能ファイル（排他所有）】
- src/visualizer/visualizer.py
- tests/test_tier2_boundary_corner.py

【実装・修正タスク】
Challenger 1（da070a41-2344-4a95-92fc-6f3074f5db9b）の敵対的ストレステストで発見された脆弱性を修復してください：
1. **NaN / inf 安全ガードの実装**:
   - `src/visualizer/visualizer.py` の `get_band_label` の先頭に、`if rating is None or math.isnan(rating) or math.isinf(rating): return None` を追加し、`float('nan')`, `np.nan`, `float('inf')`, `float('-inf')` 等の異常値が入力された際に例外（`ValueError`, `OverflowError`）でクラッシュせず、安全に `None` を返すように改修してください。
   - `calculate_current_distribution_table` や `plot_distribution` 内でも、レーティングが NaN / inf のレコードが存在してもクラッシュしないよう安全にスキップ・除外する処理を確認・追加してください。
2. **境界値テストの拡充**:
   - `tests/test_tier2_boundary_corner.py` に、`NaN`, `inf`, `-inf`, `None` を `get_band_label` に渡した際にクラッシュせず `None` を返すことを検証するテストケースを追加してください。
3. **全テストスイートの検証**:
   - `.venv\Scripts\python.exe -m pytest tests -v` を実行し、既存テストおよび新規テストすべてが **100% PASS** することを確認してください。

【出力要件】
- 作業ディレクトリ内に `handoff.md` および `changes.md` を作成してください。
- 完了後、親エージェント（オーケストレーター）へ `send_message` で完了報告を行ってください。
- 全ての思考・ドキュメント・メッセージは日本語で記述してください。

</USER_REQUEST>
