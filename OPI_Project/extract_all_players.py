import argparse
import asyncio
import json
import logging
import os
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

from src.crawler.ongeki_crawler import OngekiCrawler
from src.database.calibration_store import CalibrationStore, make_subject_key


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DB_FILE = PROJECT_ROOT / "data" / "opi_calibration.sqlite"


async def collect_all_players(
    db_path: Path,
    *,
    min_rating: float,
    min_update_date: datetime,
    interval_seconds: float,
    limit: int | None = None,
) -> dict:
    collected = 0
    skipped = 0
    errors = 0
    requests = 1

    with CalibrationStore(str(db_path)) as store:
        run_id = store.start_run(limit or 999999, min_rating, min_update_date)
        status = "failed"
        try:
            async with OngekiCrawler() as crawler:
                logger.info("Fetching public users list...")
                public_users = await crawler.fetch_public_users()
                
                # フィルタリング
                eligible = [
                    item for item in public_users
                    if item["rating"] >= min_rating and item["updated_at"] >= min_update_date
                ]
                
                # レーティング降順（上手い人から優先的に取得）
                eligible.sort(key=lambda x: x["rating"], reverse=True)
                
                if limit:
                    eligible = eligible[:limit]
                    
                total_eligible = len(eligible)
                logger.info(f"Found {total_eligible} eligible users to process.")

                for i, candidate in enumerate(eligible, 1):
                    user_id = candidate["user_id"]
                    subject_key = make_subject_key(user_id)
                    previous_update = store.source_updated_at(subject_key)
                    
                    if previous_update and candidate["updated_at"] <= previous_update:
                        skipped += 1
                        if i % 100 == 0:
                            logger.info(f"Progress: {i}/{total_eligible} (Skipped User {user_id})")
                        continue

                    await asyncio.sleep(interval_seconds)
                    requests += 1
                    
                    try:
                        logger.info(f"Progress: {i}/{total_eligible} (Fetching User {user_id}, Rating {candidate['rating']})")
                        snapshot = await crawler.fetch_user_snapshot(
                            user_id,
                            last_crawled_at=previous_update,
                        )
                        if snapshot is None:
                            skipped += 1
                            continue
                            
                        store.upsert_snapshot(subject_key, snapshot["profile"], snapshot["scores"])
                        collected += 1
                    except PermissionError:
                        logger.error(f"Permission denied for user {user_id}. Stopping.")
                        raise
                    except (RuntimeError, ValueError) as e:
                        logger.warning(f"Error processing user {user_id}: {e}")
                        errors += 1

            status = "completed"
        finally:
            store.finish_run(
                run_id,
                status=status,
                collected_users=collected,
                skipped_users=skipped,
                error_users=errors,
                request_count=requests,
            )
            counts = store.counts()
            logger.info(f"Run finished with status: {status}")
            logger.info(f"Collected: {collected}, Skipped: {skipped}, Errors: {errors}")

    return {
        "status": status,
        "database": db_path.as_posix(),
        "requested_limit": limit,
        "collected_users": collected,
        "skipped_users": skipped,
        "error_users": errors,
        "request_count": requests,
        **counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="公開一覧から全プレイヤーのデータを長期収集するスクリプト")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_FILE, help="出力SQLite DB")
    parser.add_argument("--min-rating", type=float, default=18.0, help="最低レーティング")
    parser.add_argument("--min-update-date", default="2025-03-27", help="最終更新日の下限 (YYYY-MM-DD)")
    parser.add_argument("--interval", type=float, default=3.0, help="個別ページ間の待機秒数")
    parser.add_argument("--limit", type=int, default=None, help="最大収集人数の制限（テスト用）")
    args = parser.parse_args()

    if args.interval < 3.0:
        parser.error("--interval は3秒以上で指定してください（サーバー負荷軽減のため）")

    min_update_date = datetime.strptime(args.min_update_date, "%Y-%m-%d")
    
    logger.info("Starting large-scale extraction...")
    result = asyncio.run(collect_all_players(
        args.db,
        min_rating=args.min_rating,
        min_update_date=min_update_date,
        interval_seconds=args.interval,
        limit=args.limit,
    ))
    
    # 最後にJSONで結果出力
    print("\n--- Final Report ---")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
