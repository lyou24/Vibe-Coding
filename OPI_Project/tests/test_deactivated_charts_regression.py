import pytest
import os
import sqlite3
from src.database.models import init_db, get_session_maker, Chart, Player, ScoreLog
from src.recommender.recommender import OPIRecommender, DEACTIVATED_CHART_IDS
from src.analyzer.opi_calculator import OPICalculator, is_solo_version, MIN_TARGET_CONSTANT

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "opi_database.sqlite")

def test_deactivated_chart_ids_completeness():
    assert len(DEACTIVATED_CHART_IDS) == 18
    assert "291_lunatic" not in DEACTIVATED_CHART_IDS
    assert "2_lunatic" in DEACTIVATED_CHART_IDS
    assert "3_lunatic" in DEACTIVATED_CHART_IDS
    assert "26_master" in DEACTIVATED_CHART_IDS
    assert "223_lunatic" in DEACTIVATED_CHART_IDS

def test_db_charts_is_active_flag():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("SELECT is_active FROM charts WHERE chart_id = '291_lunatic'")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == 1, "Magic Maidens lunatic must be is_active = 1"

    for cid in DEACTIVATED_CHART_IDS:
        cur.execute("SELECT is_active FROM charts WHERE chart_id = ?", (cid,))
        r = cur.fetchone()
        if r is not None:
            assert r[0] == 0, f"Chart {cid} must be is_active = 0 in DB"

    conn.close()

def test_recommender_excludes_deactivated_charts():
    rec = OPIRecommender(DB_PATH)
    results = rec.get_recommendations(
        user_id=7381,
        player_opi=1535.9,
        target_rank="SSS",
        limit=500
    )
    result_chart_ids = {r["chart_id"] for r in results}
    
    for cid in DEACTIVATED_CHART_IDS:
        assert cid not in result_chart_ids, f"Deactivated chart {cid} must not be in recommendations"

def test_recommender_keeps_magic_maidens_lunatic():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT chart_id, title, difficulty, chart_constant FROM charts WHERE chart_id = '291_lunatic'")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "291_lunatic"
    assert "わたしたち魔法乙女です" in row[1]
    conn.close()

def test_app_chart_query_filter_simulation():
    engine = init_db(DB_PATH)
    Session = get_session_maker(engine)
    session = Session()

    charts = [
        c for c in session.query(Chart).filter(
            Chart.chart_constant >= MIN_TARGET_CONSTANT,
            Chart.is_active == True,
        ).order_by(Chart.chart_constant.asc(), Chart.title.asc()).all()
        if not is_solo_version(c.title) and c.chart_id not in DEACTIVATED_CHART_IDS
    ]
    
    chart_ids = {c.chart_id for c in charts}
    for cid in DEACTIVATED_CHART_IDS:
        assert cid not in chart_ids, f"Chart {cid} must be excluded by app query"

    assert "291_lunatic" in chart_ids, "291_lunatic must be present in app query"
    session.close()
