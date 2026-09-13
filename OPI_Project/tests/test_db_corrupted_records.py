import sqlite3
import json
import sys
import os
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'opi_database.sqlite'
SEED_PATH = PROJECT_ROOT / 'data' / 'seed_data.json'

conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()

with open(SEED_PATH, 'r', encoding='utf-8') as f:
    seed_data = json.load(f)
scores = seed_data['test_user']['scores']

# DBのscore_logsと、seed_dataのscoresを照合
# DBの各レコード: user_id, chart_id, score, is_all_break, is_full_bell
cur.execute("""
    SELECT s.chart_id, c.title, c.difficulty, c.chart_constant, s.score, s.is_all_break, s.is_full_bell
    FROM score_logs s
    JOIN charts c ON s.chart_id = c.chart_id
    WHERE s.user_id = 10605
""")
db_scores = cur.fetchall()

print(f"Total score_logs in DB: {len(db_scores)}")

# seed_data 内のスコアで、この (chart_id, score) に対応する元の difficulty を確認
mismatches = []
for cid, title, c_diff, const, sc, ab, fb in db_scores:
    # 元のscoresから探す
    matching_raw = [s for s in scores if s.get('title') == title and s.get('score') == sc]
    for m in matching_raw:
        if m.get('difficulty') != c_diff:
            mismatches.append({
                "chart_id": cid,
                "title": title,
                "chart_diff": c_diff,
                "chart_const": const,
                "score": sc,
                "raw_diff": m.get('difficulty'),
                "raw_chart_id": m.get('chart_id')
            })

print(f"\nCorrupted records found in DB: {len(mismatches)}")
print("Sample corrupted records:")
for m in mismatches[:15]:
    print(f"  Chart in DB: [{m['chart_id']}] {m['title']} ({m['chart_diff']}, 定数{m['chart_const']})")
    print(f"    <- ACTUAL RAW SCORE: {m['raw_diff']} (chart_id: {m['raw_chart_id']}), Score: {m['score']}")

conn.close()
