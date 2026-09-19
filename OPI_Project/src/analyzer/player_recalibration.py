"""最新の単曲OPIとAAA以上のスコアからプレイヤー能力を再推定する。"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from src.analyzer.opi_calculator import MIN_ELIGIBLE_SCORE, TARGET_RANKS, is_solo_version
from src.analyzer.opi_overrides import get_fixed_rank_opi
from src.analyzer.opi_policy import calculate_fallback_rank_params
from src.analyzer.player_ability_estimator import AbilityObservation, estimate_player_ability
from src.database.calibrated_parameters import sync_latest_calibrated_parameters
from src.database.calibration_store import CalibrationStore


AAA_ABILITY_MODEL_VERSION = "player-ability-map-aaa-all-ranks-v1"
MIN_CHART_CONSTANT = 14.0
RANK_TO_PREFIX = {
    "S": "opi_s",
    "SS": "opi_ss",
    "SSS": "opi_sss",
    "SSS+": "opi_sssp",
    "AB+": "opi_abp",
}
RANK_SCORE_THRESHOLDS = {
    "S": 975_000,
    "SS": 990_000,
    "SSS": 1_000_000,
    "SSS+": 1_007_500,
    "AB+": 1_010_000,
}


def _canonical_hash(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _load_chart_parameters(
    master_db: Path,
    min_chart_constant: float,
) -> list[dict[str, Any]]:
    connection = sqlite3.connect(
        f"file:{master_db.resolve().as_posix()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT chart_id, title, difficulty, level, chart_constant,
                   COALESCE(is_active, 1) AS is_active,
                   opi_s_x, opi_s_y, opi_ss_x, opi_ss_y,
                   opi_sss_x, opi_sss_y, opi_sssp_x, opi_sssp_y,
                   opi_abp_x, opi_abp_y
              FROM charts
             WHERE COALESCE(is_active, 1) = 1
               AND chart_constant >= ?
             ORDER BY chart_id
            """,
            (float(min_chart_constant),),
        ).fetchall()
    finally:
        connection.close()

    charts: list[dict[str, Any]] = []
    for row in rows:
        if is_solo_version(row["title"]):
            continue
        rank_parameters = {}
        for rank in TARGET_RANKS:
            prefix = RANK_TO_PREFIX[rank]
            x_value = row[f"{prefix}_x"]
            y_value = row[f"{prefix}_y"]
            fixed_x = get_fixed_rank_opi(row["chart_id"], rank)
            if fixed_x is not None:
                x_value = fixed_x
            invalid_x = x_value is None or not math.isfinite(float(x_value))
            invalid_y = (
                y_value is None
                or not math.isfinite(float(y_value))
                or float(y_value) <= 0.0
            )
            if invalid_x or invalid_y:
                fallback_x, fallback_y = calculate_fallback_rank_params(
                    float(row["chart_constant"]), rank
                )
                x_value = fallback_x if invalid_x else x_value
                y_value = fallback_y if invalid_y else y_value
            rank_parameters[rank] = (float(x_value), float(y_value))
        charts.append(
            {
                "chart_id": str(row["chart_id"]),
                "title": str(row["title"]),
                "difficulty": str(row["difficulty"]),
                "level": str(row["level"]),
                "chart_constant": float(row["chart_constant"]),
                "is_active": True,
                "rank_parameters": rank_parameters,
            }
        )
    return charts


def _eligible_score_query(chart_ids: Iterable[str]) -> tuple[str, list[str]]:
    ids = sorted(set(chart_ids))
    placeholders = ",".join("?" for _ in ids)
    return (
        f"""
        SELECT subject_key, chart_id, score, source_updated_at
          FROM scores
         WHERE score >= ?
           AND chart_id IN ({placeholders})
         ORDER BY subject_key, chart_id
        """,
        ids,
    )


def _score_data_hash(
    store: CalibrationStore,
    chart_ids: Iterable[str],
    min_score: int,
) -> tuple[str, int, int]:
    query, ids = _eligible_score_query(chart_ids)
    digest = hashlib.sha256()
    score_count = 0
    subjects: set[str] = set()
    for row in store.connection.execute(query, (int(min_score), *ids)):
        digest.update(
            (
                f"{row['subject_key']}\0{row['chart_id']}\0{row['score']}\0"
                f"{row['source_updated_at']}\n"
            ).encode("utf-8")
        )
        score_count += 1
        subjects.add(str(row["subject_key"]))
    return digest.hexdigest(), score_count, len(subjects)


def _save_estimates(
    store: CalibrationStore,
    *,
    run_id: int,
    charts: list[dict[str, Any]],
    min_score: int,
    min_eligible_charts: int,
    min_class_count: int,
) -> tuple[int, int, int]:
    chart_map = {chart["chart_id"]: chart for chart in charts}
    query, ids = _eligible_score_query(chart_map)
    all_subjects = store.subject_keys()
    processed_subjects: set[str] = set()
    estimated_count = 0
    unestimated_count = 0
    observation_count = 0
    current_subject: str | None = None
    current_observations: list[AbilityObservation] = []
    current_chart_count = 0

    def save_current() -> None:
        nonlocal estimated_count, unestimated_count, observation_count
        if current_subject is None:
            return
        estimate = estimate_player_ability(
            current_observations,
            min_observation_count=min_eligible_charts * len(TARGET_RANKS),
            min_class_count=min_class_count,
        )
        store.save_player_ability_estimate(
            run_id=run_id,
            subject_key=current_subject,
            estimate=estimate,
            coverage=current_chart_count / len(charts),
        )
        processed_subjects.add(current_subject)
        observation_count += len(current_observations)
        if estimate.is_estimable:
            estimated_count += 1
        else:
            unestimated_count += 1

    for row in store.connection.execute(query, (int(min_score), *ids)):
        subject_key = str(row["subject_key"])
        if current_subject is not None and subject_key != current_subject:
            save_current()
            current_observations = []
            current_chart_count = 0
        current_subject = subject_key
        chart = chart_map[str(row["chart_id"])]
        score = int(row["score"])
        current_chart_count += 1
        current_observations.extend(
            AbilityObservation(
                x=chart["rank_parameters"][rank][0],
                y=chart["rank_parameters"][rank][1],
                achieved=score >= RANK_SCORE_THRESHOLDS[rank],
            )
            for rank in TARGET_RANKS
        )
    save_current()

    for subject_key in sorted(all_subjects - processed_subjects):
        estimate = estimate_player_ability(
            [],
            min_observation_count=min_eligible_charts * len(TARGET_RANKS),
            min_class_count=min_class_count,
        )
        store.save_player_ability_estimate(
            run_id=run_id,
            subject_key=subject_key,
            estimate=estimate,
            coverage=0.0,
        )
        unestimated_count += 1
    return estimated_count, unestimated_count, observation_count


def build_aaa_calibrated_ability_report(
    calibration_db: Path,
    master_db: Path,
    *,
    min_score: int = MIN_ELIGIBLE_SCORE,
    min_eligible_charts: int = 20,
    min_class_count: int = 3,
    min_chart_constant: float = MIN_CHART_CONSTANT,
) -> dict[str, Any]:
    """最新項目パラメータとAAA以上のスコアで能力値を履歴保存する。"""
    sync_report = sync_latest_calibrated_parameters(calibration_db, master_db)
    charts = _load_chart_parameters(master_db, min_chart_constant)
    if not charts:
        raise ValueError("再推定対象の譜面パラメータがありません")

    parameter_payload = [
        {
            "chart_id": chart["chart_id"],
            "title": chart["title"],
            "difficulty": chart["difficulty"],
            "level": chart["level"],
            "chart_constant": chart["chart_constant"],
            "is_active": chart["is_active"],
            "rank_parameters": chart["rank_parameters"],
        }
        for chart in charts
    ]
    parameter_hash = _canonical_hash(parameter_payload)
    master_version_id = f"master-aaa-{parameter_hash[:16]}"
    config = {
        "minimum_score": int(min_score),
        "score_condition": "AAA以上",
        "min_eligible_charts": int(min_eligible_charts),
        "min_class_count": int(min_class_count),
        "min_chart_constant": float(min_chart_constant),
        "target_ranks": TARGET_RANKS,
        "rank_score_thresholds": RANK_SCORE_THRESHOLDS,
        "prior_mean": 1500.0,
        "prior_sigma": 500.0,
        "theta_bounds": [0.0, 4000.0],
    }
    config_json = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    with CalibrationStore(str(calibration_db)) as store:
        store.save_chart_master_snapshot(
            version_id=master_version_id,
            content_hash=parameter_hash,
            source_name=master_db.name,
            charts=parameter_payload,
        )
        parent_run = store.connection.execute(
            """
            SELECT run_id
              FROM estimation_runs
             WHERE status = 'completed'
               AND model_version LIKE '2pl-item-%'
             ORDER BY run_id DESC
             LIMIT 1
            """
        ).fetchone()
        parent_run_id = int(parent_run["run_id"]) if parent_run else None
        score_hash, eligible_score_count, eligible_player_count = _score_data_hash(
            store,
            (chart["chart_id"] for chart in charts),
            min_score,
        )
        data_hash = _canonical_hash(
            {
                "parameter_hash": parameter_hash,
                "eligible_score_hash": score_hash,
                "parent_item_run_id": parent_run_id,
            }
        )
        run_key = _canonical_hash(
            {
                "model_version": AAA_ABILITY_MODEL_VERSION,
                "master_version_id": master_version_id,
                "data_hash": data_hash,
                "config": config,
            }
        )
        player_count = store.connection.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        run_id, should_execute = store.start_or_resume_estimation_run(
            run_key=run_key,
            model_version=AAA_ABILITY_MODEL_VERSION,
            master_version_id=master_version_id,
            data_hash=data_hash,
            config_json=config_json,
            player_count=player_count,
            parent_run_id=parent_run_id,
        )

        observation_count = 0
        if should_execute:
            try:
                estimated_count, unestimated_count, observation_count = _save_estimates(
                    store,
                    run_id=run_id,
                    charts=charts,
                    min_score=min_score,
                    min_eligible_charts=min_eligible_charts,
                    min_class_count=min_class_count,
                )
                store.finish_estimation_run(
                    run_id,
                    status="completed",
                    estimated_player_count=estimated_count,
                    unestimated_player_count=unestimated_count,
                )
            except Exception:
                store.connection.rollback()
                store.finish_estimation_run(
                    run_id,
                    status="failed",
                    estimated_player_count=0,
                    unestimated_player_count=player_count,
                )
                raise

        with store.transaction() as connection:
            connection.execute(
                """
                UPDATE players
                   SET estimated_opi = (
                       SELECT estimate.theta
                         FROM player_ability_estimates AS estimate
                        WHERE estimate.run_id = ?
                          AND estimate.subject_key = players.subject_key
                          AND estimate.is_estimable = 1
                   )
                """,
                (run_id,),
            )

        report = store.ability_run_report(run_id)
        report.update(
            {
                "reused_completed_run": not should_execute,
                "parent_item_run_id": parent_run_id,
                "master_chart_count": len(charts),
                "eligible_score_count": eligible_score_count,
                "eligible_player_count": eligible_player_count,
                "observation_count": observation_count,
                "minimum_score": int(min_score),
                "score_condition": "AAA以上",
                "parameter_sync": sync_report,
            }
        )
        return report
