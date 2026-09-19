## 2026-09-14T13:43:32Z
あなたは E2E Testing Track を担当する Test Writer です。
作業ディレクトリ: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\.agents\teamwork_preview_test_writer_e2e
プロジェクトルート: C:\Users\lyoul\AI_Project\90_Git\OPI_Project

【必読ファイル】
- 要求仕様書原本: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\.agents\ORIGINAL_REQUEST.md（特にセクション 2026-09-14T13:31:31Z）
- プロジェクト全体計画: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\PROJECT.md
- Explorer 3 の調査報告: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\.agents\teamwork_preview_explorer_survey_3\handoff.md

【ミッション】
要求仕様原本に基づく包括的な新受入基準 E2E テストスイートを構築してください。
実装内部のコードに依存しない「Opaque-box（ブラックボックス）」「Requirement-driven（要求駆動）」テストを設計・作成します。

【具体的な作成対象とファイル所有権】
あなたが所有・編集するファイルは以下のみです：
1. `TEST_INFRA.md`（プロジェクトルートに作成）
   - テスト設計思想、受入基準テストアーキテクチャ、テストケース一覧を記録。
2. `tests/test_tier4_m4_new_acceptance.py`（新規作成）
   - `streamlit.testing.v1.AppTest` を活用した最新受入基準自動検証テスト（AC-1〜AC-6）：
     - AC-1: Streamlitアプリの起動および実行時例外ゼロ
     - AC-2: R1 新5段階ランク（S, SS, SSS, SSS+, AB+）への完全対応と旧ランク（SSS+ABFB, AP）の完全排除
     - AC-3: R2 リコメンドUI（「クリア割合」0〜100%スライダー、複数選択マルチセレクト、未選択時全対象ヒット）
     - AC-4: R3 難易度表グリッド化（100帯降順ソート）および「マイOPI難易度表」の達成済みセル識別
     - AC-5: R4 動的散布図（Plotly図の生成と選択ユーザー現在位置ハイライト）
     - AC-6: テストユーザーID `10605`（397件スコア）によるE2Eリコメンド・OPI算出テスト
3. `TEST_READY.md`（プロジェクトルートに作成）
   - テストスイートの準備完了を宣言し、テスト実行コマンドとカバレッジサマリーを記録。

【制約・注意事項】
- アプリケーションの実装コード（app.py, src/ 等）は編集しないでください。テストコードとテストメタデータのみを編集します。
- 思考、レポート、メッセージ等はすべて日本語で行ってください。
- 完了時は作業ディレクトリ内の `handoff.md` に結果をまとめ、親オーケストレーターに `send_message` で報告してください。
