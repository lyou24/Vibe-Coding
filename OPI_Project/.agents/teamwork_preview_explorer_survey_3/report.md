# 配布環境・Git管理・要件定義書 調査報告書 (report.md)

- **調査日時**: 2026-09-13
- **調査担当**: teamwork_preview_explorer (調査3担当)
- **対象リポジトリ**: `C:\Users\lyoul\マイドライブ\lyou_Obsidian\90_Git\OPI_Project`
- **Gitリポジトリルート**: `C:\Users\lyoul\マイドライブ\lyou_Obsidian\90_Git`
- **対象要件定義書**: `C:\Users\lyoul\マイドライブ\lyou_Obsidian\00_Inbox\OPI要件定義書.md`

---

## 1. 配布・ポータビリティ（R2）の調査結果

### 1.1 `run_opi.bat` の実装および起動フロー精査
`run_opi.bat` は、第三者のWindows PC環境において環境構築の手間なくワンクリックでWebアプリケーションを起動できるように高度に設計されています。

- **文字コード・パス解決**:
  - `chcp 65001 >nul`: UTF-8コードページを設定し、日本語Windows環境における文字化けを防止。
  - `cd /d "%~dp0"`: バッチファイル自身のディレクトリへ移動。空白を含むパスやマルチバイト文字（`マイドライブ`等）にも引用符で完全対応。
- **自動仮想環境構築（Bootstrap機構）**:
  - `.venv\Scripts\activate.bat` の存在を検証。
  - **未セットアップ時**:
    1. `python --version` でホストOS上のPython存在を検証（見つからない場合はエラーメッセージを表示し `pause` して安全終了）。
    2. `python -m venv .venv` によりプロジェクトローカルに仮想環境を作成。
    3. `call .venv\Scripts\activate.bat` でアクティベート（`call` 構文によりバッチ処理の制御消失を確実に防止）。
    4. `python -m pip install --upgrade pip` でpipを最新化。
    5. `pip install -r requirements.txt` で必要パッケージを一括インストール（失敗時はエラーハンドリング）。
  - **セットアップ済み時**:
    - `call .venv\Scripts\activate.bat` のみを実行し、即座に起動フェーズへ移行。
- **Streamlit起動フロー**:
  - `streamlit run app.py %*` を実行。引数 `%*` を通す設計になっており、ブラウザが自動的に起動。
  - 末尾に `pause` が配置され、異常終了時やコンソール確認時にウィンドウが即座に閉じるのを防止。

### 1.2 `requirements.txt` および依存関係の精査
現在の `requirements.txt` の構成：
```text
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
- **現状**: 主要な全モジュール（WebUI、2PL IRT、スクレイピング、可視化、ORM）が必要十分に網羅されています。
- **検証**: 仮想環境内の `pip list` を確認した結果、Streamlit 1.63.0, SQLAlchemy 2.0.52, pandas 3.0.5, numpy 2.5.3, scipy 1.18.1 等が正常にインストールされており、全100件のpytestスイートが33.87秒で100%パスすることを確認しました。

### 1.3 パスの動的化・絶対パスハードコードの検証
- **検証結果**: ソースコード（`app.py`, `main.py`, `seed.py`, `src/**/*.py`）全体を網羅的に検索した結果、固定ドライブ文字（`C:\`, `G:\`）や特定のユーザー名（`lyoul`）のハードコードは一切存在しません。
- **パス解決の方式**: すべて `os.path.dirname(__file__)` や `os.path.abspath` を基準に相対解決されており、任意のディレクトリや他者PCへ配布・移動しても完全に動作します。

### 1.4 オフライン配布性とデータベース同梱
- `data/opi_database.sqlite` (417KB) および `data/seed_data.json` (614KB) がリポジトリ内に配置されており、初期コミットに含まれています。
- これにより、初回起動時からID `10605` を含むデータが利用可能であり、外部インターネット通信が遮断された第三者のPC環境でもオフラインで総合OPIの表示・リコメンド・難易度表が完全に稼働します。

### 1.5 ポータビリティに関する推奨改善案
- **DB未存在時の自動リカバリ**:
  万が一 `data/opi_database.sqlite` が未存在または破損していた場合に備え、`run_opi.bat` に以下のフォールバック処理を追加するとさらに堅牢になります：
  ```bat
  if not exist "data\opi_database.sqlite" (
      echo 初期データベースを構築しています [seed.py]...
      python seed.py
  )
  ```
- **Python ランチャー `py` のフォールバック**:
  PATHにPythonが登録されていないが `py` コマンドが有効なWindows環境を考慮し、`python` が失敗した場合に `py -3` を試行する分岐があるとより親切です。

---

## 2. GitリポジトリとGitHub連携（R4）の調査結果

### 2.1 リポジトリ構成と現在の状態
- **Gitリポジトリルート**: `C:/Users/lyoul/マイドライブ/lyou_Obsidian/90_Git`
  - プロジェクトルート（`OPI_Project`）の上位ディレクトリ `90_Git` が Git ルート（`.git`）となっています。
  - プロジェクトファイルはすべて `OPI_Project/` ディレクトリ配下に格納されています。
- **現在のブランチ**: `main`
- **コミット履歴**:
  - 最新コミット: `e69942e1bd8a15fbaeddeec77df83e34b8fc58f4`
  - コミットメッセージ: `最初のコミット`（Author: Ryo Maeda <lyou.luv.mga@gmail.com>）
  - ローカル `HEAD` と `origin/main` は一致。

### 2.2 リモートリポジトリおよびプッシュ可否の検証
- **リモート設定**:
  - `origin https://github.com/lyou24/Vibe-Coding.git (fetch)`
  - `origin https://github.com/lyou24/Vibe-Coding.git (push)`
- **通信・認証テスト**:
  - `git ls-remote origin`: 正常終了（code 0）。リモートの `refs/heads/main` のハッシュがローカルと一致していることを確認。
  - `git push --dry-run origin main`: 正常終了（code 0, `Everything up-to-date`）。GitHubへのプッシュ認証が有効であり、いつでもプッシュ可能な状態であることを実証。

### 2.3 検出された重大な課題（.gitignoreの欠如とpycacheの追跡）
- **課題1: `.gitignore` が存在しない**:
  リポジトリルート（`90_Git`）にもプロジェクトルート（`OPI_Project`）にも `.gitignore` が存在しません。
- **課題2: キャッシュファイル・バイナリの誤追跡**:
  最初のコミット `e69942e` において、`__pycache__/*.pyc`（50個以上のバイトコードファイル）や `tests/__pycache__/*.pyc` がGitの管理対象としてコミットされています。
  そのため、テスト実行やアプリ起動のたびに大量の `.pyc` ファイルが `git status` で `modified` と判定され、ワーキングツリーが恒常的に汚染されています。
- **未コミットの修正**:
  - `OPI_Project/PROJECT.md`: パス表記の相対化
  - `OPI_Project/tests/test_tier4_realworld_acceptance.py`: 要件定義書パス探索の相対化
  - `OPI_Project/.agents/ORIGINAL_REQUEST.md`: 新規プロンプト追記

### 2.4 推奨されるGit管理改善手順
1. `.gitignore` をリポジトリルートまたはプロジェクトルートに作成：
   ```gitignore
   __pycache__/
   *.py[cod]
   *$py.class
   .pytest_cache/
   .venv/
   venv/
   *.env
   .agents/*/
   !.agents/ORIGINAL_REQUEST.md
   ```
2. Git追跡から不要なキャッシュを削除（ファイル実体は残す）：
   ```powershell
   git rm -r --cached OPI_Project/__pycache__ OPI_Project/tests/__pycache__ OPI_Project/src/**/__pycache__
   ```
3. 変更点を適切なコミットメッセージでコミットし、`git push origin main` を実行する。

---

## 3. 要件定義書の履歴更新（R3）の調査結果

### 3.1 要件定義書の現状
- **対象ファイル**: `C:\Users\lyoul\マイドライブ\lyou_Obsidian\00_Inbox\OPI要件定義書.md`
- **状態**: 2026-09-12 作成の初期バージョン（全216行）。2PL IRT数理モデル、総合OPI最尤推定、リコメンドエンジン、分布図、難易度表の要件が記述されています。

### 3.2 履歴保存型アップデート（非破壊更新）の絶対ルール
- **削除厳禁**: 元の文章・段落・コード・表を絶対に削除してはならない。
- **訂正時のルール**:
  - 仕様が変更・訂正された箇所は、元の文章を取り消し線（`~~削除対象テキスト~~`）で囲み、その直後に新しい記述を追加する。
  - 例：
    ```markdown
    ~~- **抽出対象ユーザー**: 最終更新日が **2025年3月27日以降** のユーザー。~~
    - **抽出対象ユーザー**: 最終更新日が **2025年3月27日以降** のユーザー（**【2026-09-13 追記】** 実稼働・受入テスト用ID `10605` をデフォルトとしてシードデータに固定収録）。
    ```
- **追記時のルール**:
  - 新機能や実装結果、受入基準の達成報告は、既存セクションの末尾、または新たなセクション（例: `## 4. 実装・検証結果報告`）として追記する。
- **メタデータの更新**:
  - フロントマターの `updated_at: "2026-09-13"` の更新。

### 3.3 自動テストハーネス（AC3）による制約
- `tests/test_tier4_realworld_acceptance.py` の `test_ac3_doc_non_destructive_update` において、以下の2点が自動検証されています：
  1. 必須コアセクション（`# 1. 要件定義書（Requirements Definition）`、`F-01`〜`F-07`、`## 3.2 レーティング別 総合OPI目標値および分布統計`）がすべて存在すること。
  2. `git diff` で削除行（`-` で始まる行）が検出された場合、その行に取り消し線 `~~` または `updated_at` が含まれていなければ `AssertionError` でテストが失敗すること。
- したがって、要件定義書の更新時はこのテストハーネスをパスすることが客観的な受入条件となります。

### 3.4 今回追記すべき更新内容（M4向け提案）
1. **配布・ポータビリティの達成**:
   - `run_opi.bat` による自動仮想環境構築（.venv）、依存パッケージ一括導入、Streamlit自動起動（F-08）の実装完了を追記。
2. **5目標ランク統合最尤推定・多次元フィルターの実装**:
   - SS〜APの全5目標ランクを統合した最尤推定（MLE）アルゴリズムおよび、レベル・定数範囲・達成状況多次元フィルター（F-03, F-05）の実装完了を追記。
3. **ID 10605 での受入検証結果**:
   - テスト用ユーザーID `10605`（レーティング 19.98）において、推定総合OPI 2062.8 が算出され、勝率30%〜70%のリコメンド楽曲（Apollo, 怨撃 等）が正常に出力された実測結果の追記。
4. **オフライン稼働保証**:
   - 初期SQLiteデータベース（`opi_database.sqlite`）同梱による、外部通信不要のゼロコンフィグ実行保証の追記。

---

## 4. まとめと次マイルストーンへの提言

| 領域 | 状態 | 判定 | 次アクション |
|---|---|---|---|
| **R2: 配布・ポータビリティ** | `run_opi.bat` による完全自動セットアップ実装済み、パス非依存、DB同梱 | **READY** | `seed.py` 自動フォールバックの検討（任意追加） |
| **R4: Git管理・GitHub連携** | GitHubリモート通信・プッシュ認証OK、コミット履歴1件 | **ACTION NEEDED** | `.gitignore` 追加、`.pyc` の追跡解除、適切なコミット＆プッシュ |
| **R3: 要件定義書更新** | 現状216行、AC3テストハーネス存在 | **READY FOR M4** | セクション4を追記し非破壊更新、`test_ac3` でパス確認 |
