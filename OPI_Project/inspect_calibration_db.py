"""校正DBの構造とデータを調査するスクリプト"""
import sqlite3

conn = sqlite3.connect("data/opi_calibration.sqlite", timeout=60)
cur = conn.cursor()

# テーブル一覧
print("=== テーブル一覧 ===")
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cur.fetchall()
for t in tables:
    print(f"  {t[0]}")

# 各テーブルのスキーマと行数
for t in tables:
    tname = t[0]
    print(f"\n=== {tname} ===")
    cur.execute(f"PRAGMA table_info({tname})")
    cols = cur.fetchall()
    for c in cols:
        print(f"  {c[1]} ({c[2]})")
    cur.execute(f"SELECT COUNT(*) FROM {tname}")
    count = cur.fetchone()[0]
    print(f"  行数: {count}")

# item_parameter_estimates のサンプル
print("\n=== item_parameter_estimates サンプル ===")
try:
    cur.execute("SELECT * FROM item_parameter_estimates LIMIT 5")
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    print(f"  カラム: {cols}")
    for row in rows:
        print(f"  {row}")
except Exception as e:
    print(f"  テーブルなし or エラー: {e}")

# estimation_runs のサンプル
print("\n=== estimation_runs サンプル ===")
try:
    cur.execute("SELECT * FROM estimation_runs ORDER BY run_id DESC LIMIT 5")
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    print(f"  カラム: {cols}")
    for row in rows:
        print(f"  {row}")
except Exception as e:
    print(f"  テーブルなし or エラー: {e}")

# players テーブル確認
print("\n=== players サンプル ===")
try:
    cur.execute("SELECT * FROM players LIMIT 10")
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    print(f"  カラム: {cols}")
    for row in rows:
        print(f"  {row}")
except Exception as e:
    print(f"  テーブルなし or エラー: {e}")

# score_logs テーブル確認
print("\n=== score_logs サンプル ===")
try:
    cur.execute("SELECT * FROM score_logs LIMIT 5")
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    print(f"  カラム: {cols}")
    for row in rows:
        print(f"  {row}")
except Exception as e:
    print(f"  テーブルなし or エラー: {e}")

# charts テーブル確認
print("\n=== charts サンプル ===")
try:
    cur.execute("SELECT * FROM charts LIMIT 3")
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    print(f"  カラム: {cols}")
    for row in rows:
        print(f"  {row}")
except Exception as e:
    print(f"  テーブルなし or エラー: {e}")

# ソロver.を含む楽曲を確認
print("\n=== ソロver.を含む楽曲 ===")
try:
    cur.execute("SELECT DISTINCT title FROM charts WHERE title LIKE '%ソロver%' OR title LIKE '%ソロVer%' OR title LIKE '%ソロver%'")
    rows = cur.fetchall()
    print(f"  件数: {len(rows)}")
    for row in rows:
        print(f"  {row[0]}")
except Exception as e:
    print(f"  エラー: {e}")

# 本番DBでもソロver.を確認
print("\n=== 本番DB ソロver.を含む楽曲 ===")
try:
    conn2 = sqlite3.connect("data/opi_database.sqlite", timeout=30)
    cur2 = conn2.cursor()
    cur2.execute("SELECT chart_id, title, chart_constant FROM charts WHERE title LIKE '%ソロ%'")
    rows = cur2.fetchall()
    print(f"  件数: {len(rows)}")
    for row in rows:
        print(f"  {row}")
    conn2.close()
except Exception as e:
    print(f"  エラー: {e}")

conn.close()
print("\n=== 完了 ===")
