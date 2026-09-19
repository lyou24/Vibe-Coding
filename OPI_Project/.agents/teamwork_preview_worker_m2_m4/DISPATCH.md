## 2026-09-14T14:02:05Z

あなたは Milestone 2〜4（UI高度化・グリッド化・マイ難易度表・動的散布図）を担当する Worker です。
作業ディレクトリ: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\.agents\teamwork_preview_worker_m2_m4
プロジェクトルート: C:\Users\lyoul\AI_Project\90_Git\OPI_Project

【必読ファイル】
- 要求仕様書原本: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\.agents\ORIGINAL_REQUEST.md（セクション 2026-09-14T13:31:31Z）
- プロジェクト全体計画: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\PROJECT.md
- E2Eテスト仕様書: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\TEST_INFRA.md
- E2E新受入テストコード: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\tests\test_tier4_m4_new_acceptance.py
- Explorer 1 報告書（UI設計・コードスニペット）: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\.agents\teamwork_preview_explorer_survey_1\handoff.md
- Worker M1 報告書: C:\Users\lyoul\AI_Project\90_Git\OPI_Project\.agents\teamwork_preview_worker_m1\handoff.md

【MANDATORY INTEGRITY WARNING】
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

【所有権・変更対象ファイル】
- `app.py`
- `src/visualizer/visualizer.py`

【実装ミッション】
1. **R2: リコメンド機能のUI高度化 (`app.py`)**:
   - 目標ランク、レベル、現在ランクを `st.multiselect` で複数選択可能にし、**未選択（空）の場合は全対象を表示する**フォールバックを実装（`effective_target_ranks = target_ranks or TARGET_RANK_OPTIONS`）。
   - 「勝率 Min/Max」の入力欄を廃止し、0〜100%の範囲スライダー `clear_rate_range = st.slider("クリア割合範囲（%）", min_value=0.0, max_value=100.0, value=(30.0, 70.0), step=1.0)` を設置。
   - UI上の表記を「勝率」から「クリア割合」に完全変更（テーブル列名、ソート選択肢など）。

2. **R3: OPI難易度表のグリッド化 & 「マイOPI難易度表」の実装 (`app.py`)**:
   - 難易度表を 100 OPIごとの帯域（例: 2200帯, 2100帯, ...）で区切ったグリッド形式とし、難しい曲（OPIが高い曲）ほど上に表示されるよう**降順ソート**を徹底。
   - タブを `tab1, tab2, tab3, tab4 = st.tabs(["🎯 リコメンド楽曲", "📊 統計・分布図", "📜 OPI難易度表", "⭐ マイOPI難易度表"])` に拡張。
   - 「⭐ マイOPI難易度表」タブでは、選択中のユーザーが対象目標ランクを達成済みの楽曲セルを色付きハイライト（背景色 `#e8f5e9`、緑枠、バッジ `<span style='color:#2e7d32; font-weight:bold;'>[達成済]</span>` 等）で描画し、未達成曲と視覚的に明確に区別できるようにする。

3. **R4: 統計・分布図の動的グラフ化 (`src/visualizer/visualizer.py`, `app.py`)**:
   - `src/visualizer/visualizer.py` に Plotly による動的散布図生成メソッド `create_distribution_figure(player_rating, player_opi, player_name)` を実装。
     - 横軸: レーティング生値（`rating`）、縦軸: 総合OPI（`total_opi`）。
     - 全プレイヤー（青系マーカー）の散布図を描画。
     - 選択中のユーザーが存在する場合、赤色の星型マーカー（`size=14, color='crimson', symbol='star'`）で現在位置をハイライト表示。
   - `app.py` の「📊 統計・分布図」タブにおいて、ボタン押下を待たずに `st.plotly_chart` で動的グラフを即時描画。

4. **テスト検証と受入基準達成**:
   - `.venv\Scripts\pytest.exe tests/test_tier4_m4_new_acceptance.py -v` を実行し、全8テストが 100% PASSED となることを確認。
   - `.venv\Scripts\pytest.exe tests/` を実行し、全体テストがパスすることを確認。
   - Streamlit 起動検証（`streamlit.testing.v1.AppTest` 等）でエラーがないことを確認。
