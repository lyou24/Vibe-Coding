import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional


SCHEMA_VERSION = 2


def make_subject_key(user_id: int) -> str:
    """公開IDをDBへ保存しないための安定した仮名キーを生成する。"""
    value = f"ongeki-score.net:user:{user_id}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


class CalibrationStore:
    """実プレイヤー校正用DB。既存のデモ・本番DBとは分離して管理する。"""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS crawl_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                requested_users INTEGER NOT NULL,
                collected_users INTEGER NOT NULL DEFAULT 0,
                skipped_users INTEGER NOT NULL DEFAULT 0,
                error_users INTEGER NOT NULL DEFAULT 0,
                request_count INTEGER NOT NULL DEFAULT 0,
                min_rating REAL NOT NULL,
                min_update_date TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS players (
                subject_key TEXT PRIMARY KEY,
                rating REAL,
                estimated_opi REAL,
                source_updated_at TEXT NOT NULL,
                collected_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scores (
                subject_key TEXT NOT NULL,
                chart_id TEXT NOT NULL,
                music_id TEXT NOT NULL,
                title TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                level TEXT NOT NULL,
                score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 1010000),
                is_all_break INTEGER NOT NULL CHECK(is_all_break IN (0, 1)),
                is_full_bell INTEGER NOT NULL CHECK(is_full_bell IN (0, 1)),
                achieve_ss INTEGER NOT NULL CHECK(achieve_ss IN (0, 1)),
                achieve_sss INTEGER NOT NULL CHECK(achieve_sss IN (0, 1)),
                achieve_sssp INTEGER NOT NULL CHECK(achieve_sssp IN (0, 1)),
                achieve_abfb INTEGER NOT NULL CHECK(achieve_abfb IN (0, 1)),
                achieve_ap INTEGER NOT NULL CHECK(achieve_ap IN (0, 1)),
                source_updated_at TEXT NOT NULL,
                PRIMARY KEY(subject_key, chart_id),
                FOREIGN KEY(subject_key) REFERENCES players(subject_key) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS ix_scores_chart_id ON scores(chart_id);

            CREATE TABLE IF NOT EXISTS chart_master_versions (
                version_id TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL UNIQUE,
                source_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                chart_count INTEGER NOT NULL CHECK(chart_count >= 0)
            );

            CREATE TABLE IF NOT EXISTS chart_master_items (
                version_id TEXT NOT NULL,
                chart_id TEXT NOT NULL,
                title TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                level TEXT NOT NULL,
                chart_constant REAL NOT NULL,
                is_active INTEGER NOT NULL CHECK(is_active IN (0, 1)),
                PRIMARY KEY(version_id, chart_id),
                FOREIGN KEY(version_id) REFERENCES chart_master_versions(version_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS estimation_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_key TEXT NOT NULL UNIQUE,
                model_version TEXT NOT NULL,
                master_version_id TEXT NOT NULL,
                data_hash TEXT NOT NULL,
                config_json TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                player_count INTEGER NOT NULL DEFAULT 0,
                estimated_player_count INTEGER NOT NULL DEFAULT 0,
                unestimated_player_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(master_version_id) REFERENCES chart_master_versions(version_id)
            );

            CREATE TABLE IF NOT EXISTS player_ability_estimates (
                run_id INTEGER NOT NULL,
                subject_key TEXT NOT NULL,
                theta REAL,
                item_count INTEGER NOT NULL,
                achieved_count INTEGER NOT NULL,
                unachieved_count INTEGER NOT NULL,
                coverage REAL NOT NULL,
                negative_log_likelihood REAL,
                negative_log_posterior REAL,
                is_estimable INTEGER NOT NULL CHECK(is_estimable IN (0, 1)),
                reason TEXT,
                boundary_reached INTEGER NOT NULL CHECK(boundary_reached IN (0, 1)),
                PRIMARY KEY(run_id, subject_key),
                FOREIGN KEY(run_id) REFERENCES estimation_runs(run_id) ON DELETE CASCADE,
                FOREIGN KEY(subject_key) REFERENCES players(subject_key) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS item_parameter_estimates (
                run_id INTEGER NOT NULL,
                chart_id TEXT NOT NULL,
                target_rank TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                achieved_count INTEGER NOT NULL,
                unachieved_count INTEGER NOT NULL,
                is_estimable INTEGER NOT NULL CHECK(is_estimable IN (0, 1)),
                reason TEXT,
                x REAL,
                y REAL,
                negative_log_likelihood REAL,
                boundary_reached INTEGER NOT NULL CHECK(boundary_reached IN (0, 1)),
                PRIMARY KEY(run_id, chart_id, target_rank),
                FOREIGN KEY(run_id) REFERENCES estimation_runs(run_id) ON DELETE CASCADE
            );
            """
        )
        self.connection.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def start_run(self, requested_users: int, min_rating: float, min_update_date: datetime) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO crawl_runs(
                started_at, status, requested_users, min_rating, min_update_date
            ) VALUES(?, 'running', ?, ?, ?)
            """,
            (datetime.now().isoformat(timespec="seconds"), requested_users, min_rating, min_update_date.date().isoformat()),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        collected_users: int,
        skipped_users: int,
        error_users: int,
        request_count: int,
    ) -> None:
        self.connection.execute(
            """
            UPDATE crawl_runs
               SET completed_at = ?, status = ?, collected_users = ?, skipped_users = ?,
                   error_users = ?, request_count = ?
             WHERE run_id = ?
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                status,
                collected_users,
                skipped_users,
                error_users,
                request_count,
                run_id,
            ),
        )
        self.connection.commit()

    def source_updated_at(self, subject_key: str) -> Optional[datetime]:
        row = self.connection.execute(
            "SELECT source_updated_at FROM players WHERE subject_key = ?",
            (subject_key,),
        ).fetchone()
        return datetime.fromisoformat(row["source_updated_at"]) if row else None

    def subject_keys(self) -> set[str]:
        return {
            row["subject_key"]
            for row in self.connection.execute("SELECT subject_key FROM players")
        }

    def upsert_snapshot(self, subject_key: str, profile: dict, scores: list[dict]) -> None:
        """1ユーザー分を原子的に保存する。欠落行を理由に既存データは削除しない。"""
        if not scores:
            raise ValueError("空のスコアは保存できません")

        source_updated_at = profile["updated_at"].date().isoformat()
        collected_at = datetime.now().isoformat(timespec="seconds")
        with self.transaction() as connection:
            existing_player = connection.execute(
                "SELECT source_updated_at FROM players WHERE subject_key = ?",
                (subject_key,),
            ).fetchone()
            if existing_player and source_updated_at < existing_player["source_updated_at"]:
                return

            connection.execute(
                """
                INSERT INTO players(subject_key, rating, source_updated_at, collected_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(subject_key) DO UPDATE SET
                    rating = excluded.rating,
                    source_updated_at = excluded.source_updated_at,
                    collected_at = excluded.collected_at
                WHERE excluded.source_updated_at >= players.source_updated_at
                """,
                (subject_key, profile.get("rating"), source_updated_at, collected_at),
            )

            for score in scores:
                score_value = int(score["score"])
                is_ab = bool(score.get("is_all_break", False))
                is_fb = bool(score.get("is_full_bell", False))
                connection.execute(
                    """
                    INSERT INTO scores(
                        subject_key, chart_id, music_id, title, difficulty, level, score,
                        is_all_break, is_full_bell, achieve_ss, achieve_sss, achieve_sssp,
                        achieve_abfb, achieve_ap, source_updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(subject_key, chart_id) DO UPDATE SET
                        title = excluded.title,
                        level = excluded.level,
                        score = excluded.score,
                        is_all_break = excluded.is_all_break,
                        is_full_bell = excluded.is_full_bell,
                        achieve_ss = excluded.achieve_ss,
                        achieve_sss = excluded.achieve_sss,
                        achieve_sssp = excluded.achieve_sssp,
                        achieve_abfb = excluded.achieve_abfb,
                        achieve_ap = excluded.achieve_ap,
                        source_updated_at = excluded.source_updated_at
                    WHERE excluded.source_updated_at >= scores.source_updated_at
                      AND excluded.score >= scores.score
                    """,
                    (
                        subject_key,
                        score["chart_id"],
                        score["music_id"],
                        score["title"],
                        score["difficulty"],
                        score.get("level", ""),
                        score_value,
                        is_ab,
                        is_fb,
                        score_value >= 990_000,
                        score_value >= 1_000_000,
                        score_value >= 1_007_500,
                        score_value >= 1_007_500 and is_ab and is_fb,
                        score_value == 1_010_000,
                        source_updated_at,
                    ),
                )

    def counts(self) -> dict[str, int]:
        players = self.connection.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        scores = self.connection.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
        charts = self.connection.execute("SELECT COUNT(DISTINCT chart_id) FROM scores").fetchone()[0]
        return {"players": players, "scores": scores, "charts": charts}

    def save_chart_master_snapshot(
        self,
        *,
        version_id: str,
        content_hash: str,
        source_name: str,
        charts: list[dict],
    ) -> None:
        """譜面マスタを内容ハッシュ単位で冪等保存する。"""
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT content_hash, chart_count FROM chart_master_versions WHERE version_id = ?",
                (version_id,),
            ).fetchone()
            if existing:
                if existing["content_hash"] != content_hash or existing["chart_count"] != len(charts):
                    raise ValueError("同じversion_idに異なる譜面マスタが存在します")
                return

            connection.execute(
                """
                INSERT INTO chart_master_versions(
                    version_id, content_hash, source_name, created_at, chart_count
                ) VALUES(?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    content_hash,
                    source_name,
                    datetime.now().isoformat(timespec="seconds"),
                    len(charts),
                ),
            )
            connection.executemany(
                """
                INSERT INTO chart_master_items(
                    version_id, chart_id, title, difficulty, level, chart_constant, is_active
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        version_id,
                        chart["chart_id"],
                        chart["title"],
                        chart["difficulty"],
                        chart["level"],
                        float(chart["chart_constant"]),
                        bool(chart["is_active"]),
                    )
                    for chart in charts
                ],
            )

    def start_or_resume_estimation_run(
        self,
        *,
        run_key: str,
        model_version: str,
        master_version_id: str,
        data_hash: str,
        config_json: str,
        player_count: int,
    ) -> tuple[int, bool]:
        """同一入力の完了runは再利用し、未完了runだけ安全に再実行する。"""
        existing = self.connection.execute(
            "SELECT run_id, status FROM estimation_runs WHERE run_key = ?",
            (run_key,),
        ).fetchone()
        if existing and existing["status"] == "completed":
            return int(existing["run_id"]), False

        with self.transaction() as connection:
            if existing:
                run_id = int(existing["run_id"])
                connection.execute(
                    "DELETE FROM player_ability_estimates WHERE run_id = ?",
                    (run_id,),
                )
                connection.execute(
                    """
                    UPDATE estimation_runs
                       SET status = 'running', started_at = ?, completed_at = NULL,
                           player_count = ?, estimated_player_count = 0,
                           unestimated_player_count = 0
                     WHERE run_id = ?
                    """,
                    (datetime.now().isoformat(timespec="seconds"), player_count, run_id),
                )
                return run_id, True

            cursor = connection.execute(
                """
                INSERT INTO estimation_runs(
                    run_key, model_version, master_version_id, data_hash, config_json,
                    started_at, status, player_count
                ) VALUES(?, ?, ?, ?, ?, ?, 'running', ?)
                """,
                (
                    run_key,
                    model_version,
                    master_version_id,
                    data_hash,
                    config_json,
                    datetime.now().isoformat(timespec="seconds"),
                    player_count,
                ),
            )
            return int(cursor.lastrowid), True

    def save_player_ability_estimate(
        self,
        *,
        run_id: int,
        subject_key: str,
        estimate,
        coverage: float,
    ) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO player_ability_estimates(
                run_id, subject_key, theta, item_count, achieved_count, unachieved_count,
                coverage, negative_log_likelihood, negative_log_posterior,
                is_estimable, reason, boundary_reached
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                subject_key,
                estimate.theta,
                estimate.item_count,
                estimate.achieved_count,
                estimate.unachieved_count,
                float(coverage),
                estimate.negative_log_likelihood,
                estimate.negative_log_posterior,
                estimate.is_estimable,
                estimate.reason,
                estimate.boundary_reached,
            ),
        )

    def finish_estimation_run(
        self,
        run_id: int,
        *,
        status: str,
        estimated_player_count: int,
        unestimated_player_count: int,
    ) -> None:
        self.connection.execute(
            """
            UPDATE estimation_runs
               SET status = ?, completed_at = ?, estimated_player_count = ?,
                   unestimated_player_count = ?
             WHERE run_id = ?
            """,
            (
                status,
                datetime.now().isoformat(timespec="seconds"),
                estimated_player_count,
                unestimated_player_count,
                run_id,
            ),
        )
        self.connection.commit()

    def ability_run_report(self, run_id: int) -> dict:
        run = self.connection.execute(
            "SELECT * FROM estimation_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if not run:
            raise ValueError("指定した推定runが存在しません")

        estimates = self.connection.execute(
            "SELECT * FROM player_ability_estimates WHERE run_id = ? ORDER BY subject_key",
            (run_id,),
        ).fetchall()
        theta_values = sorted(
            float(row["theta"])
            for row in estimates
            if row["is_estimable"] and row["theta"] is not None
        )
        reason_counts = {}
        for row in estimates:
            if row["reason"]:
                reason_counts[row["reason"]] = reason_counts.get(row["reason"], 0) + 1

        median_theta = None
        if theta_values:
            middle = len(theta_values) // 2
            median_theta = (
                theta_values[middle]
                if len(theta_values) % 2
                else (theta_values[middle - 1] + theta_values[middle]) / 2.0
            )
        return {
            "run_id": int(run["run_id"]),
            "status": run["status"],
            "model_version": run["model_version"],
            "master_version_id": run["master_version_id"],
            "data_hash": run["data_hash"],
            "player_count": int(run["player_count"]),
            "estimated_player_count": int(run["estimated_player_count"]),
            "unestimated_player_count": int(run["unestimated_player_count"]),
            "unestimated_reasons": reason_counts,
            "theta_min": theta_values[0] if theta_values else None,
            "theta_median": median_theta,
            "theta_max": theta_values[-1] if theta_values else None,
        }
