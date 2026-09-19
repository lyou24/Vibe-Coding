# Handoff Report — 実行環境・テスト・受入検証 調査 (Explorer 3)

## 1. Observation (直接観察事実)

### 1.1 実行環境・依存関係
- **Python環境**:
  - バージョン: `Python 3.14.7`
  - 仮想環境パス: `C:\Users\lyoul\AI_Project\90_Git\OPI_Project\.venv\Scripts\python.exe`
- **依存定義ファイル**:
  - `requirements.txt` (全9行):
    ```
    aiohttp
    beautifulsoup4
    pandas
    numpy
    scipy
    matplotlib
    seaborn
    SQLAlchemy
    streamlit
    ```
  - `Pipfile`, `pyproject.toml`: 存在しない（依存管理は `requirements.txt` 単一）。
- **主要パッケージのインストール状況（pip list実測値）**:
  - `streamlit`: `1.63.0`
  - `pandas`: `3.0.5`
  - `numpy`: `2.5.3`
  - `scipy`: `1.18.1`
  - `matplotlib`: `3.11.2`
  - `seaborn`: `0.13.2`
  - `SQLAlchemy`: `2.0.52`
  - `pytest`: `9.1.1`
  - `pytest-asyncio`: `1.4.0`
  - `altair`: `6.2.2`
  - `sqlite3`: `3.50.4` (Python 3.14.7 組み込み)
- **重大な欠落**:
  - **`plotly` は `requirements.txt` に未記載、かつ `.venv` 環境にもインストールされていない（pip list に非存在）**。
  - 最新要求 R4「横軸をレーティング生値、縦軸を総合OPIとした散布図をStreamlit上に動的グラフ（Plotly等）として実装」を満たすには、`requirements.txt` への `plotly` 追加および `pip install plotly` が不可欠。
- **アプリケーション起動構成**:
  - `run_opi.bat` (51行):
    - `chcp 65001 >nul`（UTF-8）
    - `cd /d "%~dp0"`（相対ディレクトリ移動）
    - `.venv` 未存在時: `python -m venv .venv` → `call .venv\Scripts\activate.bat` → `python -m pip install --upgrade pip` → `pip install -r requirements.txt`
    - 起動コマンド: `streamlit run app.py %*` (ポートデフォルト: 8501)
  - `.streamlit/config.toml`: 存在しない（デフォルト設定で起動）。

### 1.2 既存テストの状況
- **テストディレクトリ構造**:
  - `tests/`: 30ファイル、計174テスト（`pytest --collect-only` で確認）。
  - 主要テストスイート:
    - `tests/test_tier1_features.py`: 単体機能テスト
    - `tests/test_tier2_boundaries.py` / `test_tier2_boundary_corner.py`: 境界値・極値テスト
    - `tests/test_tier3_integration.py`: 複数機能結合テスト
    - `tests/test_tier4_realworld_acceptance.py`: 実世界受入基準テスト (AC1〜AC3)
    - `tests/test_m3_webui_integration.py`: WebUIおよびアルゴリズム結合テスト
- **pytest実行結果実測値**:
  - 実行コマンド: `.\.venv\Scripts\python.exe -m pytest --tb=no -q`
  - 結果: **`23 failed, 151 passed in 33.48s`**
- **テスト失敗の主原因分析**:
  1. `test_m3_webui_integration.py` (2件失敗):
     - `test_app_ast_m3_features_presence`: `TARGET_RANK_OPTIONS = ["SS", "SSS", "SSS+", "S", "AB+"]` を期待しているが、`app.py:20` は依然として旧ランク `["SS", "SSS", "SSS+", "SSS+ABFB", "AP"]` のまま。
     - `test_five_ranks_mle_estimation_progression`: `OPICalculator.build_user_achievements` が返すランク集合が旧ランク（`{'AP', 'SS', 'SSS', 'SSS+', 'SSS+ABFB'}`）のままであり、新ランク（`{'AB+', 'S', 'SS', 'SSS', 'SSS+'}`）と不一致。
  2. `test_tier4_realworld_acceptance.py::test_ac3_doc_non_destructive_update` (1件失敗):
     - `00_Inbox/OPI要件定義書.md` を探す相対パス（`..\..\..\00_Inbox`）がプロジェクト移動（`AI_Project`）に伴い不整合となり、ファイル不存在エラー。実体は `C:\Users\lyoul\AI_Project\lyou_Obsidian\00_Inbox\OPI要件定義書.md` に存在。
  3. その他シード・整合性テスト（20件失敗）:
     - `migrate_target_ranks.py` によるDBカラム変更（`opi_s_x`, `opi_abp_x`等）が行われた後、旧テスト側のアサーション（旧カラム名や旧フラグ参照）が追いついていないことによるもの。

### 1.3 受入基準の自動検証・テスト自動化アプローチ
- **`streamlit.testing.v1.AppTest` の実証実験**:
  - コマンド: `from streamlit.testing.v1 import AppTest; at = AppTest.from_file('app.py', default_timeout=10); at.run()`
  - 結果: **例外ゼロ（`len(at.exception) == 0`）で正常終了**。実行所要時間 約2秒。
  - 取得可能ウィジェット実測:
    - Sliders: `['譜面定数範囲']`
    - Multiselects: `['目標ランク（複数選択）', 'レベル絞り込み（複数選択）', '現在の達成ランク（複数選択）']`
    - Selectboxes: `['表示順', '目標ランク選択']`
  - 判定: Streamlit UIに対する自動検証フレームワークとして `AppTest` が完全に機能する。
- **Playwrightの状況**:
  - `import playwright` → `ModuleNotFoundError: No module named 'playwright'`
  - Playwright は未インストール。外部ブラウザ依存やダウンロードが不要な `AppTest` の方がCI/CD親和性・実行速度（2秒 vs 20秒以上）・保守性の観点で圧倒的に有利。

### 1.4 テスト用データ・ユーザーID
- **データベース実測 (`data/opi_database.sqlite`)**:
  - `players` テーブル: 全 2,505 レコード
  - `score_logs` テーブル: 全 37,208 レコード
  - スキーマ:
    - `charts`: `opi_ss_x, opi_ss_y, opi_sss_x, opi_sss_y, opi_sssp_x, opi_sssp_y, opi_s_x, opi_s_y, opi_abp_x, opi_abp_y` (新5段階ランク対応カラムに移行済み)
    - `score_logs`: `achieve_ss, achieve_sss, achieve_sssp, achieve_s, achieve_abp` (新5段階対応カラムに移行済み)
- **テスト用ID `10605` の状況**:
  - プレイヤー名: `ＮＥＧＩＮＥ`
  - レーティング: `19.950`
  - スコアログ件数: `397` 件（スコア範囲: 252,263 〜 1,009,217）
  - オフラインフィクスチャ: `tests/fixtures/sample_user_10605.html`（ID 10605のHTMLスナップショット）が存在し、`test_tier4_realworld_acceptance.py` で利用可能。

---

## 2. Logic Chain (論理の連鎖)

1. **実行環境と新機能依存（R4）の因果関係**:
   - 観察1.1より、環境には `streamlit 1.63.0` が導入されているが、`plotly` は未インストールであり、`requirements.txt` にも未記載。
   - 新要件 R4 では Plotly による動的散布図の描画が要求されている。
   - `run_opi.bat` は `pip install -r requirements.txt` を自動実行するため、`requirements.txt` に `plotly` を追加しない限り、第三者PCで `run_opi.bat` を起動した際に即座に `ModuleNotFoundError: No module named 'plotly'` でクラッシュする。
   - ⇒ **論理的帰結**: 実装フェーズにおいて `requirements.txt` への `plotly` 追加および `.venv` への `pip install plotly` が前提必須タスクとなる。

2. **受入基準の自動検証手法の選定**:
   - 観察1.3より、`streamlit.testing.v1.AppTest` は追加パッケージなしで即時利用可能であり、`at = AppTest.from_file('app.py'); at.run()` が例外ゼロで実行できることを実証した。
   - `at.slider`, `at.multiselect` などのウィジェット値の取得・変更・リランがPythonコードから数行で実行可能。
   - Playwright などの外部ブラウザ自動化はブラウザバイナリのダウンロードや環境差異のリスクが高く不要。
   - ⇒ **論理的帰結**: R1〜R4の客観的・機械的受入検証には `streamlit.testing.v1.AppTest` を主軸とした pytest ハーネスを設計・実装するのが最も確実かつ高信頼である。

3. **既存テスト失敗の構造的要因と新受入基準テストの独立性**:
   - 観察1.2より、174件中23件のテストが失敗しているが、その大半は「DBスキーマが新5段階ランクに移行済みであるのに対し、`app.py` や `opi_calculator.py`、および旧テストコードの一部が旧ランク（`SSS+ABFB`, `AP`）を参照している」という単一の構造的不整合に起因している。
   - 既存の `test_tier4_realworld_acceptance.py` は昨日の要求（M1〜M4の旧受入基準: run_opi.batの静的チェック、要件定義書非破壊更新等）を対象としている。
   - ⇒ **論理的帰結**: 今回の最新要求（2026-09-14T13:31:31Z）の受入基準（R1〜R4）を漏れなく検証するために、独立した新受入基準テストファイル（`tests/test_tier4_m4_new_acceptance.py`）を新設し、機械的合格判定を行うべきである。

---

## 3. Caveats (留意事項・仮定・未調査領域)

1. **既存テストの修正スコープ**:
   - 既存の23件のテスト失敗のうち、`test_m3_webui_integration.py` は新5段階ランクの適用により直ちにパスする見込みであるが、シードデータ検証（`test_challenger1_m2_verification.py` 等）は過去の固定値アサーションを含んでいる可能性がある。Workerフェーズでのテスト修正時は、最新要件との整合性を確認すること。
2. **`OPI要件定義書.md` の参照パス**:
   - `test_tier4_realworld_acceptance.py::test_ac3_doc_non_destructive_update` において、`00_Inbox/OPI要件定義書.md` を探すパスがハードコードされている。実際のパス `C:\Users\lyoul\AI_Project\lyou_Obsidian\00_Inbox\OPI要件定義書.md` も探索候補に含めるようフォールバックパスを追加する必要がある。
3. **Streamlit バージョン非推奨警告**:
   - `AppTest` 実行時に `Please replace use_container_width with width`（2025-12-31以降非推奨）の警告が出力された。現時点では動作に支障ないが、WorkerがUIコードを修正する際に `width='stretch'` への置き換えを推奨する。

---

## 4. Conclusion (結論・提言)

1. **実行環境・依存関係**:
   - 実行基盤は Python 3.14.7 + Streamlit 1.63.0。
   - **直ちに行うべき処置**: `requirements.txt` に `plotly` を追加し、`.venv` に `plotly` をインストールする。
2. **受入基準（R1〜R4）の自動検証ハーネス設計**:
   - 新規テストファイル `tests/test_tier4_m4_new_acceptance.py` を作成し、`streamlit.testing.v1.AppTest` を活用して以下の6テストケースを実装することを提言する：
     - **AC-1 (アプリ起動 & 例外ゼロ)**: `AppTest.from_file('app.py').run()` で `len(at.exception) == 0` を検証。
     - **AC-2 (R1: 新5段階ランク対応)**: UIおよび `OPICalculator.build_user_achievements` のランク選択肢が `["S", "SS", "SSS", "SSS+", "AB+"]` のみであり、旧ランク表記が完全に排除されていることを検証。
     - **AC-3 (R2: リコメンドUI高度化)**:
       - `at.slider` に「クリア割合」（0〜100%スライダー）が存在し、旧文言「勝率」が存在しないこと。
       - レベル・目標ランク・現在ランクが `at.multiselect` で動作し、空選択時に全対象がヒットすること。
       - スライダー範囲変更時に結果テーブルが正しくフィルタリングされること。
     - **AC-4 (R3: 難易度表グリッド化 & マイOPI難易度表)**:
       - 100 OPI 単位の帯域でグルーピングされ、適正OPIの降順でソートされていること。
       - 「マイOPI難易度表」タブ/ビューが存在し、達成済み楽曲セルに色付けスタイルが付与され未達成と区別できること。
     - **AC-5 (R4: 動的散布図)**:
       - 散布図が Plotly Figure（`go.Figure`）として生成され、横軸が生レーティング、縦軸が総合OPIであること。
       - 選択したユーザー（ID: 10605 等）の位置が目立つマーカー/トレースでハイライトされていること。
     - **AC-6 (ID 10605 E2E動作)**:
       - ユーザーID `10605`（397スコア）での総合OPI算出（2000〜2100近傍）およびリコメンド出力がエラーなく動作すること。
3. **テスト用データ**:
   - `data/opi_database.sqlite` に 2,505名のプレイヤーおよび ID 10605（397スコア）が既に存在し、追加のモック生成不要で即時テスト可能。

---

## 5. Verification Method (独立検証方法)

後続エージェント（Reviewer, Challenger, Auditor）が本調査結果を独立検証するための手順：

1. **Python環境・依存関係の検証**:
   ```powershell
   & ".\.venv\Scripts\python.exe" --version
   & ".\.venv\Scripts\python.exe" -m pip list | Select-String -Pattern "streamlit|plotly|pandas|pytest"
   ```
   - 検証結果期待値: `streamlit 1.63.0` が表示され、`plotly` は非表示（未インストール）であること。

2. **Streamlit AppTest の稼働検証**:
   ```powershell
   & ".\.venv\Scripts\python.exe" -c "from streamlit.testing.v1 import AppTest; at = AppTest.from_file('app.py', default_timeout=10); at.run(); print('Exceptions:', len(at.exception)); print('Sliders:', [s.label for s in at.slider])"
   ```
   - 検証結果期待値: `Exceptions: 0` と出力されること。

3. **既存pytestテストスイートの実行**:
   ```powershell
   & ".\.venv\Scripts\python.exe" -m pytest tests/test_m3_webui_integration.py -v
   ```
   - 検証結果期待値: `TARGET_RANK_OPTIONS` および `build_user_achievements` の新5段階ランク不一致により2件 FAILED となること（本レポートの指摘と完全一致）。

4. **テスト用データ ID 10605 の存在検証**:
   ```powershell
   & ".\.venv\Scripts\python.exe" -c "import sqlite3; conn = sqlite3.connect('data/opi_database.sqlite'); cur = conn.cursor(); cur.execute('SELECT user_id, player_name, rating FROM players WHERE user_id = 10605'); print('Player:', cur.fetchone()); cur.execute('SELECT count(*) FROM score_logs WHERE user_id = 10605'); print('Scores:', cur.fetchone()[0])"
   ```
   - 検証結果期待値: `Player: (10605, 'ＮＥＧＩＮＥ', 19.95)`, `Scores: 397` が出力されること。
