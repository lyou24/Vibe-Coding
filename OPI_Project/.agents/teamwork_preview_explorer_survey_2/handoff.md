# Explorer 2 調査引き継ぎレポート（DB・ロジック・ランク体系）

## 1. Observation（直接観測結果）

### (1) データベース構造とマイグレーション状況
- **DBファイル**: `data/opi_database.sqlite` および `data/opi_calibration.sqlite`
- **スキーマ確認コマンド実行結果**:
  - `python -c "import sqlite3; conn = sqlite3.connect('data/opi_database.sqlite'); cur = conn.cursor(); cur.execute('PRAGMA table_info(charts)'); print('charts cols:', [c[1] for c in cur.fetchall()]); cur.execute('PRAGMA table_info(score_logs)'); print('score_logs cols:', [c[1] for c in cur.fetchall()]); cur.execute('SELECT COUNT(*), COUNT(opi_s_x), COUNT(opi_ss_x), COUNT(opi_sss_x), COUNT(opi_sssp_x), COUNT(opi_abp_x) FROM charts'); print('charts stats:', cur.fetchone()); cur.execute('SELECT COUNT(*), COUNT(achieve_s), COUNT(achieve_ss), COUNT(achieve_sss), COUNT(achieve_sssp), COUNT(achieve_abp) FROM score_logs'); print('score_logs stats:', cur.fetchone())"`
  - 出力:
    ```text
    charts cols: ['chart_id', 'title', 'difficulty', 'level', 'chart_constant', 'is_active', 'opi_ss_x', 'opi_ss_y', 'opi_sss_x', 'opi_sss_y', 'opi_sssp_x', 'opi_sssp_y', 'opi_s_x', 'opi_s_y', 'opi_abp_x', 'opi_abp_y']
    score_logs cols: ['id', 'user_id', 'chart_id', 'score', 'is_all_break', 'is_full_bell', 'achieve_ss', 'achieve_sss', 'achieve_sssp', 'achieve_s', 'achieve_abp']
    charts stats: (543, 543, 543, 543, 543, 543)
    score_logs stats: (875, 875, 875, 875, 875, 875)
    ```
- **playersテーブル情報**:
  - `user_id`, `player_name`, `rating`, `total_opi`, `log_updated_at`, `system_updated_at`
  - レコード数: 2,505件。テスト用ID `10605`（rating: 19.95, total_opi: 1468.107）が存在。
  - レーティング最小: 17.75、最大: 21.208、平均: 19.04
  - 総合OPI最小: 1183.5、最大: 2427.4、平均: 1803.4
- **観測**: SQLiteの実データベース側は、新5段階（`S`, `SS`, `SSS`, `SSS+`, `AB+`）へのカラム変更・データ更新（`score >= 975000` で `achieve_s=1`、`score >= 1010000` で `achieve_abp=1`）が完全に完了している。

---

### (2) アプリケーションコード側における旧ランク（SSS+ABFB, AP）の残存箇所
`grep_search` によるコード精査結果:

1. **`app.py`**:
   - **Line 20**: `TARGET_RANK_OPTIONS = ["SS", "SSS", "SSS+", "SSS+ABFB", "AP"]`
   - **Line 81-82**:
     ```python
     score_log.achieve_abfb = (score_val >= 1007500 and score_log.is_all_break and score_log.is_full_bell)
     score_log.achieve_ap = score_val == 1010000
     ```
   - **Line 242**: `options=["未SS", "SS", "SSS", "SSS+", "SSS+ABFB", "AP"],`
   - **Line 282-289**: `current_rank_order = {"未SS": 0, "SS止まり": 1, "SSS止まり": 2, "SSS+止まり": 3, "ABFB止まり": 4, "AP": 5}`
   - **Line 328**: `（定数15+のSSS〜SSS+、14+帯のAP・ABFB安定）`

2. **`src/analyzer/opi_calculator.py`**:
   - **Line 27-28**:
     ```python
     if r in ("AP", "ALL PERFECT", "ALLPERFECT"):
         return "S"
     ```
     ※ 過去の機械的一括置換スクリプト（`fix_tests.py` 等）の副作用により、APが誤って "S" にマッピングされている。
   - **Line 60-65**:
     ```python
     elif norm_rank == "SSS+ABFB":
         x = getattr(chart, "opi_s_x", None)
         y = getattr(chart, "opi_s_y", None)
     elif norm_rank == "AP":
         x = getattr(chart, "opi_abp_x", None)
         y = getattr(chart, "opi_abp_y", None)
     ```
     ※ `norm_rank == "S"` および `norm_rank == "AB+"` の明示的分岐が存在しない。
   - **Line 224-233** (`build_user_achievements`):
     ```python
     ach_abfb = getattr(s, "achieve_s", False) or (score_val >= 1007500 and is_ab and is_fb)
     ach_ap = getattr(s, "achieve_abp", False) or (score_val >= 1010000)

     rank_status = [
         ("SS", ach_ss),
         ("SSS", ach_sss),
         ("SSS+", ach_sssp),
         ("SSS+ABFB", ach_abfb),
         ("AP", ach_ap),
     ]
     ```
     ※ 依然として旧5段階（`SSS+ABFB`, `AP`）のキーでベクトルを構築しており、`ach_s` (score >= 975,000) の判定が不正確。

3. **`src/recommender/recommender.py`**:
   - **Line 31-42** (`_determine_current_rank`):
     ```python
     if score >= 1010000 or getattr(score_log, "achieve_ap", False):
         return "AP", f"AP ({score:,})"
     if (score >= 1007500 and is_ab and is_fb) or getattr(score_log, "achieve_abfb", False):
         return "ABFB止まり", f"SSS+ABFB ({score:,})"
     if score >= 1007500 or getattr(score_log, "achieve_sssp", False):
         return "SSS+止まり", f"SSS+ ({score:,})"
     if score >= 1000000 or getattr(score_log, "achieve_sss", False):
         return "SSS止まり", f"SSS ({score:,})"
     if score >= 990000 or getattr(score_log, "achieve_ss", False):
         return "SS止まり", f"SS ({score:,})"
     return "未SS", f"未SS ({score:,})"
     ```
   - **Line 59-62** (`_is_target_achieved`):
     ```python
     elif norm_target_rank == "SSS+ABFB":
         return bool(getattr(score_log, "achieve_abfb", False) or (score >= 1007500 and is_ab and is_fb))
     elif norm_target_rank == "AP":
         return bool(getattr(score_log, "achieve_ap", False) or score >= 1010000)
     ```
     ※ `"S"` および `"AB+"` に対する既達成判定が存在しないため、`target_rank="S"` または `"AB+"` でリコメンドを実行した際に除外されないバグが発生している。
   - **Line 83-95** (`_matches_current_rank_filter`): 旧ランク名（ABFB止まり、AP等）のフィルタリングロジック。

4. **`seed.py`**:
   - **Line 159-162**:
     ```python
     chart_obj.opi_abfb_x = opi_params["opi_abfb_x"]
     chart_obj.opi_abfb_y = opi_params["opi_abfb_y"]
     chart_obj.opi_ap_x = opi_params["opi_ap_x"]
     chart_obj.opi_ap_y = opi_params["opi_ap_y"]
     ```
     ※ `opi_policy.py` は新キー（`opi_s_x`, `opi_abp_x`）を返しているため、実行すると `KeyError: 'opi_abfb_x'` でクラッシュする。
   - **Line 226-227**:
     ```python
     log_obj.achieve_abfb = (score_val >= 1007500 and is_ab and is_fb)
     log_obj.achieve_ap = score_val == 1010000
     ```

5. **`main.py`**:
   - **Line 80-81**: `score_log.achieve_abfb` / `achieve_ap` への代入。

---

### (3) リコメンド内部クエリ・フィルタロジックの現状
- **`app.py` Line 219-281**:
  - `target_ranks = st.multiselect(...)`: 未選択（空リスト）の場合、`for target_rank in target_ranks:` が0回となり結果が空になる。
  - `win_rate_min_percent = st.number_input(...)`, `win_rate_max_percent = st.number_input(...)`: 「勝率」という名称の数値入力2個になっている（範囲スライダーではない）。
  - `param_level = level_filters or None`: `recommender.py` 側で `if isinstance(level, (list, tuple, set)): if chart.level not in level: continue` と実装されており、複数選択に対応済み。
  - 選択肢 `LEVEL_OPTIONS = ["14", "14+", "15", "15+"]`: DB内には `"13+"`（定数13.7以上）が存在するが、選択肢から除外されている。

---

### (4) 難易度表・マイ難易度表の実装状況
- **`app.py` Line 352-402**:
  - 単一のセレクトボックス `diff_target_rank = st.selectbox(...)`
  - `groupby("OPI帯", sort=False)` を使用し、`st.columns(4)` でテキストカード形式で出力。グリッド表（表形式）になっていない。
  - ユーザーごとの達成状況（`score_logs`）の照合や、達成済みセルの色付け（「マイOPI難易度表」）は未実装。

---

### (5) 散布図用データ集計・動的グラフ化の状況
- **`src/visualizer/visualizer.py`**:
  - `load_player_data()`: `SELECT user_id, rating, total_opi FROM players WHERE rating IS NOT NULL AND total_opi IS NOT NULL`
  - `create_distribution_plot()`: `matplotlib` + `seaborn` で静止画 PNG（`data/opi_distribution.png`）を生成・保存。
- **依存パッケージ**:
  - `.venv` に `plotly` は未インストール（`ModuleNotFoundError: No module named 'plotly'`）。
  - `requirements.txt` に `plotly` の記載なし。

---

### (6) 既存テストスイートの実行結果
- コマンド: `.venv\Scripts\pytest tests/`
- 結果: `24 failed, 150 passed in 31.23s`
- 主な失敗要因:
  1. `seed.py` の `KeyError: 'opi_abfb_x'` により、シード実行を伴うテスト（約12件）が失敗。
  2. `test_m3_webui_integration.py`: `TARGET_RANK_OPTIONS` が旧ランクのまま、および `build_user_achievements` の戻り値キーが旧ランクのままで失敗。
  3. `test_m2_challenger_adversarial.py`: `recommender.py` の `_is_target_achieved` が新ランク（`S`, `AB+`）に対応していないため失敗。
  4. `test_challenger2_m3_harness.py`: 過去の機械置換（`fix_tests.py`）により、テスト側のアサートで `SS < SSS < SSS+ < S < AB+`（S: sss + 240）と難易度順が逆転してしまっている。
  5. `test_tier4_realworld_acceptance.py`: `00_Inbox/OPI要件定義書.md` のファイルパス不一致（Obsidian側パスとの差異）。

---

## 2. Logic Chain（推論・分析の論理連鎖）

1. **DB層の健全性**:
   - DB内のカラム情報および全件データカウントより、`charts` および `score_logs` テーブルには新5段階のカラムが実在し、全レコードに欠損なくマイグレーション値が格納されている。
   - したがって、DBスキーマ変更やデータ再マイグレーションは不要であり、アプリケーション層のクエリおよび参照コードの修正に専念できる。

2. **OPI計算ロジック・リコメンドロジックの不整合原因**:
   - `opi_policy.py`（基準アンカー）は新5段階（S: -240, SS: -120, SSS: 0, SSS+: +120, AB+: +240）に対応済み。
   - しかし、`opi_calculator.py` と `recommender.py` の内部メソッドにおいて旧ランク名（`SSS+ABFB`, `AP`）による条件分岐が残留しており、新ランク名（`S`, `AB+`）が渡された場合に例外またはフォールバック・未達成判定バイパスが発生している。
   - 特に `recommender._is_target_achieved` で `S` と `AB+` の判定が抜けているため、すでに達成済みの譜面が除外されずリコメンドに出てしまう重大なロジック破綻がある。

3. **リコメンドUIの未選択時挙動とスライダー対応**:
   - 要件 R2「未選択時は全対象を表示する」に対し、現行の `app.py` は `for target_rank in target_ranks:` でループしているため、目標ランクのチェックを全解除すると0件になる。
   - 対策: `effective_target_ranks = target_ranks if target_ranks else TARGET_RANK_OPTIONS` とすることで、空選択時に全ランクをクエリする設計が必要。
   - 「クリア割合」範囲スライダー: `st.number_input` 2個を `st.slider("クリア割合（%）", min_value=0.0, max_value=100.0, value=(30.0, 70.0), step=1.0)` に置き換え、引数 `win_rate_min / max`（0.0〜1.0）へ正規化して渡す。

4. **マイ難易度表の実現方針**:
   - 難易度表タブにおいて、`charts` を定数14.0以上から取得し、`calc.get_chart_rank_params(c, target_rank)` で適正OPIを算出。
   - 帯域（`opi // 100 * 100`）ごとに降順（例: 2200帯 → 2100帯 → ...）でソート。
   - 選択中のユーザーIDから `user_scores = {s.chart_id: s for s in session.query(ScoreLog).filter_by(user_id=uid).all()}` を引く。
   - 各譜面セルについて、`score_log` が存在し、かつ対象ランクの条件を満たしている場合（S: >=975,000, SS: >=990,000, SSS: >=1,000,000, SSS+: >=1,007,500, AB+: >=1,010,000）、セルをハイライト色（例: `#d4edda` や達成バッジ）で描画する。

5. **散布図の動的グラフ化と依存関係**:
   - `players` テーブルの `rating` と `total_opi` から全プレイヤーの散布図を作成可能。
   - 選択中のプレイヤー（`player.rating`, `recommendation_opi`）を特定し、別のプロット（色: 赤、シンボル: 星型、サイズ大）としてオーバーレイする。
   - Plotly（`plotly.graph_objects` または `plotly.express`）を使用することで、ホバー表示（プレイヤー名、レート、OPI）やズーム機能付きのインタラクティブな描画が Streamlit の `st.plotly_chart` で実現できる。
   - ただし、環境および `requirements.txt` に `plotly` が不足しているため、追加パッケージ導入が必要。

6. **テストコード側の矛盾と修正の必要性**:
   - `test_challenger2_m3_harness.py` の116行目（`assert params["SSS+"] < params["S"]`）は、過去の `fix_tests.py` が `SSS+ABFB` を単純に `S` に置換したことで生まれた「論理的バグ」。
   - Sはオンゲキにおいてスコア975,000（オフセット -240.0）であり、難易度序列は `S < SS < SSS < SSS+ < AB+` である。
   - テストコード側のアサート順序および期待値を正しいオフセット（S: sss-240, SS: sss-120, SSS: sss+0, SSS+: sss+120, AB+: sss+240）に整合させる必要がある。

---

## 3. Caveats（制約事項・前提条件）

1. **読み取り専用制約**:
   - 本調査は Explorer（読み取り専用）として実施したため、ソースコードおよびテストコードの修正は一切行っていない。
2. **Plotly パッケージの未インストール**:
   - 現行の `.venv` には `plotly` が入っていないため、実装担当者は `pip install plotly` および `requirements.txt` への追記を行う必要がある。
3. **テスト用ドキュメントパス**:
   - `test_tier4_realworld_acceptance.py` が参照する `00_Inbox/OPI要件定義書.md` は、ローカルの実行パス設定に依存している。

---

## 4. Conclusion（結論と改修タスク詳細）

### 【改修対象ファイルと具体的修正内容一覧】

| 対象ファイル | 修正箇所 | 修正内容の詳細 |
|:---|:---|:---|
| `requirements.txt` | 新規行 | `plotly` を追記し、仮想環境にインストール |
| `app.py` | Line 20-21 | `TARGET_RANK_OPTIONS = ["S", "SS", "SSS", "SSS+", "AB+"]`<br>`LEVEL_OPTIONS` に `"13+"` を追加 |
| `app.py` | Line 78-83 | `score_log.achieve_s = score_val >= 975000`<br>`score_log.achieve_abp = score_val >= 1010000`<br>（旧 `achieve_abfb`, `achieve_ap` を全廃） |
| `app.py` | Line 219-245 | 目標ランク・現在ランクの未選択時対応（`effective_target_ranks = target_ranks or TARGET_RANK_OPTIONS`）<br>現在ランクの選択肢を `["未S", "S止まり", "SS止まり", "SSS止まり", "SSS+止まり", "AB+"]` に更新 |
| `app.py` | Line 248-255 | `st.number_input` 2個を `st.slider("クリア割合（%）", 0.0, 100.0, (30.0, 70.0), 1.0)` に統合 |
| `app.py` | Line 282-290 | `current_rank_order` を新ランク序列に修正 |
| `app.py` | Line 301-314 | リコメンド一覧の列名「勝率」を「クリア割合」に変更 |
| `app.py` | Line 338-350 | Plotlyによる動的散布図表示（`st.plotly_chart`）へ移行し、選択ユーザーの位置を赤色ハイライト表示 |
| `app.py` | Line 352-402 | OPI難易度表を100帯ごとのグリッド表形式に改修（降順ソート徹底）。<br>新タブ「👑 マイOPI難易度表」を追加し、選択ユーザーの達成済み楽曲セルを色付きハイライト |
| `src/analyzer/opi_calculator.py` | Line 23-29 | `normalize_rank` で `"S"` を正常判定し、`"AB+"` / `"ABP"` / `"AP"` を `"AB+"` へ正規化 |
| `src/analyzer/opi_calculator.py` | Line 60-65 | `get_chart_rank_params` で `norm_rank == "S"`（`opi_s_x`）および `"AB+"`（`opi_abp_x`）を正しく参照 |
| `src/analyzer/opi_calculator.py` | Line 224-233 | `build_user_achievements` の5段階ベクトルを `[("S", ach_s), ("SS", ach_ss), ("SSS", ach_sss), ("SSS+", ach_sssp), ("AB+", ach_abp)]` に更新 |
| `src/recommender/recommender.py` | Line 18-43 | `_determine_current_rank` の新6段階判定（`AB+`, `SSS+止まり`, `SSS止まり`, `SS止まり`, `S止まり`, `未S`） |
| `src/recommender/recommender.py` | Line 44-64 | `_is_target_achieved` に `"S"` (>=975,000) および `"AB+"` (>=1,010,000) の判定を実装 |
| `src/recommender/recommender.py` | Line 66-97 | `_matches_current_rank_filter` の新カテゴリ名対応 |
| `src/visualizer/visualizer.py` | 新規メソッド | Plotlyを用いた動的散布図生成メソッド（全プレイヤー散布図 + 選択プレイヤーの強調プロット）を追加 |
| `seed.py` | Line 159-162, 226-227 | `opi_s_x`, `opi_abp_x`, `achieve_s`, `achieve_abp` に更新（KeyError解消） |
| `main.py` | Line 80-81 | `achieve_s`, `achieve_abp` に更新 |
| `tests/` | 該当テスト | `test_challenger2_m3_harness.py` 等で `S` と `SSS+` の難易度順序が逆転しているアサートを正しい仕様（S < SS < SSS < SSS+ < AB+）に修正 |

---

## 5. Verification Method（独立検証手順）

実装担当者およびレビュアーは、以下の手順で改修の妥当性を独立検証できます。

1. **シード投入スクリプトの単体検証**:
   ```powershell
   .venv\Scripts\python seed.py
   ```
   - 判定基準: `KeyError: 'opi_abfb_x'` が発生せず、`全シードデータのDB投入が正常に完了しました` が出力されること。

2. **OPI算出およびリコメンドエンジンの動作検証**:
   ```powershell
   .venv\Scripts\python -c "from src.recommender.recommender import OPIRecommender; rec = OPIRecommender('data/opi_database.sqlite'); print('S recs:', len(rec.get_recommendations(user_id=10605, target_rank='S'))); print('AB+ recs:', len(rec.get_recommendations(user_id=10605, target_rank='AB+')))"
   ```
   - 判定基準: エラーなく各目標ランクのリコメンドが取得できること。

3. **全体テストスイートの実行**:
   ```powershell
   .venv\Scripts\pytest tests/
   ```
   - 判定基準: 修正対象のユニットテスト・統合テストが100%パスすること。

4. **Webアプリケーションの動作検証**:
   ```powershell
   .venv\Scripts\streamlit run app.py
   ```
   - 判定基準:
     1. ブラウザでエラーなく起動すること。
     2. ユーザーID `10605` で検索し、総合OPIが正常表示されること。
     3. リコメンドタブで「クリア割合」の0〜100%スライダー、および各マルチセレクトが動作すること（未選択時に全対象が表示されること）。
     4. 統計タブで Plotly 散布図が表示され、ID 10605 の位置が赤色等でハイライトされること。
     5. 難易度表タブで100帯ごとのグリッドが降順表示され、「マイOPI難易度表」で達成済み楽曲が色付けされること。
