import csv
import sqlite3

from export_difficulty_tables import export_csv, load_difficulty_rows


def _create_master(path):
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE charts(
                chart_id TEXT PRIMARY KEY, title TEXT NOT NULL, version TEXT, genre TEXT,
                difficulty TEXT, level TEXT, chart_constant REAL, is_active INTEGER,
                opi_s_x REAL, opi_s_y REAL, opi_ss_x REAL, opi_ss_y REAL,
                opi_sss_x REAL, opi_sss_y REAL, opi_sssp_x REAL, opi_sssp_y REAL,
                opi_abp_x REAL, opi_abp_y REAL
            )
            """
        )
        values = (
            1400.0, 45.0, 1500.0, 46.0, 1600.0, 47.0,
            1700.0, 48.0, 1800.0, 49.0,
        )
        connection.execute(
            "INSERT INTO charts VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("normal", "通常楽曲", "bright", "VARIETY", "MASTER", "14+", 14.8, 1, *values),
        )
        connection.execute(
            "INSERT INTO charts VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("solo", "通常楽曲 ソロver.", "bright", "VARIETY", "MASTER", "14+", 14.8, 1, *values),
        )


def test_offline_table_uses_db_values_and_excludes_solo(tmp_path):
    database = tmp_path / "master.sqlite"
    _create_master(database)

    rows = load_difficulty_rows(database)

    assert [row["chart_id"] for row in rows] == ["normal"]
    assert rows[0]["opi_sss_x"] == 1600.0


def test_csv_contains_all_rank_parameters(tmp_path):
    database = tmp_path / "master.sqlite"
    output = tmp_path / "difficulty.csv"
    _create_master(database)

    export_csv(load_difficulty_rows(database), output)

    with output.open(encoding="utf-8-sig", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["SSS適正OPI"] == "1600.0"
    assert row["AB+個人差度"] == "49.0"


def test_offline_table_applies_fixed_abp_opi(tmp_path):
    database = tmp_path / "master.sqlite"
    _create_master(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE charts SET chart_id = '808_master', opi_abp_x = 2080.0 WHERE chart_id = 'normal'"
        )

    rows = load_difficulty_rows(database)

    assert rows[0]["opi_abp_x"] == 2500.0
