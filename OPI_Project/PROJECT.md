# Project: OPI Web Application Enhancement (Streamlit)

## Architecture
- **Web UI**: Streamlit (`app.py`) を中心としたフロントエンド。タブ構成:
  - Tab 1: 🎯 リコメンド楽曲
  - Tab 2: 📊 統計・分布図
  - Tab 3: 📜 OPI難易度表
  - Tab 4: ⭐ マイOPI難易度表（新規追加）
- **Core Analytics**:
  - `src/analyzer/opi_calculator.py`: OPI算出、正規化、プレイヤー統計、MLE推定
  - `src/analyzer/opi_policy.py`: 新5段階ランク（S, SS, SSS, SSS+, AB+）の基準値・アンカー定義
  - `src/recommender/recommender.py`: リコメンド抽出、フィルタリング、現在ランク判定、既達成判定
  - `src/visualizer/visualizer.py`: Plotlyを用いたインタラクティブ動的散布図生成（Rating vs OPI）
- **Database & Storage**:
  - SQLite (`data/opi_database.sqlite`)
  - `charts` テーブル: 新5段階ランク対応（`opi_s_x`, `opi_s_y`, `opi_ss_x`, `opi_sss_x`, `opi_sssp_x`, `opi_abp_x`）
  - `score_logs` テーブル: 新5段階ランク対応（`achieve_s`, `achieve_ss`, `achieve_sss`, `achieve_sssp`, `achieve_abp`）
  - `players` テーブル: 全2,505名（テストユーザーID: `10605`）

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | 依存パッケージのPlotly追加 | requirements.txt に plotly を追加し環境インストール | M1 | Survey (Explorer 3) |
| 2 | 新5段階ランク完全対応 (R1) | UI表示・内部クエリ・シード・集計における旧ランク（SSS+ABFB, AP）の全廃と新5段階（S, SS, SSS, SSS+, AB+）への完全置換 | M1 | ORIGINAL_REQUEST §R1 |
| 3 | リコメンドUI高度化 (R2) | レベル・ランクのマルチセレクト（未選択時全対象表示）、0〜100%「クリア割合」範囲スライダーの実装と文言改称 | M2 | ORIGINAL_REQUEST §R2 |
| 4 | OPI難易度表グリッド化 (R3) | 100 OPIごとの帯域グリッド表示および難易度降順ソートの徹底 | M3 | ORIGINAL_REQUEST §R3 |
| 5 | マイOPI難易度表の実装 (R3) | 選択ユーザーの達成済み楽曲セルを色付きハイライト（背景色・バッジ）する新ビュー/タブの実装 | M3 | ORIGINAL_REQUEST §R3 |
| 6 | レーティング vs OPI 動的散布図 (R4) | Plotlyによるインタラクティブ動的散布図の実装と、選択ユーザーの現在位置ハイライト（星型マーカー） | M4 | ORIGINAL_REQUEST §R4 |
| 7 | E2Eテスト自動検証ハーネス構築 | Streamlit AppTest を活用した受入基準（AC-1〜AC-6）の自動検証テストスイート構築 | E2E Track | ORIGINAL_REQUEST §Acceptance Criteria |
| 8 | トークン・リソース管理と引き継ぎ書作成 (R5) | フェーズごとのリソース確認と安全な完了報告・引き継ぎ書作成 | Final Milestone | ORIGINAL_REQUEST §R5 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Testing Track | AppTestを用いた新受入基準テストスイート（AC-1〜AC-6）の構築と TEST_READY.md 公開 | none | DONE |
| 1 | M1: 依存環境更新 & 新5段階ランク完全対応 (R1) | requirements.txt, app.py, opi_calculator.py, recommender.py, seed.py, main.py の旧ランク排除と新ランク対応 | none | DONE |
| 2 | M2: リコメンドUI高度化 (R2) | app.py のリコメンドUI（未選択時全対象マルチセレクト、0〜100%クリア割合スライダー） | M1 | IN_PROGRESS |
| 3 | M3: 難易度表グリッド化 & マイ難易度表 (R3) | 100 OPI帯降順グリッド化、マイOPI難易度表タブ実装と達成セルハイライト | M1 | PLANNED |
| 4 | M4: レーティング vs OPI 動的散布図 (R4) | visualizer.py の Plotly 散布図生成、app.py の動的表示とユーザー位置ハイライト | M1 | PLANNED |
| Final | Final Milestone: 100% E2E Pass & Coverage Hardening | E2Eテスト全件通過の確認、アドバーサリアル検証、引き継ぎ書作成 (R5) | E2E, M1, M2, M3, M4 | PLANNED |

## Interface Contracts
### `src/analyzer/opi_calculator.py`
- `normalize_rank(rank_str: str) -> str`:
  - `"S" -> "S"`, `"SS" -> "SS"`, `"SSS" -> "SSS"`, `"SSS+" -> "SSS+"`, `"AB+" -> "AB+"`
  - 入力エイリアス: `"ABP", "AP" -> "AB+"`
- `get_chart_rank_params(chart, rank_str: str) -> tuple[float, float]`:
  - `"S" -> (chart.opi_s_x, chart.opi_s_y)`
  - `"AB+" -> (chart.opi_abp_x, chart.opi_abp_y)`
- `build_user_achievements(score_logs) -> list[tuple[str, bool]]`:
  - 順序: `[("S", ach_s), ("SS", ach_ss), ("SSS", ach_sss), ("SSS+", ach_sssp), ("AB+", ach_abp)]`

### `src/recommender/recommender.py`
- `_determine_current_rank(score_log) -> tuple[str, str]`:
  - 判定順: `AB+` (>=1010000 or achieve_abp) → `SSS+止まり` (>=1007500 or achieve_sssp) → `SSS止まり` (>=1000000 or achieve_sss) → `SS止まり` (>=990000 or achieve_ss) → `S止まり` (>=975000 or achieve_s) → `未S`
- `_is_target_achieved(score_log, target_rank: str) -> bool`:
  - `"S"`: score >= 975000 or achieve_s
  - `"AB+"`: score >= 1010000 or achieve_abp

### `src/visualizer/visualizer.py`
- `create_distribution_figure(player_rating: Optional[float] = None, player_opi: Optional[float] = None, player_name: str = "あなた") -> plotly.graph_objects.Figure`:
  - 全プレイヤー散布図（rating >= 17.75, total_opi）
  - 選択ユーザー位置ハイライト（赤い星型マーカー）

## Code Layout
- `app.py`: Streamlit フロントエンド（UI表示、フィルタ、タブ、グリッド）
- `requirements.txt`: 依存パッケージ一覧
- `src/analyzer/opi_calculator.py`: OPI算出ロジック
- `src/analyzer/opi_policy.py`: ランク体系基準定義
- `src/recommender/recommender.py`: リコメンドロジック
- `src/visualizer/visualizer.py`: Plotly可視化
- `seed.py`: シードデータ投入スクリプト
- `main.py`: CLI実行エントリーポイント
- `tests/test_tier4_m4_new_acceptance.py`: 新受入基準E2Eテスト
