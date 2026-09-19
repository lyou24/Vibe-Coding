"""校正DBの最新項目パラメータをWebアプリ用DBへ同期する。"""

from __future__ import annotations

import math
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from src.analyzer.opi_overrides import ABP_FIXED_CHART_IDS, ABP_FIXED_OPI


RANK_TO_COLUMN_PREFIX = {
    "S": "opi_s",
    "SS": "opi_ss",
    "SSS": "opi_sss",
    "SSS+": "opi_sssp",
    "AB+": "opi_abp",
}


def _is_solo_version(title: str | None) -> bool:
    normalized = unicodedata.normalize("NFKC", title or "").casefold()
    return "ソロver" in normalized


def _read_only_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"file:{path.resolve().as_posix()}?mode=ro",
        uri=True,
        timeout=30.0,
    )
    connection.row_factory = sqlite3.Row
    return connection


def sync_latest_calibrated_parameters(
    calibration_db_path: str | Path,
    master_db_path: str | Path,
) -> dict[str, Any]:
    """最新の完了済み2PL推定結果を本番譜面マスタへ原子的に反映する。

    同じ推定runを反映済みなら書き込みを省略する。推定不能だったランクは
    本番DBの既存値を維持する。ただし明示定義されたAB+譜面は固定値を優先する。
    """

    calibration_path = Path(calibration_db_path)
    master_path = Path(master_db_path)
    if not calibration_path.is_file():
        return {
            "status": "calibration_db_missing",
            "run_id": None,
            "model_version": None,
            "estimate_count": 0,
            "updated_count": 0,
        }
    if not master_path.is_file():
        return {
            "status": "master_db_missing",
            "run_id": None,
            "model_version": None,
            "estimate_count": 0,
            "updated_count": 0,
        }

    calibration = _read_only_connection(calibration_path)
    try:
        run = calibration.execute(
            """
            SELECT run_id, model_version
              FROM estimation_runs
             WHERE status = 'completed'
               AND model_version LIKE '2pl-item-%'
             ORDER BY run_id DESC
             LIMIT 1
            """
        ).fetchone()
        if run is None:
            return {
                "status": "completed_run_missing",
                "run_id": None,
                "model_version": None,
                "estimate_count": 0,
                "updated_count": 0,
            }

        run_id = int(run["run_id"])
        model_version = str(run["model_version"])
        raw_estimates = calibration.execute(
            """
            SELECT chart_id, target_rank, x, y
              FROM item_parameter_estimates
             WHERE run_id = ?
               AND is_estimable = 1
            """,
            (run_id,),
        ).fetchall()
    finally:
        calibration.close()

    estimates = []
    for row in raw_estimates:
        prefix = RANK_TO_COLUMN_PREFIX.get(str(row["target_rank"]))
        x = row["x"]
        y = row["y"]
        if (
            prefix is None
            or x is None
            or y is None
            or not math.isfinite(float(x))
            or not math.isfinite(float(y))
            or float(y) <= 0.0
        ):
            continue
        estimates.append((str(row["chart_id"]), prefix, float(x), float(y)))

    source_mtime_ns = calibration_path.stat().st_mtime_ns
    master = sqlite3.connect(master_path, timeout=30.0)
    master.row_factory = sqlite3.Row
    try:
        master.execute(
            """
            CREATE TABLE IF NOT EXISTS opi_calibration_state(
                state_key TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                source_mtime_ns INTEGER NOT NULL,
                run_id INTEGER NOT NULL,
                model_version TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                estimate_count INTEGER NOT NULL,
                updated_count INTEGER NOT NULL
            )
            """
        )
        chart_rows = master.execute(
            """
            SELECT chart_id, title,
                   opi_s_x, opi_s_y, opi_ss_x, opi_ss_y,
                   opi_sss_x, opi_sss_y, opi_sssp_x, opi_sssp_y,
                   opi_abp_x, opi_abp_y
              FROM charts
            """
        ).fetchall()
        charts = {str(row["chart_id"]): row for row in chart_rows}
        estimates = [
            estimate
            for estimate in estimates
            if estimate[0] in charts and not _is_solo_version(charts[estimate[0]]["title"])
        ]
        abp_overrides = [
            chart_id
            for chart_id in ABP_FIXED_CHART_IDS
            if chart_id in charts and not _is_solo_version(charts[chart_id]["title"])
        ]

        state = master.execute(
            """
            SELECT source_path, source_mtime_ns, run_id, model_version,
                   estimate_count, updated_count
              FROM opi_calibration_state
             WHERE state_key = 'latest_item_parameters'
            """
        ).fetchone()
        parameters_are_current = all(
            charts[chart_id][f"{prefix}_x"] is not None
            and charts[chart_id][f"{prefix}_y"] is not None
            and math.isclose(
                float(charts[chart_id][f"{prefix}_x"]),
                x,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            and math.isclose(
                float(charts[chart_id][f"{prefix}_y"]),
                y,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            for chart_id, prefix, x, y in estimates
        )
        overrides_are_current = all(
            charts[chart_id]["opi_abp_x"] is not None
            and math.isclose(
                float(charts[chart_id]["opi_abp_x"]),
                ABP_FIXED_OPI,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            for chart_id in abp_overrides
        )
        if (
            state is not None
            and str(state["source_path"]) == str(calibration_path.resolve())
            and int(state["source_mtime_ns"]) == source_mtime_ns
            and int(state["run_id"]) == run_id
            and str(state["model_version"]) == model_version
            and int(state["estimate_count"]) == len(estimates)
            and parameters_are_current
            and overrides_are_current
        ):
            master.commit()
            return {
                "status": "current",
                "run_id": run_id,
                "model_version": model_version,
                "estimate_count": int(state["estimate_count"]),
                "updated_count": 0,
            }

        updated_count = 0
        master.execute("BEGIN IMMEDIATE")
        for chart_id, prefix, x, y in estimates:
            current = charts[chart_id]
            current_x = current[f"{prefix}_x"]
            current_y = current[f"{prefix}_y"]
            if (
                current_x is not None
                and current_y is not None
                and math.isclose(float(current_x), x, rel_tol=0.0, abs_tol=1e-9)
                and math.isclose(float(current_y), y, rel_tol=0.0, abs_tol=1e-9)
            ):
                continue
            master.execute(
                f"UPDATE charts SET {prefix}_x = ?, {prefix}_y = ? WHERE chart_id = ?",
                (x, y, chart_id),
            )
            updated_count += 1

        # 推定不能時の一般補完より、ユーザー指定のAB+固定値を常に優先する。
        for chart_id in abp_overrides:
            current_x = master.execute(
                "SELECT opi_abp_x FROM charts WHERE chart_id = ?",
                (chart_id,),
            ).fetchone()[0]
            if current_x is not None and math.isclose(
                float(current_x), ABP_FIXED_OPI, rel_tol=0.0, abs_tol=1e-9
            ):
                continue
            master.execute(
                "UPDATE charts SET opi_abp_x = ? WHERE chart_id = ?",
                (ABP_FIXED_OPI, chart_id),
            )
            updated_count += 1

        master.execute(
            """
            INSERT INTO opi_calibration_state(
                state_key, source_path, source_mtime_ns, run_id, model_version,
                applied_at, estimate_count, updated_count
            ) VALUES('latest_item_parameters', ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(state_key) DO UPDATE SET
                source_path = excluded.source_path,
                source_mtime_ns = excluded.source_mtime_ns,
                run_id = excluded.run_id,
                model_version = excluded.model_version,
                applied_at = excluded.applied_at,
                estimate_count = excluded.estimate_count,
                updated_count = excluded.updated_count
            """,
            (
                str(calibration_path.resolve()),
                source_mtime_ns,
                run_id,
                model_version,
                datetime.now().isoformat(timespec="seconds"),
                len(estimates),
                updated_count,
            ),
        )
        master.commit()
        return {
            "status": "applied",
            "run_id": run_id,
            "model_version": model_version,
            "estimate_count": len(estimates),
            "updated_count": updated_count,
        }
    except Exception:
        master.rollback()
        raise
    finally:
        master.close()
