import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional


SCHEMA_VERSION = 1


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
