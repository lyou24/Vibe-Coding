# TEST_READY — 新受入基準 E2E テストスイート準備完了宣言

## 1. 宣言 (Declaration)
オンゲキ OPI Web アプリケーション改修プロジェクト（2026-09-14T13:31:31Z 要求仕様）に対する、
**包括的新受入基準 E2E 自動検証テストスイート（AC-1 〜 AC-6 + Adversarial）の構築および初期検証が完了しました。**

本テストスイートは実装コードに依存しない **Opaque-box（ブラックボックス）** かつ **Requirement-driven（要求駆動）** の原則に則り設計されています。

---

## 2. テストファイル・構成物

| ファイルパス | 役割 | 状態 |
|---|---|---|
| `TEST_INFRA.md` | テスト設計思想、受入アーキテクチャ、テストケース一覧、権威ソース定義 | 作成完了 |
| `tests/test_tier4_m4_new_acceptance.py` | `streamlit.testing.v1.AppTest` を用いた AC-1〜AC-6 および敵対的検証コード | 作成・検証完了 |
| `TEST_READY.md` | テストスイート準備完了宣言、実行コマンド、カバレッジサマリー（本ファイル） | 作成完了 |

---

## 3. テスト実行コマンド (Execution Commands)

仮想環境内の Python / pytest を使用して以下を実行してください：

```powershell
# E2E 新受入基準テストスイートの実行
.\.venv\Scripts\python.exe -m pytest tests/test_tier4_m4_new_acceptance.py -v

# 詳細ログ・出力付き実行
.\.venv\Scripts\python.exe -m pytest tests/test_tier4_m4_new_acceptance.py -v -s

# 特定受入基準のみのピンポイント実行例 (例: AC-2 新5段階ランク)
.\.venv\Scripts\python.exe -m pytest tests/test_tier4_m4_new_acceptance.py -k "test_ac2" -v
```

---

## 4. カバレッジサマリーと初期検証結果 (ATDD Baseline: Red)

現在（改修実装前）の実行結果は、**3 PASSED / 5 FAILED** となっており、未改修の要件欠落を厳密かつ正確に検出するベースライン（ATDD: Red）として機能しています。

| テスト関数名 | 対象基準 | 初期判定 | 検出理由 / 実装要件 (Workerへの引き継ぎ) |
|---|---|---|---|
| `test_ac1_app_launch_and_zero_exceptions` | **AC-1** | **PASSED** | アプリケーションが例外ゼロで正常起動することを確認。 |
| `test_ac2_new_five_ranks_compliance_and_legacy_elimination` | **AC-2 (R1)** | **FAILED** | 目標・現在ランク選択肢および `TARGET_RANKS` に旧ランク（`SSS+ABFB`, `AP`）が残存しており、新5段階（`S`, `AB+`）への置換が未完了。 |
| `test_ac3_recommendation_ui_slider_and_multiselect` | **AC-3 (R2)** | **FAILED** | 旧表記「勝率」の number_input が残存し、0〜100%「クリア割合」範囲スライダーが未実装。 |
| `test_ac4_difficulty_grid_and_my_opi_view` | **AC-4 (R3)** | **FAILED** | タブ構成に「マイOPI難易度表」が存在せず、達成済みセルのハイライトが未実装。 |
| `test_ac5_dynamic_scatterplot_plotly_and_highlight` | **AC-5 (R4)** | **FAILED** | `requirements.txt` に `plotly` 未記載、環境未インストール、Plotly Figure 生成ロジック未実装。 |
| `test_ac6_e2e_user_10605_calculation_and_recommendation` | **AC-6 (Core)**| **FAILED** | ID 10605 の総合OPI算出値が 1476.4（旧ランク参照不整合による）。新ランク体系適合後に 2000〜2100 の適正水準へ到達して合格する。 |
| `test_adversarial_invalid_user_input_handling` | **Adversarial** | **PASSED** | 不正なユーザーID入力（"invalid_id_abc"）に対して例外クラッシュせず警告・エラー通知を表示。 |
| `test_adversarial_boundary_slider_filters` | **Adversarial** | **PASSED** | スライダー極値（100%〜100%等）設定時にゼロ除算等の例外を起こさず安全に動作。 |

---

## 5. 後続実装チーム（Worker / Reviewer）への手引き

各マイルストーンの実装完了に伴い、以下の順序でテストが GREEN（合格）へ移行します：

1. **M1 (R1 新5段階ランク対応)**:
   - `requirements.txt` に `plotly` を追加し、`.venv` にインストール。
   - `app.py`, `src/analyzer/opi_calculator.py`, `src/recommender/recommender.py` の旧ランク（`SSS+ABFB`, `AP`）を完全排除し、新5段階（`S`, `SS`, `SSS`, `SSS+`, `AB+`）に置換。
   - ⇒ `test_ac2` が GREEN に移行。
2. **M2 (R2 リコメンドUI高度化)**:
   - `app.py` の「勝率」入力欄を「クリア割合」0〜100% 範囲スライダーに改称・置換。
   - 未選択時全対象ヒットのフォールスルーを担保。
   - ⇒ `test_ac3` が GREEN に移行。
3. **M3 (R3 難易度表グリッド化 & マイOPI難易度表)**:
   - 100 OPI帯降順グリッド化と、「マイOPI難易度表」タブを追加し達成済みセルをハイライト。
   - ⇒ `test_ac4` が GREEN に移行。
4. **M4 (R4 レーティング vs OPI 動的散布図)**:
   - `src/visualizer/visualizer.py` に `create_distribution_figure` を実装し、Plotly 動的散布図とユーザー位置（星型マーカー）ハイライトを導入。
   - ⇒ `test_ac5` が GREEN に移行。
5. **Final Milestone**:
   - ID 10605 の総合OPI算出値が新5段階ランク体系により約 2076 に正常算出され、リコメンド楽曲テーブルが出力される。
   - ⇒ `test_ac6` が GREEN に移行し、**8件全件通過（100% PASS）** を達成。
