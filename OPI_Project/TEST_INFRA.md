# TEST_INFRA — 受入基準E2Eテストアーキテクチャ・設計仕様書

## 1. テスト設計思想 (Design Philosophy)

本テストインフラは、オンゲキOPIシステムの最新要求仕様（`ORIGINAL_REQUEST.md` 2026-09-14T13:31:31Z）に基づき構築された総合E2E受入検証スイートです。
以下のコア原則を徹底して設計されています：

1. **Opaque-box（ブラックボックス検証）**:
   内部実装コードの細部や関数シグネチャの恣意的な実装に依存せず、要求仕様書に定義された入出力契約、UIウィジェットの動作、公開API・スキーマ契約に基づいて検証を行います。
2. **Requirement-driven（要求駆動検証）**:
   各テストケースは `ORIGINAL_REQUEST.md` の要件（R1〜R4）および受入基準と1対1で対応し、仕様の充足性を客観的・機械的に判定します。
3. **Non-facade / Real Logic Execution（実ロジック実行）**:
   常に成功する形だけのファサードテストやモックの多用を排除し、実際のSQLiteデータベース（2,505名プレイヤー、実データID `10605` の397スコアログ）および Streamlit の実行ランタイム（`AppTest`）を用いて実計算・描画を検証します。
4. **Adversarial & Boundary Verification（敵対的・境界値検証）**:
   旧ランク表記（`SSS+ABFB`, `AP`）の完全排除、マルチセレクト空選択時のフォールスルー挙動、0〜100%スライダーの境界値など、エッジケースを網羅します。

---

## 2. 受入基準テストアーキテクチャ (Architecture)

```
[ ORIGINAL_REQUEST.md / PROJECT.md ]
                 │ (要件・受入基準定義)
                 ▼
[ tests/test_tier4_m4_new_acceptance.py ]
   ├── streamlit.testing.v1.AppTest (インプロセスUI自動検証)
   │     ├── ウィジェット状態操作 (slider, multiselect, text_input)
   │     ├── UIツリー走査 (metric, dataframe, markdown, plotly_chart)
   │     └── 実行時例外検出 (len(at.exception) == 0)
   ├── Core Engine Verification (計算・契約検証)
   │     ├── OPICalculator (新5段階ランクMLE推定・パラメータ抽出)
   │     ├── OPIRecommender (フィルタリング・達成判定・現在ランク判定)
   │     └── OPIVisualizer (Plotly動的散布図・星型マーカーハイライト)
   └── Real Database (data/opi_database.sqlite)
         ├── players (ID 10605: ＮＥＧＩＮＥ)
         ├── score_logs (397件)
         └── charts (新5段階ランク対応カラム)
```

- **UI検証エンジン**: `streamlit.testing.v1.AppTest`
  外部ブラウザ（Playwright等）のダウンロードやネットワーク通信を必要とせず、高速・確定的にStreamlitのコンポーネントツリーとセッションステートを検査・操作。
- **データソース**: `data/opi_database.sqlite`
  実測2,505名およびテストユーザーID `10605`（スコア397件）のDBを直接使用。

---

## 3. 受入基準マッピングとテストケース一覧 (Test Inventory)

| テストケースID | 受入基準 | 対象要件 | テスト関数名 | 主な検証内容 |
|---|---|---|---|---|
| **TC-AC-1** | AC-1 | アプリ稼働 | `test_ac1_app_launch_and_zero_exceptions` | `app.py` 起動時の例外ゼロ（`len(at.exception) == 0`）、タイトル描画、重大エラー不在 |
| **TC-AC-2** | AC-2 | R1: 新5段階ランク対応 | `test_ac2_new_five_ranks_compliance_and_legacy_elimination` | 目標・現在ランク選択肢が `["S", "SS", "SSS", "SSS+", "AB+"]` に完全移行、旧ランク（`SSS+ABFB`, `AP`）の完全排除、コアロジックの契約適合 |
| **TC-AC-3** | AC-3 | R2: リコメンドUI高度化 | `test_ac3_recommendation_ui_slider_and_multiselect` | 0〜100%「クリア割合」範囲スライダー（旧表記「勝率」の廃止）、レベル・ランクのマルチセレクト、未選択時全対象ヒット挙動 |
| **TC-AC-4** | AC-4 | R3: 難易度表グリッド化 & マイ難易度表 | `test_ac4_difficulty_grid_and_my_opi_view` | 100 OPI帯域グリッドの降順ソート徹底、マイOPI難易度表タブの存在、達成済み楽曲セルの視覚的識別（色付きハイライト） |
| **TC-AC-5** | AC-5 | R4: 動的散布図 | `test_ac5_dynamic_scatterplot_plotly_and_highlight` | Plotly Figure 生成（横軸: Rating, 縦軸: Total OPI）、選択ユーザー位置のハイライト（星型マーカー等）、Streamlit上での描画 |
| **TC-AC-6** | AC-6 | 10605 E2E検証 | `test_ac6_e2e_user_10605_calculation_and_recommendation` | テスト用ID `10605` 入力時の例外なし完走、総合OPI算出値（2000〜2100）、リコメンド楽曲テーブルの正常出力 |
| **TC-ADV-1** | Adversarial | 耐障害性 | `test_adversarial_invalid_user_input_handling` | 不正な文字列ID（"abc" 等）や負数・空文字入力時のUI例外耐性とエラーハンドリング |
| **TC-ADV-2** | Adversarial | 境界値フィルタ | `test_adversarial_boundary_slider_filters` | クリア割合 0%〜100% の極値設定時の安全なフィルタリング動作 |

---

## 4. 期待値の権威ソース (Authoritative Sources of Expected Output)

1. **新5段階ランク体系 (R1)**:
   - 権威ソース: `ORIGINAL_REQUEST.md` §R1, `PROJECT.md` §Interface Contracts
   - 期待値: ランク集合は `{"S", "SS", "SSS", "SSS+", "AB+"}` のみ。旧ランク `"SSS+ABFB"`, `"AP"` は排除。
2. **リコメンドUI (R2)**:
   - 権威ソース: `ORIGINAL_REQUEST.md` §R2
   - 期待値: スライダーラベルは「クリア割合」、範囲 `0` 〜 `100`。マルチセレクト未選択時は全件ヒット（空リストで0件ヒットにならない）。
3. **難易度表グリッド & マイ難易度表 (R3)**:
   - 権威ソース: `ORIGINAL_REQUEST.md` §R3
   - 期待値: 帯域は100 OPI単位で降順（高い帯域が上位）。達成済みセルには視覚的識別スタイル（背景色等）が付与。
4. **動的散布図 (R4)**:
   - 権威ソース: `ORIGINAL_REQUEST.md` §R4, `PROJECT.md` §Feature 6
   - 期待値: Plotly `Figure` オブジェクト。X軸=レーティング、Y軸=総合OPI。選択ユーザーの現在位置ハイライトトレースが存在。
5. **テストユーザーID `10605` (AC-1 / AC-6)**:
   - 権威ソース: `ORIGINAL_REQUEST.md` §1, `PROJECT.md` §Interface Contracts, `handoff.md` (Explorer 3)
   - 期待値: プレイヤー名「ＮＥＧＩＮＥ」、レーティング 19.950、スコアログ 397件、推定総合OPI 2000〜2100 の適正水準。

---

## 5. テスト実行手順

```powershell
# E2E 新受入基準テストスイートの実行
.\.venv\Scripts\python.exe -m pytest tests/test_tier4_m4_new_acceptance.py -v

# 詳細ログ付き実行
.\.venv\Scripts\python.exe -m pytest tests/test_tier4_m4_new_acceptance.py -v -s
```
