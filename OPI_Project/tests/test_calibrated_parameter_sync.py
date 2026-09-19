import sqlite3

from src.database.calibrated_parameters import sync_latest_calibrated_parameters


def _create_calibration_db(path):
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE estimation_runs(
                run_id INTEGER PRIMARY KEY,
                model_version TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE item_parameter_estimates(
                run_id INTEGER NOT NULL,
                chart_id TEXT NOT NULL,
                target_rank TEXT NOT NULL,
                is_estimable INTEGER NOT NULL,
                x REAL,
                y REAL
            )
            """
        )
        connection.executemany(
            "INSERT INTO estimation_runs VALUES(?, ?, ?)",
            [
                (1, "2pl-item-old", "completed"),
                (2, "2pl-item-current", "completed"),
            ],
        )
        connection.executemany(
            "INSERT INTO item_parameter_estimates VALUES(?, ?, ?, ?, ?, ?)",
            [
                (1, "chart_1", "SSS", 1, 1500.0, 60.0),
                (2, "chart_1", "S", 1, 1410.0, 55.0),
                (2, "chart_1", "SSS", 1, 1712.5, 72.0),
                (2, "chart_1", "AB+", 0, None, None),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def _create_master_db(path):
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE charts(
                chart_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                opi_s_x REAL, opi_s_y REAL,
                opi_ss_x REAL, opi_ss_y REAL,
                opi_sss_x REAL, opi_sss_y REAL,
                opi_sssp_x REAL, opi_sssp_y REAL,
                opi_abp_x REAL, opi_abp_y REAL
            )
            """
        )
        connection.execute(
            "INSERT INTO charts VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("chart_1", "通常楽曲", 1300.0, 40.0, 1420.0, 40.0, 1540.0, 40.0, 1660.0, 40.0, 1780.0, 40.0),
        )
        connection.commit()
    finally:
        connection.close()


def test_latest_calibrated_parameters_are_applied_atomically(tmp_path):
    calibration_db = tmp_path / "calibration.sqlite"
    master_db = tmp_path / "master.sqlite"
    _create_calibration_db(calibration_db)
    _create_master_db(master_db)

    report = sync_latest_calibrated_parameters(calibration_db, master_db)

    assert report == {
        "status": "applied",
        "run_id": 2,
        "model_version": "2pl-item-current",
        "estimate_count": 2,
        "updated_count": 2,
    }
    connection = sqlite3.connect(master_db)
    try:
        values = connection.execute(
            "SELECT opi_s_x, opi_s_y, opi_sss_x, opi_sss_y, opi_abp_x FROM charts"
        ).fetchone()
        assert values == (1410.0, 55.0, 1712.5, 72.0, 1780.0)
    finally:
        connection.close()


def test_same_calibration_run_is_not_written_twice(tmp_path):
    calibration_db = tmp_path / "calibration.sqlite"
    master_db = tmp_path / "master.sqlite"
    _create_calibration_db(calibration_db)
    _create_master_db(master_db)

    sync_latest_calibrated_parameters(calibration_db, master_db)
    second = sync_latest_calibrated_parameters(calibration_db, master_db)

    assert second["status"] == "current"
    assert second["run_id"] == 2
    assert second["estimate_count"] == 2
    assert second["updated_count"] == 0


def test_same_run_is_reapplied_when_master_values_have_drifted(tmp_path):
    calibration_db = tmp_path / "calibration.sqlite"
    master_db = tmp_path / "master.sqlite"
    _create_calibration_db(calibration_db)
    _create_master_db(master_db)
    sync_latest_calibrated_parameters(calibration_db, master_db)

    with sqlite3.connect(master_db) as connection:
        connection.execute("UPDATE charts SET opi_sss_x = 1500.0 WHERE chart_id = 'chart_1'")

    report = sync_latest_calibrated_parameters(calibration_db, master_db)

    assert report["status"] == "applied"
    assert report["updated_count"] == 1
    with sqlite3.connect(master_db) as connection:
        assert connection.execute("SELECT opi_sss_x FROM charts").fetchone()[0] == 1712.5


def test_fixed_abp_override_is_applied_and_drift_is_repaired(tmp_path):
    calibration_db = tmp_path / "calibration.sqlite"
    master_db = tmp_path / "master.sqlite"
    _create_calibration_db(calibration_db)
    _create_master_db(master_db)
    with sqlite3.connect(master_db) as connection:
        connection.execute(
            "UPDATE charts SET chart_id = '808_master', opi_abp_x = 2080.0 WHERE chart_id = 'chart_1'"
        )

    first = sync_latest_calibrated_parameters(calibration_db, master_db)
    assert first["status"] == "applied"
    assert first["updated_count"] == 1
    with sqlite3.connect(master_db) as connection:
        assert connection.execute("SELECT opi_abp_x FROM charts").fetchone()[0] == 2500.0
        connection.execute("UPDATE charts SET opi_abp_x = 2100.0")

    repaired = sync_latest_calibrated_parameters(calibration_db, master_db)
    assert repaired["status"] == "applied"
    assert repaired["updated_count"] == 1
    with sqlite3.connect(master_db) as connection:
        assert connection.execute("SELECT opi_abp_x FROM charts").fetchone()[0] == 2500.0


def test_solo_version_is_not_applied(tmp_path):
    calibration_db = tmp_path / "calibration.sqlite"
    master_db = tmp_path / "master.sqlite"
    _create_calibration_db(calibration_db)
    _create_master_db(master_db)
    with sqlite3.connect(master_db) as connection:
        connection.execute("UPDATE charts SET title = '通常楽曲 ソロver.'")

    report = sync_latest_calibrated_parameters(calibration_db, master_db)

    assert report["estimate_count"] == 0
    with sqlite3.connect(master_db) as connection:
        assert connection.execute("SELECT opi_sss_x FROM charts").fetchone()[0] == 1540.0


def test_missing_calibration_db_keeps_master_unchanged(tmp_path):
    master_db = tmp_path / "master.sqlite"
    _create_master_db(master_db)

    report = sync_latest_calibrated_parameters(tmp_path / "missing.sqlite", master_db)

    assert report["status"] == "calibration_db_missing"
    connection = sqlite3.connect(master_db)
    try:
        assert connection.execute("SELECT opi_sss_x FROM charts").fetchone()[0] == 1540.0
    finally:
        connection.close()
