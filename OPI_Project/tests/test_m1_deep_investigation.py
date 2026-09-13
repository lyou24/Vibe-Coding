import sys
import os
import json
import sqlite3
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
DB_PATH = DATA_DIR / 'opi_database.sqlite'
SEED_JSON_PATH = DATA_DIR / 'seed_data.json'

with open(SEED_JSON_PATH, 'r', encoding='utf-8') as f:
    seed_data = json.load(f)

music_master = seed_data["music_master"]
scores = seed_data["test_user"]["scores"]

print("==================================================")
print("INVESTIGATION 1: 定数 15.8, 15.9（怨撃、Apolloなど）の定数値確認")
print("==================================================")
target_titles = ["怨撃", "Apollo", "Recoil", "光焔のラテラルアーク", "Op.I《fear-TITΛN-》", "Trrricksters!!", "感情アクセラレイション", "Starring Stars"]
for m in music_master:
    if m["title"] in target_titles:
        print(f"Chart: {m['chart_id']}, Title: {m['title']}, Diff: {m['difficulty']}, Level: {m['level']}, Const: {m['chart_constant']}")

print("\n定数 15.7 以上の全譜面:")
for m in music_master:
    if m["chart_constant"] >= 15.7:
        print(f"  {m['chart_id']}: {m['title']} ({m['difficulty']}) const={m['chart_constant']}")

print("\n==================================================")
print("INVESTIGATION 2: seed.py のスコア登録で 416件 になる理由の調査")
print("==================================================")
# seed.py の照合ロジックをシミュレーションして、なぜ 744件 -> 416件 になるのか追跡する
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

all_charts = cur.execute("SELECT chart_id, title, difficulty, chart_constant FROM charts").fetchall()
chart_by_id = {c[0]: c for c in all_charts}
chart_by_title_diff = {(c[1], c[2]): c for c in all_charts}
chart_by_title = {c[1]: c for c in all_charts}

registered_charts = set()
skipped_no_chart = []
multiple_scores_for_same_chart = {}

for s in scores:
    target_chart = None
    if s.get("chart_id") and s["chart_id"] in chart_by_id:
        target_chart = chart_by_id[s["chart_id"]]
        match_type = "by_id"
    elif (s.get("title"), s.get("difficulty", "").upper()) in chart_by_title_diff:
        target_chart = chart_by_title_diff[(s["title"], s.get("difficulty", "").upper())]
        match_type = "by_title_diff"
    elif s.get("title") in chart_by_title:
        target_chart = chart_by_title[s["title"]]
        match_type = "by_title_only"
    else:
        target_chart = None
        match_type = "none"

    if not target_chart:
        skipped_no_chart.append(s)
    else:
        cid = target_chart[0]
        if cid in registered_charts:
            if cid not in multiple_scores_for_same_chart:
                multiple_scores_for_same_chart[cid] = []
            multiple_scores_for_same_chart[cid].append(s)
        registered_charts.add(cid)

print(f"Total scores in seed: {len(scores)}")
print(f"Unique charts matched: {len(registered_charts)}")
print(f"Scores skipped (not in charts >= 13.7): {len(skipped_no_chart)}")
print(f"Sum: {len(registered_charts)} + {len(skipped_no_chart)} = {len(registered_charts) + len(skipped_no_chart)}")
print(f"Multiple scores for same chart count: {len(multiple_scores_for_same_chart)}")

if multiple_scores_for_same_chart:
    print("\nCharts with multiple score entries in seed scores:")
    for cid, s_list in list(multiple_scores_for_same_chart.items())[:5]:
        print(f"  Chart ID {cid} has {len(s_list)+1} scores:")
        c_info = chart_by_id[cid]
        print(f"    Chart in DB: {c_info}")
        for s in s_list:
            print(f"    Duplicate score: title='{s.get('title')}', diff='{s.get('difficulty')}', score={s.get('score')}")

# 先ほどの 588件マッチ と 416件 の差分の正体
# 先ほどのテストでは title in master_titles (難易度を無視してタイトルだけでマッチ) を含めていた！
# 同一タイトルで難易度違い（MASTERとEXPERTなど）がある場合どうなるか？
print("\n難易度の一致を確認:")
matched_exact = 0
matched_diff_mismatch = 0
for s in scores:
    cid = s.get("chart_id")
    title = s.get("title")
    diff = s.get("difficulty", "").upper()
    if cid and cid in chart_by_id:
        matched_exact += 1
    elif (title, diff) in chart_by_title_diff:
        matched_exact += 1
    elif title in chart_by_title:
        matched_diff_mismatch += 1
        # print(f"  Title matched but diff mismatched: score diff={diff}, DB diff={chart_by_title[title][2]}")

print(f"Exact match (by chart_id or (title, diff)): {matched_exact}")
print(f"Diff mismatch (title matched to different difficulty): {matched_diff_mismatch}")

conn.close()
