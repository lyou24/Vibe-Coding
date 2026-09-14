import argparse
import asyncio
import json
import os
from collections import defaultdict, deque
from datetime import datetime

from src.crawler.ongeki_crawler import OngekiCrawler
from src.database.calibration_store import CalibrationStore, make_subject_key


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_FILE = os.path.join(PROJECT_ROOT, "data", "opi_calibration.sqlite")
MAX_COLLECTION_USERS = 100


def select_stratified_sample(candidates: list[dict], max_users: int) -> list[dict]:
    """0.5刻みのレーティング帯から順番に選び、能力帯の偏りを抑える。"""
    bands: dict[int, deque] = defaultdict(deque)
    ordered = sorted(candidates, key=lambda item: (item["updated_at"], item["rating"]), reverse=True)
    for candidate in ordered:
        bands[int(candidate["rating"] * 2)].append(candidate)

    selected = []
    band_keys = sorted(bands)
    while len(selected) < max_users and band_keys:
        remaining = []
        for band in band_keys:
            if bands[band] and len(selected) < max_users:
                selected.append(bands[band].popleft())
            if bands[band]:
                remaining.append(band)
        band_keys = remaining
    return selected


def select_collection_candidates(
    candidates: list[dict],
    existing_subject_keys: set[str],
    max_users: int,
) -> list[dict]:
    """既存対象を優先し、DB全体が指定人数を超えない範囲だけ新規追加する。"""
    existing = [
        candidate for candidate in candidates
        if make_subject_key(candidate["user_id"]) in existing_subject_keys
    ]
    new = [
        candidate for candidate in candidates
        if make_subject_key(candidate["user_id"]) not in existing_subject_keys
    ]
    selected_existing = select_stratified_sample(existing, min(max_users, len(existing)))
    remaining_slots = max(0, max_users - len(existing_subject_keys))
    return selected_existing + select_stratified_sample(new, remaining_slots)


async def collect_sample(
    db_path: str,
    *,
    max_users: int,
    min_rating: float,
    min_update_date: datetime,
    interval_seconds: float,
) -> dict:
    collected = 0
    skipped = 0
    errors = 0
    requests = 1

    with CalibrationStore(db_path) as store:
        run_id = store.start_run(max_users, min_rating, min_update_date)
        status = "failed"
        try:
            async with OngekiCrawler() as crawler:
                public_users = await crawler.fetch_public_users()
                eligible = [
                    item for item in public_users
                    if item["rating"] >= min_rating and item["updated_at"] >= min_update_date
                ]
                selected = select_collection_candidates(
                    eligible,
                    store.subject_keys(),
                    max_users,
                )

                for candidate in selected:
                    subject_key = make_subject_key(candidate["user_id"])
                    previous_update = store.source_updated_at(subject_key)
                    if previous_update and candidate["updated_at"] <= previous_update:
                        skipped += 1
                        continue

                    await asyncio.sleep(interval_seconds)
                    requests += 1
                    try:
                        snapshot = await crawler.fetch_user_snapshot(
                            candidate["user_id"],
                            last_crawled_at=previous_update,
                        )
                        if snapshot is None:
                            skipped += 1
                            continue
                        store.upsert_snapshot(subject_key, snapshot["profile"], snapshot["scores"])
                        collected += 1
                    except PermissionError:
                        raise
                    except (RuntimeError, ValueError):
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

    return {
        "status": status,
        "database": os.path.abspath(db_path),
        "requested_users": max_users,
        "collected_users": collected,
        "skipped_users": skipped,
        "error_users": errors,
        "request_count": requests,
        **counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="公開一覧から小規模な実プレイヤー校正DBを作成する")
    parser.add_argument("--db", default=DEFAULT_DB_FILE, help="出力SQLite DB")
    parser.add_argument("--max-users", type=int, default=12, help="最大収集人数")
    parser.add_argument("--min-rating", type=float, default=18.0, help="最低レーティング")
    parser.add_argument("--min-update-date", default="2025-03-27", help="最終更新日の下限 (YYYY-MM-DD)")
    parser.add_argument("--interval", type=float, default=3.0, help="個別ページ間の待機秒数")
    args = parser.parse_args()

    if not 1 <= args.max_users <= MAX_COLLECTION_USERS:
        parser.error(f"--max-users は1〜{MAX_COLLECTION_USERS}で指定してください")
    if args.interval < 3.0:
        parser.error("--interval は3秒以上で指定してください")

    min_update_date = datetime.strptime(args.min_update_date, "%Y-%m-%d")
    result = asyncio.run(collect_sample(
        args.db,
        max_users=args.max_users,
        min_rating=args.min_rating,
        min_update_date=min_update_date,
        interval_seconds=args.interval,
    ))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
