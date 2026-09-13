import sqlite3
from datetime import datetime

from calibrate_player_abilities import build_ability_report, file_sha256
from src.database.calibration_store import CalibrationStore, SCHEMA_VERSION, make_subject_key
from validate_calibration_db import build_validation_report


def create_master_db(path, chart_count: int = 6):
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE charts(
                chart_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                level TEXT NOT NULL,
                chart_constant REAL NOT NULL,
                is_active INTEGER
            )
            """
        )
        connection.executemany(
            "INSERT INTO charts VALUES(?, ?, 'MASTER', '14', ?, 1)",
            [
                (f"{index}_master", f"曲{index}", 14.0 + index / 10)
                for index in range(1, chart_count + 1)
            ],
        )
        connection.commit()
    finally:
        connection.close()


def add_player(store: CalibrationStore, user_id: int, scores: list[int]):
    store.upsert_snapshot(
        make_subject_key(user_id),
        {"rating": 18.0 + user_id / 100, "updated_at": datetime(2026, 9, 14)},
        [
            {
                "chart_id": f"{index}_master",
                "music_id": str(index),
                "title": f"曲{index}",
                "difficulty": "MASTER",
                "level": "14",
                "score": score,
                "is_all_break": False,
                "is_full_bell": False,
            }
            for index, score in enumerate(scores, start=1)
        ],
    )


def test_schema_v2_is_additive_and_preserves_existing_rows(tmp_path):
    db_path = tmp_path / "calibration.sqlite"
    with CalibrationStore(str(db_path)) as store:
        add_player(store, 1, [1_000_000, 999_000])

    with CalibrationStore(str(db_path)) as store:
        assert SCHEMA_VERSION == 2
        assert store.counts()["players"] == 1
        schema_version = store.connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        assert schema_version == "2"
        assert store.connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='estimation_runs'"
        ).fetchone()[0] == 1


def test_ability_pipeline_is_reproducible_and_main_db_read_only(tmp_path):
    main_db = tmp_path / "main.sqlite"
    calibration_db = tmp_path / "calibration.sqlite"
    create_master_db(main_db)
    with CalibrationStore(str(calibration_db)) as store:
        add_player(store, 1, [1_001_000, 1_000_000, 999_000, 998_000, 1_002_000, 997_000])
        add_player(store, 2, [997_000, 998_000, 1_000_000, 1_001_000, 999_000, 1_002_000])

    hash_before = file_sha256(main_db)
    first = build_ability_report(
        calibration_db,
        main_db,
        min_items=4,
        min_class_count=1,
    )
    second = build_ability_report(
        calibration_db,
        main_db,
        min_items=4,
        min_class_count=1,
    )

    assert first["status"] == "completed"
    assert first["estimated_player_count"] == 2
    assert first["unestimated_player_count"] == 0
    assert first["main_database_written"] is False
    assert first["main_database_hash_unchanged"] is True
    assert second["run_id"] == first["run_id"]
    assert second["reused_completed_run"] is True
    assert file_sha256(main_db) == hash_before

    connection = sqlite3.connect(calibration_db)
    try:
        assert connection.execute("SELECT COUNT(*) FROM chart_master_versions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM estimation_runs").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM player_ability_estimates").fetchone()[0] == 2
    finally:
        connection.close()

    validation = build_validation_report(str(calibration_db))
    assert validation["schema_version"] == "2"
    assert validation["chart_master_versions"] == 1
    assert validation["player_ability_estimates"] == 2
    assert validation["estimable_player_abilities"] == 2


def test_ability_pipeline_records_unestimable_players(tmp_path):
    main_db = tmp_path / "main.sqlite"
    calibration_db = tmp_path / "calibration.sqlite"
    create_master_db(main_db)
    with CalibrationStore(str(calibration_db)) as store:
        add_player(store, 1, [1_000_000] * 6)

    report = build_ability_report(
        calibration_db,
        main_db,
        min_items=4,
        min_class_count=1,
    )

    assert report["estimated_player_count"] == 0
    assert report["unestimated_player_count"] == 1
    assert report["unestimated_reasons"] == {"single_class": 1}
