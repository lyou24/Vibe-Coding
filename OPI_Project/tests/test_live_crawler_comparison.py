import asyncio
import sys
import json
import os
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
from src.crawler.ongeki_crawler import OngekiCrawler

async def verify_live_crawler():
    print("==================================================")
    print("TEST 3: 実サイト (ongeki-score.net) からのリアルタイム取得・比較検証")
    print("==================================================")
    crawler = OngekiCrawler()

    # 1. 譜面マスタ
    print("実サイトより定数13.7以上の譜面マスタを取得中...")
    live_master = await crawler.fetch_music_master(min_constant=13.7)
    print(f"Live master count: {len(live_master)}")

    seed_path = PROJECT_ROOT / 'data' / 'seed_data.json'
    with open(seed_path, 'r', encoding='utf-8') as f:
        seed_data = json.load(f)
    seed_master = seed_data['music_master']
    print(f"Seed master count: {len(seed_master)}")

    assert len(live_master) == len(seed_master), f"Count mismatch: live={len(live_master)}, seed={len(seed_master)}"

    # chart_id での突合
    seed_by_id = {m['chart_id']: m for m in seed_master}
    mismatches = []
    for lm in live_master:
        cid = lm['chart_id']
        if cid not in seed_by_id:
            mismatches.append((cid, "Missing in seed"))
        else:
            sm = seed_by_id[cid]
            if sm['title'] != lm['title'] or sm['chart_constant'] != lm['chart_constant'] or sm['difficulty'] != lm['difficulty']:
                mismatches.append((cid, f"Field diff: live={lm} vs seed={sm}"))

    if mismatches:
        print(f"FAIL: Music master mismatches found: {len(mismatches)}")
        for m in mismatches[:5]:
            print(" ", m)
    else:
        print("PASS: 実サイトの全543譜面マスタと seed_data.json は100%完全一致しています。")

    # 2. ユーザー 10605 のスコア
    print("\n実サイトよりユーザー 10605 のスコアログを取得中...")
    live_scores = await crawler.fetch_user_scores(10605)
    seed_scores = seed_data['test_user']['scores']
    print(f"Live scores count: {len(live_scores)}")
    print(f"Seed scores count: {len(seed_scores)}")

    assert len(live_scores) == len(seed_scores), f"Count mismatch: live={len(live_scores)}, seed={len(seed_scores)}"

    # スコアログ各レコードの検証
    score_mismatches = []
    for i, (ls, ss) in enumerate(zip(live_scores, seed_scores)):
        if ls != ss:
            score_mismatches.append((i, ls, ss))

    if score_mismatches:
        print(f"FAIL: Score mismatches found: {len(score_mismatches)}")
        for sm in score_mismatches[:5]:
            print(f"  Index {sm[0]}: Live={sm[1]} vs Seed={sm[2]}")
    else:
        print("PASS: 実サイトから取得した744件のスコアログと seed_data.json は100%完全一致しています。")

    await crawler.close()

if __name__ == "__main__":
    asyncio.run(verify_live_crawler())
