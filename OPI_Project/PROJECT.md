# Project: OPI (Ongeki Power Indicator) Web Application

## Architecture
- **Web UI & Presentation**: Streamlit (`app.py`)
- **Core Algorithms**:
  - Item Response Theory (2PL IRT) MLE Estimation (`src/analyzer/opi_calculator.py`)
  - Recommendation Engine with Multi-dimensional Filters (`src/recommender/recommender.py`)
  - Visualization Engine with Interactive Matplotlib / Streamlit (`src/visualizer/plotter.py`)
- **Data & Crawling**:
  - SQLite Database (`data/opi_database.sqlite`, `src/models/schema.py`)
  - Web Scraping & Diff Crawling (`src/crawler/ongeki_crawler.py`)
  - Data Seeding & Offline Fixtures (`seed.py`, `data/seed_data.json`)
- **Distribution & Portability**:
  - Windows Batch Launcher with Auto-Bootstrap (`run_opi.bat`)

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F-01 | データベース・ORMモデル | charts, players, score_logs のテーブル定義および2PLパラメータ保持 | M2 | 要件定義書 2.1 |
| F-02 | データ収集・差分クローラー | OngekiScoreLogからのプロフィール・スコア取得と差分更新・強制更新 | M2 | 要件定義書 1.2 |
| F-03 | OPI算出アルゴリズム | 2PL IRTモデルに基づく全5目標ランク（SS〜AP）統合最尤推定（L2正則化） | M3 | 要件定義書 2.2 |
| F-04 | 総合OPI算出・初期化 | プレイヤーの全スコアログから総合OPIを算出しDB保持（初期表示保証） | M2 | 要件定義書 2.2 |
| F-05 | リコメンドエンジン | 総合OPIに対する勝率30%〜70%の未達成楽曲抽出と多次元フィルター | M3 | 要件定義書 2.3 |
| F-06 | 分布図・可視化 | レーティング帯別OPI分布・回帰直線およびプレイヤープロット | M3 | 要件定義書 3.2 |
| F-07 | 難易度表表示 | 定数帯・目標ランク別の適正OPI難易度一覧表示 | M3 | 要件定義書 3.4 |
| F-08 | 配布ブートストラップ | Windows環境で未セットアップ時にvenv生成とpip installを自動実行 | M1 | 要件定義書 AC2 |
| F-09 | ID 10605 統合テスト | テスト用ID 10605 でのOPI算出（2000〜2100）およびリコメンド出力確認 | M4 | 要件定義書 AC1 |
| F-10 | ドキュメント履歴更新 | OPI要件定義書.md の非破壊的更新（追記・取り消し線のみ） | M4 | 要件定義書 AC3 |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | 配布ブートストラップ & パス動的化 | `run_opi.bat` の自動venv作成・pipインストール実装、ハードコードパス解消 | none | DONE |
| M2 | データ層・クローラー・初期化修復 | `seed.py` での初期OPI算出、`ongeki_crawler.py` の差分閉塞解消、`(title, diff)` 厳密照合 | M1 | DONE |
| M3 | WebUI・OPI/リコメンド完全統合 | `app.py` の5ランク統合OPI算出、多次元フィルターUI、境界値分類修正、NaN/infガード | M2 | DONE |
| M4 | 総合E2E検証 & ドキュメント非破壊更新 | 全テスト100%パス、ID 10605 実動作検証、`OPI要件定義書.md` 履歴更新、Gitプッシュ | M3 | DONE |
| M5 | フォレンジック監査 & 最終判定 | `teamwork_preview_auditor` による完全性検証、Sentinel完了報告 | M4 | DONE |

---

## Interface Contracts
### `src/crawler/ongeki_crawler.py` ↔ `app.py`
- `fetch_user_profile(user_id: int, last_crawled_at: Optional[datetime] = None, force: bool = False) -> Optional[Dict]`
- `fetch_user_scores(user_id: int) -> List[Dict]`

### `src/analyzer/opi_calculator.py` ↔ `app.py`
- `build_user_achievements(charts: List[Chart], scores: List[ScoreLog]) -> List[Dict[str, Any]]`
  - Returns `[{'x': float, 'y': float, 'achieved': int}, ...]` across all 5 target ranks.
- `estimate_user_opi(achievements: List[Dict[str, Any]], initial_theta: float = 1500.0) -> float`

### `src/recommender/recommender.py` ↔ `app.py`
- `get_recommendations(user_id: int, target_rank: str = "SSS", level: Optional[str] = None, chart_constant_min: Optional[float] = None, chart_constant_max: Optional[float] = None, current_rank: Optional[str] = None, limit: int = 15) -> List[Dict[str, Any]]`

---

## Code Layout
- `90_Git/OPI_Project/` (または `OPI_Project/`)
  - `app.py`: Streamlit Webアプリケーション
  - `main.py`: CLI実行スクリプト
  - `seed.py`: 初期データ投入スクリプト
  - `run_opi.bat`: Windows用ブートストラップ起動バッチ
  - `requirements.txt`: 依存ライブラリ一覧
  - `data/`: SQLiteデータベース、シードJSON
  - `src/`:
    - `models/schema.py`: SQLAlchemy ORM
    - `analyzer/opi_calculator.py`: 2PL IRT MLE 算出
    - `recommender/recommender.py`: リコメンドロジック
    - `visualizer/plotter.py`: グラフ描画
    - `crawler/ongeki_crawler.py`: クローラー
  - `tests/`: pytest テストスイート（Tiers 1〜4）


