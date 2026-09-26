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
from src.recommender.recommender import OPIRecommender, DEACTIVATED_CHART_IDS
from src.export.full_image_export import build_full_hd_image
from src.visualizer.visualizer import OPIVisualizer
from src.components.cpi_table import render_cpi_table

from PIL import Image
try:
    opi_icon = Image.open("assets/opi_icon.jpg")
except Exception:
    opi_icon = "🎵"
st.set_page_config(page_title="OPI", page_icon=opi_icon, layout="wide", initial_sidebar_state="auto")

# モバイル（iPhone等）向けのレスポンシブCSS調整
st.markdown("""
<style>
    /* モバイル表示時の余白最適化（画面幅を最大限活用） */
    @media (max-width: 768px) {
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 2rem !important;
            padding-left: 0.25rem !important;
            padding-right: 0.25rem !important;
        }
        /* 入力フォームのフォントサイズ調整（iOSズーム防止） */
        input, select, textarea {
            font-size: 16px !important;
        }
        /* タブの視認性向上 */
        button[data-baseweb="tab"] {
            padding: 8px 10px !important;
            font-size: 13px !important;
        }
    }

    /* CPI風テーブルのスタイル（iPhone1画面に綺麗に収まる設計） */
    .cpi-table-container {
        width: 100%;
        margin: 6px 0 12px 0;
        overflow-x: hidden;
    }
    .cpi-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 11.5px;
        line-height: 1.25;
        table-layout: fixed;
        background-color: #fff;
        border: 1px solid #dee2e6;
        border-radius: 4px;
    }
    .cpi-table th {
        background-color: #f8f9fa;
        color: #495057;
        font-weight: 600;
        padding: 6px 2px;
        border-bottom: 2px solid #dee2e6;
        border-right: 1px solid #edf2f7;
        text-align: center;
        font-size: 11px;
    }
    .cpi-table td {
        padding: 5px 3px;
        border-bottom: 1px solid #eee;
        border-right: 1px solid #f8f9fa;
        vertical-align: middle;
        text-align: center;
    }
    .cpi-table tr:hover {
        background-color: #f8fafc;
    }
    .cpi-col-title { width: 34%; text-align: left !important; padding-left: 4px !important; }
    .cpi-col-genre { width: 17%; }
    .cpi-col-lv { width: 17%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 10.5px; font-weight: 500; }
    .cpi-col-cur { width: 10%; }
    .cpi-col-target { width: 10%; }
    .cpi-col-rate { width: 12%; text-align: right !important; padding-right: 4px !important; font-family: monospace, sans-serif; font-size: 10.5px; }

    .cpi-title-text {
        font-weight: 500;
        color: #212529;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        line-height: 1.25;
        word-break: break-all;
    }

    .badge-np { background: #e0e0e0; color: #757575; border-radius: 3px; padding: 2px 0; font-size: 9.5px; font-weight: 700; display: block; }
    .badge-mis { background: #9e9e9e; color: #fff; border-radius: 3px; padding: 2px 0; font-size: 9.5px; font-weight: 700; display: block; }
    .badge-s { background: #66bb6a; color: #fff; border-radius: 3px; padding: 2px 0; font-size: 9.5px; font-weight: 700; display: block; }
    .badge-ss { background: #42a5f5; color: #fff; border-radius: 3px; padding: 2px 0; font-size: 9.5px; font-weight: 700; display: block; }
    .badge-sss { background: #ffa726; color: #fff; border-radius: 3px; padding: 2px 0; font-size: 9.5px; font-weight: 700; display: block; }
    .badge-sssp { background: #ef5350; color: #fff; border-radius: 3px; padding: 2px 0; font-size: 9.5px; font-weight: 700; display: block; }
    .badge-abp { background: #ab47bc; color: #fff; border-radius: 3px; padding: 2px 0; font-size: 9.5px; font-weight: 700; display: block; }

    .badge-genre {
        color: #fff;
        border-radius: 3px;
        padding: 2px 1px;
        font-size: 9px;
        font-weight: 600;
        display: block;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .genre-variety { background: #00897b; }
    .genre-ongeki { background: #f4511e; }
    .genre-chumai { background: #8e24aa; }
    .genre-toho { background: #d81b60; }
    .genre-pops { background: #1e88e5; }
    .genre-other { background: #546e7a; }

    /* 楽曲名リンクのスタイル（タップ可能・CPI風） */
    .cpi-title-link {
        color: #212529 !important;
        text-decoration: underline dotted #adb5bd !important;
        font-weight: 500;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        line-height: 1.25;
        word-break: break-all;
        cursor: pointer;
    }
    .cpi-title-link:hover, .cpi-title-link:active {
        color: #007bff !important;
        text-decoration: underline solid #007bff !important;
    }

    .cpi-row-selected td {
        background-color: #e8f4fd !important;
    }

    /* CPI風 楽曲詳細カードのスタイル */
    .cpi-detail-card {
        background-color: #ffffff;
        border: 1px solid #ced4da;
        border-radius: 6px;
        padding: 10px 12px;
        margin: 6px 0 14px 0;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
    }
    .cpi-detail-header {
        border-bottom: 2px solid #e9ecef;
        padding-bottom: 6px;
        margin-bottom: 8px;
    }
    .cpi-detail-title-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        flex-wrap: wrap;
    }
    .cpi-detail-title {
        font-size: 15px;
        font-weight: 700;
        color: #212529;
    }
    .cpi-detail-diff {
        font-size: 10.5px;
        font-weight: 700;
        padding: 1px 6px;
        border-radius: 3px;
        color: #fff;
    }
    .diff-master { background-color: #9c27b0; }
    .diff-lunatic { background-color: #d32f2f; }
    .diff-expert { background-color: #f57c00; }
    .diff-advanced { background-color: #388e3c; }
    .diff-basic { background-color: #1976d2; }

    .cpi-detail-meta {
        font-size: 11px;
        color: #6c757d;
        margin-top: 3px;
    }

    /* プレイヤー情報テーブル */
    .cpi-detail-player-table {
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 10px;
        font-size: 11.5px;
        border: 1px solid #dee2e6;
        table-layout: fixed;
    }
    .cpi-detail-player-table th {
        background-color: #f8f9fa;
        color: #495057;
        font-weight: 600;
        padding: 5px 4px;
        border: 1px solid #dee2e6;
        text-align: center;
        font-size: 11px;
    }
    .cpi-detail-player-table td {
        padding: 6px 4px;
        border: 1px solid #dee2e6;
        text-align: center;
        vertical-align: middle;
    }
    .cpi-detail-player-table .player-name {
        color: #007bff;
        font-weight: 700;
    }
    .cpi-detail-player-table .player-opi {
        font-family: monospace, sans-serif;
        font-weight: 600;
    }
    .cpi-detail-player-table .player-score {
        font-family: monospace, sans-serif;
        font-weight: 600;
        color: #212529;
    }

    .cpi-section-title {
        font-size: 12.5px;
        font-weight: 700;
        color: #343a40;
        margin: 8px 0 4px 0;
    }

    /* 適正OPI・クリア割合テーブル */
    .cpi-detail-rate-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 11px;
        border: 1px solid #dee2e6;
        table-layout: fixed;
    }
    .cpi-detail-rate-table th {
        color: #ffffff;
        font-weight: 700;
        padding: 6px 2px;
        text-align: center;
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    .cpi-detail-rate-table .th-s { background-color: #5cb85c; }
    .cpi-detail-rate-table .th-ss { background-color: #5bc0de; }
    .cpi-detail-rate-table .th-sss { background-color: #f0ad4e; }
    .cpi-detail-rate-table .th-sssp { background-color: #d9534f; }
    .cpi-detail-rate-table .th-abp { background-color: #ab47bc; }

    .cpi-detail-rate-table td {
        padding: 6px 2px;
        text-align: center;
        border: 1px solid #dee2e6;
        vertical-align: middle;
    }
    .cpi-detail-rate-table .row-opi {
        background-color: #fdfdfe;
        font-weight: 700;
        font-size: 10.5px;
    }
    .cpi-detail-rate-table .rank-pos {
        font-size: 9px;
        font-weight: normal;
        color: #6c757d;
        display: block;
    }
    .cpi-detail-rate-table .row-rate {
        background-color: #ffffff;
        font-family: monospace, sans-serif;
        font-size: 11.5px;
        font-weight: 700;
        color: #212529;
    }

    /* CPI風フィルターUIのスタイル調整 */
    .filter-header-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin: 8px 0 4px 0;
    }
    button[key^="btn_all_"], button[key^="btn_none_"] {
        font-size: 11px !important;
        padding: 1px 6px !important;
        min-height: 26px !important;
        height: 26px !important;
        line-height: 1 !important;
        border-radius: 4px !important;
    }
    div[data-testid="stCheckbox"] {
        margin-bottom: 2px !important;
    }
    div[data-testid="stCheckbox"] label {
        font-size: 12px !important;
        padding-top: 1px !important;
        padding-bottom: 1px !important;
    }

    /* マイOPI難易度表（スマホ版）3列〜4列タイルグリッド（iPhone対応） */
    .mobile-opi-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 5px;
        margin: 4px 0 8px 0;
        width: 100%;
        box-sizing: border-box;
    }
    @media (min-width: 600px) {
        .mobile-opi-grid {
            grid-template-columns: repeat(4, 1fr);
            gap: 7px;
        }
    }
    .mobile-opi-card {
        border-radius: 6px;
        border: 2px solid;
        padding: 6px 3px;
        min-height: 42px;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        box-sizing: border-box;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    .mobile-opi-title {
        font-size: 11px;
        font-weight: 700;
        line-height: 1.2;
        word-break: break-all;
        overflow: hidden;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
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

def sync_deactivated_charts(session):
    """配信終了曲の is_active = False をDBへ同期（自己修復機能）"""
    try:
        session.query(Chart).filter(
            Chart.chart_id.in_(DEACTIVATED_CHART_IDS),
            Chart.is_active == True
        ).update({Chart.is_active: False}, synchronize_session=False)
        session.query(Chart).filter(
            Chart.chart_id == "291_lunatic",
            Chart.is_active == False
        ).update({Chart.is_active: True}, synchronize_session=False)
        session.commit()
    except Exception:
        session.rollback()

_startup_session = Session()
try:
    sync_deactivated_charts(_startup_session)
finally:
    _startup_session.close()

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

from datetime import date, datetime, timezone, timedelta
import requests

JST = timezone(timedelta(hours=9))

def get_scrapingbee_api_key():
    """Streamlit Secrets または環境変数から ScrapingBee の API キーを取得"""
    api_key = None
    try:
        if hasattr(st, "secrets") and "SCRAPINGBEE_API_KEY" in st.secrets:
            api_key = st.secrets["SCRAPINGBEE_API_KEY"]
    except Exception:
        pass
    if not api_key:
        api_key = os.environ.get("SCRAPINGBEE_API_KEY")
    return api_key

def fetch_html_via_scrapingbee(user_id: int, api_key: str) -> str:
    url = f"https://ongeki-score.net/user/{user_id}"
    scrapingbee_endpoint = "https://app.scrapingbee.com/api/v1/"
    
    # 試行1: 標準JSレンダリング + 全リソース読み込み(Cloudflareチャレンジ用)
    params_std = {
        'api_key': api_key,
        'url': url,
        'render_js': 'true',
        'block_resources': 'false',
        'wait': '5000',
    }
    resp = requests.get(scrapingbee_endpoint, params=params_std, timeout=90)
    if resp.status_code == 200 and "Just a moment..." not in resp.text:
        return resp.text

    # 試行2: 厳格なWAF対策用 プレミアム住宅用プロキシ (日本IP)
    params_premium = {
        'api_key': api_key,
        'url': url,
        'render_js': 'true',
        'block_resources': 'false',
        'premium_proxy': 'true',
        'country_code': 'jp',
        'wait': '5000',
    }
    resp_premium = requests.get(scrapingbee_endpoint, params=params_premium, timeout=120)
    if resp_premium.status_code == 200 and "Just a moment..." not in resp_premium.text:
        return resp_premium.text
    else:
        err_msg = resp_premium.text if resp_premium.status_code != 200 else "Cloudflareの認証を突破できませんでした。"
        raise RuntimeError(f"ScrapingBee HTTP {resp_premium.status_code}: {err_msg}")

# --- バックエンド処理ラッパー ---
def apply_user_snapshot_to_db(snapshot: dict, session) -> tuple:
    """スナップショットデータからDBを安全に更新し、OPIを再算出する共通処理"""
    profile = snapshot.get("profile")
    scores = snapshot.get("scores", [])

    if not profile or not scores:
        return False, "プロフィールまたはスコアを解析できませんでした。"

    user_id = profile["user_id"]
    player_db = session.query(Player).filter_by(user_id=user_id).first()
    if not player_db:
        player_db = Player(user_id=user_id)
        session.add(player_db)
    player_db.player_name = profile.get('player_name', f"User_{user_id}")
    if profile.get('rating') is not None:
        player_db.rating = profile['rating']
    
    player_db.log_updated_at = datetime.now(JST)

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
        score_log.achieve_s = score_val >= 970000
        score_log.achieve_ss = score_val >= 990000
        score_log.achieve_sss = score_val >= 1000000
        score_log.achieve_sssp = score_val >= 1007500
        score_log.achieve_abp = score_val >= 1010000

    if matched_chart_ids:
        # 対象譜面から除外された古いスコアを削除
        session.query(ScoreLog).filter(
            ScoreLog.user_id == user_id,
            ~ScoreLog.chart_id.in_(matched_chart_ids),
        ).delete(synchronize_session=False)

        # OPIの再算出
        calc = OPICalculator()
        active_charts = [
            c for c in session.query(Chart).filter(
                Chart.is_active == True
            ).all()
            if not is_solo_version(c.title) and c.chart_id not in DEACTIVATED_CHART_IDS
        ]
        user_scores = session.query(ScoreLog).filter_by(user_id=user_id).all()
        achievements = calc.build_user_achievements(
            active_charts,
            user_scores,
            min_score=None,
            min_chart_constant=MIN_TARGET_CONSTANT,
        )
        if achievements:
            est_opi = calc.estimate_user_opi(achievements, initial_theta=player_db.total_opi or 1500.0)
            player_db.total_opi = est_opi

        session.commit()
        return True, f"ユーザー {user_id} の最新スコアを更新しました（対象譜面 {len(matched_chart_ids)} 件）。"
    else:
        session.rollback()
        return False, "取得スコアを譜面マスタへ1件も照合できなかったため、更新を中断しました。"


async def fetch_and_analyze_user(user_id: int, force: bool = True) -> bool:
    """ユーザーデータを収集し、OPIを算出する（最新スナップショット方式・安全アトミック更新）"""
    session = Session()
    crawler = OngekiCrawler()
    api_key = get_scrapingbee_api_key()

    try:
        snapshot = None
        # 1. ScrapingBee APIキーがあれば、Cloudflareを回避して直接HTMLを取得
        if api_key:
            with st.spinner(f"ScrapingBee 経由でユーザー {user_id} の最新スコアを取得中..."):
                try:
                    html_text = fetch_html_via_scrapingbee(user_id, api_key)
                    snapshot = OngekiCrawler.parse_user_text_or_html(html_text, user_id, force=force)
                except Exception as sb_err:
                    st.sidebar.warning(f"ScrapingBee経由の取得でエラーが発生しました: {sb_err}")

        # 2. キーがない場合や失敗した場合は既存のクローラーへフォールバック
        if not snapshot:
            with st.spinner(f"OngekiScoreLog からユーザー {user_id} の最新データを取得中..."):
                snapshot = await crawler.fetch_user_snapshot(user_id, force=force)

        if not snapshot:
            st.sidebar.warning(f"ユーザー {user_id} の最新データ取得に失敗したか、データが存在しませんでした。既存データを使用します。")
            return False

        success, msg = apply_user_snapshot_to_db(snapshot, session)
        if success:
            st.sidebar.success(msg)
            return True
        else:
            st.sidebar.warning(msg)
            return False
    except Exception as e:
        session.rollback()
        st.sidebar.warning(f"最新データの自動取得で制限が発生しました: {e}\n\n💡 下の「📋 スコア貼り付け手動更新」から、OngekiScoreLog の画面を全選択コピーして貼り付けることで、即座に本日の最新スコアに更新・再計算できます。")
        return False
    finally:
        session.close()
        await crawler.close()

# --- UI構築 ---
st.title("Ongeki Power Indicator (OPI)")


TARGET_AUTH_HASH = "96cae35ce8a9b0244178bf28e4966c2ce1b8385723a96a6b838858cdd6ca0a1e"


def check_password() -> bool:
    """合言葉（パスワード）の認証チェック（URLクエリパラメータ永続化対応）"""
    # 1. セッション内で既に認証済み
    if st.session_state.get("authenticated", False):
        return True

    # 2. クエリパラメータに認証トークンがある場合は自動パス（ページリロードやリンク遷移時のセッション維持）
    if st.query_params.get("auth") == TARGET_AUTH_HASH:
        st.session_state["authenticated"] = True
        return True

    st.markdown("---")
    st.markdown("### 🔒 アクセス制限")
    st.info("合言葉を入力してください。")

    col1, col2 = st.columns([3, 1])
    with col1:
        password_input = st.text_input("合言葉", type="password", key="app_password_input", placeholder="合言葉を入力")
    with col2:
        st.write("")
        st.write("")
        submit = st.button("入場する", key="app_login_btn")

    if submit or password_input:
        input_hash = hashlib.sha256(password_input.strip().encode("utf-8")).hexdigest()

        secrets_password = None
        try:
            if hasattr(st, "secrets") and "APP_PASSWORD" in st.secrets:
                secrets_password = st.secrets["APP_PASSWORD"]
        except Exception:
            pass

        if (secrets_password and password_input.strip() == str(secrets_password)) or input_hash == TARGET_AUTH_HASH:
            st.session_state["authenticated"] = True
            st.query_params["auth"] = TARGET_AUTH_HASH
            return True
        else:
            if password_input:
                st.error("合言葉が正しくありません。")

    return False


if not check_password():
    st.stop()

# クエリパラメータに user_id がある場合、検索フォームの初期値として引き継ぐ
if "user_id_input" not in st.session_state:
    qp_uid = st.query_params.get("user_id", "")
    if qp_uid:
        st.session_state["user_id_input"] = qp_uid

if calibration_sync["status"] == "error":
    st.warning(f"校正済み譜面OPIの読み込みに失敗したため、既存値を使用します: {calibration_sync['message']}")
elif calibration_sync["status"] not in {"applied", "current", "calibration_db_missing"}:
    st.warning("完了済みの校正データが見つからないため、既存の譜面OPIを使用します。")

st.sidebar.header("プレイヤー検索")
user_input = st.sidebar.text_input("OngekiScoreLog ユーザーID", key="user_id_input")

col_sb1, col_sb2 = st.sidebar.columns(2)
with col_sb1:
    search_button = st.button("🔍 検索", key="search_btn", use_container_width=True)
with col_sb2:
    update_button = st.button("🔄 最新更新", key="update_btn", use_container_width=True, help="ScrapingBee経由で最新スコアを取得・更新します")

# --- 🔖 ブックマークレットで更新 ---
with st.sidebar.expander("🔖 ブックマークレットで更新", expanded=False):
    st.markdown("""
Cloudflareの制限を回避するため、**ブックマークレット**を利用した半自動更新が最も簡単です。

**【準備（初回のみ）】**
以下のコードをコピーし、ブラウザの新しいブックマークを作成してURL欄に貼り付けてください（名前は「OPI更新」などがおすすめ）。
""")
    bookmarklet_code = """javascript:(function(){var m=document.documentElement.outerHTML;if(!m.includes("ongeki-score.net")){alert("OngekiScoreLogの自分のページで実行してください。");return;}var t=document.createElement("textarea");t.value=m;document.body.appendChild(t);t.select();document.execCommand("copy");document.body.removeChild(t);alert("スコアデータをコピーしました！\\nOPI Projectの『📋 スコア貼り付け手動更新』欄にペーストしてください。");})();"""
    st.code(bookmarklet_code, language="javascript")
    st.markdown("""
**【毎回の更新手順】**
1. 自分の [OngekiScoreLog](https://ongeki-score.net/) を開く
2. 登録したブックマークレットをクリック（全データが自動コピーされます）
3. この画面下の「📋 スコア貼り付け手動更新」欄にペーストして「手動反映」を押す
""")

# --- 📋 スコア貼り付け手動更新（HTML/テキスト） ---
with st.sidebar.expander("📋 スコア貼り付け手動更新（HTML/テキスト）", expanded=False):
    st.caption("Cloudflare等の制限で自動取得できない場合、OngekiScoreLog（https://ongeki-score.net/user/{ID}）のHTMLソースまたは画面テキストを貼り付けて手動反映できます。")
    manual_uid_val = st.text_input("ユーザーID（未入力時は上のIDを使用）", key="manual_uid_input")
    manual_content = st.text_area("HTMLソースまたはテキスト", height=150, key="manual_content_input", placeholder="<!DOCTYPE html> ... またはコピーしたページ内容")
    if st.button("手動反映", key="manual_apply_btn"):
        target_uid_str = manual_uid_val.strip() or user_input.strip()
        if not target_uid_str.isdigit():
            st.sidebar.error("有効な数値のユーザーIDを指定してください。")
        elif not manual_content.strip():
            st.sidebar.error("HTMLソースまたはテキストを入力してください。")
        else:
            target_uid = int(target_uid_str)
            try:
                with st.spinner("貼り付けデータを解析・反映中..."):
                    snapshot = OngekiCrawler.parse_user_text_or_html(manual_content, target_uid, force=True)
                    m_session = Session()
                    try:
                        ok, m_msg = apply_user_snapshot_to_db(snapshot, m_session)
                        if ok:
                            st.sidebar.success(f"手動反映完了: {m_msg}")
                            st.session_state["user_id_input"] = str(target_uid)
                            st.session_state["last_synced_uid"] = target_uid
                            st.rerun()
                        else:
                            st.sidebar.warning(m_msg)
                    finally:
                        m_session.close()
            except Exception as e:
                st.sidebar.error(f"解析エラー: {e}")

# --- 検索および最新データ同期ロジック ---
if user_input.isdigit():
    uid = int(user_input)
    # 「🔄 最新更新」ボタンが押された場合のみ外部通信(ScrapingBee)を実行
    if update_button:
        success = asyncio.run(fetch_and_analyze_user(uid, force=True))
        if success:
            st.session_state["last_synced_uid"] = uid
            st.rerun()
    elif search_button:
        s_session = Session()
        try:
            p = s_session.query(Player).filter_by(user_id=uid).first()
            if not p:
                st.sidebar.info(f"ユーザー {uid} のデータがDBにありません。横の「🔄 最新更新」を押して取得してください。")
        finally:
            s_session.close()
elif user_input:
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
            if not is_solo_version(c.title) and c.chart_id not in DEACTIVATED_CHART_IDS
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

        # ユーザースコア辞書
        scores_map = {s.chart_id: s for s in player_scores}

        # 各ランクごとの全譜面難易度順位（ランキング）の算出
        rank_orders_map = {}
        target_eval_ranks = ["S", "SS", "SSS", "SSS+", "AB+"]
        for r_name in target_eval_ranks:
            c_list = []
            for c in eligible_charts:
                x_val, _ = calc.get_chart_rank_params(c, r_name)
                if x_val is not None:
                    c_list.append((c.chart_id, x_val))
            c_list.sort(key=lambda t: t[1], reverse=True)
            for pos, (cid, x_val) in enumerate(c_list, 1):
                rank_orders_map[(cid, r_name)] = (x_val, pos, len(c_list))

        col_prof, col_btn = st.columns([3, 1])
        with col_prof:
            st.header(f"👤 {player.player_name} さんのデータ")
            if player.log_updated_at:
                date_str = player.log_updated_at.strftime('%Y-%m-%d %H:%M') if hasattr(player.log_updated_at, 'strftime') else str(player.log_updated_at)[:16]
                st.caption(f"スコア最終更新日時: {date_str}")
        with col_btn:
            st.write("")
            if st.button("🔄 最新スコアに更新", key="main_refresh_score_btn", help="OngekiScoreLog から最新スコアを再取得して反映します"):
                asyncio.run(fetch_and_analyze_user(uid, force=True))
                st.session_state["last_synced_uid"] = uid
                st.rerun()

        col1, col2, col3 = st.columns(3)
        col1.metric("レーティング", f"{player.rating:.3f}" if player.rating else "N/A")
        col2.metric("リコメンドOPI", f"{qualified_opi:.1f}" if qualified_opi else "N/A")
        col3.metric("AAA以上の対象率", f"{coverage:.1f}%")
        st.caption(
            f"対象は譜面定数{MIN_TARGET_CONSTANT:.1f}以上。リコメンドはAAA以上の "
            f"{qualified_chart_count}/{scored_chart_count}譜面から推定したOPIのみを使用します。"
        )
        st.caption(
            "最終データ更新: "
            + (player.log_updated_at.strftime("%Y-%m-%d %H:%M") if hasattr(player.log_updated_at, 'strftime') else str(player.log_updated_at)[:16])
        )
        
        st.divider()

        # タブで情報を切り替え
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🎯 リコメンド楽曲", "📊 統計・分布図", "📜 OPI難易度表", "⭐ マイOPI難易度表", "⭐ マイOPI難易度表（スマホ版）"])

        with tab1:
            st.subheader("おすすめの目標楽曲")
            
            # CPI風絞り込みフィルターの定義
            CPI_GENRE_OPTIONS = ["オンゲキ", "チュウマイ", "VARIETY", "東方Project", "POPS & ANIME", "niconico"]
            CPI_CURRENT_OPTIONS = [
                ("NP", "未プレイ"),
                ("未S", "未S"),
                ("S", "S止まり"),
                ("SS", "SS止まり"),
                ("SSS", "SSS止まり"),
                ("SSS+", "SSS+止まり"),
                ("AB+", "AB+")
            ]
            CPI_TARGET_OPTIONS = ["S", "SS", "SSS", "SSS+", "AB+"]
            CPI_LEVEL_OPTIONS = ["14", "14+", "15"]

            # 初期化（初回アクセス時）
            if "cpi_filter_init" not in st.session_state:
                for g in CPI_GENRE_OPTIONS:
                    st.session_state[f"chk_genre_{g}"] = True
                for label, val in CPI_CURRENT_OPTIONS:
                    st.session_state[f"chk_cur_{val}"] = True
                for tr in CPI_TARGET_OPTIONS:
                    st.session_state[f"chk_tar_{tr}"] = True
                for lv in CPI_LEVEL_OPTIONS:
                    st.session_state[f"chk_lv_{lv}"] = True
                st.session_state.cpi_filter_init = True

            # 多次元フィルターUI（CPI風絞り込み）
            with st.expander("🔽 絞り込み", expanded=False):
                # 1. ジャンル
                h_col, b_col1, b_col2 = st.columns([3.5, 1.25, 1.25])
                with h_col:
                    st.markdown("**ジャンル**")
                with b_col1:
                    if st.button("全てチェック", key="btn_all_genre"):
                        for g in CPI_GENRE_OPTIONS:
                            st.session_state[f"chk_genre_{g}"] = True
                        st.rerun()
                with b_col2:
                    if st.button("全て非チェック", key="btn_none_genre"):
                        for g in CPI_GENRE_OPTIONS:
                            st.session_state[f"chk_genre_{g}"] = False
                        st.rerun()

                g_cols = st.columns(3)
                for idx, g in enumerate(CPI_GENRE_OPTIONS):
                    with g_cols[idx % 3]:
                        st.checkbox(g, key=f"chk_genre_{g}")

                st.markdown("<hr style='margin: 6px 0; border: none; border-top: 1px solid #eee;'>", unsafe_allow_html=True)

                # 2. 現ランプ
                h_col, b_col1, b_col2 = st.columns([3.5, 1.25, 1.25])
                with h_col:
                    st.markdown("**現ランプ**")
                with b_col1:
                    if st.button("全てチェック", key="btn_all_cur"):
                        for label, val in CPI_CURRENT_OPTIONS:
                            st.session_state[f"chk_cur_{val}"] = True
                        st.rerun()
                with b_col2:
                    if st.button("全て非チェック", key="btn_none_cur"):
                        for label, val in CPI_CURRENT_OPTIONS:
                            st.session_state[f"chk_cur_{val}"] = False
                        st.rerun()

                c_cols = st.columns(4)
                for idx, (label, val) in enumerate(CPI_CURRENT_OPTIONS):
                    with c_cols[idx % 4]:
                        st.checkbox(label, key=f"chk_cur_{val}")

                st.markdown("<hr style='margin: 6px 0; border: none; border-top: 1px solid #eee;'>", unsafe_allow_html=True)

                # 3. 目標ランプ
                h_col, b_col1, b_col2 = st.columns([3.5, 1.25, 1.25])
                with h_col:
                    st.markdown("**目標ランプ**")
                with b_col1:
                    if st.button("全てチェック", key="btn_all_tar"):
                        for tr in CPI_TARGET_OPTIONS:
                            st.session_state[f"chk_tar_{tr}"] = True
                        st.rerun()
                with b_col2:
                    if st.button("全て非チェック", key="btn_none_tar"):
                        for tr in CPI_TARGET_OPTIONS:
                            st.session_state[f"chk_tar_{tr}"] = False
                        st.rerun()

                t_cols = st.columns(5)
                for idx, tr in enumerate(CPI_TARGET_OPTIONS):
                    with t_cols[idx % 5]:
                        st.checkbox(tr, key=f"chk_tar_{tr}")

                st.markdown("<hr style='margin: 6px 0; border: none; border-top: 1px solid #eee;'>", unsafe_allow_html=True)

                # 4. レベル
                h_col, b_col1, b_col2 = st.columns([3.5, 1.25, 1.25])
                with h_col:
                    st.markdown("**レベル**")
                with b_col1:
                    if st.button("全てチェック", key="btn_all_lv"):
                        for lv in CPI_LEVEL_OPTIONS:
                            st.session_state[f"chk_lv_{lv}"] = True
                        st.rerun()
                with b_col2:
                    if st.button("全て非チェック", key="btn_none_lv"):
                        for lv in CPI_LEVEL_OPTIONS:
                            st.session_state[f"chk_lv_{lv}"] = False
                        st.rerun()

                l_cols = st.columns(3)
                for idx, lv in enumerate(CPI_LEVEL_OPTIONS):
                    with l_cols[idx % 3]:
                        st.checkbox(f"Lv {lv}", key=f"chk_lv_{lv}")

                st.markdown("<hr style='margin: 6px 0; border: none; border-top: 1px solid #eee;'>", unsafe_allow_html=True)

                # 5. 詳細条件
                col_w1, col_w2 = st.columns(2)
                with col_w1:
                    constant_range = st.slider(
                        "譜面定数範囲",
                        min_value=MIN_TARGET_CONSTANT,
                        max_value=15.7,
                        value=(MIN_TARGET_CONSTANT, 15.7),
                        step=0.1,
                        key="filter_constant_range"
                    )
                with col_w2:
                    clear_rate_range = st.slider(
                        "クリア割合範囲（%）",
                        min_value=0.0,
                        max_value=100.0,
                        value=(30.0, 70.0),
                        step=1.0,
                        key="filter_clear_rate_range"
                    )

                sort_key = st.selectbox(
                    "並び順",
                    options=["適正順", "クリア割合が高い順", "現在ランク順", "目標ランク順"],
                    key="filter_sort_key"
                )

            # チェックボックス選択状態の抽出
            selected_genres = [g for g in CPI_GENRE_OPTIONS if st.session_state.get(f"chk_genre_{g}", True)]
            selected_cur_ranks = [val for label, val in CPI_CURRENT_OPTIONS if st.session_state.get(f"chk_cur_{val}", True)]
            selected_target_ranks = [tr for tr in CPI_TARGET_OPTIONS if st.session_state.get(f"chk_tar_{tr}", True)]
            selected_levels = [lv for lv in CPI_LEVEL_OPTIONS if st.session_state.get(f"chk_lv_{lv}", True)]

            param_level = selected_levels if selected_levels else ["__NONE__"]
            param_current_rank = selected_cur_ranks if selected_cur_ranks else ["__NONE__"]
            const_min, const_max = constant_range
            clear_rate_min, clear_rate_max = clear_rate_range
            effective_target_ranks = selected_target_ranks

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
                "未プレイ": -1,
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
            
            if selected_genres:
                recs = [item for item in recs if item.get("genre") in selected_genres or (not item.get("genre") and "不明" in selected_genres)]
            else:
                recs = []
            
            if recs:
                if 'recs_page' not in st.session_state:
                    st.session_state.recs_page = 0
                
                PAGE_SIZE = 20
                total_pages = max(1, (len(recs) - 1) // PAGE_SIZE + 1)
                
                if st.session_state.recs_page >= total_pages:
                    st.session_state.recs_page = total_pages - 1
                
                cur_page = st.session_state.recs_page + 1
                start_idx = st.session_state.recs_page * PAGE_SIZE
                end_idx = start_idx + PAGE_SIZE
                page_data = recs[start_idx:end_idx]

                # CPI風HTMLテーブルの生成（iPhone1画面に綺麗に収まる設計）
                def get_genre_badge(genre):
                    g = str(genre or "不明")
                    short_g = g
                    cls = "genre-other"
                    if "POPS" in g or "ANIME" in g:
                        short_g = "P&A"
                        cls = "genre-pops"
                    elif "東方" in g:
                        short_g = "東方"
                        cls = "genre-toho"
                    elif "オンゲキ" in g:
                        cls = "genre-ongeki"
                    elif "チュウマイ" in g or "CHUNITHM" in g or "maimai" in g:
                        cls = "genre-chumai"
                    elif "VARIETY" in g:
                        cls = "genre-variety"
                    return f'<span class="badge-genre {cls}">{html.escape(short_g)}</span>'

                def get_rank_badge(rank_str):
                    r = str(rank_str)
                    if r == "NP":
                        return '<span class="badge-np">NP</span>'
                    elif r == "未S":
                        return '<span class="badge-mis">未S</span>'
                    elif r == "S":
                        return '<span class="badge-s">S</span>'
                    elif r == "SS":
                        return '<span class="badge-ss">SS</span>'
                    elif r == "SSS":
                        return '<span class="badge-sss">SSS</span>'
                    elif r == "SSS+":
                        return '<span class="badge-sssp">SSS+</span>'
                    elif r == "AB+":
                        return '<span class="badge-abp">AB+</span>'
                    return f'<span>{html.escape(r)}</span>'

                def format_current_rank(item):
                    cr = item.get("current_rank", "")
                    cs = str(item.get("current_status", ""))
                    if cr in ["未プレイ", "NP"] or not cs or cs == "未プレイ":
                        return "NP"
                    if cr == "未S":
                        return "未S"
                    if cr.endswith("止まり"):
                        return cr.replace("止まり", "")
                    return cr or "NP"

                # 楽曲詳細の選択状態の同期（クエリパラメータ または session_state）
                query_chart_id = st.query_params.get("chart_id")
                if query_chart_id and query_chart_id != st.session_state.get("detail_chart_id"):
                    st.session_state.detail_chart_id = query_chart_id

                selected_detail_id = st.session_state.get("detail_chart_id")

                # CPI風 楽曲詳細ポップアップ（モーダルダイアログ）
                def render_chart_detail_content(detail_chart):
                    d_score_log = scores_map.get(detail_chart.chart_id)
                    d_cur_cat, d_cur_disp = recommender._determine_current_rank(d_score_log)
                    d_cur_badge = get_rank_badge(format_current_rank({"current_rank": d_cur_cat, "current_status": d_cur_disp}))

                    if d_score_log and d_score_log.score:
                        d_score_text = f"{d_score_log.score:,}"
                    else:
                        d_score_text = "未プレイ"

                    d_title_esc = html.escape(detail_chart.title)
                    d_diff_raw = detail_chart.difficulty.value if hasattr(detail_chart.difficulty, 'value') else str(detail_chart.difficulty)
                    d_diff_cls = f"diff-{d_diff_raw.lower()}"
                    d_version, d_genre = CHART_METADATA.get(detail_chart.chart_id, ("不明", "不明"))
                    if not d_genre or d_genre == "不明":
                        d_genre = getattr(detail_chart, "genre", "オンゲキ")

                    # 各ランクの適正OPIとクリア割合
                    rate_cells_opi = []
                    rate_cells_prob = []
                    for r_name in ["S", "SS", "SSS", "SSS+", "AB+"]:
                        x_val, y_val = calc.get_chart_rank_params(detail_chart, r_name)
                        if x_val is not None:
                            rank_info = rank_orders_map.get((detail_chart.chart_id, r_name))
                            order_str = f"({rank_info[1]}位)" if rank_info else ""
                            prob_val = calc.irt_probability(recommendation_opi or 1500.0, x_val, y_val)
                            rate_cells_opi.append(f"<td>{x_val:.1f} <span class='rank-pos'>{order_str}</span></td>")
                            rate_cells_prob.append(f"<td>{prob_val * 100:.2f}%</td>")
                        else:
                            rate_cells_opi.append("<td>-</td>")
                            rate_cells_prob.append("<td>-</td>")

                    detail_card_html = f"""
                    <div class="cpi-detail-card" style="margin: 0; box-shadow: none; border: none; padding: 0;">
                        <div class="cpi-detail-header">
                            <div class="cpi-detail-title-row">
                                <span class="cpi-detail-title" style="font-size: 15px;">{d_title_esc}</span>
                                <span class="cpi-detail-diff {d_diff_cls}">{d_diff_raw}</span>
                            </div>
                            <div class="cpi-detail-meta" style="font-size: 11px; margin-top: 3px;">
                                <span>{html.escape(str(d_genre))}</span> / <span>{html.escape(str(d_version))}</span> / <span>Lv.{detail_chart.level}（定数 {detail_chart.chart_constant:.1f}）</span>
                            </div>
                        </div>
                        <table class="cpi-detail-player-table">
                            <thead>
                                <tr>
                                    <th>プレイヤー</th>
                                    <th>リコメンドOPI</th>
                                    <th>ランプ</th>
                                    <th>スコア</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td class="player-name">{html.escape(player.player_name)}</td>
                                    <td class="player-opi">{recommendation_opi:.1f}</td>
                                    <td class="player-rank">{d_cur_badge}</td>
                                    <td class="player-score">{d_score_text}</td>
                                </tr>
                            </tbody>
                        </table>
                        <div class="cpi-section-title">適正OPI・クリア割合</div>
                        <table class="cpi-detail-rate-table">
                            <thead>
                                <tr>
                                    <th class="th-s">S</th>
                                    <th class="th-ss">SS</th>
                                    <th class="th-sss">SSS</th>
                                    <th class="th-sssp">SSS+</th>
                                    <th class="th-abp">AB+</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr class="row-opi">
                                    {''.join(rate_cells_opi)}
                                </tr>
                                <tr class="row-rate">
                                    {''.join(rate_cells_prob)}
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    """
                    st.markdown(detail_card_html, unsafe_allow_html=True)
                    if st.button("✕ 閉じる", key="btn_close_detail_modal", use_container_width=True):
                        st.session_state.detail_chart_id = None
                        if "chart_id" in st.query_params:
                            del st.query_params["chart_id"]
                        st.rerun()

                if hasattr(st, "dialog"):
                    @st.dialog("🎵 楽曲詳細情報", width="small")
                    def show_chart_detail_dialog(c_obj):
                        render_chart_detail_content(c_obj)
                else:
                    def show_chart_detail_dialog(c_obj):
                        render_chart_detail_content(c_obj)

                rows_html = []
                for item in page_data:
                    title_esc = html.escape(item.get("title", ""))
                    genre_badge = get_genre_badge(item.get("genre", "不明"))
                    lv_text = f"{item.get('level', '')} ({item.get('constant', 0.0):.1f})"
                    cur_rank = format_current_rank(item)
                    cur_badge = get_rank_badge(cur_rank)
                    target_badge = get_rank_badge(item.get("target_rank", ""))
                    win_rate = f"{item.get('probability', 0.0) * 100:.2f}%"

                    # 曲名タップでノンリロード詳細を開くリンク（data-chart-id属性＆選択中ハイライト）
                    is_selected = (item.get("chart_id") == selected_detail_id)
                    row_cls = " class='cpi-row-selected'" if is_selected else ""
                    title_link = f'<a href="#" data-chart-id="{item["chart_id"]}" class="cpi-title-link" title="タップして詳細を表示">{title_esc}</a>'

                    rows_html.append(f"""<tr{row_cls}>
                        <td class="cpi-col-title"><div class="cpi-title-text">{title_link}</div></td>
                        <td class="cpi-col-genre">{genre_badge}</td>
                        <td class="cpi-col-lv">{lv_text}</td>
                        <td class="cpi-col-cur">{cur_badge}</td>
                        <td class="cpi-col-target">{target_badge}</td>
                        <td class="cpi-col-rate">{win_rate}</td>
                    </tr>""")

                table_html = f"""<div id="cpi-table-view" class="cpi-table-container">
                    <table class="cpi-table">
                        <thead>
                            <tr>
                                <th class="cpi-col-title">楽曲名</th>
                                <th class="cpi-col-genre">ジャンル</th>
                                <th class="cpi-col-lv">Lv</th>
                                <th class="cpi-col-cur">現在</th>
                                <th class="cpi-col-target">目標</th>
                                <th class="cpi-col-rate">クリア割合</th>
                            </tr>
                        </thead>
                        <tbody>
                            {''.join(rows_html)}
                        </tbody>
                    </table>
                </div>"""

                # 案②: カスタムコンポーネントによるノンリロード表示
                comp_result = render_cpi_table(
                    html_content=table_html,
                    key=f"cpi_table_comp_{cur_page}"
                )
                if comp_result and isinstance(comp_result, dict):
                    clicked_id = comp_result.get("chart_id")
                    clicked_ts = comp_result.get("timestamp")
                    if clicked_ts != st.session_state.get("last_cpi_click_ts"):
                        st.session_state.last_cpi_click_ts = clicked_ts
                        st.session_state.detail_chart_id = clicked_id

                # ポップアップの表示発火（タップ検知時は同一ターン内で即時展開）
                active_detail_id = st.session_state.get("detail_chart_id")
                if active_detail_id:
                    detail_chart = next((c for c in eligible_charts if c.chart_id == active_detail_id), None)
                    if not detail_chart:
                        detail_chart = session.query(Chart).filter_by(chart_id=active_detail_id).first()

                    if detail_chart:
                        show_chart_detail_dialog(detail_chart)

                # 件数表示（CPI風）
                st.markdown(
                    f"<div style='text-align: center; font-size: 13px; color: #495057; margin-bottom: 6px;'>"
                    f"表示中 : ({start_idx + 1} 〜 {min(end_idx, len(recs))}) / 全 {len(recs)} 件"
                    f"</div>",
                    unsafe_allow_html=True
                )

                # ページネーション（スライダー & 前後ボタン：スマホ完全対応）
                if total_pages > 1:
                    st.markdown(
                        f"<div style='text-align: center; font-size: 13px; font-weight: 600; color: #1f77b4; margin-top: 10px; margin-bottom: 2px;'>"
                        f"📄 ページ {cur_page} / {total_pages}"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                    new_page = st.slider(
                        "ページ選択スライダー",
                        min_value=1,
                        max_value=total_pages,
                        value=cur_page,
                        step=1,
                        key="rec_page_slider",
                        label_visibility="collapsed"
                    )
                    if new_page != cur_page:
                        st.session_state.recs_page = new_page - 1
                        st.rerun()

                    c_prev, c_next = st.columns(2)
                    with c_prev:
                        if st.button("◀ 前のページ", disabled=(cur_page == 1), key="btn_pnav_prev", use_container_width=True):
                            st.session_state.recs_page -= 1
                            st.rerun()
                    with c_next:
                        if st.button("次のページ ▶", disabled=(cur_page == total_pages), key="btn_pnav_next", use_container_width=True):
                            st.session_state.recs_page += 1
                            st.rerun()

                recommendation_settings = [
                    f"プレイヤー: {player.player_name} / リコメンドOPI: {recommendation_opi:.1f}",
                    f"目標ランク: {', '.join(effective_target_ranks)}",
                    f"レベル: {', '.join(selected_levels) if selected_levels else '全対象'}",
                    f"譜面定数: {const_min:.1f}〜{const_max:.1f}",
                    f"現在ランク: {', '.join(selected_cur_ranks) if selected_cur_ranks else '全対象'}",
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
            vis = OPIVisualizer(DB_FILE)
            df_target_stats = vis.calculate_current_distribution_table()
            if not df_target_stats.empty:
                st.caption("全スコア対象のプレイヤーデータから算出したレーティング帯別の分布統計です。")
                st.dataframe(df_target_stats, use_container_width=True)
            else:
                st.info("分布統計データを読み込めませんでした。")

            st.divider()
            st.subheader("レーティング別 総合OPI動的分布図")
            # アプリが重くならないよう自身の位置は表示せず、全プレイヤーの分布図のみ表示
            fig = vis.create_distribution_figure(
                player_rating=None,
                player_opi=None,
                player_data=None,
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
                if not is_solo_version(c.title) and c.chart_id not in DEACTIVATED_CHART_IDS
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
                    df_charts["OPI帯"] = (df_charts[opi_column] // 50 * 50).astype(int)

                    unique_bands = sorted(df_charts["OPI帯"].unique(), reverse=True)
                    for opi_band in unique_bands:
                        band_rows = df_charts[df_charts["OPI帯"] == opi_band]
                        with st.expander(f"OPI {opi_band}〜{opi_band + 49}（{len(band_rows)}曲）", expanded=True):
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
            st.subheader("⭐ マイOPI難易度表")
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
                if not is_solo_version(c.title) and c.chart_id not in DEACTIVATED_CHART_IDS
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
                    df_my_charts["OPI帯"] = (df_my_charts[opi_column] // 50 * 50).astype(int)

                    unique_bands = sorted(df_my_charts["OPI帯"].unique(), reverse=True)
                    for opi_band in unique_bands:
                        band_rows = df_my_charts[df_my_charts["OPI帯"] == opi_band]
                        band_achieved = int(sum(band_rows["is_achieved"]))
                        with st.expander(f"【達成 {band_achieved}/{len(band_rows)}】 OPI {opi_band}〜{opi_band + 49}", expanded=True):
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

        with tab5:
            st.subheader("⭐ マイOPI難易度表（スマホ版）")
            my_diff_simple_target_rank = st.selectbox(
                "目標ランク選択",
                options=TARGET_RANK_OPTIONS,
                index=2,
                key="my_diff_simple_target_rank_select"
            )

            calc = OPICalculator()
            recommender = OPIRecommender(DB_FILE)
            user_scores_map = {s.chart_id: s for s in player_scores}

            charts = [
                c for c in session.query(Chart).filter(
                    Chart.chart_constant >= MIN_TARGET_CONSTANT,
                    Chart.is_active == True,
                ).order_by(Chart.chart_constant.asc(), Chart.title.asc()).all()
                if not is_solo_version(c.title) and c.chart_id not in DEACTIVATED_CHART_IDS
            ]

            if charts:
                chart_data = []
                achieved_count = 0
                for c in charts:
                    x, y = calc.get_chart_rank_params(c, my_diff_simple_target_rank)
                    if x is not None:
                        diff_name = c.difficulty.name if hasattr(c.difficulty, 'name') else str(c.difficulty)
                        version, genre = get_chart_metadata(c)
                        score_log = user_scores_map.get(c.chart_id)
                        is_achieved = recommender._is_target_achieved(score_log, my_diff_simple_target_rank)
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
                            f"{my_diff_simple_target_rank} 適正OPI": round(x, 1),
                            "個人差度": round(y, 1),
                            "達成状況": "達成済" if is_achieved else "未達成",
                            "現在ランク": current_achieved_rank or "未S",
                            "is_achieved": is_achieved,
                        })

                if chart_data:
                    total_charts = len(chart_data)
                    achieve_rate = (achieved_count / total_charts * 100) if total_charts > 0 else 0.0
                    col_m1, col_m2 = st.columns(2)
                    col_m1.metric(f"{my_diff_simple_target_rank} 達成曲数", f"{achieved_count} / {total_charts} 譜面")
                    col_m2.metric(f"{my_diff_simple_target_rank} 達成率", f"{achieve_rate:.1f}%")

                    df_my_charts = pd.DataFrame(chart_data)
                    df_my_charts = df_my_charts.sort_values(by=f"{my_diff_simple_target_rank} 適正OPI", ascending=False)
                    opi_column = f"{my_diff_simple_target_rank} 適正OPI"
                    df_my_charts["OPI帯"] = (df_my_charts[opi_column] // 50 * 50).astype(int)

                    DIFF_EMOJI_MAP = {
                        "MASTER": "🟪",
                        "EXPERT": "🟨",
                        "LUNATIC": "⬜",
                        "ADVANCED": "🟧",
                        "BASIC": "🟩",
                    }

                    unique_bands = sorted(df_my_charts["OPI帯"].unique(), reverse=True)
                    for opi_band in unique_bands:
                        band_rows = df_my_charts[df_my_charts["OPI帯"] == opi_band]
                        band_achieved = int(sum(band_rows["is_achieved"]))
                        with st.expander(f"【達成 {band_achieved}/{len(band_rows)}】 OPI {opi_band}〜{opi_band + 49}", expanded=True):
                            cards_html = []
                            for _, row in band_rows.iterrows():
                                achieved_style = ACHIEVED_RANK_CARD_STYLES.get(row["現在ランク"])
                                if achieved_style:
                                    bg_color = achieved_style["background"]
                                    border_color = achieved_style["border"]
                                    text_color = achieved_style["text"]
                                else:
                                    bg_color = "#f8f9fa"
                                    border_color = "#dee2e6"
                                    text_color = "#1f2937"

                                diff_key = str(row.get("難易度", "")).upper()
                                d_emoji = DIFF_EMOJI_MAP.get(diff_key, "")
                                title_esc = html.escape(str(row['楽曲名']))
                                disp_title = f"{d_emoji} {title_esc}" if d_emoji else title_esc

                                cards_html.append(
                                    f'<div class="mobile-opi-card" style="background-color: {bg_color}; border-color: {border_color}; color: {text_color};">'
                                    f'<span class="mobile-opi-title" style="color: {text_color};">{disp_title}</span>'
                                    f'</div>'
                                )

                            grid_html = f'<div class="mobile-opi-grid">{"".join(cards_html)}</div>'
                            st.markdown(grid_html, unsafe_allow_html=True)

                    my_difficulty_simple_cards = []
                    for _, row in df_my_charts.iterrows():
                        style = ACHIEVED_RANK_CARD_STYLES.get(row["現在ランク"], {})
                        diff_key = str(row.get("難易度", "")).upper()
                        d_emoji = DIFF_EMOJI_MAP.get(diff_key, "")
                        card_title = f"{d_emoji} {row['楽曲名']}" if d_emoji else row["楽曲名"]
                        my_difficulty_simple_cards.append({
                            "title": card_title,
                            "metadata": f"{row['難易度']}",
                            "details": [
                                f"現在: {row['現在ランク']} ({row['達成状況']})",
                            ],
                            "summary": card_title,
                            **style,
                        })
                    render_image_export(
                        "マイOPI難易度表（スマホ版）",
                        [
                            f"プレイヤー: {player.player_name} / 目標ランク: {my_diff_simple_target_rank}",
                            f"達成状況: {achieved_count}/{total_charts}譜面（{achieve_rate:.1f}%）",
                            "背景色: S=緑 / SS=青 / SSS=赤 / SSS+=黄 / AB+=橙",
                        ],
                        my_difficulty_simple_cards,
                        f"my_opi_difficulty_mobile_{my_diff_simple_target_rank.lower().replace('+', 'p')}",
                        "my_difficulty_mobile_table",
                    )

                    with st.expander("表形式で表示"):
                        st.dataframe(df_my_charts[["楽曲名", "現在ランク", "達成状況", f"{my_diff_simple_target_rank} 適正OPI"]], use_container_width=True)
                else:
                    st.info(f"{my_diff_simple_target_rank} の難易度データがありません。")
            else:
                st.info("難易度表のデータがありません。")


    else:
        st.warning("ユーザーデータが見つかりません。サイドバーから「検索 / 更新」を実行してください。")
        
    session.close()
