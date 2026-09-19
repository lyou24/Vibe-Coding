"""校正DBの推定結果のtarget_rankとchart_idの対応を確認"""
import sqlite3

conn = sqlite3.connect("data/opi_calibration.sqlite", timeout=60)
cur = conn.cursor()

# run_id=11 のestimableで高定数の結果
print("=== run_id=11 高定数 estimable ===")
cur.execute("""
    SELECT ipe.chart_id, ipe.target_rank, ipe.x, ipe.y, cmi.title, cmi.chart_constant
    FROM item_parameter_estimates ipe
    JOIN chart_master_items cmi ON ipe.chart_id = cmi.chart_id
    WHERE ipe.run_id = 11 AND ipe.is_estimable = 1 AND cmi.chart_constant >= 15.0
    ORDER BY cmi.chart_constant DESC, ipe.target_rank
    LIMIT 30
""")
rows = cur.fetchall()
for row in rows:
    print(f"  {row[0]} rank={row[1]} x={row[2]:.1f} y={row[3]:.1f} | {row[4]} ({row[5]})")

# 本番DBのchart_idフォーマット確認
print("\n=== 本番DBのchart_idフォーマット (高定数) ===")
conn2 = sqlite3.connect("data/opi_database.sqlite", timeout=30)
cur2 = conn2.cursor()
cur2.execute("SELECT chart_id, title, chart_constant FROM charts WHERE chart_constant >= 15.0 ORDER BY chart_constant DESC LIMIT 10")
for row in cur2.fetchall():
    print(f"  {row[0]} | {row[1]} ({row[2]})")

# 校正DB chart_idフォーマット確認
print("\n=== 校正DBのchart_idフォーマット (高定数) ===")
cur.execute("SELECT chart_id, title, chart_constant FROM chart_master_items WHERE chart_constant >= 15.0 ORDER BY chart_constant DESC LIMIT 10")
for row in cur.fetchall():
    print(f"  {row[0]} | {row[1]} ({row[2]})")

conn2.close()
conn.close()
