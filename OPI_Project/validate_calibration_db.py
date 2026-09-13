import argparse
import json
import os
import sqlite3


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_FILE = os.path.join(PROJECT_ROOT, "data", "opi_calibration.sqlite")


def build_validation_report(db_path: str) -> dict:
    connection = sqlite3.connect(db_path)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        private_columns = {"user_id", "player_name"}
        raw_identity_columns = []
        for table in ("players", "scores"):
            for row in connection.execute(f"PRAGMA table_info({table})"):
                if row[1] in private_columns:
                    raw_identity_columns.append(f"{table}.{row[1]}")

        return {
            "integrity": integrity,
            "foreign_key_errors": len(foreign_key_errors),
            "schema_version": connection.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()[0],
            "players": connection.execute("SELECT COUNT(*) FROM players").fetchone()[0],
            "scores": connection.execute("SELECT COUNT(*) FROM scores").fetchone()[0],
            "charts": connection.execute("SELECT COUNT(DISTINCT chart_id) FROM scores").fetchone()[0],
            "duplicate_scores": connection.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT subject_key, chart_id, COUNT(*) AS count
                      FROM scores
                     GROUP BY subject_key, chart_id
                    HAVING count > 1
                )
                """
            ).fetchone()[0],
            "invalid_scores": connection.execute(
                "SELECT COUNT(*) FROM scores WHERE score < 0 OR score > 1010000"
            ).fetchone()[0],
            "raw_identity_columns": raw_identity_columns,
            "rating_min": connection.execute("SELECT MIN(rating) FROM players").fetchone()[0],
            "rating_max": connection.execute("SELECT MAX(rating) FROM players").fetchone()[0],
            "crawl_runs": connection.execute("SELECT COUNT(*) FROM crawl_runs").fetchone()[0],
            "chart_master_versions": connection.execute(
                "SELECT COUNT(*) FROM chart_master_versions"
            ).fetchone()[0],
            "chart_master_items": connection.execute(
                "SELECT COUNT(*) FROM chart_master_items"
            ).fetchone()[0],
            "estimation_runs": connection.execute(
                "SELECT COUNT(*) FROM estimation_runs"
            ).fetchone()[0],
            "player_ability_estimates": connection.execute(
                "SELECT COUNT(*) FROM player_ability_estimates"
            ).fetchone()[0],
            "estimable_player_abilities": connection.execute(
                "SELECT COUNT(*) FROM player_ability_estimates WHERE is_estimable = 1"
            ).fetchone()[0],
            "item_parameter_estimates": connection.execute(
                "SELECT COUNT(*) FROM item_parameter_estimates"
            ).fetchone()[0],
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="実プレイヤー校正DBの整合性を検証する")
    parser.add_argument("--db", default=DEFAULT_DB_FILE, help="検証対象SQLite DB")
    args = parser.parse_args()
    print(json.dumps(build_validation_report(args.db), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
