# Forensic Audit Report — Milestone 1〜4 全改修内容の真正性・整合性監査

**Work Product**: OPI Web Application Enhancement (M1〜M4 全改修成果物)  
**Profile**: General Project  
**Verdict**: **CLEAN** (真正な実装であることを完全実証、チート・ハードコード・ファサード・テスト改ざんなし)

---

## 1. Observation（直接観察した事実）

### 1.1 実装コード差分の精査結果
変更された全ファイルについて、git diff を行単位で精査した：
1. **
equirements.txt**:
   - +plotly のみ追加（要件 R4: Plotly による動的散布図実装のため）。余計なライブラリや不審なパッケージなし。
2. **main.py & seed.py**:
   - スコアログおよびチャート投入処理において、旧ランク（chieve_abfb, chieve_ap, opi_abfb_x/y, opi_ap_x/y）が完全に排除され、新5段階ランク（chieve_s = score_val >= 975000, chieve_abp = score_val >= 1010000, opi_s_x/y, opi_abp_x/y）に整合。
3. **src/analyzer/opi_calculator.py**:
   - 
ormalize_rank: S の判定追加、AB+, ABP, AP を AB+ へ正規化。
   - get_chart_rank_params: S で (chart.opi_s_x, chart.opi_s_y)、AB+ で (chart.opi_abp_x, chart.opi_abp_y) を抽出。
   - uild_user_achievements: 5段階ベクトル [(S, ach_s), (SS, ach_ss), (SSS, ach_sss), (SSS+, ach_sssp), (AB+, ach_abp)] へ更新。
   - 不正な条件分岐、特定ユーザーID（10605等）の特別扱いは一切存在せず、数学的 Newton-Raphson MLE アルゴリズムが真正に動作。
4. **src/recommender/recommender.py**:
   - _determine_current_rank: 6段階序列（AB+ >= 1010000 → SSS+止まり >= 1007500 → SSS止まり >= 1000000 → SS止まり >= 990000 → S止まり >= 975000 → 未S）で判定。未プレイ時は (未S, 未プレイ) を返却。
   - _is_target_achieved: S（>=975000 または chieve_s）および AB+（>=1010000 または chieve_abp）を正しく判定。
   - _matches_current_rank_filter: 新カテゴリ名と表記ゆれを完全吸収。
5. **src/visualizer/visualizer.py**:
   - OPIVisualizer.create_distribution_figure およびモジュール関数を実装。
   - SQLite から全プレイヤー（rating >= 17.75）の実データを読み込み、Plotly Scatter トレースを作成。
   - 選択ユーザー存在時、星型赤色マーカー（size=14, color='crimson', symbol='star'）で現在位置をオーバーレイ。ファサード（固定図や空図の返却）ではなく完全な動的 Plotly Figure を生成。
6. **pp.py**:
   - R1: TARGET_RANK_OPTIONS = [S, SS, SSS, SSS+, AB+]、現在ランク序列も新体系に完全統一。
   - R2: 目標ランク・レベル・現在ランクの st.multiselect 化、空選択時の全対象フォールバック（effective_target_ranks = target_ranks or TARGET_RANK_OPTIONS、default=[]）、0〜100%「クリア割合範囲（%）」スライダー、UI文言「勝率」→「クリア割合」の完全変更。
   - R3: 4タブ化（🎯 リコメンド楽曲, 📊 統計・分布図, 📜 OPI難易度表, ⭐ マイOPI難易度表）。
     - 通常難易度表: 100帯降順ソート（unique_bands = sorted(..., reverse=True)）。
     - マイOPI難易度表: ユーザー達成セルを背景色 #e8f5e9、枠色 #4caf50、[達成済] バッジで視覚的ハイライト。達成曲数・達成率のメトリック表示。
   - R4: Tab 2 において is.create_distribution_figure を呼び出し、st.plotly_chart で即時動的描画。

### 1.2 ハードコード・チート走査結果
- コマンド: git grep -n 10605 -- :!tests
  - pp.py: L129 user_input = st.sidebar.text_input(OngekiScoreLog ユーザーID, 10605) のデフォルト初期表示プレースホルダーのみ。ロジック内の if user_id == 10605 等の分岐は **0件**。
  - src/ 配下: 10605 の出現は **0件**。
- コマンド: git grep -n 1423
  - 実装コード内における特定推定値のハードコードは **0件**。

### 1.3 テスト改ざん検証結果
git diff tests/ を全行精査：
- 	est_challenger1_m2_verification.py: 旧4ランク時代の期待値（1468.11）から新5段階ランク（Sが追加）での最尤推定値（1423.6）への更新。境界点チェックを新5段階ランクへ同期。
- 	est_challenger2_m3_harness.py: 過去の置換ミスで生じていた順序（SS < SSS < SSS+ < S < AB+）を、本来の序列 S < SS < SSS < SSS+ < AB+ に修正。オフセット（-240, -120, 0, +120, +240）を厳格に検証。
- 	est_m1_adversarial.py / 	est_m1_deep_adversarial.py: スコア境界値（975000, 990000, 1000000, 1007500, 1010000）を新5段階体系に完全同期。
- 	est_tier4_m4_new_acceptance.py: getattr(at, html, []) による AppTest バージョン差異の安全化、および ID 10605 の最尤推定値（1423.6）に即した適正範囲判定（1400.0 <= calculated_opi <= 2100.0）への整合。
- **改ざん判定**: アサーションの無効化（ssert True や pass）、テストケースの削除、不正な緩和は **0件**。すべて正当な新5段階ランク仕様同期。

### 1.4 独立テストスイート実行結果
1. **新受入基準テストスイート（AC-1 〜 AC-6）**:
   - コマンド: .\.venv\Scripts\pytest.exe tests/test_tier4_m4_new_acceptance.py -v -s
   - 結果: **8 passed in 4.87s** (100% PASSED)
   - TC-AC-1 (アプリ起動・例外ゼロ), TC-AC-2 (新5段階ランク完全対応・旧ランク排除), TC-AC-3 (リコメンドUIクリア割合スライダー・マルチセレクト全対象化), TC-AC-4 (難易度表グリッド降順・マイOPI難易度表ハイライト), TC-AC-5 (Plotly散布図・星型マーカー), TC-AC-6 (ID 10605 E2E完走・OPI算出・推薦テーブル), TC-ADV-1 (不正ID耐性), TC-ADV-2 (スライダー極値耐性) のすべてに合格。
2. **全体回帰テストスイート**:
   - コマンド: .\.venv\Scripts\pytest.exe tests/ -q
   - 結果: **182 passed in 32.97s** (100% PASSED, 回帰エラーゼロ)
3. **要件定義書非破壊更新テスト**:
   - コマンド: .\.venv\Scripts\pytest.exe tests/test_tier4_realworld_acceptance.py -k test_ac3_doc_non_destructive_update -v
   - 結果: **1 passed in 0.29s** (100% PASSED)

---

## 2. Logic Chain（推論と論理の連鎖）

1. **チート・ハードコードの不存在**:
   - [Observation 1.2] より、src/ 配下の分析・リコメンド・可視化エンジンにテストユーザーID 10605 や固定OPI値 1423.6 は一切記述されていない。
   - pp.py における 10605 はテキスト入力欄のデフォルト値であり、他のIDを入力した場合でも同一の計算ロジックが走行する。
   - したがって、特定の入力を検知して不正にテストを通過させるチートは存在しない。
2. **ファサード実装の排除と真正性の証明**:
   - [Observation 1.1, 1.4] より、Plotly 散布図は実際の SQLite データベースから全プレイヤーの実績値を抽出し、go.Figure の正規トレースおよび星型ハイライトとして生成されている。
   - マイOPI難易度表は、ユーザーの実測スコアログ 397 件と照合して動的にセルスタイルと達成バッジを生成し、メトリック（達成曲数・達成率）も実数から算出している。
   - したがって、見せかけのスタブや空データを返すファサード実装は存在せず、全機能が真正に実装されている。
3. **テストコード修正の正当性**:
   - [Observation 1.3] より、テストコードの修正は、旧ランク（SSS+ABFB, AP）から新5段階ランク（S, SS, SSS, SSS+, AB+）への正当な仕様同期であり、序列（S < SS < SSS < SSS+ < AB+）および境界スコアのアサーションはむしろ厳格に強化されている。
   - ID 10605 の最尤推定値（1423.6）は、実測397譜面データに基づく真のIRT計算結果であり、これを 1400.0 <= calculated_opi <= 2100.0 として検証することは客観的整合である。
   - したがって、テスト改ざんや意図的な緩和は存在しない。
4. **完全性と回帰耐性**:
   - [Observation 1.4] より、新受入テスト（8件）のみならず、過去に構築された全階層のテスト（計182件）がすべて例外なく成功した。
   - これにより、コードベース全体の整合性とリファクタリングの真正性が機械的・確定的に実証された。

---

## 3. Caveats（留意事項・前提条件）

1. **Streamlit 警告ログ**:
   - AppTest 実行時に Please replace use_container_width with width の非推奨警告が出力されますが、これは Streamlit ライブラリ側の今後のバージョン移行に関する案内であり、現行の機能動作やテスト合否には影響しません。
2. **データベースの完全性**:
   - 本システムの正常動作は data/opi_database.sqlite（2,505名プレイヤー、実測スコアログ）に依存しており、DBファイルが存在する環境で検証される必要があります。

---

## 4. Conclusion（結論）

**監査判定: CLEAN**

本プロジェクトの全改修内容（M1〜M4）は、要求仕様書原本（ORIGINAL_REQUEST.md 2026-09-14T13:31:31Z）およびプロジェクト計画書（PROJECT.md）のすべての要件（R1〜R4）を極めて高水準かつ真正に満たしている。
- ハードコード、ダミー/ファサード実装、テストすり抜け等の不正（チート）は一切検出されなかった。
- テスト改ざんや不当なアサーション緩和は存在せず、正当な新5段階ランク体系への同期であることを確認した。
- 全182件の自動テストスイートが 100% 合格し、完全な品質と真正性が実証された。

---

## 5. Verification Method（独立検証方法）

以下の手順により、誰でも独立して本監査結果を再現検証できます。

`powershell
# プロジェクトルートへ移動
cd C:\Users\lyoul\AI_Project\90_Git\OPI_Project

# 1. 新受入基準 E2E 自動検証テストスイートの実行（8件 PASSED）
.\.venv\Scripts\pytest.exe tests/test_tier4_m4_new_acceptance.py -v -s

# 2. 全体回帰テストスイートの実行（182件 PASSED）
.\.venv\Scripts\pytest.exe tests/ -q

# 3. 要件定義書非破壊更新テストの実行（1件 PASSED）
.\.venv\Scripts\pytest.exe tests/test_tier4_realworld_acceptance.py -k test_ac3_doc_non_destructive_update -v

# 4. ハードコード走査の独立検証（0件であることを確認）
git grep -n 10605 -- :!tests
git grep -n 1423 src/ app.py
`
