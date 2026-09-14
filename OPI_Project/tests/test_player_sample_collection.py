import sqlite3
from datetime import datetime

from collect_player_sample import (
    MAX_COLLECTION_USERS,
    select_collection_candidates,
    select_stratified_sample,
)
from src.crawler.ongeki_crawler import OngekiCrawler
from src.database.calibration_store import CalibrationStore, make_subject_key


def test_public_user_parser_extracts_only_valid_rows():
    html = """
    <table>
      <tr><th>ID</th><th>Rating</th><th>Update</th></tr>
      <tr><td><a href="/user/101">A</a></td><td class="sort_rating">18.250</td><td class="sort_update">2026-09-10</td></tr>
      <tr><td><a href="/user/102">B</a></td><td class="sort_rating">19.500</td><td class="sort_update">invalid</td></tr>
      <tr><td><a href="/music/101/master">曲</a></td><td class="sort_rating">20.000</td><td class="sort_update">2026-09-10</td></tr>
    </table>
    """

    assert OngekiCrawler.parse_public_users(html) == [{
        "user_id": 101,
        "rating": 18.25,
        "updated_at": datetime(2026, 9, 10),
    }]


def test_snapshot_parser_uses_one_html_for_profile_and_scores(mock_10605_html):
    snapshot = OngekiCrawler.parse_user_snapshot(mock_10605_html, 10605)

    assert snapshot is not None
    assert snapshot["profile"]["rating"] == 19.95
    assert snapshot["profile"]["updated_at"] == datetime(2026, 9, 10)
    assert len(snapshot["scores"]) >= 8
    assert snapshot["scores"][0]["chart_id"] == "1001_master"


def test_snapshot_parser_rejects_missing_update_date():
    html = """
    <table class="is-striped">
      <tr><th>プレイヤーネーム</th><td>匿名</td></tr>
      <tr><th>レーティング</th><td>19.000</td></tr>
    </table>
    <table><tr><td class="sort_title"><a href="/music/1/master">曲</a></td><td class="sort_ts">1,000,000</td></tr></table>
    """

    try:
        OngekiCrawler.parse_user_snapshot(html, 1)
    except ValueError as exc:
        assert "最終更新日" in str(exc)
    else:
        raise AssertionError("更新日不明のページは保存対象にしてはいけません")


def test_stratified_sample_covers_rating_bands():
    candidates = [
        {"user_id": 1, "rating": 18.1, "updated_at": datetime(2026, 9, 1)},
        {"user_id": 2, "rating": 18.2, "updated_at": datetime(2026, 9, 2)},
        {"user_id": 3, "rating": 19.1, "updated_at": datetime(2026, 9, 3)},
        {"user_id": 4, "rating": 20.1, "updated_at": datetime(2026, 9, 4)},
    ]

    selected = select_stratified_sample(candidates, 3)

    assert {int(item["rating"] * 2) for item in selected} == {36, 38, 40}


def test_collection_candidates_respect_total_population_limit():
    candidates = [
        {"user_id": user_id, "rating": 18.0 + user_id / 10, "updated_at": datetime(2026, 9, user_id)}
        for user_id in range(1, 5)
    ]
    existing_keys = {make_subject_key(1), make_subject_key(2)}

    selected = select_collection_candidates(candidates, existing_keys, max_users=3)

    selected_existing = [item for item in selected if make_subject_key(item["user_id"]) in existing_keys]
    selected_new = [item for item in selected if make_subject_key(item["user_id"]) not in existing_keys]
    assert len(selected_existing) == 2
    assert len(selected_new) == 1


def test_collection_hard_limit_matches_validated_next_phase():
    assert MAX_COLLECTION_USERS == 100


def test_calibration_store_is_private_atomic_and_idempotent(tmp_path):
    db_path = tmp_path / "calibration.sqlite"
    subject_key = make_subject_key(10605)
    profile = {"rating": 19.95, "updated_at": datetime(2026, 9, 10)}
    score = {
        "chart_id": "1001_master",
        "music_id": "1001",
        "title": "テスト曲",
        "difficulty": "MASTER",
        "level": "15+",
        "score": 1_008_000,
        "is_all_break": True,
        "is_full_bell": True,
    }

    with CalibrationStore(str(db_path)) as store:
        store.upsert_snapshot(subject_key, profile, [score])
        store.upsert_snapshot(subject_key, profile, [score])
        assert store.counts() == {"players": 1, "scores": 1, "charts": 1}

        older_lower = dict(
            score,
            chart_id="1002_master",
            music_id="1002",
            score=900_000,
        )
        store.upsert_snapshot(
            subject_key,
            {"rating": 19.0, "updated_at": datetime(2026, 9, 9)},
            [older_lower],
        )

    connection = sqlite3.connect(db_path)
    try:
        stored = connection.execute("SELECT rating FROM players").fetchone()
        stored_score = connection.execute("SELECT score FROM scores").fetchone()
        score_count = connection.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
        serialized = " ".join(
            str(value)
            for table in ("players", "scores")
            for row in connection.execute(f"SELECT * FROM {table}")
            for value in row
        )
    finally:
        connection.close()

    assert stored[0] == 19.95
    assert stored_score[0] == 1_008_000
    assert score_count == 1
    assert "10605" not in serialized
    assert "匿名" not in serialized
