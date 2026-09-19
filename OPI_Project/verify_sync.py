"""本番DBの譜面OPIパラメータが校正DBから同期されているか検証"""
import sqlite3

conn = sqlite3.connect("data/opi_database.sqlite", timeout=30)
cur = conn.cursor()

# OPIパラメータが設定されている譜面数を確認
cur.execute("SELECT COUNT(*) FROM charts WHERE opi_sss_x IS NOT NULL")
sss_count = cur.fetchone()[0]
print(f"opi_sss_x が設定済の譜面数: {sss_count}")

cur.execute("SELECT COUNT(*) FROM charts WHERE opi_sss_x IS NULL")
null_count = cur.fetchone()[0]
print(f"opi_sss_x が未設定の譜面数: {null_count}")

cur.execute("SELECT COUNT(*) FROM charts")
total = cur.fetchone()[0]
print(f"全譜面数: {total}")

# サンプル表示
print("\n=== OPIパラメータ設定済み譜面サンプル ===")
cur.execute("""
    SELECT chart_id, title, chart_constant, 
           opi_s_x, opi_ss_x, opi_sss_x, opi_sssp_x, opi_abp_x,
           opi_sss_y
    FROM charts 
    WHERE opi_sss_x IS NOT NULL 
    ORDER BY chart_constant DESC 
    LIMIT 15
""")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} (定数{row[2]}) S={row[3]}, SS={row[4]}, SSS={row[5]}, SSS+={row[6]}, AB+={row[7]}, y={row[8]}")

# ソロver.楽曲の確認（定数14以上）
print("\n=== ソロver.楽曲（定数14.0以上） ===")
cur.execute("SELECT chart_id, title, chart_constant FROM charts WHERE chart_constant >= 14.0 AND title LIKE '%ソロ%'")
rows = cur.fetchall()
print(f"  件数: {len(rows)}")
for row in rows:
    print(f"  {row}")

# 校正同期状態の確認
print("\n=== 校正同期状態 ===")
try:
    cur.execute("SELECT * FROM opi_calibration_state")
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    print(f"  columns: {cols}")
    for row in rows:
        print(f"  {row}")
except Exception as e:
    print(f"  テーブルなし: {e}")

# プレイヤーデータ確認
print("\n=== 登録プレイヤー ===")
cur.execute("SELECT user_id, player_name, rating, total_opi FROM players")
rows = cur.fetchall()
print(f"  登録数: {len(rows)}")
for row in rows:
    print(f"  ID={row[0]}, Name={row[1]}, Rate={row[2]}, OPI={row[3]}")

conn.close()
print("\n=== 完了 ===")
