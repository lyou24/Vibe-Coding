import argparse
import hashlib
import json
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from src.analyzer.item_parameter_estimator import (
    DEFAULT_MIN_CLASS_COUNT,
    DEFAULT_MIN_SAMPLE_SIZE,
    MODEL_VERSION,
    ItemObservation,
    estimate_item_parameters,
)
from src.analyzer.opi_calculator import TARGET_RANKS
from src.database.calibration_store import CalibrationStore


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CALIBRATION_DB = PROJECT_ROOT / "data" / "opi_calibration.sqlite"
RANK_FIELDS = {
    "S": "achieve_s",
    "SS": "achieve_ss",
    "SSS": "achieve_sss",
    "SSS+": "achieve_sssp",
    "AB+": "achieve_abp",
}


def canonical_hash(value) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def resolve_ability_run(store: CalibrationStore, ability_run_id: int | None):
    if ability_run_id is None:
        run = store.connection.execute(
            """
            SELECT * FROM estimation_runs
             WHERE status = 'completed'
               AND model_version LIKE 'player-ability-%'
             ORDER BY run_id DESC
             LIMIT 1
            """
        ).fetchone()
    else:
        run = store.connection.execute(
            """
            SELECT * FROM estimation_runs
             WHERE run_id = ? AND status = 'completed'
               AND model_version LIKE 'player-ability-%'
            """,
            (ability_run_id,),
        ).fetchone()
    if not run:
        raise ValueError("完了済みのプレイヤー能力推定runがありません")
    return run


def load_item_observations(store: CalibrationStore, ability_run_id: int, master_version_id: str):
    rows = store.connection.execute(
        """
        SELECT s.chart_id, s.achieve_s, s.achieve_ss, s.achieve_sss, s.achieve_sssp,
               s.achieve_abp, a.theta, a.subject_key
          FROM player_ability_estimates AS a
          JOIN scores AS s ON s.subject_key = a.subject_key
          JOIN chart_master_items AS m
            ON m.version_id = ? AND m.chart_id = s.chart_id
         WHERE a.run_id = ? AND a.is_estimable = 1
         ORDER BY s.chart_id, a.subject_key
        """,
        (master_version_id, ability_run_id),
    ).fetchall()

    grouped = defaultdict(list)
    digest = hashlib.sha256()
    for row in rows:
        for rank in TARGET_RANKS:
            achieved = bool(row[RANK_FIELDS[rank]])
            grouped[(row["chart_id"], rank)].append(
                ItemObservation(theta=float(row["theta"]), achieved=achieved)
            )
        digest.update(
            (
                f"{row['chart_id']}\0{row['subject_key']}\0{row['theta']:.12g}\0"
                f"{row['achieve_s']}{row['achieve_ss']}{row['achieve_sss']}"
                f"{row['achieve_sssp']}{row['achieve_abp']}\n"
            ).encode("utf-8")
        )
    return grouped, digest.hexdigest()


def build_item_report(
    calibration_db: Path,
    *,
    ability_run_id: int | None = None,
    min_samples: int = DEFAULT_MIN_SAMPLE_SIZE,
    min_class_count: int = DEFAULT_MIN_CLASS_COUNT,
    min_y: float = 1.0,
    max_y: float = 2000.0,
) -> dict:
    """固定した能力値から項目パラメータを推定し、校正DBだけへ保存する。"""
    config = {
        "min_samples": min_samples,
        "min_class_count": min_class_count,
        "min_y": min_y,
        "max_y": max_y,
        "target_ranks": TARGET_RANKS,
        "missing_scores_are_failures": False,
    }
    config_json = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    with CalibrationStore(str(calibration_db)) as store:
        ability_run = resolve_ability_run(store, ability_run_id)
        ability_run_id = int(ability_run["run_id"])
        master_version_id = ability_run["master_version_id"]
        charts = store.connection.execute(
            """
            SELECT chart_id FROM chart_master_items
             WHERE version_id = ? AND is_active = 1
             ORDER BY chart_id
            """,
            (master_version_id,),
        ).fetchall()
        observations, observation_hash = load_item_observations(
            store,
            ability_run_id,
            master_version_id,
        )
        data_hash = canonical_hash({
            "ability_run_id": ability_run_id,
            "ability_data_hash": ability_run["data_hash"],
            "observations": observation_hash,
        })
        run_key = canonical_hash({
            "model_version": MODEL_VERSION,
            "master_version_id": master_version_id,
            "data_hash": data_hash,
            "config": config,
            "parent_ability_run_id": ability_run_id,
        })
        ability_player_count = store.connection.execute(
            """
            SELECT COUNT(*) FROM player_ability_estimates
             WHERE run_id = ? AND is_estimable = 1
            """,
            (ability_run_id,),
        ).fetchone()[0]
        run_id, should_execute = store.start_or_resume_estimation_run(
            run_key=run_key,
            model_version=MODEL_VERSION,
            master_version_id=master_version_id,
            data_hash=data_hash,
            config_json=config_json,
            player_count=ability_player_count,
            parent_run_id=ability_run_id,
        )

        if should_execute:
            estimable_count = 0
            unestimable_count = 0
            try:
                for chart in charts:
                    for rank in TARGET_RANKS:
                        estimate = estimate_item_parameters(
                            observations.get((chart["chart_id"], rank), []),
                            min_sample_size=min_samples,
                            min_class_count=min_class_count,
                            min_y=min_y,
                            max_y=max_y,
                        )
                        boundary_reached = bool(
                            estimate.is_estimable
                            and estimate.y is not None
                            and (
                                abs(estimate.y - min_y) <= 1e-6
                                or abs(estimate.y - max_y) <= 1e-6
                            )
                        )
                        if boundary_reached:
                            estimate = replace(
                                estimate,
                                is_estimable=False,
                                reason="parameter_boundary",
                            )
                        store.save_item_parameter_estimate(
                            run_id=run_id,
                            chart_id=chart["chart_id"],
                            target_rank=rank,
                            estimate=estimate,
                            boundary_reached=boundary_reached,
                        )
                        if estimate.is_estimable:
                            estimable_count += 1
                        else:
                            unestimable_count += 1
                store.finish_item_estimation_run(
                    run_id,
                    status="completed",
                    result_count=estimable_count,
                    unestimable_result_count=unestimable_count,
                )
            except Exception:
                store.connection.rollback()
                store.finish_item_estimation_run(
                    run_id,
                    status="failed",
                    result_count=0,
                    unestimable_result_count=len(charts) * len(TARGET_RANKS),
                )
                raise

        report = store.item_run_report(run_id)
        report.update({
            "mode": "calibration_only",
            "main_database_written": False,
            "reused_completed_run": not should_execute,
            "master_chart_count": len(charts),
        })
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description="校正DBの譜面・目標ランク別2PL推定可否を検証する")
    parser.add_argument("--calibration-db", type=Path, default=DEFAULT_CALIBRATION_DB)
    parser.add_argument("--ability-run-id", type=int)
    parser.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLE_SIZE)
    parser.add_argument("--min-class-count", type=int, default=DEFAULT_MIN_CLASS_COUNT)
    parser.add_argument("--min-y", type=float, default=1.0)
    parser.add_argument("--max-y", type=float, default=2000.0)
    args = parser.parse_args()

    report = build_item_report(
        args.calibration_db,
        ability_run_id=args.ability_run_id,
        min_samples=args.min_samples,
        min_class_count=args.min_class_count,
        min_y=args.min_y,
        max_y=args.max_y,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
