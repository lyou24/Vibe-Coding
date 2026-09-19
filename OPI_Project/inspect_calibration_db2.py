"""追加調査: 校正DB estimable な推定結果の詳細確認"""
import sqlite3

conn = sqlite3.connect("data/opi_calibration.sqlite", timeout=60)
cur = conn.cursor()

# 最新のitem推定run (run_id=11) の推定可能な結果
print("=== estimable item_parameter_estimates (run_id=11) サンプル ===")
cur.execute("""
    SELECT chart_id, target_rank, x, y, sample_count, achieved_count, unachieved_count
    FROM item_parameter_estimates 
    WHERE run_id = 11 AND is_estimable = 1
    ORDER BY x DESC
    LIMIT 20
""")
rows = cur.fetchall()
for row in rows:
    print(f"  {row}")

print(f"\n=== estimable件数 ===")
cur.execute("SELECT COUNT(*) FROM item_parameter_estimates WHERE run_id = 11 AND is_estimable = 1")
print(f"  {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM item_parameter_estimates WHERE run_id = 11 AND is_estimable = 0")
print(f"  unestimable: {cur.fetchone()[0]}")

# target_rank の種類確認
print(f"\n=== target_rank の種類 ===")
cur.execute("SELECT DISTINCT target_rank FROM item_parameter_estimates WHERE run_id = 11")
rows = cur.fetchall()
for row in rows:
    print(f"  {row[0]}")

# player_ability_estimates のサンプル
print(f"\n=== player_ability_estimates (run_id=10) サンプル ===")
cur.execute("""
    SELECT subject_key, theta, item_count, achieved_count, unachieved_count, is_estimable
    FROM player_ability_estimates 
    WHERE run_id = 10 AND is_estimable = 1
    ORDER BY theta DESC
    LIMIT 10
""")
rows = cur.fetchall()
for row in rows:
    print(f"  {row}")

cur.execute("SELECT COUNT(*) FROM player_ability_estimates WHERE run_id = 10 AND is_estimable = 1")
print(f"  estimable件数: {cur.fetchone()[0]}")

# chart_master_items のサンプル
print(f"\n=== chart_master_items サンプル ===")
cur.execute("SELECT * FROM chart_master_items LIMIT 5")
rows = cur.fetchall()
cols = [desc[0] for desc in cur.description]
print(f"  columns: {cols}")
for row in rows:
    print(f"  {row}")

# 校正DB内のソロver.曲確認
print(f"\n=== scores内 ソロver. 楽曲確認 ===")
cur.execute("SELECT DISTINCT title FROM scores WHERE title LIKE '%ソロver%' OR title LIKE '%ソロVer%'")
rows = cur.fetchall()
print(f"  件数: {len(rows)}")
for row in rows:
    print(f"  {row[0]}")

# item_parameter_estimates の推定可能なもので target_rank ごとの件数
print(f"\n=== target_rank別 estimable件数 (run_id=11) ===")
cur.execute("""
    SELECT target_rank, COUNT(*) 
    FROM item_parameter_estimates 
    WHERE run_id = 11 AND is_estimable = 1 
    GROUP BY target_rank
""")
rows = cur.fetchall()
for row in rows:
    print(f"  {row[0]}: {row[1]}")

conn.close()
print("\n=== 完了 ===")
