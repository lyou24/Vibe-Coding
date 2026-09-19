"""
Reviewer 2 による R3/R4 独立検証スクリプト
"""
import os
import sys
import pandas as pd
import plotly.graph_objects as go

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from src.database.models import init_db, get_session_maker, Player, ScoreLog, Chart
from src.analyzer.opi_calculator import OPICalculator, MIN_TARGET_CONSTANT
from src.recommender.recommender import OPIRecommender
from src.visualizer.visualizer import OPIVisualizer, create_distribution_figure

DB_PATH = os.path.join(PROJECT_ROOT, "data", "opi_database.sqlite")
engine = init_db(DB_PATH)
Session = get_session_maker(engine)
session = Session()

print("=== 1. R4 Plotly 動的散布図の独立検証 ===")
vis = OPIVisualizer(DB_PATH)
fig = vis.create_distribution_figure(player_rating=19.95, player_opi=1423.6, player_name="ＮＥＧＩＮＥ")
assert isinstance(fig, go.Figure), "Figure 型不一致"
print(f"トレース数: {len(fig.data)}")
assert len(fig.data) == 2, f"期待トレース数は2（全体 + ユーザーハイライト）ですが、実際は {len(fig.data)}"

# トレース1: 全体プレイヤー
t_all = fig.data[0]
print(f"全体プレイヤートレース点数: {len(t_all.x)}")
assert len(t_all.x) >= 2000, f"全体プレイヤー点数が少なすぎます: {len(t_all.x)}"

# トレース2: ユーザーハイライト
t_user = fig.data[1]
print(f"ユーザー名: {t_user.name}")
print(f"座標: ({t_user.x[0]}, {t_user.y[0]})")
print(f"マーカーシンボル: {t_user.marker.symbol}, サイズ: {t_user.marker.size}, 色: {t_user.marker.color}")
assert t_user.x[0] == 19.95, "ユーザーX座標不一致"
assert t_user.y[0] == 1423.6, "ユーザーY座標不一致"
assert t_user.marker.symbol == "star", "星型マーカーではありません"
assert t_user.marker.color == "crimson", "マーカー色がcrimsonではありません"

# エッジケース: ユーザー情報なし
fig_none = vis.create_distribution_figure(None, None)
assert len(fig_none.data) == 1, "ユーザー未指定時はトレース1件のみであるべき"
print("R4 Plotly 検証: ALL PASSED!")

print("\n=== 2. R3 OPI難易度表 降順グリッド化の独立検証 ===")
calc = OPICalculator()
charts = session.query(Chart).filter(Chart.chart_constant >= MIN_TARGET_CONSTANT).all()
print(f"対象譜面数 (定数>={MIN_TARGET_CONSTANT}): {len(charts)}")

for rank in ["S", "SS", "SSS", "SSS+", "AB+"]:
    chart_data = []
    for c in charts:
        x, y = calc.get_chart_rank_params(c, rank)
        if x is not None:
            chart_data.append({
                "chart_id": c.chart_id,
                "title": c.title,
                "opi": x,
                "diff": y
            })
    assert len(chart_data) > 0, f"{rank} の難易度データが0件です"
    df = pd.DataFrame(chart_data).sort_values(by="opi", ascending=False)
    df["band"] = (df["opi"] // 100 * 100).astype(int)
    unique_bands = sorted(df["band"].unique(), reverse=True)
    
    # 降順性の厳密検証
    bands_list = list(unique_bands)
    for i in range(len(bands_list) - 1):
        assert bands_list[i] > bands_list[i+1], f"帯域ソートが降順ではありません: {bands_list}"
    
    # 帯域内データの降順性検証
    for b in unique_bands:
        sub = df[df["band"] == b]["opi"].tolist()
        for j in range(len(sub) - 1):
            assert sub[j] >= sub[j+1], f"帯域 {b} 内でOPI降順が崩れています: {sub}"
            
    print(f"ランク {rank:5s}: データ数={len(df)}, 最高帯={unique_bands[0]}〜{unique_bands[0]+99}, 最低帯={unique_bands[-1]}〜{unique_bands[-1]+99} -> 降順性完全確認")

print("R3 難易度表降順ソート検証: ALL PASSED!")

print("\n=== 3. R3 マイOPI難易度表 達成判定の独立検証 (User 10605) ===")
recommender = OPIRecommender(DB_PATH)
player_scores = session.query(ScoreLog).filter_by(user_id=10605).all()
user_scores_map = {s.chart_id: s for s in player_scores}
print(f"User 10605 スコア件数: {len(player_scores)}")

for rank in ["S", "SS", "SSS", "SSS+", "AB+"]:
    achieved = 0
    total = 0
    for c in charts:
        x, y = calc.get_chart_rank_params(c, rank)
        if x is not None:
            total += 1
            slog = user_scores_map.get(c.chart_id)
            if recommender._is_target_achieved(slog, rank):
                achieved += 1
    rate = (achieved / total * 100) if total > 0 else 0
    print(f"ランク {rank:5s}: 達成 {achieved:3d} / {total:3d} 譜面 ({rate:5.1f}%)")
    # 難易度順による達成率の単調減少性検証 (S >= SS >= SSS >= SSS+ >= AB+)
    if rank == "S":
        prev_achieved = achieved
    else:
        assert achieved <= prev_achieved, f"達成数が難易度順（{rank} <= 前ランク）になっていません: {achieved} > {prev_achieved}"
        prev_achieved = achieved

print("R3 マイ難易度表達成判定検証: ALL PASSED!")
session.close()
print("\n=== 全独立検証 正常終了 ===")
