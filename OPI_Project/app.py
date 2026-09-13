import streamlit as st
import asyncio
import os
import pandas as pd
from src.crawler.ongeki_crawler import OngekiCrawler
from src.analyzer.opi_calculator import OPICalculator
from src.database.models import init_db, get_session_maker, Player, ScoreLog, Chart
from src.recommender.recommender import OPIRecommender
from src.visualizer.visualizer import OPIVisualizer

st.set_page_config(page_title="OPI System", layout="wide")

DB_FILE = os.path.join(os.path.dirname(__file__), "data", "opi_database.sqlite")
engine = init_db(DB_FILE)
Session = get_session_maker(engine)

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

                    session.commit()
                    st.sidebar.success(f"ユーザー {user_id} のデータを更新しました（スコア {len(scores)} 件）。")
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
                achievements = calc.build_user_achievements(charts, scores)
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
        # プロフィールセクション
        st.header(f"👤 {player.player_name} さんのデータ")
        col1, col2, col3 = st.columns(3)
        col1.metric("レーティング", f"{player.rating:.2f}" if player.rating else "N/A")
        col2.metric("総合OPI (推定地力)", f"{player.total_opi:.1f}" if player.total_opi else "N/A")
        col3.metric("最終データ更新", player.log_updated_at.strftime("%Y-%m-%d") if player.log_updated_at else "N/A")
        
        st.divider()

        # タブで情報を切り替え
        tab1, tab2, tab3 = st.tabs(["🎯 リコメンド楽曲", "📊 統計・分布図", "📜 OPI難易度表"])

        with tab1:
            st.subheader("おすすめの目標楽曲 (勝率 30%〜70% 帯)")
            
            # 多次元フィルターUI
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                target_rank = st.selectbox(
                    "目標ランク",
                    options=["SSS", "SS", "SSS+", "SSS+ABFB", "AP"],
                    index=0,
                    key="filter_target_rank"
                )
                level_filter = st.selectbox(
                    "レベル絞り込み",
                    options=["すべて", "13+", "14", "14+", "15", "15+"],
                    index=0,
                    key="filter_level"
                )
            with col_f2:
                constant_range = st.slider(
                    "譜面定数範囲",
                    min_value=13.7,
                    max_value=16.0,
                    value=(13.7, 16.0),
                    step=0.1,
                    key="filter_constant_range"
                )
                current_rank_filter = st.selectbox(
                    "現在の達成ランクで絞り込み",
                    options=["なし", "SS", "SSS", "SSS+", "SSS+ABFB", "AP"],
                    index=0,
                    key="filter_current_rank"
                )

            param_level = None if level_filter == "すべて" else level_filter
            param_current_rank = None if current_rank_filter == "なし" else current_rank_filter
            const_min, const_max = constant_range

            recommender = OPIRecommender(DB_FILE)
            recs = recommender.get_recommendations(
                user_id=uid,
                target_rank=target_rank,
                level=param_level,
                chart_constant_min=const_min,
                chart_constant_max=const_max,
                current_rank=param_current_rank,
                limit=15
            )
            
            if recs:
                df_recs = pd.DataFrame(recs)
                df_recs['勝率'] = (df_recs['probability'] * 100).round(1).astype(str) + '%'
                df_recs['目標OPI'] = df_recs['target_opi'].round(1)
                df_recs = df_recs.rename(columns={
                    "title": "楽曲名", 
                    "difficulty": "難易度",
                    "level": "レベル", 
                    "constant": "定数", 
                    "current_status": "現在の達成状況"
                })
                display_cols = ["楽曲名", "難易度", "レベル", "定数", "目標OPI", "勝率", "現在の達成状況"]
                valid_cols = [c for c in display_cols if c in df_recs.columns]
                st.dataframe(df_recs[valid_cols], use_container_width=True)
            else:
                st.info("データが不足しているか、適正範囲の楽曲が見つかりませんでした。フィルター条件を調整してみてください。")
                
        with tab2:
            st.subheader("レーティング別 総合OPI分布 (±0.25)")
            vis = OPIVisualizer(DB_FILE)
            img_path = os.path.join(os.path.dirname(__file__), "data", "opi_distribution.png")
            
            if st.button("分布図を最新データで更新"):
                with st.spinner("グラフを生成中..."):
                    vis.create_distribution_plot(img_path)
            
            if os.path.exists(img_path):
                st.image(img_path, use_container_width=True)
            else:
                st.info("分布図がまだ生成されていません。更新ボタンを押してください。")
                
        with tab3:
            st.subheader("OPI 難易度表")
            diff_target_rank = st.selectbox(
                "目標ランク選択",
                options=["SSS", "SS", "SSS+", "SSS+ABFB", "AP"],
                index=0,
                key="diff_target_rank_select"
            )
            
            calc = OPICalculator()
            charts = session.query(Chart).order_by(Chart.chart_constant.asc(), Chart.title.asc()).all()
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
                    df_charts = df_charts.sort_values(by=f"{diff_target_rank} 適正OPI", ascending=True)
                    st.dataframe(df_charts, use_container_width=True)
                else:
                    st.info(f"{diff_target_rank} の難易度データがありません。")
            else:
                st.info("難易度表のデータがありません。")

    else:
        st.warning("ユーザーデータが見つかりません。サイドバーから「検索 / 更新」を実行してください。")
        
    session.close()
