# ハンドオフレポート: OPIコードベース・アーキテクチャ調査

## 1. Observation（直接観察事実）

1. **テストスイートの通過状況**:
   - 実行コマンド: `.venv\Scripts\python.exe -m pytest tests -v`
   - 結果: `100 passed in 29.22s (exit code 0)`
   - 受入基準テスト（`test_ac1_web_app_syntax_and_imports`, `test_ac1_user_10605_opi_and_recommendation`, `test_ac2_run_opi_bat_bootstrap`, `test_ac3_doc_non_destructive_update`）はすべてPASS。

2. **ユーザー10605の総合OPI実測値と目標値**:
   - `data/opi_database.sqlite` 内の `Player` レコード（ID 10605）:
     `rating = 19.95`, `total_opi = 1426.6621599594012`
   - `seed_data.json` 内のテストユーザー10605のスコアログ:
     - 登録総件数: 744件、定数13.7以上の譜面マッチ数: 397件
     - 最高スコア: 1,009,217、AP達成数: 0曲
     - 定数15.0以上の譜面（38件）の達成状況: Apollo (252,263点), LAMIA (509,274点), girls.exe (904,159点) などSS未満が多数。
   - `src/analyzer/opi_calculator.py` で397件×5ランク（1,985エントリ）から算出した総合OPI: `1426.66`
   - `tests/fixtures/sample_user_10605.html`（代表14曲ハイレベルログ）から算出した総合OPI: `2021.07`
   - 受入基準 AC1 の指定範囲: `2000.0 〜 2100.0`

3. **レーティング帯域分類の丸め計算式**:
   - `src/visualizer/visualizer.py` 36行目:
     ```python
     center = round((rating + 0.25) * 2 - 0.5) / 2
     ```
   - 実証計算:
     - `rating = 18.24` -> `center = 18.0`
     - `rating = 18.25` -> `(18.25 + 0.25)*2 - 0.5 = 36.5` -> `round(36.5) = 36` (偶数丸め) -> `center = 18.0`（本来は 18.5 帯）
     - `rating = 19.25` -> `center = 19.0`（本来は 19.5 帯）
   - `tests/test_tier2_boundaries.py` 86〜88行目:
     テスト内では本番コードを呼ばず、`math.floor((rating - 17.75) / 0.5) * 0.5 + 18.0` を自前実装して検証していたため、本番コードのバグを検知できていない。

4. **目標ランク補完オフセットの定義不整合**:
   - `seed.py` 125〜134行目:
     `opi_ss_x: base_sss - 120.0`, `opi_sssp_x: base_sss + 120.0`, `opi_abfb_x: base_sss + 240.0`, `opi_ap_x: base_sss + 360.0`
   - `src/analyzer/opi_calculator.py` 87〜96行目:
     `SS: sss_x - 250.0`, `SSS+: sss_x + 150.0`, `SSS+ABFB: sss_x + 250.0`, `AP: sss_x + 370.0`

5. **WebUIでの分布統計量テーブルの未表示**:
   - `app.py` 200〜213行目（Tab 2: 統計・分布図）:
     `opi_distribution.png` の画像表示のみ。要件定義書 3.2 の数値テーブル（人数、中央値、平均、IQR）の表示UIが存在しない。

6. **リコメンドUIのフィルター選択肢**:
   - `app.py` 161〜166行目:
     `options=["なし", "SS", "SSS", "SSS+", "SSS+ABFB", "AP"]` となっており、未SS/未達成を直接指定する選択肢がない。

---

## 2. Logic Chain（推論チェーン）

1. [Observation 1, 2 より]
   - 全100件のテストがパスしているが、テスト内のID 10605受入検証（`test_ac1_user_10605_opi_and_recommendation`）は `sample_user_10605.html`（代表14曲ハイレベルログ）を用いており、総合OPI `2021.07` でパスしている。
   - しかし、実運用DB（`opi_database.sqlite`）に初期投入されている実スコアログ（397件）から算出された総合OPIは `1426.66` であり、画面上でユーザー10605を開くと `1426.7` と表示される。
   - これは、全曲一括のIRT最尤推定モデルが、未詰め・低スコアの大量の「未達成」を実力不足として捉えるためである。レーティング19.950のプレイヤーに対して1426.7（レート17.5〜18.0相当）と表示されるため、仕様と実データの間に認識の乖離が生じている。

2. [Observation 3 より]
   - `visualizer.py` の `get_band_label` における `round()` 偶数丸め処理は、数学的・統計的な帯域境界 `[center - 0.25, center + 0.25)` の左閉右開ルールを満たしておらず、偶数丸めの境界点（18.25, 19.25, 20.25等）で1つ下の帯域に誤分類される。
   - テストスイート側が本番実装をインポートせず独自関数をテストしていたため、本番コードのバグが見逃されていた。

3. [Observation 4 より]
   - `seed.py` の初期登録ロジックと `opi_calculator.py` の動的補完ロジックでオフセット値が異なるため、DBカラムが空の譜面を計算した場合とシード済み譜面を計算した場合で、同じ譜面定数であっても適正OPIが最大130pt乖離するリスクがある。

4. [Observation 5, 6 より]
   - 要件定義書 3.2 の統計テーブル表示およびリコメンドの未SS絞り込みは、WebUI（`app.py`）での実装が不足している。

---

## 3. Caveats（留保事項・前提条件）

- **外部API・実サイト巡回**: 本調査環境では外部通信は遮断されていないが、OngekiScoreLogへの過剰な負荷を避けるため、全曲スクレイピングの再実行は行わず、既存のシードデータおよびローカルテストスイートの実行結果に基づいて検証した。
- **総合OPI算出ロジックの変更方針**: 総合OPIを「全曲ログ最尤推定」のまま維持するか、「上位ベスト枠（例: 上位30〜50曲）」に基づく方式に改修するかは、要件定義書のモデル定義（2.2 ③「対象全譜面」）との整合性に関わるため、実装前に仕様方針の合意が必要である。

---

## 4. Conclusion（結論）

OPIプロジェクトの基本機能（2PL IRT、リコメンド、差分クローラー、WebUI、Windows配布バッチ）は高い完成度で構築されており、全100テストが合格している。
しかし、本番品質および要件完全準拠を達成するために、以下の修正・改善が必要である：

1. **P1 (バグ修正)**: `src/visualizer/visualizer.py` の偶数丸めバグを `math.floor` 方式に修正し、テストを本番コード検証型に改修する。
2. **P1 (機能補完)**: `src/visualizer/visualizer.py` および `app.py` に要件3.2の「レート帯別統計テーブル」表示を追加する。
3. **P2 (不整合解消)**: `seed.py` と `opi_calculator.py` のランク別OPIオフセット定義を一元化する。
4. **P2 (UI改善)**: `app.py` のリコメンドフィルターに「未達成/未SS」選択肢を追加する。
5. **P2 (ドキュメント整合)**: `PROJECT.md` のファイルパス記述（`models.py`, `visualizer.py`）を実態に合わせる。
6. **P3 (仕様追記)**: `OPI要件定義書.md` に全曲ログ推定（1426.7）とベスト枠推定（2021.1）の差異に関する仕様説明を非破壊（追記形式）で追記する。

---

## 5. Verification Method（独立検証方法）

以下の手順で調査結果を独立検証できる：

1. **テストスイートの全件実行**:
   ```powershell
   .venv\Scripts\python.exe -m pytest tests -v
   ```
   -> 全100テストがPASSすることを確認。

2. **ユーザー10605のDB内OPI実測値確認**:
   ```powershell
   powershell -NoProfile -Command "@'
   import sqlite3
   con = sqlite3.connect('data/opi_database.sqlite')
   print(con.execute('SELECT user_id, player_name, rating, total_opi FROM players WHERE user_id=10605').fetchall())
   '@ | .venv\Scripts\python.exe"
   ```
   -> 出力が `1426.66` であることを確認（要件目標値 2000〜2100 との乖離を確認）。

3. **レーティング帯域分類バグの再現**:
   ```powershell
   powershell -NoProfile -Command "@'
   def get_band_label_current(rating):
       return f'{round((rating + 0.25) * 2 - 0.5) / 2:.1f}'

   print('18.24 ->', get_band_label_current(18.24)) # 18.0
   print('18.25 ->', get_band_label_current(18.25)) # 18.0 (バグ: 本来は18.5)
   print('19.25 ->', get_band_label_current(19.25)) # 19.0 (バグ: 本来は19.5)
   '@ | .venv\Scripts\python.exe"
   ```
   -> 境界値 18.25 が 18.0 に誤分類されることを確認。

4. **WebUIの起動と目視確認**:
   ```powershell
   .venv\Scripts\streamlit run app.py
   ```
   -> Tab 1 の current_rank 選択肢、Tab 2 の統計表欠落、Tab 3 の難易度表表示を確認。

