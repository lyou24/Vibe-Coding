import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
import pandas as pd
from src.database.models import init_db, get_session_maker, Chart, Player, ScoreLog
from src.recommender.recommender import OPIRecommender
from src.analyzer.opi_calculator import MIN_TARGET_CONSTANT, is_solo_version

# 1. DB確認
conn = sqlite3.connect('data/opi_database.sqlite')
cursor = conn.cursor()
cursor.execute("SELECT chart_id, title, difficulty, level, is_active FROM charts WHERE is_active = 0")
inactive_charts = cursor.fetchall()
print(f"[TEST 1] Inactive charts count: {len(inactive_charts)} (Expected: 18)")
assert len(inactive_charts) == 18, f"Expected 18, got {len(inactive_charts)}"

# 「わたしたち魔法乙女です☆」の確認
cursor.execute("SELECT chart_id, title, difficulty, is_active FROM charts WHERE title LIKE '%魔法乙女%'")
otome_charts = cursor.fetchall()
print(f"[TEST 2] 'わたしたち魔法乙女です☆' charts: {otome_charts}")
for oc in otome_charts:
    assert oc[3] == 1, f"Chart {oc[0]} should be active, but is {oc[3]}"

conn.close()

# 2. 難易度表クエリの検証
engine = init_db('data/opi_database.sqlite')
Session = get_session_maker(engine)
session = Session()

charts = [
    c for c in session.query(Chart).filter(
        Chart.chart_constant >= MIN_TARGET_CONSTANT,
        Chart.is_active == True,
    ).order_by(Chart.chart_constant.asc(), Chart.title.asc()).all()
    if not is_solo_version(c.title)
]

chart_ids = set(c.chart_id for c in charts)
inactive_ids = set(r[0] for r in inactive_charts)

overlap = chart_ids.intersection(inactive_ids)
print(f"[TEST 3] Overlap between active query and inactive charts: {overlap} (Expected: set())")
assert len(overlap) == 0, f"Found inactive charts in difficulty table: {overlap}"

assert "291_lunatic" in chart_ids, "'291_lunatic' (魔法乙女) should be in difficulty table!"
print("[TEST 4] '291_lunatic' is present in active difficulty table: PASS")

# 3. リコメンドの検証
recommender = OPIRecommender('data/opi_database.sqlite')
recs = recommender.get_recommendations(user_id=10605, target_rank="SSS", limit=50)
rec_chart_ids = set(r.get("chart_id") for r in recs if r.get("chart_id"))
rec_overlap = rec_chart_ids.intersection(inactive_ids)
print(f"[TEST 5] Recommender overlap with inactive charts: {rec_overlap} (Expected: set())")
assert len(rec_overlap) == 0, f"Recommender returned inactive charts: {rec_overlap}"

session.close()
print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")
