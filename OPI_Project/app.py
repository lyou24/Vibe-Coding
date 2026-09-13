import streamlit as st
import asyncio
import os
import pandas as pd
from src.crawler.ongeki_crawler import OngekiCrawler
from src.analyzer.opi_calculator import (
    MIN_ELIGIBLE_SCORE,
    MIN_TARGET_CONSTANT,
    OPICalculator,
)
from src.database.models import init_db, get_session_maker, Player, ScoreLog, Chart
from src.recommender.recommender import OPIRecommender
from src.visualizer.visualizer import OPIVisualizer

st.set_page_config(page_title="OPI System", layout="wide")

DB_FILE = os.path.join(os.path.dirname(__file__), "data", "opi_database.sqlite")
engine = init_db(DB_FILE)
Session = get_session_maker(engine)
TARGET_RANK_OPTIONS = ["SS", "SSS", "SSS+", "SSS+ABFB", "AP"]
LEVEL_OPTIONS = ["14", "14+", "15", "15+"]

# --- バックエンド処理ラッパー ---
async def fetch_and_analyze_user(user_id: int, force: bool = False):
    """ユーザーデータを収集し、OPIを算出する（安全アトミック更新・5目標ランク統合最尤推定）"""
    session = Session()
    crawler = OngekiCrawler()
    calc = OPICalculator()
    
    try:
        player_db = session.query(Player).filter_by(user_id=user_id).first()
        last_crawled_at = player_db.log_updated_at if player_db else None
        
        with st.spinner(f"OngekiScoreLog からユーザー {user_id} のデータを取得中..."):
            profile = await crawler.fetch_user_profile(user_id, last_crawled_at=last_crawled_at, force=force)
            
            if profile:
                scores = await crawler.fetch_user_scores(user_id)
                # 安全アトミック更新: プロフィールとスコアの両方が取得できた場合のみDBにコミット
                if scores is not None and len(scores) > 0:
                    if not player_db:
                        player_db = Player(user_id=user_id)
                        session.add(player_db)
                    player_db.player_name = profile['player_name']
                    player_db.rating = profile['rating']
                    player_db.log_updated_at = profile['updated_at']

                    charts = session.query(Chart).all()
                    chart_by_id = {c.chart_id: c for c in charts}
                    chart_by_title_diff = {
                        (c.title, c.difficulty.name if hasattr(c.difficulty, 'name') else str(c.difficulty)): c 
                        for c in charts
                    }
                    matched_chart_ids = set()

                    for s in scores:
                        chart = None
                        # 1. chart_id による照合
                        if s.get('chart_id'):
                            chart = chart_by_id.get(s['chart_id'])
                        # 2. (title, difficulty) による照合
                        if not chart and 'title' in s and 'difficulty' in s:
                            chart = chart_by_title_diff.get((s['title'], s['difficulty']))

                        if not chart:
                            continue

                        matched_chart_ids.add(chart.chart_id)
                        score_log = session.query(ScoreLog).filter_by(user_id=user_id, chart_id=chart.chart_id).first()
                        if not score_log:
                            score_log = ScoreLog(user_id=user_id, chart_id=chart.chart_id)
                            session.add(score_log)
                        
                        score_val = s['score']
                        score_log.score = score_val
                        score_log.is_all_break = s.get('is_all_break', False)
                        score_log.is_full_bell = s.get('is_full_bell', False)
                        score_log.achieve_ss = score_val >= 990000
                        score_log.achieve_sss = score_val >= 1000000
                        score_log.achieve_sssp = score_val >= 1007500
                        score_log.achieve_abfb = (score_val >= 1007500 and score_log.is_all_break and score_log.is_full_bell)
                        score_log.achieve_ap = score_val == 1010000

                    if matched_chart_ids:
                        session.query(ScoreLog).filter(
                            ScoreLog.user_id == user_id,
                            ~ScoreLog.chart_id.in_(matched_chart_ids),
                        ).delete(synchronize_session=False)
                        session.commit()
                        st.sidebar.success(
                            f"ユーザー {user_id} のデータを更新しました"
                            f"（対象譜面 {len(matched_chart_ids)} 件）。"
                        )
                    else:
                        session.rollback()
                        st.sidebar.warning(
                            "取得スコアを譜面マスタへ1件も照合できなかったため、更新を中断しました。"
                        )
                else:
                    session.rollback()
                    st.sidebar.warning(f"ユーザー {user_id} のスコア取得に失敗したか、スコアデータが存在しませんでした。差分閉塞防止のため更新を中断しました。")
            else:
                st.sidebar.info(f"ユーザー {user_id} の新規更新はありませんでした（スキップ）。強制更新する場合は「強制更新」にチェックを入れてください。")
                
        with st.spinner("OPIを算出中..."):
            # 5段階全目標ランク統合最尤推定
            player_db = session.query(Player).filter_by(user_id=user_id).first()
            if player_db:
                charts = session.query(Chart).all()
                scores = session.query(ScoreLog).filter_by(user_id=user_id).all()
                achievements = calc.build_user_achievements(
                    charts,
                    scores,
                    min_score=None,
                    min_chart_constant=MIN_TARGET_CONSTANT,
                )
                if achievements:
                    est_opi = calc.estimate_user_opi(achievements, initial_theta=player_db.total_opi or 1500.0)
                    player_db.total_opi = est_opi
                    session.commit()
    finally:
        session.close()
        await crawler.close()

# --- UI構築 ---
st.title("オンゲキ OPI (Ongeki Power Indicator) システム")

st.sidebar.header("プレイヤー検索")
user_input = st.sidebar.text_input("OngekiScoreLog ユーザーID", "10605")
force_update = st.sidebar.checkbox("強制更新（キャッシュバイパス）", value=False)
opi_policy = st.sidebar.radio(
    "リコメンドに使うOPI",
    options=["全プレイ（標準）", "AAA以上（試験補正）"],
    index=0,
    help="AAA以上は『一度触っただけ』の低スコアを除外する試験値です。対象曲の選択バイアスを含みます。",
)
search_button = st.sidebar.button("検索 / 更新")

if search_button:
    if user_input.isdigit():
        uid = int(user_input)
        # クローリングとOPI計算を同期的に実行
        asyncio.run(fetch_and_analyze_user(uid, force=force_update))
    else:
        st.sidebar.error("有効な数値のIDを入力してください。")

# --- メインコンテンツの表示 ---
if user_input.isdigit():
    uid = int(user_input)
    session = Session()
    player = session.query(Player).filter_by(user_id=uid).first()
    
    if player:
        calc = OPICalculator()
        eligible_charts = session.query(Chart).filter(
            Chart.chart_constant >= MIN_TARGET_CONSTANT
        ).all()
        player_scores = session.query(ScoreLog).filter_by(user_id=uid).all()
        all_achievements = calc.build_user_achievements(
            eligible_charts,
            player_scores,
            min_score=None,
        )
        qualified_achievements = calc.build_user_achievements(
            eligible_charts,
            player_scores,
            min_score=MIN_ELIGIBLE_SCORE,
        )
        standard_opi = (
            calc.estimate_user_opi(all_achievements, initial_theta=player.total_opi or 1500.0)
            if all_achievements
            else player.total_opi
        )
        qualified_opi = (
            calc.estimate_user_opi(qualified_achievements, initial_theta=standard_opi or 1500.0)
            if qualified_achievements
            else None
        )
        scored_chart_count = len({item["chart_id"] for item in all_achievements})
        qualified_chart_count = len({item["chart_id"] for item in qualified_achievements})
        coverage = (
            qualified_chart_count / scored_chart_count * 100
            if scored_chart_count
            else 0.0
        )
        recommendation_opi = (
            qualified_opi
            if opi_policy == "AAA以上（試験補正）" and qualified_opi is not None
            else standard_opi
        )

        # プロフィールセクション
        st.header(f"👤 {player.player_name} さんのデータ")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("レーティング", f"{player.rating:.2f}" if player.rating else "N/A")
        col2.metric("総合OPI（標準）", f"{standard_opi:.1f}" if standard_opi else "N/A")
        col3.metric("総合OPI（AAA以上・試験）", f"{qualified_opi:.1f}" if qualified_opi else "N/A")
        col4.metric("試験値の対象率", f"{coverage:.1f}%")
        st.caption(
            f"対象は譜面定数{MIN_TARGET_CONSTANT:.1f}以上。試験値はAAA以上の "
            f"{qualified_chart_count}/{scored_chart_count}譜面を使用し、標準値はDBへ保存します。"
        )
        st.caption(
            "最終データ更新: "
            + (player.log_updated_at.strftime("%Y-%m-%d") if player.log_updated_at else "N/A")
        )
        
        st.divider()

        # タブで情報を切り替え
        tab1, tab2, tab3 = st.tabs(["🎯 リコメンド楽曲", "📊 統計・分布図", "📜 OPI難易度表"])

        with tab1:
            st.subheader("おすすめの目標楽曲")
            
            # 多次元フィルターUI
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                target_ranks = st.multiselect(
                    "目標ランク（複数選択可）",
                    options=TARGET_RANK_OPTIONS,
                    default=["SSS"],
                    key="filter_target_rank"
                )
                level_filters = st.multiselect(
                    "レベル絞り込み（複数選択可）",
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
                    "現在の達成ランク（複数選択可）",
                    options=["未SS", "SS", "SSS", "SSS+", "SSS+ABFB", "AP"],
                    default=[],
                    key="filter_current_rank"
                )

            col_w1, col_w2, col_sort = st.columns(3)
            with col_w1:
                win_rate_min_percent = st.number_input(
                    "勝率 Min（%）", min_value=0.0, max_value=100.0, value=30.0, step=1.0
                )
            with col_w2:
                win_rate_max_percent = st.number_input(
                    "勝率 Max（%）", min_value=0.0, max_value=100.0, value=70.0, step=1.0
                )
            with col_sort:
                sort_key = st.selectbox(
                    "並び順",
                    options=["適正順", "勝率が高い順", "現在ランク順", "目標ランク順"],
                )

            param_level = level_filters or None
            param_current_rank = current_rank_filters or None
            const_min, const_max = constant_range

            recommender = OPIRecommender(DB_FILE)
            recs = []
            for target_rank in target_ranks:
                recs.extend(recommender.get_recommendations(
                    user_id=uid,
                    player_opi=recommendation_opi,
                    target_rank=target_rank,
                    level=param_level,
                    chart_constant_min=const_min,
                    chart_constant_max=const_max,
                    current_rank=param_current_rank,
                    win_rate_min=win_rate_min_percent / 100,
                    win_rate_max=win_rate_max_percent / 100,
                    limit=200,
                ))

            current_rank_order = {
                "未SS": 0,
                "SS止まり": 1,
                "SSS止まり": 2,
                "SSS+止まり": 3,
                "ABFB止まり": 4,
                "AP": 5,
            }
            target_rank_order = {rank: index for index, rank in enumerate(TARGET_RANK_OPTIONS)}
            if sort_key == "勝率が高い順":
                recs.sort(key=lambda item: item["probability"], reverse=True)
            elif sort_key == "現在ランク順":
                recs.sort(key=lambda item: current_rank_order.get(item["current_rank"], 99))
            elif sort_key == "目標ランク順":
                recs.sort(key=lambda item: target_rank_order.get(item["target_rank"], 99))
            else:
                recs.sort(key=lambda item: item["opi_diff"])
            
            if recs:
                df_recs = pd.DataFrame(recs)
                df_recs['勝率'] = (df_recs['probability'] * 100).round(1).astype(str) + '%'
                df_recs['目標OPI'] = df_recs['target_opi'].round(1)
                df_recs = df_recs.rename(columns={
                    "title": "楽曲名", 
                    "difficulty": "難易度",
                    "level": "レベル", 
                    "constant": "定数", 
                    "current_status": "現在の達成状況",
                    "target_rank": "目標ランク",
                })
                display_cols = ["楽曲名", "難易度", "レベル", "定数", "現在の達成状況", "目標ランク", "目標OPI", "勝率"]
                valid_cols = [c for c in display_cols if c in df_recs.columns]
                st.dataframe(df_recs[valid_cols], use_container_width=True)
            else:
                st.info("データが不足しているか、適正範囲の楽曲が見つかりませんでした。フィルター条件を調整してみてください。")
                
        with tab2:
            st.subheader("レーティング別 総合OPI目標値および分布統計表")
            st.caption("※ 要件定義書 3.2 基準値（各レーティング基準値 ±0.25 帯域における総合OPIの分布統計）")
            df_target_stats = OPIVisualizer.get_target_distribution_table()
            st.dataframe(df_target_stats, use_container_width=True)

            with st.expander("💡 レーティング別OPI分析の示唆（目標水準ガイド）", expanded=True):
                st.markdown("""
                - **レート18.0到達の目安**: 総合OPI 約 **1480**（定数14.0のSSS〜SSS+安定ライン）
                - **レート19.0到達の目安**: 総合OPI 約 **1790超**（定数14後半のSSS+、定数15のSSSライン）
                - **レート20.0以上（トップ層）**: 総合OPI 約 **2070超**（定数15+のSSS〜SSS+、14+帯のAP・ABFB安定）
                - **バラつき（IQR）**: 同じレート帯でもプレイヤーの傾向（単曲詰め型 vs 広く触る型）により上下に約60〜110程度の差が存在します。
                """)

            vis = OPIVisualizer(DB_FILE)
            df_current_stats = vis.calculate_current_distribution_table()
            if not df_current_stats.empty and len(df_current_stats) > 0:
                with st.expander("📊 現在のDB登録プレイヤー実測統計表", expanded=False):
                    st.dataframe(df_current_stats, use_container_width=True)

            st.divider()
            st.subheader("レーティング別 総合OPI分布図")
            img_path = os.path.join(os.path.dirname(__file__), "data", "opi_distribution.png")
            
            if st.button("分布図を最新データで更新"):
                with st.spinner("グラフを生成中..."):
                    vis.create_distribution_plot(img_path)
            
            if os.path.exists(img_path):
                st.image(img_path, use_container_width=True)
            else:
                st.info("分布図がまだ生成されていません。「分布図を最新データで更新」ボタンを押してください。")
                
        with tab3:
            st.subheader("OPI 難易度表")
            diff_target_rank = st.selectbox(
                "目標ランク選択",
                options=TARGET_RANK_OPTIONS,
                index=0,
                key="diff_target_rank_select"
            )
            
            calc = OPICalculator()
            charts = session.query(Chart).filter(
                Chart.chart_constant >= MIN_TARGET_CONSTANT
            ).order_by(Chart.chart_constant.asc(), Chart.title.asc()).all()
            if charts:
                chart_data = []
                for c in charts:
                    x, y = calc.get_chart_rank_params(c, diff_target_rank)
                    if x is not None:
                        diff_name = c.difficulty.name if hasattr(c.difficulty, 'name') else str(c.difficulty)
                        chart_data.append({
                            "楽曲名": c.title,
                            "難易度": diff_name,
                            "レベル": c.level,
                            "定数": c.chart_constant,
                            f"{diff_target_rank} 適正OPI": round(x, 1),
                            "個人差度": round(y, 1)
                        })
                
                if chart_data:
                    df_charts = pd.DataFrame(chart_data)
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

                    with st.expander("表形式で表示"):
                        st.dataframe(df_charts.drop(columns=["OPI帯"]), use_container_width=True)
                else:
                    st.info(f"{diff_target_rank} の難易度データがありません。")
            else:
                st.info("難易度表のデータがありません。")

    else:
        st.warning("ユーザーデータが見つかりません。サイドバーから「検索 / 更新」を実行してください。")
        
    session.close()
