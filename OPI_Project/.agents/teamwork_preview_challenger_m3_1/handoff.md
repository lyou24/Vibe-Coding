# 敵対的検証ハンドオフレポート: 境界値・帯域分類ストレステスト

- **エージェント**: teamwork_preview_challenger_m3_1 (EMPIRICAL CHALLENGER)
- **ロール**: critic, specialist
- **作業ディレクトリ**: `C:\Users\lyoul\マイドライブ\lyou_Obsidian\90_Git\OPI_Project\.agents\teamwork_preview_challenger_m3_1`
- **判定結果**: **REQUEST_CHANGES**

---

## 1. Observation（直接観察事実）

### 1.1 ソースコード実装
対象ファイル: `src/visualizer/visualizer.py` (21〜37行目)
```python
    @staticmethod
    def get_band_label(rating: float) -> str | None:
        """
        要件定義書 1.3 F-06 / 3.2:
        レーティング18.0以上のユーザーを0.5刻みの基準値（18.0, 18.5, 19.0, ...）とし、
        各基準値 ±0.25 の帯域（[center - 0.25, center + 0.25)）に厳密に分類する。
        例:
          18.0帯: 17.75 <= rating < 18.25
          18.5帯: 18.25 <= rating < 18.75
          19.0帯: 18.75 <= rating < 19.25
        17.75未満は None を返す。
        """
        if rating is None or rating < 17.75:
            return None
        # 浮動小数点丸め誤差（例: 18.25 - 17.75 = 0.49999999999999956）対策として 1e-9 を加算
        band_idx = math.floor((rating - 17.75 + 1e-9) / 0.5)
        center = 18.0 + band_idx * 0.5
        return f"{center:.1f}"
```

### 1.2 敵対的ストレステスト実行結果
実行コマンド:
```powershell
.venv\Scripts\python.exe -c "
import math, numpy as np; from src.visualizer.visualizer import OPIVisualizer;
test_suite = [
    ('17.7499', 17.7499, None),
    ('17.750', 17.750, '18.0'),
    ('18.2499', 18.2499, '18.0'),
    ('18.250', 18.250, '18.5'),
    ('18.7499', 18.7499, '18.5'),
    ('18.750', 18.750, '19.0'),
    ('20.250', 20.250, '20.5'),
    ('21.250', 21.250, '21.5'),
    ('0.0', 0.0, None),
    ('99.9', 99.9, '100.0'),
    ('None', None, None),
    ('float_nan', float('nan'), None),
    ('np_nan', np.nan, None),
    ('float_inf', float('inf'), None),
    ('float_neg_inf', float('-inf'), None),
    ('18.25 - 1e-10', 18.25 - 1e-10, '18.0'),
    ('18.25 - 1e-8', 18.25 - 1e-8, '18.0'),
    ('18.249 (DECIMAL 5,3)', 18.249, '18.0'),
]
for name, val, expected in test_suite:
    try:
        actual = OPIVisualizer.get_band_label(val)
        status = 'PASS' if actual == expected else 'FAIL'
        print(f'{name:25} | {str(actual):30} | {status}')
    except Exception as e:
        print(f'{name:25} | {type(e).__name__}: {e} | CRASH')
"
```

出力結果（実測値）:
```text
| Case                      | Input                  | Expected   | Actual                         | Result   |
|---------------------------|------------------------|------------|--------------------------------|----------|
| 17.7499                   | 17.7499                | None       | None                           | PASS     |
| 17.750                    | 17.75                  | 18.0       | 18.0                           | PASS     |
| 18.2499                   | 18.2499                | 18.0       | 18.0                           | PASS     |
| 18.250                    | 18.25                  | 18.5       | 18.5                           | PASS     |
| 18.7499                   | 18.7499                | 18.5       | 18.5                           | PASS     |
| 18.750                    | 18.75                  | 19.0       | 19.0                           | PASS     |
| 20.250                    | 20.25                  | 20.5       | 20.5                           | PASS     |
| 21.250                    | 21.25                  | 21.5       | 21.5                           | PASS     |
| 0.0                       | 0.0                    | None       | None                           | PASS     |
| 99.9                      | 99.9                   | 100.0      | 100.0                          | PASS     |
| None                      | None                   | None       | None                           | PASS     |
| float_nan                 | nan                    | None       | ValueError: cannot convert float NaN to integer | CRASH    |
| np_nan                    | nan                    | None       | ValueError: cannot convert float NaN to integer | CRASH    |
| float_inf                 | inf                    | None       | OverflowError: cannot convert float infinity to integer | CRASH    |
| float_neg_inf             | -inf                   | None       | None                           | PASS     |
| 18.25 - 1e-10             | 18.2499999999          | 18.0       | 18.5                           | FAIL     |
| 18.25 - 1e-8              | 18.24999999            | 18.0       | 18.0                           | PASS     |
| 18.249 (DECIMAL 5,3)      | 18.249                 | 18.0       | 18.0                           | PASS     |
```

---

## 2. Logic Chain（推論チェーン）

1. **特定境界値の判定精度**:
   - `17.7499`, `17.750`, `18.2499`, `18.250`, `18.7499`, `18.750`, `20.250`, `21.250` はすべて意図通りのラベルに正しく分類された（PASS）。
   - M3 Worker が解消した偶数丸め（Banker's rounding）のバグは確実に治っており、境界値判定自体は要件定義書 1.3 F-06 / 3.2 に適合している。
2. **NaN / inf 入力による例外破綻（CRASH）**:
   - Python の仕様上、`float('nan') < 17.75` は `False` を返す。
   - `if rating is None or rating < 17.75:` の判定では `float('nan')` が素通りし、35行目の `math.floor((rating - 17.75 + 1e-9) / 0.5)` に達する。
   - `math.floor(float('nan'))` は未捕捉の `ValueError: cannot convert float NaN to integer` を発生させてプロセスを即死させる。
   - 同様に、`float('inf')` が渡された場合も判定を通過し、`math.floor(inf)` で `OverflowError: cannot convert float infinity to integer` が発生する。
3. **浮動小数点の丸め誤差と微小イプシロン加算の影響（Epsilon Leakage）**:
   - 実装では `+ 1e-9` を加算しているため、境界値の直前にある値（例: $18.25 - 10^{-10}$）は `18.0` 帯ではなく `18.5` 帯へ繰り上がる。
   - ただし、オンゲキの公式レーティング仕様は `DECIMAL(5,3)`（刻み幅 0.001）であるため、実データ境界（`18.249` vs `18.250` 等）では $10^{-6}$ 以上のマージンがあり、実測値で誤分類されることはない（PASS）。
4. **判定の導出**:
   - 指示文において「NaN、Noneなどに対する分類挙動を経験的に検証してください」「合格ならAPPROVE、破綻があればREQUEST_CHANGES」と明確に義務付けられている。
   - `float('nan')`, `np.nan`, `float('inf')` での未捕捉クラッシュは明らかな破綻（防衛的プログラミングの欠如）であり、放置すれば将来的なデータ連携や直接呼出時に障害を引き起こすため、**REQUEST_CHANGES** と判定する。

---

## 3. Caveats（留保事項）

1. **WebUIおよびバッチ実行における直下の影響**:
   - `visualizer.py` の 114行目および 154行目において `df = df[df['rating'] >= 17.75].copy()` のフィルタが先行して実行されるため、Pandas の仕様上 `NaN >= 17.75` は `False` となり、現在の内部呼出フローでは偶然 NaN が除外されている。
   - しかし、`OPIVisualizer.get_band_label` は独立した `@staticmethod` として公開されており、単体呼出やフィルタ無しのパイプラインで即座にクラッシュする潜在的欠陥である。
2. **上限レーティングの仕様**:
   - 要件定義書 3.2 の表は `21.0` 帯（`20.75 〜 21.24`）までしか例示されていないが、現状のロジックは `21.25` に対して `21.5`、`99.9` に対して `100.0` と外挿して安全に分類している。この拡張性は好ましい仕様と評価する。

---

## 4. Conclusion（結論および改修要求）

### 判定: **REQUEST_CHANGES**

`src/visualizer/visualizer.py` の `get_band_label` において、`NaN` および `inf` に対する安全ガードが欠落しており、未補足例外（`ValueError`, `OverflowError`）で異常終了することが実証された。

### 推奨される修正案:
`src/visualizer/visualizer.py` の `get_band_label` 先頭を以下のように修正すること:

```python
    @staticmethod
    def get_band_label(rating: float) -> str | None:
        if rating is None:
            return None
        try:
            val = float(rating)
        except (ValueError, TypeError):
            return None
        if math.isnan(val) or math.isinf(val) or val < 17.75:
            return None
        band_idx = math.floor((val - 17.75 + 1e-9) / 0.5)
        center = 18.0 + band_idx * 0.5
        return f"{center:.1f}"
```

この修正により、`None`, `NaN`, `inf`, 不正文字列（非数値）のいずれが渡されても安全に `None` を返却し、完全な堅牢性が保証される。

---

## 5. Verification Method（独立検証手順）

1. **クラッシュの再現（現状の破綻確認）**:
   ```powershell
   .venv\Scripts\python.exe -c "from src.visualizer.visualizer import OPIVisualizer; OPIVisualizer.get_band_label(float('nan'))"
   ```
   -> `ValueError: cannot convert float NaN to integer` で終了することを確認。

2. **修正後の完全性検証コマンド**:
   ```powershell
   .venv\Scripts\python.exe -c "
   import math, numpy as np; from src.visualizer.visualizer import OPIVisualizer;
   assert OPIVisualizer.get_band_label(float('nan')) is None
   assert OPIVisualizer.get_band_label(np.nan) is None
   assert OPIVisualizer.get_band_label(float('inf')) is None
   assert OPIVisualizer.get_band_label(float('-inf')) is None
   assert OPIVisualizer.get_band_label(None) is None
   assert OPIVisualizer.get_band_label(17.7499) is None
   assert OPIVisualizer.get_band_label(17.750) == '18.0'
   assert OPIVisualizer.get_band_label(18.2499) == '18.0'
   assert OPIVisualizer.get_band_label(18.250) == '18.5'
   assert OPIVisualizer.get_band_label(18.7499) == '18.5'
   assert OPIVisualizer.get_band_label(18.750) == '19.0'
   assert OPIVisualizer.get_band_label(20.250) == '20.5'
   assert OPIVisualizer.get_band_label(21.250) == '21.5'
   print('ALL_BOUNDARY_AND_NAN_TESTS_PASSED')
   "
   ```
