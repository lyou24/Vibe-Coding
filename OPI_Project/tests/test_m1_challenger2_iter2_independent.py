import os
import sys
import json
import sqlite3
import pytest
import asyncio
from sqlalchemy.exc import IntegrityError

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.database.models import get_engine, get_session_maker, ScoreLog, Chart, Player, DifficultyEnum
from src.crawler.ongeki_crawler import OngekiCrawler

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "opi_database.sqlite")
SEED_JSON_PATH = os.path.join(DATA_DIR, "seed_data.json")

def test_independent_score_logs_difficulty_strict_matching():
    """
    【独立検証】スコアログ397件の難易度完全一致
    - MASTER 譜面に MASTER 以外のスコアが1件も入っていないこと
    - LUNATIC 譜面に LUNATIC 以外のスコアが1件も入っていないこと
    - EXPERT 譜面に EXPERT 以外のスコアが1件も入っていないこと
    - BASIC, ADVANCED のスコアが1件も入っていないこと
    """
    assert os.path.exists(DB_PATH)
    with open(SEED_JSON_PATH, "r", encoding="utf-8") as f:
        seed_data = json.load(f)

    raw_scores = seed_data["test_user"]["scores"]
    music_master = seed_data["music_master"]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT s.chart_id, c.title, c.difficulty, c.chart_constant,
               s.score, s.is_all_break, s.is_full_bell,
               s.achieve_ss, s.achieve_sss, s.achieve_sssp
        FROM score_logs s
        JOIN charts c ON s.chart_id = c.chart_id
        WHERE s.user_id = 10605
    """)
    records = cur.fetchall()
    conn.close()

    assert len(records) == 397, f"Expected 397 records, got {len(records)}"

    master_scores = []
    lunatic_scores = []
    expert_scores = []
    other_scores = []

    for r in records:
        diff = r[2].upper()
        if diff == "MASTER":
            master_scores.append(r)
        elif diff == "LUNATIC":
            lunatic_scores.append(r)
        elif diff == "EXPERT":
            expert_scores.append(r)
        else:
            other_scores.append(r)

    assert len(other_scores) == 0, f"Found scores with invalid difficulty: {other_scores}"
    assert len(master_scores) == 337, f"Expected 337 MASTER scores, got {len(master_scores)}"
    assert len(lunatic_scores) == 36, f"Expected 36 LUNATIC scores, got {len(lunatic_scores)}"
    assert len(expert_scores) == 24, f"Expected 24 EXPERT scores, got {len(expert_scores)}"

    # 生ログとの完全一致（1件も取り違えがないこと）
    # raw_scores から (title, difficulty) をキーとした辞書を作成
    raw_by_title_diff = {}
    for s in raw_scores:
        key = (s["title"], s["difficulty"].upper())
        raw_by_title_diff[key] = s

    for r in records:
        cid, title, diff, constant, score, is_ab, is_fb, ss, sss, sssp = r
        key = (title, diff.upper())
        assert key in raw_by_title_diff, f"Score for {key} in DB but not found in raw scores!"
        raw_s = raw_by_title_diff[key]
        assert raw_s["difficulty"].upper() == diff.upper(), (
            f"Difficulty mismatch for {title}: DB={diff}, RAW={raw_s['difficulty']}"
        )
        assert raw_s["score"] == score, (
            f"Score mismatch for {title} ({diff}): DB={score}, RAW={raw_s['score']}"
        )

def test_same_title_multi_difficulty_separation():
    """
    同一曲名で複数難易度（定数13.7以上）が存在する場合、
    難易度ごとに正しく別のスコア（または該当難易度のみ）が紐付いていること
    """
    with open(SEED_JSON_PATH, "r", encoding="utf-8") as f:
        seed_data = json.load(f)
    raw_scores = seed_data["test_user"]["scores"]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # 同一曲名で複数譜面が charts に存在するもの
    cur.execute("""
        SELECT title, COUNT(*)
        FROM charts
        GROUP BY title
        HAVING COUNT(*) > 1
    """)
    multi_charts_titles = [row[0] for row in cur.fetchall()]

    for title in multi_charts_titles:
        cur.execute("""
            SELECT s.chart_id, c.title, c.difficulty, s.score
            FROM score_logs s
            JOIN charts c ON s.chart_id = c.chart_id
            WHERE s.user_id = 10605 AND c.title = ?
        """, (title,))
        logs = cur.fetchall()
        for cid, t, diff, sc in logs:
            # raw_scores 内で (title, diff) に該当するスコアと一致するか
            matching_raw = [
                s for s in raw_scores
                if s["title"] == title and s["difficulty"].upper() == diff.upper()
            ]
            assert len(matching_raw) == 1, (
                f"Expected exactly 1 raw score for {title} [{diff}], found {len(matching_raw)}"
            )
            assert matching_raw[0]["score"] == sc, (
                f"Cross-contamination detected for {title} [{diff}]! DB score={sc}, RAW={matching_raw[0]['score']}"
            )
    conn.close()

def test_unique_constraint_enforcement():
    """
    DBレベルの複合一意制約 (user_id, chart_id) が物理的に二重登録を阻止すること
    """
    engine = get_engine(DB_PATH)
    Session = get_session_maker(engine)
    session = Session()

    # 既存のスコアログを1件取得
    first_log = session.query(ScoreLog).first()
    assert first_log is not None

    # 同一の (user_id, chart_id) で重複登録を試行
    duplicate_log = ScoreLog(
        user_id=first_log.user_id,
        chart_id=first_log.chart_id,
        score=999999
    )
    session.add(duplicate_log)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.close()

@pytest.mark.asyncio
async def test_crawler_context_manager_resource_cleanup():
    """
    OngekiCrawler の __aenter__ / __aexit__ が正しくセッションを管理・解放すること
    """
    crawler_instance = None
    async with OngekiCrawler() as crawler:
        crawler_instance = crawler
        assert crawler.session is not None
        assert not crawler.session.closed

    assert crawler_instance.session.closed, "Crawler session was not closed on exit!"

if __name__ == "__main__":
    test_independent_score_logs_difficulty_strict_matching()
    test_same_title_multi_difficulty_separation()
    test_unique_constraint_enforcement()
    asyncio.run(test_crawler_context_manager_resource_cleanup())
    print("ALL 4 INDEPENDENT EMPIRICAL TESTS PASSED DIRECTLY!")
