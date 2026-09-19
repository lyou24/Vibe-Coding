# Handoff Report — UI & Streamlit App 現状精査と改修箇所特定

## 1. Observation（直接観察した事実）

### 1.1 要求仕様原本（ORIGINAL_REQUEST.md セクション 2026-09-14T13:31:31Z）
- **R1（新5段階ランク対応）**: 旧ランク（SSS+ABFB, AP）を新しい5段階（S, SS, SSS, SSS+, AB+）に完全に置き換える。DBマイグレーションは完了済み。
- **R2（リコメンドUI高度化）**: レベル、現在ランク、目標ランクをマルチセレクト化し未選択時は全対象とする。0〜100%の範囲スライダー設置、「勝率」から「クリア割合」への文言変更。
- **R3（難易度表グリッド化・マイ難易度表）**: 100 OPIごとの帯域で区切ったグリッド形式（難易度降順）。「マイOPI難易度表」タブ/ビューで達成済み楽曲セルを色付き塗りつぶし。
- **R4（動的散布図）**: レーティング vs 総合OPIの散布図を動的グラフ（Plotly等）として実装し、選択ユーザーの現在位置をハイライト表示。

---

### 1.2 R1関連（新5段階ランク対応）の観察事実
DBモデル（`src/database/models.py`）およびポリシー（`src/analyzer/opi_policy.py`）では新5段階ランクへのマイグレーションが完了しているが、UI（`app.py`）および一部バックエンドに旧ランクが多数残存している。

1. **`app.py` L20**:
   ```python
   TARGET_RANK_OPTIONS = ["SS", "SSS", "SSS+", "SSS+ABFB", "AP"]
   ```
   → 旧ランク `SSS+ABFB`, `AP` が残り、`S` と `AB+` が欠落している。

2. **`app.py` L78-L83（スコアログ保存処理）**:
   ```python
   score_log.achieve_ss = score_val >= 990000
   score_log.achieve_sss = score_val >= 1000000
   score_log.achieve_sssp = score_val >= 1007500
   score_log.achieve_abfb = (score_val >= 1007500 and score_log.is_all_break and score_log.is_full_bell)
   score_log.achieve_ap = score_val == 1010000
   ```
   → `ScoreLog` モデルの実カラムは `achieve_s`, `achieve_abp` であり、`achieve_abfb` や `achieve_ap` はモデル定義（`src/database/models.py` L73-L77）に存在せず AttributeError または不整合となる。

3. **`app.py` L240-L245（現在ランク選択フィルター）**:
   ```python
   current_rank_filters = st.multiselect(
       "現在の達成ランク（複数選択可）",
       options=["未SS", "SS", "SSS", "SSS+", "SSS+ABFB", "AP"],
       default=[],
       key="filter_current_rank"
   )
   ```
   → 旧ランク名 `SSS+ABFB`, `AP` がUIの選択肢に露出している。

4. **`app.py` L282-L289（ソート順辞書）**:
   ```python
   current_rank_order = {
       "未SS": 0,
       "SS止まり": 1,
       "SSS止まり": 2,
       "SSS+止まり": 3,
       "ABFB止まり": 4,
       "AP": 5,
   }
   ```
   → 旧ランクの並び順定義のままとなっている。

5. **`tests/test_m3_webui_integration.py` でのエラー**:
   `pytest tests/test_m3_webui_integration.py` 実行結果：
   ```
   > assert 'TARGET_RANK_OPTIONS = ["SS", "SSS", "SSS+", "S", "AB+"]' in code
   E AssertionError
   ...
   > assert ranks_in_ach == {"SS", "SSS", "SSS+", "S", "AB+"}
   E AssertionError: assert {'AP', 'SS', 'SSS', 'SSS+', 'SSS+ABFB'} == {'AB+', 'S', 'SS', 'SSS', 'SSS+'}
   ```
   `app.py` だけでなく `src/analyzer/opi_calculator.py` L227-L233（`rank_status`）にも旧ランクが残存していることが確認された。

---

### 1.3 R2関連（リコメンドUI高度化）の観察事実
`app.py` L217-L298 のリコメンドUIにおいて以下の実装を確認：

1. **未選択時の全対象フォールバック不備（L224, L268-L280）**:
   ```python
   target_ranks = st.multiselect(
       "目標ランク（複数選択可）",
       options=TARGET_RANK_OPTIONS,
       default=["SSS"],
       key="filter_target_rank"
   )
   ...
   for target_rank in target_ranks:
       recs.extend(recommender.get_recommendations(...))
   ```
   → ユーザーが `target_ranks` を全て削除（未選択）にした場合、`target_ranks` が空リストとなり `for` ループが0回実行され、結果が0件（「データが不足しているか...」）になってしまう。「未選択時は全対象を表示する」要件を満たしていない。
   ※同様に `level_filters` は `param_level = level_filters or None` とされ、`recommender.py` 側で `if level is not None:` と判定されているため未選択時は全対象になっている。

2. **勝率数値入力（L248-L255）**:
   ```python
   col_w1, col_w2, col_sort = st.columns(3)
   with col_w1:
       win_rate_min_percent = st.number_input(
           "勝率 Min（%）", min_value=0.0, max_value=100.0, value=30.0, step=1.0
       )
   with col_w2:
       win_rate_max_percent = st.number_input(
           "勝率 Max（%）", min_value=0.0, max_value=100.0, value=70.0, step=1.0
       )
   ```
   → スライダーではなく2つの `st.number_input` で実装されており、「勝率」という表記になっている。

3. **テーブル表示・ソート文言（L259, L291, L302, L312）**:
   - `options=["適正順", "勝率が高い順", "現在ランク順", "目標ランク順"]`
   - `if sort_key == "勝率が高い順":`
   - `df_recs['勝率'] = (df_recs['probability'] * 100).round(1).astype(str) + '%'`
   - `display_cols = [..., "勝率"]`
   すべて「勝率」と表記されている。

---

### 1.4 R3関連（難易度表グリッド化・マイ難易度表）の観察事実
`app.py` L351-L402（`tab3`）の難易度表実装を確認：

1. **現在の表示構造（L385-L395）**:
   ```python
   df_charts = df_charts.sort_values(by=f"{diff_target_rank} 適正OPI", ascending=False)
   opi_column = f"{diff_target_rank} 適正OPI"
   df_charts["OPI帯"] = (df_charts[opi_column] // 100 * 100).astype(int)

   for opi_band, band_rows in df_charts.groupby("OPI帯", sort=False):
       st.markdown(f"### OPI {opi_band}〜{opi_band + 99}")
       columns = st.columns(4)
       for index, (_, row) in enumerate(band_rows.iterrows()):
           with columns[index % 4]:
               st.write(f"**{row['楽曲名']}**")
               st.caption(
                   f"{row['難易度']} / Lv.{row['レベル']} / "
                   f"定数 {row['定数']:.1f} / OPI {row[opi_column]:.1f}"
               )
   ```
   - 既に 100 OPIごとの帯域で `ascending=False`（降順）ソートされ、4列のカラムにカード配置されている。
   - ただし、単なる `st.write` と `st.caption` のプレーンテキストであり、表/グリッドとしての区切り枠（ボーダー）や視覚的なセル表現が希薄である。
   - 「マイOPI難易度表」が存在しない（達成済みかどうかの判定およびセルのハイライト表示機能がない）。

---

### 1.5 R4関連（動的散布図）の観察事実
1. **現状の実装（`app.py` L339-L350, `src/visualizer/visualizer.py` L165-L207）**:
   - `vis.create_distribution_plot(img_path)` で matplotlib + seaborn を用いてローカルに `opi_distribution.png` を保存。
   - `app.py` で「分布図を最新データで更新」ボタンを押下して初めて画像生成され、`st.image(img_path)` で静的PNG画像を表示している。
   - 散布図には DB 内の全プレイヤーの点（青色）しか描画されず、**検索中のユーザー自身の位置（レーティング, 総合OPI）は一切プロットされていない**。
2. **ライブラリ環境の確認**:
   - `requirements.txt`: matplotlib, seaborn のみ記載、`plotly` は未記載。
   - `.venv` 仮想環境で `python -c "import plotly"` を実行した結果: `ModuleNotFoundError: No module named 'plotly'`。

---

## 2. Logic Chain（観察から結論への推論）

1. **R1（新5段階ランク対応）の論理連鎖**:
   - [Observation 1.2] より、DB側のカラム名（`opi_s_x`, `opi_abp_x`, `achieve_s`, `achieve_abp`）と、共通ポリシー（`src/analyzer/opi_policy.py`）で新5段階ランク（S, SS, SSS, SSS+, AB+）が定義されている。
   - 一方、`app.py` L20, L78-83, L240-245, L282-289 では旧ランク名（SSS+ABFB, AP）がハードコードされている。
   - したがって、`app.py` の定数定義、クローラー取得スコアの代入ロジック、UIフィルターの選択肢、ソート辞書を新5段階ランクに更新することで、UI上の旧ランク露出を解消し、DBとの整合性を担保できる。
   - さらに、`tests/test_m3_webui_integration.py` を通過させるため、UIから呼び出される `src/analyzer/opi_calculator.py` および `src/recommender/recommender.py` 内の旧ランク文字列も併せて新ランクに修正する必要がある。

2. **R2（リコメンド機能UI高度化）の論理連鎖**:
   - [Observation 1.3] より、現在 `target_ranks` が空のときはループが回らず結果が0件になる。
   - 「未選択時は全対象を表示」を実現するには、`effective_target_ranks = target_ranks if target_ranks else TARGET_RANK_OPTIONS` のように空判定フォールバックを設ける必要がある。
   - `st.number_input` 2個を `st.slider("クリア割合範囲（%）", min_value=0, max_value=100, value=(30, 70), step=1)` に置き換えることで、直感的かつ要求仕様通りの0〜100%範囲スライダーになる。
   - UI上の「勝率」表記をすべて「クリア割合」に置換することで、要件ACを完全に満たす。

3. **R3（難易度表グリッド化・マイ難易度表）の論理連鎖**:
   - [Observation 1.4] より、現在の100 OPI単位のグルーピングおよび降順ソート処理は良好に機能している。
   - これをベースに、「マイOPI難易度表」を追加する方法として、タブを `tab1, tab2, tab3, tab4 = st.tabs(["🎯 リコメンド楽曲", "📊 統計・分布図", "📜 OPI難易度表", "⭐ マイOPI難易度表"])` に拡張するのが最も自然で操作性が高い。
   - マイ難易度表では、対象ユーザーのスコアログから各譜面が目標ランクを達成済みか判定し、達成済みセルには視覚的なハイライト（背景色 `#e8f5e9`・緑枠・「✅ 達成済」バッジ等）をインラインCSS / Markdownまたはコンテナで付与することで、一目で判別可能なマイ難易度表が実現できる。

4. **R4（動的散布図）の論理連鎖**:
   - [Observation 1.5] より、現状の静的PNG画像＋手動ボタン更新方式はユーザビリティが低く、ユーザー位置ハイライトもない。
   - `plotly` を導入（`requirements.txt` への追記と `pip install plotly`）し、`plotly.graph_objects.Figure` を生成して `st.plotly_chart` で即時描画する方式に変更するのがベストプラクティスである。
   - 全体プレイヤーの散布図トレースに加え、検索中のユーザーが存在し `player.rating` と `standard_opi` が有効な場合は、別のトレースとして赤色の星型マーカー（`size=14, color='red', symbol='star'`）をオーバーレイすることで、「動的グラフ化」と「ユーザー位置ハイライト」の要件を完全に満たすことができる。

---

## 3. Caveats（留意事項・前提条件）

1. **Plotly のインストール要件**:
   - 現在仮想環境に `plotly` が存在しないため、実装時には `pip install plotly` の実行が必須となる。もし外部パッケージ追加を最小限に抑えたい場合は Streamlit 組み込みの `st.scatter_chart` (Altair) も選択肢となるが、リッチなツールチップや特定マーカーの強調には Plotly が圧倒的に適している。
2. **新ランク `S` および `AB+` の達成判定しきい値**:
   - `migrate_target_ranks.py` では `S` は `score >= 975000`、`AB+` は `score >= 1010000`（または `score >= 1007500 and is_all_break`）と設定されている。実装時にはオンゲキ公式のS基準（970,000点 vs 975,000点）および `opi_policy.py` のポリシーとの整合性に注意する。
3. **読み取り専用制約の遵守**:
   - 本調査ではコードの変更は一切行っておらず、提案スニペットの提示にとどめている。

---

## 4. Conclusion（結論・具体的改修箇所と提案コード）

以下の各ファイル・行番号に対して改修を実施することを提案する。

### 改修箇所 1: `app.py`
#### (1) 新5段階ランク定義への変更
- **対象**: `app.py` L20
  ```python
  # Before
  TARGET_RANK_OPTIONS = ["SS", "SSS", "SSS+", "SSS+ABFB", "AP"]
  
  # After
  TARGET_RANK_OPTIONS = ["S", "SS", "SSS", "SSS+", "AB+"]
  ```

#### (2) スコア取得時の新ランクフラグ代入
- **対象**: `app.py` L78-L83
  ```python
  # Before
  score_log.achieve_ss = score_val >= 990000
  score_log.achieve_sss = score_val >= 1000000
  score_log.achieve_sssp = score_val >= 1007500
  score_log.achieve_abfb = (score_val >= 1007500 and score_log.is_all_break and score_log.is_full_bell)
  score_log.achieve_ap = score_val == 1010000

  # After
  score_log.achieve_s = score_val >= 975000
  score_log.achieve_ss = score_val >= 990000
  score_log.achieve_sss = score_val >= 1000000
  score_log.achieve_sssp = score_val >= 1007500
  score_log.achieve_abp = (score_val >= 1007500 and score_log.is_all_break)
  ```

#### (3) リコメンドUIのマルチセレクト未選択時全対象化 ＆ 0〜100%スライダー化 ＆ クリア割合改称
- **対象**: `app.py` L219-L298
  ```python
  # Before:
  # target_ranks, level_filters, constant_range, current_rank_filters
  # win_rate_min_percent = st.number_input(...)
  # win_rate_max_percent = st.number_input(...)
  
  # After:
  with col_f1:
      target_ranks = st.multiselect(
          "目標ランク（複数選択可、未選択時は全対象）",
          options=TARGET_RANK_OPTIONS,
          default=["SSS"],
          key="filter_target_rank"
      )
      level_filters = st.multiselect(
          "レベル絞り込み（複数選択可、未選択時は全対象）",
          options=LEVEL_OPTIONS,
          default=[],
          key="filter_level"
      )
  with col_f2:
      constant_range = st.slider(
          "譜面定数範囲",
          min_value=MIN_TARGET_CONSTANT,
          max_value=15.7,
          value=(MIN_TARGET_CONSTANT, 15.7),
          step=0.1,
          key="filter_constant_range"
      )
      current_rank_filters = st.multiselect(
          "現在の達成ランク（複数選択可、未選択時は全対象）",
          options=["未S", "S止まり", "SS止まり", "SSS止まり", "SSS+止まり", "AB+"],
          default=[],
          key="filter_current_rank"
      )

  col_w1, col_sort = st.columns([2, 1])
  with col_w1:
      clear_rate_range = st.slider(
          "クリア割合範囲（%）",
          min_value=0,
          max_value=100,
          value=(30, 70),
          step=1,
          key="filter_clear_rate_range"
      )
  with col_sort:
      sort_key = st.selectbox(
          "並び順",
          options=["適正順", "クリア割合が高い順", "現在ランク順", "目標ランク順"],
      )

  param_level = level_filters or None
  param_current_rank = current_rank_filters or None
  const_min, const_max = constant_range
  clear_rate_min, clear_rate_max = clear_rate_range

  # 未選択時は全対象とするフォールバック
  selected_targets = target_ranks if target_ranks else TARGET_RANK_OPTIONS

  recommender = OPIRecommender(DB_FILE)
  recs = []
  for target_rank in selected_targets:
      recs.extend(recommender.get_recommendations(
          user_id=uid,
          player_opi=recommendation_opi,
          target_rank=target_rank,
          level=param_level,
          chart_constant_min=const_min,
          chart_constant_max=const_max,
          current_rank=param_current_rank,
          win_rate_min=clear_rate_min / 100.0,
          win_rate_max=clear_rate_max / 100.0,
          limit=200,
      ))
  ```

#### (4) リコメンド一覧の表示文言
- **対象**: `app.py` L301-L314
  ```python
  # '勝率' -> 'クリア割合' へ変更
  df_recs['クリア割合'] = (df_recs['probability'] * 100).round(1).astype(str) + '%'
  display_cols = ["楽曲名", "難易度", "レベル", "定数", "現在の達成状況", "目標ランク", "目標OPI", "クリア割合"]
  ```

#### (5) タブ拡張と「マイOPI難易度表」の実装
- **対象**: `app.py` L211 および L351以降
  ```python
  tab1, tab2, tab3, tab4 = st.tabs(["🎯 リコメンド楽曲", "📊 統計・分布図", "📜 OPI難易度表", "⭐ マイOPI難易度表"])
  ```
  `tab4` において、`player_scores` の辞書 `{s.chart_id: s for s in player_scores}` を作成し、各セルで：
  ```python
  is_achieved = recommender._is_target_achieved(user_score_log, diff_target_rank)
  if is_achieved:
      bg_color = "#e8f5e9"
      border_color = "#4caf50"
      badge = "<span style='color:#2e7d32; font-weight:bold;'>[達成済]</span>"
  else:
      bg_color = "#f8f9fa"
      border_color = "#dee2e6"
      badge = "<span style='color:#757575;'>[未達成]</span>"

  card_html = f"""
  <div style="background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 6px; padding: 8px; margin-bottom: 8px;">
      <div style="font-weight: bold; font-size: 0.95em;">{row['楽曲名']}</div>
      <div style="font-size: 0.8em; color: #555;">
          {row['難易度']} Lv.{row['レベル']} (定数 {row['定数']:.1f})<br/>
          適正OPI: <b>{row[opi_column]:.1f}</b> {badge}
      </div>
  </div>
  """
  st.markdown(card_html, unsafe_allow_html=True)
  ```

#### (6) Plotly による動的散布図の実装
- **対象**: `app.py` L339-L350
  ボタン押下を待たずに即時描画：
  ```python
  st.subheader("レーティング別 総合OPI動的分布図")
  fig = vis.create_distribution_figure(
      player_rating=player.rating,
      player_opi=standard_opi,
      player_name=player.player_name
  )
  st.plotly_chart(fig, use_container_width=True)
  ```

---

### 改修箇所 2: `src/visualizer/visualizer.py`
`create_distribution_figure` メソッドの追加：
```python
import plotly.graph_objects as go

def create_distribution_figure(
    self,
    player_rating: Optional[float] = None,
    player_opi: Optional[float] = None,
    player_name: str = "あなた"
) -> go.Figure:
    df = self.load_player_data()
    df = df.dropna(subset=['rating', 'total_opi']).copy()
    df = df[np.isfinite(df['rating']) & np.isfinite(df['total_opi']) & (df['rating'] >= 17.75)].copy()

    fig = go.Figure()

    # 全プレイヤーの散布図
    fig.add_trace(go.Scatter(
        x=df['rating'],
        y=df['total_opi'],
        mode='markers',
        marker=dict(size=6, color='rgba(31, 119, 180, 0.45)'),
        name='登録プレイヤー',
        hovertemplate='Rating: %{x:.2f}<br>OPI: %{y:.1f}<extra></extra>'
    ))

    # 選択ユーザーのハイライト
    if player_rating is not None and player_opi is not None:
        fig.add_trace(go.Scatter(
            x=[player_rating],
            y=[player_opi],
            mode='markers+text',
            marker=dict(size=14, color='crimson', symbol='star', line=dict(width=2, color='white')),
            name=f"{player_name} (現在地)",
            text=[f"★ {player_name}"],
            textposition="top center",
            hovertemplate=f"<b>{player_name}</b><br>Rating: %{{x:.2f}}<br>総合OPI: %{{y:.1f}}<extra></extra>"
        ))

    fig.update_layout(
        title="レーティング vs 総合OPI 分布図",
        xaxis_title="レーティング",
        yaxis_title="総合OPI",
        template="plotly_white",
        hovermode="closest",
        margin=dict(l=40, r=40, t=50, b=40)
    )
    return fig
```

---

### 改修箇所 3: `requirements.txt`
`plotly` を追加：
```txt
aiohttp
beautifulsoup4
pandas
numpy
scipy
matplotlib
seaborn
SQLAlchemy
streamlit
plotly
```

---

## 5. Verification Method（独立検証方法）

実装完了後、以下の手順・コマンドにより独立検証可能である。

1. **WebUI統合テストの実行**:
   ```bash
   .venv\Scripts\pytest.exe tests/test_m3_webui_integration.py -v
   ```
   - `TARGET_RANK_OPTIONS` が新ランクとなり、AST検査をパスすること。
   - `build_user_achievements` の成否ベクトルが新5段階ランク（S, SS, SSS, SSS+, AB+）で生成され、テストが全てパスすること。

2. **Streamlit アプリケーションの起動と画面検証**:
   ```bash
   .venv\Scripts\streamlit.exe run app.py
   ```
   - ID `10605` で検索実行。
   - **R1検証**: 目標ランク選択、現在ランク選択に新5段階ランク（S, SS, SSS, SSS+, AB+）が表示されていること。
   - **R2検証**:
     - レベル・目標ランクを未選択（空）にした際、エラーにならず全対象でリコメンドが表示されること。
     - 「クリア割合範囲（%）」スライダーが 0〜100% で動作し、テーブル列名およびソート名が「クリア割合」となっていること。
   - **R3検証**:
     - 「OPI難易度表」が 100 OPIごとに降順でグリッド表示されていること。
     - 「マイOPI難易度表」タブを開いた際、ユーザー達成済みの楽曲セルが緑色にハイライトされ、未達成セルと明確に区別できること。
   - **R4検証**:
     - 「統計・分布図」タブに Plotly インタラクティブ散布図が表示され、ID 10605 の現在位置（Rating, OPI）が赤い星マーカーでハイライトされていること。
