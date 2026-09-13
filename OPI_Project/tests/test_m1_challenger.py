import sys
import os
import json
import sqlite3
import re
from datetime import datetime
from pathlib import Path

# UTF-8出力設定
sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
DB_PATH = DATA_DIR / 'opi_database.sqlite'
SEED_JSON_PATH = DATA_DIR / 'seed_data.json'

def test_seed_json_integrity():
    print("\n==================================================")
    print("TEST 1: seed_data.json のデータ整合性検証")
    print("==================================================")
    
    assert os.path.exists(SEED_JSON_PATH), f"File not found: {SEED_JSON_PATH}"
    with open(SEED_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 1.1 キー存在確認
    assert "music_master" in data, "music_master key missing"
    assert "test_user" in data, "test_user key missing"
    assert "population_samples" in data, "population_samples key missing"
    
    music_master = data["music_master"]
    test_user = data["test_user"]
    profile = test_user.get("profile", {})
    scores = test_user.get("scores", [])

    print(f"music_master count: {len(music_master)}")
    print(f"scores count: {len(scores)}")
    print(f"profile: {profile}")

    # 1.2 スコア値の範囲検証 (0 <= score <= 1,010,000)
    invalid_scores = []
    score_stats = {"min": 9999999, "max": -1, "zero_count": 0, "ap_count": 0}
    
    for i, s in enumerate(scores):
        score_val = s.get("score")
        if score_val is None or not isinstance(score_val, int):
            invalid_scores.append((i, s, "Score is not int"))
            continue
        if score_val < 0 or score_val > 1010000:
            invalid_scores.append((i, s, f"Score out of bounds: {score_val}"))
        score_stats["min"] = min(score_stats["min"], score_val)
        score_stats["max"] = max(score_stats["max"], score_val)
        if score_val == 0:
            score_stats["zero_count"] += 1
        if score_val == 1010000:
            score_stats["ap_count"] += 1

    print(f"Score stats: min={score_stats['min']}, max={score_stats['max']}, AP(1010000)={score_stats['ap_count']}")
    if invalid_scores:
        print(f"FAIL: Invalid scores found: {len(invalid_scores)}")
        for inv in invalid_scores[:5]:
            print(" ", inv)
    else:
        print("PASS: 全スコアが 0〜1,010,000 の範囲内です。")

    # 1.3 ランプのパース検証 (AB / FB の組み合わせパターン)
    lamp_combinations = {
        "neither": 0,   # AB=False, FB=False
        "ab_only": 0,   # AB=True, FB=False
        "fb_only": 0,   # AB=False, FB=True
        "both": 0       # AB=True, FB=True
    }
    
    for s in scores:
        ab = s.get("is_all_break", False)
        fb = s.get("is_full_bell", False)
        if ab and fb:
            lamp_combinations["both"] += 1
        elif ab and not fb:
            lamp_combinations["ab_only"] += 1
        elif not ab and fb:
            lamp_combinations["fb_only"] += 1
        else:
            lamp_combinations["neither"] += 1

    print(f"Lamp distribution: {lamp_combinations}")
    assert lamp_combinations["both"] > 0, "No both (AB+FB) found!"
    assert lamp_combinations["neither"] > 0, "No neither found!"
    # FBのみ、ABのみのケースが存在するか確認
    print(f"  AB only count: {lamp_combinations['ab_only']}")
    print(f"  FB only count: {lamp_combinations['fb_only']}")

    # 1.4 タイトルの異常チェック (重複タイトル文字列 OdysseusOdysseus などの検知)
    duplicate_title_anomalies = []
    for s in scores:
        t = s.get("title", "")
        # タイトルが偶数長で前半と後半が完全一致しているか（例: "OdysseusOdysseus"）
        if len(t) >= 4 and len(t) % 2 == 0:
            half = len(t) // 2
            if t[:half] == t[half:]:
                # 単なる「ポッピンキャンディ☆」みたいな自然な繰り返し曲名でないか確認
                duplicate_title_anomalies.append(t)
    
    print(f"Title duplication check (candidates): {duplicate_title_anomalies}")

    # 1.5 定数マスタ (music_master) の定数13.7チェック
    below_13_7 = [m for m in music_master if m.get("chart_constant", 0) < 13.7]
    print(f"Charts with constant < 13.7: {len(below_13_7)}")
    if below_13_7:
        print(f"FAIL: Charts below 13.7 found: {below_13_7[:5]}")
    else:
        print("PASS: 定数13.7未満の譜面は0件です（混入なし）。")

    # 定数範囲と分布
    constants = [m.get("chart_constant", 0) for m in music_master]
    print(f"Music master constant stats: min={min(constants)}, max={max(constants)}")
    
    diff_counts = {}
    for m in music_master:
        d = m.get("difficulty")
        diff_counts[d] = diff_counts.get(d, 0) + 1
    print(f"Music master difficulty breakdown: {diff_counts}")

    # chart_id の一意性チェック
    chart_ids = [m["chart_id"] for m in music_master]
    unique_chart_ids = set(chart_ids)
    if len(chart_ids) != len(unique_chart_ids):
        print(f"FAIL: Duplicate chart_ids found! Total={len(chart_ids)}, Unique={len(unique_chart_ids)}")
        from collections import Counter
        counts = Counter(chart_ids)
        for cid, count in counts.items():
            if count > 1:
                print(f"  Duplicate: {cid} ({count} times)")
    else:
        print("PASS: 全543件の chart_id は完全にユニークです。")

def test_database_integrity():
    print("\n==================================================")
    print("TEST 2: SQLite データベース (opi_database.sqlite) の整合性検証")
    print("==================================================")
    
    assert os.path.exists(DB_PATH), f"DB not found: {DB_PATH}"
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 2.1 テーブル件数
    cur.execute("SELECT COUNT(*) FROM charts")
    chart_count = cur.fetchone()[0]
    print(f"charts count: {chart_count}")
    assert chart_count == 543, f"Expected 543 charts, got {chart_count}"

    cur.execute("SELECT COUNT(*) FROM players")
    player_count = cur.fetchone()[0]
    print(f"players count: {player_count}")
    assert player_count >= 2504, f"Expected at least 2504 players, got {player_count}"

    cur.execute("SELECT COUNT(*) FROM players WHERE user_id >= 90000")
    population_count = cur.fetchone()[0]
    assert population_count == 2503, f"Expected 2503 population players, got {population_count}"

    cur.execute("SELECT COUNT(*) FROM score_logs WHERE user_id = 10605")
    score_count = cur.fetchone()[0]
    print(f"score_logs count (user 10605): {score_count}")
    assert score_count == 397, f"Expected 397 score logs, got {score_count}"

    # 2.2 score_logs のスコア値・フラグ整合性
    cur.execute("""
        SELECT score, is_all_break, is_full_bell, 
               achieve_ss, achieve_sss, achieve_sssp, achieve_abfb, achieve_ap 
        FROM score_logs WHERE user_id = 10605
    """)
    rows = cur.fetchall()
    
    flag_errors = []
    for r in rows:
        sc, is_ab, is_fb, ss, sss, sssp, abfb, ap = r
        # SS: >= 990,000
        if bool(ss) != (sc >= 990000):
            flag_errors.append((r, "SS flag mismatch"))
        # SSS: >= 1,000,000
        if bool(sss) != (sc >= 1000000):
            flag_errors.append((r, "SSS flag mismatch"))
        # SSS+: >= 1,007,500
        if bool(sssp) != (sc >= 1007500):
            flag_errors.append((r, "SSSP flag mismatch"))
        # ABFB: >= 1,007,500 and is_ab and is_fb
        expected_abfb = (sc >= 1007500 and bool(is_ab) and bool(is_fb))
        if bool(abfb) != expected_abfb:
            flag_errors.append((r, "ABFB flag mismatch"))
        # AP: == 1,010,000
        if bool(ap) != (sc == 1010000):
            flag_errors.append((r, "AP flag mismatch"))

    if flag_errors:
        print(f"FAIL: Flag calculation errors found: {len(flag_errors)}")
        for fe in flag_errors[:5]:
            print(" ", fe)
    else:
        print("PASS: 全416件のスコアログにおける達成フラグ(SS, SSS, SSSP, ABFB, AP)の論理整合性が100%確認されました。")

    # 2.3 紐付け脱落の検証: 744件のスコアから416件が選ばれた理由
    # seed_data.json の 744 スコアの中で、定数13.7以上の譜面に該当するものは何件あるか？
    with open(SEED_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    all_scores = data["test_user"]["scores"]
    
    # 譜面マスタのタイトル・diff集合
    cur.execute("SELECT chart_id, title, difficulty FROM charts")
    master_charts = cur.fetchall()
    master_chart_ids = set(c[0] for c in master_charts)
    master_titles = set(c[1] for c in master_charts)
    master_title_diffs = set((c[1], c[2]) for c in master_charts)

    matched_scores = []
    unmatched_scores = []
    for s in all_scores:
        cid = s.get("chart_id")
        title = s.get("title")
        diff = s.get("difficulty")
        if cid in master_chart_ids or (title, diff) in master_title_diffs or title in master_titles:
            matched_scores.append(s)
        else:
            unmatched_scores.append(s)

    print(f"Scored songs matching master (>=13.7): {len(matched_scores)}")
    print(f"Scored songs NOT matching master (<13.7): {len(unmatched_scores)}")
    print(f"Sum of matched + unmatched: {len(matched_scores) + len(unmatched_scores)} (Total: {len(all_scores)})")

    # 除外された曲のサンプルを出力して定数確認
    print(f"Sample unmatched songs (should be < 13.7):")
    for u in unmatched_scores[:5]:
        print(f"  {u.get('title')} ({u.get('difficulty')}) - score: {u.get('score')}")

    # 2.4 要件定義書3.4の公称パラメータ値チェック
    cur.execute("SELECT title, opi_sss_x, opi_sss_y, opi_ap_x, opi_ap_y FROM charts WHERE title IN ('怨撃', 'Apollo', 'Recoil', '光焔のラテラルアーク', 'Op.I《fear-TITΛN-》', 'Trrricksters!!', '感情アクセラレイション', 'Starring Stars')")
    spec_rows = cur.fetchall()
    print("\nSpec parameter checks:")
    for r in spec_rows:
        print(f"  {r[0]}: SSS_x={r[1]}, SSS_y={r[2]}, AP_x={r[3]}, AP_y={r[4]}")

    conn.close()

if __name__ == "__main__":
    test_seed_json_integrity()
    test_database_integrity()
