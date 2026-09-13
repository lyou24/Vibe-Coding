import os
import sys
import json
import sqlite3
import pytest

# プロジェクトルートの設定
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "opi_database.sqlite")
SEED_JSON_PATH = os.path.join(DATA_DIR, "seed_data.json")

def load_seed_data():
    with open(SEED_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# ==============================================================================
# 1. スコアログの数値範囲・型・論理整合性テスト
# ==============================================================================
def test_score_values_range():
    """744件の全スコア値が 0 〜 1,010,000 の範囲内であること"""
    seed_data = load_seed_data()
    scores = seed_data["test_user"]["scores"]
    assert len(scores) == 744, f"Expected 744 scores, got {len(scores)}"

    for s in scores:
        score = s.get("score")
        assert isinstance(score, int), f"Score must be int, got {type(score)} for {s}"
        assert 0 <= score <= 1010000, f"Score out of valid bounds (0~1010000): {score} in {s}"

# ==============================================================================
# 2. ランプ判定（AB, FB）の網羅的テスト
# ==============================================================================
def test_lamp_parsing_combinations():
    """ランプ（AB, FB）の4パターン（両方、ABのみ、FBのみ、なし）が正しくパースされていること"""
    seed_data = load_seed_data()
    scores = seed_data["test_user"]["scores"]

    ab_only = [s for s in scores if s.get("is_all_break") and not s.get("is_full_bell")]
    fb_only = [s for s in scores if not s.get("is_all_break") and s.get("is_full_bell")]
    both = [s for s in scores if s.get("is_all_break") and s.get("is_full_bell")]
    neither = [s for s in scores if not s.get("is_all_break") and not s.get("is_full_bell")]

    assert len(ab_only) > 0, "AB only cases should exist (found 0)"
    assert len(fb_only) > 0, "FB only cases should exist (found 0)"
    assert len(both) > 0, "Both (AB+FB) cases should exist (found 0)"
    assert len(neither) > 0, "Neither cases should exist (found 0)"
    assert len(ab_only) + len(fb_only) + len(both) + len(neither) == len(scores)

# ==============================================================================
# 3. 譜面定数13.7の境界値・完全性テスト
# ==============================================================================
def test_music_master_constant_filter():
    """music_masterの全譜面定数が13.7以上であり、未満の混入が0件であること"""
    seed_data = load_seed_data()
    music_master = seed_data["music_master"]
    assert len(music_master) == 543, f"Expected 543 charts, got {len(music_master)}"

    below_13_7 = [m for m in music_master if m.get("chart_constant", 0) < 13.7]
    assert len(below_13_7) == 0, f"Charts with constant < 13.7 found: {below_13_7}"

    chart_ids = [m["chart_id"] for m in music_master]
    assert len(chart_ids) == len(set(chart_ids)), "Duplicate chart_id found in music_master"

# ==============================================================================
# 4. 【敵対的検証】スコアマッチングにおける難易度不一致（データ汚染）テスト
# ==============================================================================
def test_db_score_logs_difficulty_integrity():
    """
    DB (score_logs) に登録されているスコアログが、マスタの譜面難易度と厳密に一致していること。
    EXPERTのスコアがMASTERの譜面に紐付けられる等のデータ汚染が存在しないことを検証する。
    """
    assert os.path.exists(DB_PATH), f"DB file not found: {DB_PATH}"
    seed_data = load_seed_data()
    raw_scores = seed_data["test_user"]["scores"]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT s.chart_id, c.title, c.difficulty, s.score
        FROM score_logs s
        JOIN charts c ON s.chart_id = c.chart_id
        WHERE s.user_id = 10605
    """)
    db_records = cur.fetchall()
    conn.close()

    corrupted = []
    for cid, title, c_diff, score in db_records:
        # 元スコアログから一致するレコードを探索
        matched_raw = [s for s in raw_scores if s.get("title") == title and s.get("score") == score]
        if not matched_raw:
            corrupted.append((cid, title, c_diff, score, "No raw score found"))
            continue
        # 難易度の一致をチェック
        raw_diffs = [s.get("difficulty") for s in matched_raw]
        if c_diff not in raw_diffs:
            corrupted.append({
                "chart_id": cid,
                "title": title,
                "db_diff": c_diff,
                "score": score,
                "raw_diff": raw_diffs[0]
            })

    assert len(corrupted) == 0, (
        f"CRITICAL: Found {len(corrupted)} corrupted score_logs in DB where difficulty was mismatched! "
        f"Sample corrupted: {corrupted[:5]}"
    )
