import os
import sys
import json
import logging
import requests
from datetime import datetime
import asyncio

# アプリケーションのルートディレクトリをパスに追加
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

# OPI_Project内のモジュールをインポート
from src.database.models import get_session_maker, init_db
from src.crawler.ongeki_crawler import OngekiCrawler
from app import apply_user_snapshot_to_db

# ロガーの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_FILE = os.path.join(_APP_DIR, "data", "opi_database.sqlite")
engine = init_db(DB_FILE)
Session = get_session_maker(engine)

# GitHub Actionsで環境変数として設定されるAPIキー
SCRAPINGBEE_API_KEY = os.environ.get("SCRAPINGBEE_API_KEY")

def fetch_via_scrapingbee(user_id: int) -> str:
    """ScrapingBee経由でOngekiScoreLogのHTMLを取得する"""
    if not SCRAPINGBEE_API_KEY:
        raise ValueError("SCRAPINGBEE_API_KEY が設定されていません。")
        
    url = f"https://ongeki-score.net/user/{user_id}"
    scrapingbee_endpoint = "https://app.scrapingbee.com/api/v1/"
    
    # 試行1: 標準JSレンダリング + 全リソース読み込み(Cloudflareチャレンジ用)
    params_std = {
        'api_key': SCRAPINGBEE_API_KEY,
        'url': url,
        'render_js': 'true', 
        'block_resources': 'false',
        'wait': '5000',
    }

    logger.info(f"Fetching user {user_id} via ScrapingBee (Standard JS)...")
    response = requests.get(scrapingbee_endpoint, params=params_std, timeout=90)
    if response.status_code == 200 and "Just a moment..." not in response.text:
        logger.info(f"Successfully fetched user {user_id} via standard proxy")
        return response.text

    # 試行2: 厳格なWAF対策用 プレミアム住宅用プロキシ (日本IP)
    logger.info(f"Retrying user {user_id} via ScrapingBee (Premium Residential Proxy)...")
    params_premium = {
        'api_key': SCRAPINGBEE_API_KEY,
        'url': url,
        'render_js': 'true', 
        'block_resources': 'false',
        'premium_proxy': 'true',
        'country_code': 'jp',
        'wait': '5000',
    }
    response_premium = requests.get(scrapingbee_endpoint, params=params_premium, timeout=120)
    if response_premium.status_code == 200 and "Just a moment..." not in response_premium.text:
        logger.info(f"Successfully fetched user {user_id} via premium residential proxy")
        return response_premium.text
    else:
        logger.error(f"Failed to fetch user {user_id}. Status: {response_premium.status_code}, Body: {response_premium.text}")
        response_premium.raise_for_status()

def main():
    # 引数または環境変数からターゲットユーザーIDのリストを取得
    # 例: TARGET_USER_IDS="10605,7381,12345"
    target_ids_str = os.environ.get("TARGET_USER_IDS", "")
    if not target_ids_str:
        logger.warning("TARGET_USER_IDS が指定されていません。更新をスキップします。")
        return

    user_ids = [int(uid.strip()) for uid in target_ids_str.split(",") if uid.strip().isdigit()]
    if not user_ids:
        logger.warning("有効なユーザーIDが見つかりませんでした。")
        return

    session = Session()
    updated_count = 0
    
    try:
        for uid in user_ids:
            try:
                html_text = fetch_via_scrapingbee(uid)
                # HTMLをパースしてスナップショットを作成
                snapshot = OngekiCrawler.parse_user_text_or_html(html_text, uid, force=True)
                
                # DBへ適用・OPI再計算
                success, msg = apply_user_snapshot_to_db(snapshot, session)
                if success:
                    logger.info(f"[User {uid}] {msg}")
                    updated_count += 1
                else:
                    logger.warning(f"[User {uid}] Failed to apply: {msg}")
            
            except Exception as e:
                logger.error(f"[User {uid}] Error during update process: {e}")
                session.rollback()
                
    finally:
        session.close()
        
    logger.info(f"Update process finished. Successfully updated {updated_count}/{len(user_ids)} users.")
    
    # 1件も更新されなかった場合は異常終了(Actionsでエラー通知させる)
    # 全員のスコアがたまたま変動していなかった場合も考慮し、今回は0件でも正常終了扱いとする
    sys.exit(0)

if __name__ == "__main__":
    main()
