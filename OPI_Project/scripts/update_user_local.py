"""
ローカル環境からOngekiScoreLogの公開データを直接取得し、
外部有料API（ScrapingBee等）を使わずにSQLiteデータベースを更新・OPI再計算するスクリプト。

使用方法:
    python scripts/update_user_local.py [ユーザーID]
    （引数を省略した場合は 10605 が対象となります）
"""

import asyncio
import os
import sys

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

from src.crawler.ongeki_crawler import OngekiCrawler
from src.database.models import init_db, get_session_maker, Player, ScoreLog
from app import apply_user_snapshot_to_db

async def update_user_local(user_id: int = 10605):
    print(f"=== ユーザー {user_id} のスコア直接更新開始（API不使用・ローカル高速取得） ===")
    crawler = OngekiCrawler()
    try:
        snapshot = await crawler.fetch_user_snapshot(user_id, force=True)
        if not snapshot:
            print("❌ ユーザーデータの取得に失敗しました。")
            return False

        profile = snapshot.get("profile", {})
        scores = snapshot.get("scores", [])
        print(f"✅ 取得成功: プレイヤー名={profile.get('player_name')}, レーティング={profile.get('rating')}, 総譜面数={len(scores)}件")

        db_path = os.path.join(_PROJECT_DIR, "data", "opi_database.sqlite")
        engine = init_db(db_path)
        Session = get_session_maker(engine)
        session = Session()
        try:
            success, message = apply_user_snapshot_to_db(snapshot, session)
            print(f"📊 DB反映結果: {message}")
            if success:
                p = session.query(Player).filter_by(user_id=user_id).first()
                count = session.query(ScoreLog).filter_by(user_id=user_id).count()
                print(f"✨ 反映完了: プレイヤー={p.player_name}, OPI={p.total_opi:.2f}, 更新日時={p.log_updated_at}, 対象スコア件数={count}件")
                return True
            return False
        finally:
            session.close()
    finally:
        await crawler.close()

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    
    target_uid = 10605
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        target_uid = int(sys.argv[1])
        
    asyncio.run(update_user_local(target_uid))
