import json
import sqlite3
import sys
import os
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
seed_path = PROJECT_ROOT / 'data' / 'seed_data.json'

with open(seed_path, 'r', encoding='utf-8') as f:
    seed_data = json.load(f)

scores = seed_data['test_user']['scores']
master = seed_data['music_master']

print(f"Total scores: {len(scores)}")
print(f"Sample score with chart_id: {[s for s in scores if 'chart_id' in s][:3]}")
scores_without_chart_id = [s for s in scores if 'chart_id' not in s]
print(f"Scores WITHOUT chart_id: {len(scores_without_chart_id)}")

# scores 内の各難易度内訳
diff_counts = {}
for s in scores:
    d = s.get("difficulty")
    diff_counts[d] = diff_counts.get(d, 0) + 1
print(f"Scores difficulty breakdown: {diff_counts}")

# music_master 内の chart_id 集合
master_chart_ids = set(m['chart_id'] for m in master)
master_title_diffs = set((m['title'], m['difficulty']) for m in master)

# scores のうち、chart_id が master_chart_ids に存在するもの
scores_in_master_by_id = [s for s in scores if s.get('chart_id') in master_chart_ids]
print(f"Scores matching master by exact chart_id: {len(scores_in_master_by_id)}")

# scores のうち、(title, diff) が master_title_diffs に存在するもの
scores_in_master_by_td = [s for s in scores if (s.get('title'), s.get('difficulty')) in master_title_diffs]
print(f"Scores matching master by (title, difficulty): {len(scores_in_master_by_td)}")

# 優先度3 (title only) でマッチしてしまったケースの詳細
title_only_matches = []
master_by_title = {}
for m in master:
    master_by_title.setdefault(m['title'], []).append(m)

for s in scores:
    cid = s.get('chart_id')
    td = (s.get('title'), s.get('difficulty'))
    if cid not in master_chart_ids and td not in master_title_diffs:
        if s.get('title') in master_by_title:
            title_only_matches.append((s, master_by_title[s.get('title')]))

print(f"\nTitle only matches count: {len(title_only_matches)}")
print("Sample title only matches:")
for s, m_list in title_only_matches[:10]:
    print(f"  Score: title='{s.get('title')}', diff='{s.get('difficulty')}', score={s.get('score')}, cid={s.get('chart_id')}")
    for m in m_list:
        print(f"    -> Mapped to Master: cid='{m['chart_id']}', diff='{m['difficulty']}', const={m['chart_constant']}")

