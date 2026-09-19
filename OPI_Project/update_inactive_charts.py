import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3

# 除外対象の18譜面ID
TARGET_CHART_IDS = [
    "2_lunatic",   # シュガーソングとビターステップ (LUNATIC 13+)
    "3_lunatic",   # 回レ！雪月花 (LUNATIC 14)
    "26_master",   # ぼくらの16bit戦争 (MASTER 13+)
    "32_lunatic",  # ブリキノダンス (LUNATIC 13+)
    "89_lunatic",  # No Remorse (LUNATIC 14)
    "201_master",  # GO! GO! MANIAC (MASTER 13+)
    "223_lunatic", # 緋蜂 (LUNATIC 14+)
    "305_lunatic", # どどんぱち大音頭 (LUNATIC 13+)
    "393_lunatic", # 東亞 -O.N.G.E.K.I. MIX- (LUNATIC 13+)
    "404_master",  # この番組はうら若き公務員たちの提供でお送りいたします (MASTER 13+)
    "586_lunatic", # Hide & Attack (LUNATIC 13+)
    "670_master",  # 腐れ外道とチョコレゐト (MASTER 13+)
    "689_lunatic", # うまぴょい伝説 (LUNATIC 13+)
    "690_master",  # HEAVEN'S RAVE (MASTER 13+)
    "711_lunatic", # Ἀταραξία (LUNATIC 13+)
    "735_lunatic", # 空色メモリーズ (LUNATIC 13+)
    "749_master",  # タイガーランペイジ (MASTER 13+)
    "887_master",  # アンチグラビティ・ガール (MASTER 13+)
]

conn = sqlite3.connect('data/opi_database.sqlite')
cursor = conn.cursor()

# 念のため「291_lunatic」がリストに含まれていないことを保証
assert "291_lunatic" not in TARGET_CHART_IDS, "291_lunatic must NOT be deleted!"

# 更新前の確認
cursor.execute("SELECT chart_id, title, difficulty, level, is_active FROM charts WHERE chart_id IN ({})".format(
    ",".join("?" * len(TARGET_CHART_IDS))
), TARGET_CHART_IDS)
rows = cursor.fetchall()
print(f"Found {len(rows)} charts to deactivate:")
for r in rows:
    print(f"  {r[0]}: {r[1]} ({r[2]} {r[3]}), current is_active={r[4]}")

# is_active = 0 に更新
cursor.execute("UPDATE charts SET is_active = 0 WHERE chart_id IN ({})".format(
    ",".join("?" * len(TARGET_CHART_IDS))
), TARGET_CHART_IDS)
conn.commit()

# 更新後の確認
cursor.execute("SELECT count(*) FROM charts WHERE is_active = 0")
inactive_count = cursor.fetchone()[0]
print(f"\nInactive charts count in DB: {inactive_count}")

cursor.execute("SELECT chart_id, title, is_active FROM charts WHERE chart_id = '291_lunatic'")
otome = cursor.fetchone()
print(f"Check 'わたしたち魔法乙女です☆': {otome}")

conn.close()
print("Database update successfully completed.")
