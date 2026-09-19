import sqlite3
from datetime import datetime

from src.analyzer.player_recalibration import (
    AAA_ABILITY_MODEL_VERSION,
    build_aaa_calibrated_ability_report,
)
from src.database.calibration_store import CalibrationStore, make_subject_key
from src.visualizer.visualizer import OPIVisualizer


def _create_master(path):
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE charts(
                chart_id TEXT PRIMARY KEY, title TEXT NOT NULL, difficulty TEXT NOT NULL,
                level TEXT NOT NULL, chart_constant REAL NOT NULL, is_active INTEGER,
                opi_s_x REAL, opi_s_y REAL, opi_ss_x REAL, opi_ss_y REAL,
                opi_sss_x REAL, opi_sss_y REAL, opi_sssp_x REAL, opi_sssp_y REAL,
                opi_abp_x REAL, opi_abp_y REAL
            )
            """
        )
        for index in range(1, 7):
            base = 1400.0 + index * 20.0
            connection.execute(
                "INSERT INTO charts VALUES(?, ?, 'MASTER', '14+', ?, 1, ?, 40, ?, 40, ?, 40, ?, 40, ?, 40)",
                (
                    f"{index}_master",
                    f"曲{index}",
                    14.0 + index / 10,
                    base,
                    base + 100,
                    base + 200,
                    base + 300,
                    base + 500,
                ),
            )


def _add_player(store, user_id, rating, scores):
    store.upsert_snapshot(
        make_subject_key(user_id),
        {"rating": rating, "updated_at": datetime(2026, 9, 15)},
        [
            {
                "chart_id": f"{index}_master",
                "music_id": str(index),
                "title": f"曲{index}",
                "difficulty": "MASTER",
                "level": "14+",
                "score": score,
                "is_all_break": score == 1_010_000,
                "is_full_bell": score >= 1_007_500,
            }
            for index, score in enumerate(scores, start=1)
        ],
    )


def test_latest_parameters_and_aaa_scores_drive_distribution_table(tmp_path):
    master_db = tmp_path / "master.sqlite"
    calibration_db = tmp_path / "calibration.sqlite"
    _create_master(master_db)
    with CalibrationStore(str(calibration_db)) as store:
        _add_player(
            store,
            1,
            18.0,
            [970_000, 975_000, 990_000, 1_000_000, 1_007_500, 1_010_000],
        )
        _add_player(
            store,
            2,
            18.1,
            [969_999, 980_000, 995_000, 1_001_000, 1_008_000, 1_009_000],
        )

    first = build_aaa_calibrated_ability_report(
        calibration_db,
        master_db,
        min_eligible_charts=4,
        min_class_count=1,
    )
    second = build_aaa_calibrated_ability_report(
        calibration_db,
        master_db,
        min_eligible_charts=4,
        min_class_count=1,
    )

    assert first["model_version"] == AAA_ABILITY_MODEL_VERSION
    assert first["eligible_score_count"] == 11
    assert first["estimated_player_count"] == 2
    assert first["minimum_score"] == 970_000
    assert second["run_id"] == first["run_id"]
    assert second["reused_completed_run"] is True

    with sqlite3.connect(calibration_db) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM players WHERE estimated_opi IS NOT NULL"
        ).fetchone()[0] == 2

    table = OPIVisualizer.get_target_distribution_table(str(calibration_db))
    assert table.loc[0, "対象レート"] == "18.0"
    assert table.loc[0, "サンプル人数"] == "2人"
    assert table.loc[0, "目標総合OPI（中央値）"] > 0
