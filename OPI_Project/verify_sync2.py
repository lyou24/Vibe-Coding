"""本番DBの同期状況をコンパクトに確認"""
import sqlite3

conn = sqlite3.connect("data/opi_database.sqlite", timeout=30)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM charts WHERE opi_sss_x IS NOT NULL")
print(f"opi_sss_x 設定済: {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM charts WHERE opi_sss_x IS NULL")
print(f"opi_sss_x 未設定: {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM charts")
print(f"全譜面数: {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM charts WHERE chart_constant >= 14.0 AND title LIKE '%ソロ%'")
print(f"ソロver.(定数14以上): {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM players WHERE total_opi IS NOT NULL")
print(f"OPI算出済プレイヤー: {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM players")
print(f"全プレイヤー: {cur.fetchone()[0]}")

# 校正同期状態
try:
    cur.execute("SELECT run_id, model_version, estimate_count, updated_count FROM opi_calibration_state")
    row = cur.fetchone()
    if row:
        print(f"校正同期: run_id={row[0]}, model={row[1]}, estimates={row[2]}, updated={row[3]}")
    else:
        print("校正同期: 状態レコードなし")
except:
    print("校正同期: テーブルなし")

# 高定数曲のOPIサンプル
print("\n--- 高定数曲のOPI値 (上位10) ---")
cur.execute("""
    SELECT title, chart_constant, opi_sss_x, opi_abp_x, opi_sss_y
    FROM charts 
    WHERE opi_sss_x IS NOT NULL AND chart_constant >= 15.0
    ORDER BY chart_constant DESC 
    LIMIT 10
""")
for row in cur.fetchall():
    print(f"  {row[0]} (定数{row[1]}) SSS={row[2]}, AB+={row[3]}, y={row[4]}")

conn.close()
