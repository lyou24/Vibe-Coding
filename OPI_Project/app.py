import sys
import os

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import streamlit as st
import asyncio
import hashlib
import html
import json
import sqlite3
from datetime import date
import pandas as pd
from src.crawler.ongeki_crawler import OngekiCrawler
from src.analyzer.opi_calculator import (
    MIN_ELIGIBLE_SCORE,
    MIN_TARGET_CONSTANT,
    OPICalculator,
    is_solo_version,
)
from src.database.models import init_db, get_session_maker, Player, ScoreLog, Chart
from src.database.calibrated_parameters import sync_latest_calibrated_parameters
from src.recommender.recommender import OPIRecommender
from src.export.full_image_export import build_full_hd_image
from src.visualizer.visualizer import OPIVisualizer

st.set_page_config(page_title="Ongeki Power Indicator", layout="wide", initial_sidebar_state="auto")

# モバイル（iPhone等）向けのレスポンシブCSS調整
st.markdown("""
<style>
    /* モバイル表示時の余白最適化 */
    @media (max-width: 768px) {
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 2rem !important;
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }
        /* 入力フォームのフォントサイズ調整（iOSズーム防止） */
        input, select, textarea {
            font-size: 16px !important;
        }
        /* テーブルの横スクロール対応 */
        .stDataFrame, div[data-testid="stTable"] {
            overflow-x: auto !important;
            -webkit-overflow-scrolling: touch !important;
        }
        /* タブの視認性向上 */
        button[data-baseweb="tab"] {
            padding: 8px 12px !important;
            font-size: 14px !important;
        }
    }
</style>
""", unsafe_allow_html=True)

DB_FILE = os.path.join(os.path.dirname(__file__), "data", "opi_database.sqlite")
CALIBRATION_DB_FILE = os.path.join(os.path.dirname(__file__), "data", "opi_calibration.sqlite")
engine = init_db(DB_FILE)
Session = get_session_maker(engine)
try:
    calibration_sync = sync_latest_calibrated_parameters(CALIBRATION_DB_FILE, DB_FILE)
except Exception as calibration_error:
    calibration_sync = {
        "status": "error",
        "message": str(calibration_error),
        "run_id": None,
        "estimate_count": 0,
        "updated_count": 0,
    }
TARGET_RANK_OPTIONS = ["S", "SS", "SSS", "SSS+", "AB+"]
LEVEL_OPTIONS = ["14", "14+", "15", "15+"]
ACHIEVED_RANK_CARD_STYLES = {
    "S": {"background": "#2e7d32", "border": "#1b5e20", "text": "#ffffff"},
    "SS": {"background": "#1565c0", "border": "#0d47a1", "text": "#ffffff"},
    "SSS": {"background": "#c62828", "border": "#b71c1c", "text": "#ffffff"},
    "SSS+": {"background": "#f9a825", "border": "#f57f17", "text": "#111827"},
    "AB+": {"background": "#c2410c", "border": "#9a3412", "text": "#ffffff"},
}
CURRENT_RANK_TO_ACHIEVED_RANK = {
    "S止まり": "S",
    "SS止まり": "SS",
    "SSS止まり": "SSS",
    "SSS+止まり": "SSS+",
    "AB+": "AB+",
}


def load_chart_metadata():
    """再起動前の旧モデルでも、追加済み列から表示値を補完する。"""
    try:
        with sqlite3.connect(DB_FILE) as connection:
            return {
                chart_id: (version or "不明", genre or "不明")
                for chart_id, version, genre in connection.execute(
                    "SELECT chart_id, version, genre FROM charts"
                )
            }
    except sqlite3.DatabaseError:
        return {}


CHART_METADATA = load_chart_metadata()


def get_chart_metadata(chart):
    fallback_version, fallback_genre = CHART_METADATA.get(
        chart.chart_id, ("不明", "不明")
    )
    return (
        getattr(chart, "version", None) or fallback_version,
        getattr(chart, "genre", None) or fallback_genre,
    )


def render_image_export(title, settings, cards, filename_prefix, key):
    """一覧をフルHD 1枚のPNGとして生成する。"""
    signature = hashlib.sha256(
        json.dumps(
            {"title": title, "settings": settings, "cards": cards},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    state_key = f"{key}_full_hd_export"
    if st.button("🖼️ フルHD画像を作成", key=f"{key}_create_full_hd"):
        with st.spinner("1920×1080の画像を作成中..."):
            st.session_state[state_key] = {
                "signature": signature,
                "data": build_full_hd_image(
                    title=title,
                    settings=settings,
                    cards=cards,
                ),
            }

    export_png = st.session_state.get(state_key)
    if export_png and export_png["signature"] == signature:
        st.download_button(
            "⬇️ フルHD画像をダウンロード",
            data=export_png["data"],
            file_name=f"{filename_prefix}_{date.today():%Y%m%d}.png",
            mime="image/png",
            key=f"{key}_download_full_hd",
        )

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
                        score_log.achieve_s = score_val >= 975000
                        score_log.achieve_ss = score_val >= 990000
                        score_log.achieve_sss = score_val >= 1000000
                        score_log.achieve_sssp = score_val >= 1007500
                        score_log.achieve_abp = score_val >= 1010000

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
                charts = [
                    c for c in session.query(Chart).filter(
                        Chart.is_active == True
                    ).all()
                    if not is_solo_version(c.title)
                ]
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
st.title("Ongeki Power Indicator (OPI)")
if calibration_sync["status"] == "error":
    st.warning(f"校正済み譜面OPIの読み込みに失敗したため、既存値を使用します: {calibration_sync['message']}")
elif calibration_sync["status"] not in {"applied", "current"}:
    st.warning("完了済みの校正データが見つからないため、既存の譜面OPIを使用します。")

st.sidebar.header("プレイヤー検索")
user_input = st.sidebar.text_input("OngekiScoreLog ユーザーID", "")
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
        calc = OPICalculator()
        eligible_charts = [
            c for c in session.query(Chart).filter(
                Chart.chart_constant >= MIN_TARGET_CONSTANT,
                Chart.is_active == True,
            ).all()
            if not is_solo_version(c.title)
        ]
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
        recommendation_opi = qualified_opi

        # プロフィールセクション
        st.header(f"👤 {player.player_name} さんのデータ")
        col1, col2, col3 = st.columns(3)
        col1.metric("レーティング", f"{player.rating:.3f}" if player.rating else "N/A")
        col2.metric("リコメンドOPI（AAA以上）", f"{qualified_opi:.1f}" if qualified_opi else "N/A")
        col3.metric("AAA以上の対象率", f"{coverage:.1f}%")
        st.caption(
            f"対象は譜面定数{MIN_TARGET_CONSTANT:.1f}以上。リコメンドはAAA以上の "
            f"{qualified_chart_count}/{scored_chart_count}譜面から推定したOPIのみを使用します。"
        )
        st.caption(
            "最終データ更新: "
            + (player.log_updated_at.strftime("%Y-%m-%d") if player.log_updated_at else "N/A")
        )
        
        st.divider()

        # タブで情報を切り替え
        tab1, tab2, tab3, tab4 = st.tabs(["🎯 リコメンド楽曲", "📊 統計・分布図", "📜 OPI難易度表", "⭐ マイOPI難易度表"])

        with tab1:
            st.subheader("おすすめの目標楽曲")
            
            # 多次元フィルターUI
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                target_ranks = st.multiselect(
                    "目標ランク（複数選択可、未選択時は全対象）",
                    options=TARGET_RANK_OPTIONS,
                    default=[],
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
                    min_value=0.0,
                    max_value=100.0,
                    value=(30.0, 70.0),
                    step=1.0,
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
            effective_target_ranks = target_ranks or TARGET_RANK_OPTIONS

            recommender = OPIRecommender(DB_FILE)
            recs = []
            if recommendation_opi is not None:
                for target_rank in effective_target_ranks:
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

            current_rank_order = {
                "未S": 0,
                "S止まり": 1,
                "SS止まり": 2,
                "SSS止まり": 3,
                "SSS+止まり": 4,
                "AB+": 5,
            }
            target_rank_order = {rank: index for index, rank in enumerate(TARGET_RANK_OPTIONS)}
            if sort_key == "クリア割合が高い順":
                recs.sort(key=lambda item: item["probability"], reverse=True)
            elif sort_key == "現在ランク順":
                recs.sort(key=lambda item: current_rank_order.get(item["current_rank"], 99))
            elif sort_key == "目標ランク順":
                recs.sort(key=lambda item: target_rank_order.get(item["target_rank"], 99))
            else:
                recs.sort(key=lambda item: item["opi_diff"])

            for item in recs:
                fallback_version, fallback_genre = CHART_METADATA.get(
                    item["chart_id"], ("不明", "不明")
                )
                if not item.get("version") or item["version"] == "不明":
                    item["version"] = fallback_version
                if not item.get("genre") or item["genre"] == "不明":
                    item["genre"] = fallback_genre
            
            if recs:
                df_recs = pd.DataFrame(recs)
                df_recs['クリア割合'] = (df_recs['probability'] * 100).round(1).astype(str) + '%'
                df_recs['目標OPI'] = df_recs['target_opi'].round(1)
                df_recs = df_recs.rename(columns={
                    "title": "楽曲名",
                    "version": "バージョン",
                    "genre": "ジャンル",
                    "difficulty": "難易度",
                    "level": "レベル", 
                    "constant": "定数", 
                    "current_status": "現在の達成状況",
                    "target_rank": "目標ランク",
                })
                display_cols = ["楽曲名", "バージョン", "ジャンル", "難易度", "レベル", "定数", "現在の達成状況", "目標ランク", "目標OPI", "クリア割合"]
                valid_cols = [c for c in display_cols if c in df_recs.columns]
                st.dataframe(df_recs[valid_cols], use_container_width=True)

                recommendation_settings = [
                    f"プレイヤー: {player.player_name} / リコメンドOPI: {recommendation_opi:.1f}",
                    f"目標ランク: {', '.join(effective_target_ranks)}",
                    f"レベル: {', '.join(level_filters) if level_filters else '全対象'}",
                    f"譜面定数: {const_min:.1f}〜{const_max:.1f}",
                    f"現在ランク: {', '.join(current_rank_filters) if current_rank_filters else '全対象'}",
                    f"クリア割合: {clear_rate_min:.0f}%〜{clear_rate_max:.0f}% / 並び順: {sort_key}",
                ]
                recommendation_cards = [
                    {
                        "title": item["title"],
                        "metadata": f"{item.get('version', '不明')} / {item.get('genre', '不明')}",
                        "details": [
                            f"{item['difficulty']}  Lv.{item['level']}（定数 {item['constant']:.1f}） / 現在: {item['current_status']}",
                            f"目標 {item['target_rank']}・OPI {item['target_opi']:.1f} / クリア割合 {item['probability'] * 100:.1f}%",
                        ],
                        "summary": f"{item['difficulty']} Lv.{item['level']} / {item['target_rank']} OPI {item['target_opi']:.1f}",
                    }
                    for item in recs
                ]
                render_image_export(
                    "おすすめ目標楽曲リスト",
                    recommendation_settings,
                    recommendation_cards,
                    "opi_recommendations",
                    "recommendations",
                )
            elif recommendation_opi is None:
                st.info("AAA以上の対象スコアがないため、リコメンドOPIを推定できません。")
            else:
                st.info("データが不足しているか、適正範囲の楽曲が見つかりませんでした。フィルター条件を調整してみてください。")
                
        with tab2:
            st.subheader("レーティング別 総合OPI目標値および分布統計表")
            ability_run = OPIVisualizer.get_latest_calibrated_ability_run(CALIBRATION_DB_FILE)
            calibrated_player_data = OPIVisualizer.load_latest_calibrated_player_data(
                CALIBRATION_DB_FILE
            )
            df_target_stats = OPIVisualizer.build_distribution_table(calibrated_player_data)
            if ability_run is not None and not df_target_stats.empty:
                st.caption(
                    f"実プレイヤー再推定 run #{ability_run['run_id']}（親単曲run "
                    f"#{ability_run['parent_run_id']}）。譜面定数14.0以上・ソロver.除外・"
                    f"AAA以上のスコアのみ。推定可能 "
                    f"{ability_run['estimated_player_count']:,}/{ability_run['player_count']:,}人。"
                )
                st.dataframe(df_target_stats, use_container_width=True)
            else:
                st.warning("AAA以上条件のプレイヤーOPI再推定結果がありません。")

            st.divider()
            st.subheader("レーティング別 総合OPI動的分布図")
            vis = OPIVisualizer(DB_FILE)
            fig = vis.create_distribution_figure(
                player_rating=player.rating,
                player_opi=recommendation_opi,
                player_name=player.player_name,
                player_data=calibrated_player_data,
            )
            st.plotly_chart(fig, use_container_width=True)
                
        with tab3:
            st.subheader("OPI 難易度表")
            diff_target_rank = st.selectbox(
                "目標ランク選択",
                options=TARGET_RANK_OPTIONS,
                index=2,
                key="diff_target_rank_select"
            )
            
            calc = OPICalculator()
            charts = [
                c for c in session.query(Chart).filter(
                    Chart.chart_constant >= MIN_TARGET_CONSTANT,
                    Chart.is_active == True,
                ).order_by(Chart.chart_constant.asc(), Chart.title.asc()).all()
                if not is_solo_version(c.title)
            ]
            if charts:
                chart_data = []
                for c in charts:
                    x, y = calc.get_chart_rank_params(c, diff_target_rank)
                    if x is not None:
                        diff_name = c.difficulty.name if hasattr(c.difficulty, 'name') else str(c.difficulty)
                        version, genre = get_chart_metadata(c)
                        chart_data.append({
                            "楽曲名": c.title,
                            "バージョン": version,
                            "ジャンル": genre,
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

                    unique_bands = sorted(df_charts["OPI帯"].unique(), reverse=True)
                    for opi_band in unique_bands:
                        band_rows = df_charts[df_charts["OPI帯"] == opi_band]
                        st.markdown(f"### OPI {opi_band}〜{opi_band + 99}")
                        columns = st.columns(4)
                        for index, (_, row) in enumerate(band_rows.iterrows()):
                            with columns[index % 4]:
                                card_html = f"""
                                <div style="background-color: #f8f9fa; color: #1f2937; border: 1px solid #dee2e6; border-radius: 6px; padding: 8px; margin-bottom: 8px;">
                                    <div style="font-weight: bold; font-size: 0.95em; color: #111827;">{html.escape(str(row['楽曲名']))} <span style="font-weight: normal; font-size: 0.78em; color: #475569;">[{html.escape(str(row['バージョン']))} / {html.escape(str(row['ジャンル']))}]</span></div>
                                    <div style="font-size: 0.8em; color: #374151;">
                                        {row['難易度']} Lv.{row['レベル']} (定数 {row['定数']:.1f})<br/>
                                        適正OPI: <b>{row[opi_column]:.1f}</b> (個人差度 {row['個人差度']:.1f})
                                    </div>
                                </div>
                                """
                                st.markdown(card_html, unsafe_allow_html=True)

                    difficulty_cards = [
                        {
                            "title": row["楽曲名"],
                            "metadata": f"{row['バージョン']} / {row['ジャンル']}",
                            "details": [
                                f"{row['難易度']}  Lv.{row['レベル']}（定数 {row['定数']:.1f}）",
                                f"適正OPI {row[opi_column]:.1f} / 個人差度 {row['個人差度']:.1f}",
                            ],
                            "summary": f"{row['難易度']} Lv.{row['レベル']} / OPI {row[opi_column]:.1f}",
                        }
                        for _, row in df_charts.iterrows()
                    ]
                    render_image_export(
                        "OPI難易度表",
                        [
                            f"目標ランク: {diff_target_rank}",
                            f"対象: 譜面定数 {MIN_TARGET_CONSTANT:.1f}以上 / 全{len(df_charts)}譜面",
                        ],
                        difficulty_cards,
                        f"opi_difficulty_{diff_target_rank.lower().replace('+', 'p')}",
                        "difficulty_table",
                    )

                    with st.expander("表形式で表示"):
                        st.dataframe(df_charts.drop(columns=["OPI帯"]), use_container_width=True)
                else:
                    st.info(f"{diff_target_rank} の難易度データがありません。")
            else:
                st.info("難易度表のデータがありません。")

        with tab4:
            st.subheader("⭐ マイOPI難易度表（達成状況可視化）")
            my_diff_target_rank = st.selectbox(
                "目標ランク選択",
                options=TARGET_RANK_OPTIONS,
                index=2,
                key="my_diff_target_rank_select"
            )

            calc = OPICalculator()
            recommender = OPIRecommender(DB_FILE)
            user_scores_map = {s.chart_id: s for s in player_scores}

            charts = [
                c for c in session.query(Chart).filter(
                    Chart.chart_constant >= MIN_TARGET_CONSTANT,
                    Chart.is_active == True,
                ).order_by(Chart.chart_constant.asc(), Chart.title.asc()).all()
                if not is_solo_version(c.title)
            ]

            if charts:
                chart_data = []
                achieved_count = 0
                for c in charts:
                    x, y = calc.get_chart_rank_params(c, my_diff_target_rank)
                    if x is not None:
                        diff_name = c.difficulty.name if hasattr(c.difficulty, 'name') else str(c.difficulty)
                        version, genre = get_chart_metadata(c)
                        score_log = user_scores_map.get(c.chart_id)
                        is_achieved = recommender._is_target_achieved(score_log, my_diff_target_rank)
                        current_rank_category, _ = recommender._determine_current_rank(score_log)
                        current_achieved_rank = CURRENT_RANK_TO_ACHIEVED_RANK.get(current_rank_category)
                        if is_achieved:
                            achieved_count += 1
                        chart_data.append({
                            "chart_id": c.chart_id,
                            "楽曲名": c.title,
                            "バージョン": version,
                            "ジャンル": genre,
                            "難易度": diff_name,
                            "レベル": c.level,
                            "定数": c.chart_constant,
                            f"{my_diff_target_rank} 適正OPI": round(x, 1),
                            "個人差度": round(y, 1),
                            "達成状況": "達成済" if is_achieved else "未達成",
                            "現在ランク": current_achieved_rank or "未S",
                            "is_achieved": is_achieved,
                        })

                if chart_data:
                    total_charts = len(chart_data)
                    achieve_rate = (achieved_count / total_charts * 100) if total_charts > 0 else 0.0
                    col_m1, col_m2 = st.columns(2)
                    col_m1.metric(f"{my_diff_target_rank} 達成曲数", f"{achieved_count} / {total_charts} 譜面")
                    col_m2.metric(f"{my_diff_target_rank} 達成率", f"{achieve_rate:.1f}%")

                    df_my_charts = pd.DataFrame(chart_data)
                    df_my_charts = df_my_charts.sort_values(by=f"{my_diff_target_rank} 適正OPI", ascending=False)
                    opi_column = f"{my_diff_target_rank} 適正OPI"
                    df_my_charts["OPI帯"] = (df_my_charts[opi_column] // 100 * 100).astype(int)

                    unique_bands = sorted(df_my_charts["OPI帯"].unique(), reverse=True)
                    for opi_band in unique_bands:
                        band_rows = df_my_charts[df_my_charts["OPI帯"] == opi_band]
                        band_achieved = int(sum(band_rows["is_achieved"]))
                        st.markdown(f"### 【達成状況 {band_achieved}/{len(band_rows)}】 適正帯域 {opi_band}〜{opi_band + 99}")
                        columns = st.columns(4)
                        for index, (_, row) in enumerate(band_rows.iterrows()):
                            with columns[index % 4]:
                                achieved_style = ACHIEVED_RANK_CARD_STYLES.get(row["現在ランク"])
                                target_status = "達成済" if row["is_achieved"] else "未達成"
                                if achieved_style:
                                    bg_color = achieved_style["background"]
                                    border_color = achieved_style["border"]
                                    text_color = achieved_style["text"]
                                    title_color = text_color
                                    detail_color = text_color
                                    badge = (
                                        f"<span style='color:{text_color}; font-weight:800;'>"
                                        f"[現在 {row['現在ランク']}] [{target_status}]</span>"
                                    )
                                else:
                                    bg_color = "#f8f9fa"
                                    border_color = "#dee2e6"
                                    text_color = "#1f2937"
                                    title_color = "#111827"
                                    detail_color = "#374151"
                                    badge = "<span style='color:#757575;'>[現在 未S] [未達成]</span>"

                                card_html = f"""
                                <div style="background-color: {bg_color}; color: {text_color}; border: 2px solid {border_color}; border-radius: 6px; padding: 8px; margin-bottom: 8px;">
                                    <div style="font-weight: bold; font-size: 0.95em; color: {title_color};">{html.escape(str(row['楽曲名']))} <span style="font-weight: normal; font-size: 0.78em; color: {title_color};">[{html.escape(str(row['バージョン']))} / {html.escape(str(row['ジャンル']))}]</span></div>
                                    <div style="font-size: 0.8em; color: {detail_color};">
                                        {row['難易度']} Lv.{row['レベル']} (定数 {row['定数']:.1f})<br/>
                                        適正OPI: <b>{row[opi_column]:.1f}</b> {badge}
                                    </div>
                                </div>
                                """
                                st.markdown(card_html, unsafe_allow_html=True)

                    my_difficulty_cards = []
                    for _, row in df_my_charts.iterrows():
                        style = ACHIEVED_RANK_CARD_STYLES.get(row["現在ランク"], {})
                        my_difficulty_cards.append({
                            "title": row["楽曲名"],
                            "metadata": f"{row['バージョン']} / {row['ジャンル']}",
                            "details": [
                                f"{row['難易度']}  Lv.{row['レベル']}（定数 {row['定数']:.1f}）",
                                f"適正OPI {row[opi_column]:.1f} / 現在 {row['現在ランク']}・{row['達成状況']}",
                            ],
                            "summary": f"{row['難易度']} Lv.{row['レベル']} / OPI {row[opi_column]:.1f} / {row['現在ランク']}",
                            **style,
                        })
                    render_image_export(
                        "マイOPI難易度表",
                        [
                            f"プレイヤー: {player.player_name} / 目標ランク: {my_diff_target_rank}",
                            f"達成状況: {achieved_count}/{total_charts}譜面（{achieve_rate:.1f}%）",
                            "背景色: S=緑 / SS=青 / SSS=赤 / SSS+=黄 / AB+=橙",
                        ],
                        my_difficulty_cards,
                        f"my_opi_difficulty_{my_diff_target_rank.lower().replace('+', 'p')}",
                        "my_difficulty_table",
                    )

                    with st.expander("表形式で表示"):
                        st.dataframe(df_my_charts.drop(columns=["chart_id", "OPI帯", "is_achieved"]), use_container_width=True)
                else:
                    st.info(f"{my_diff_target_rank} の難易度データがありません。")
            else:
                st.info("難易度表のデータがありません。")


    else:
        st.warning("ユーザーデータが見つかりません。サイドバーから「検索 / 更新」を実行してください。")
        
    session.close()
