import argparse
import hashlib
import json
import os
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.analyzer.opi_policy import calculate_fallback_rank_params
from src.analyzer.player_ability_estimator import (
    ABILITY_MODEL_VERSION,
    AbilityObservation,
    estimate_player_ability,
)
from src.database.calibration_store import CalibrationStore


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CALIBRATION_DB = PROJECT_ROOT / "data" / "opi_calibration.sqlite"
DEFAULT_MASTER_DB = PROJECT_ROOT / "data" / "opi_database.sqlite"
MIN_CHART_CONSTANT = 14.0


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_chart_master(db_path: Path, min_chart_constant: float) -> list[dict[str, Any]]:
    """メインDBを読み取り専用で開き、校正対象譜面を正規化して返す。"""
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT chart_id, title, difficulty, level, chart_constant,
                   COALESCE(is_active, 1) AS is_active
              FROM charts
             WHERE COALESCE(is_active, 1) = 1
               AND chart_constant >= ?
             ORDER BY chart_id
            """,
            (float(min_chart_constant),),
        ).fetchall()
    finally:
        connection.close()

    return [
        {
            "chart_id": row["chart_id"],
            "title": row["title"],
            "difficulty": str(row["difficulty"]),
            "level": row["level"],
            "chart_constant": float(row["chart_constant"]),
            "is_active": bool(row["is_active"]),
        }
        for row in rows
    ]


def canonical_hash(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def load_ability_observations(
    store: CalibrationStore,
    master_version_id: str,
) -> tuple[dict[str, list[AbilityObservation]], str]:
    """保存済みスコアと固定譜面マスタを結合し、SSS成否観測を作る。"""
    rows = store.connection.execute(
        """
        SELECT s.subject_key, s.chart_id, s.score, s.source_updated_at,
               m.chart_constant
          FROM scores AS s
          JOIN chart_master_items AS m
            ON m.version_id = ? AND m.chart_id = s.chart_id
         ORDER BY s.subject_key, s.chart_id
        """,
        (master_version_id,),
    ).fetchall()

    grouped: dict[str, list[AbilityObservation]] = defaultdict(list)
    digest = hashlib.sha256()
    for row in rows:
        x_value, y_value = calculate_fallback_rank_params(row["chart_constant"], "SSS")
        grouped[row["subject_key"]].append(
            AbilityObservation(
                x=float(x_value),
                y=float(y_value),
                achieved=int(row["score"]) >= 1_000_000,
            )
        )
        digest.update(
            f"{row['subject_key']}\0{row['chart_id']}\0{row['score']}\0{row['source_updated_at']}\n".encode("utf-8")
        )
    return dict(grouped), digest.hexdigest()


def build_ability_report(
    calibration_db: Path,
    master_db: Path,
    *,
    min_items: int = 20,
    min_class_count: int = 3,
    min_chart_constant: float = MIN_CHART_CONSTANT,
) -> dict[str, Any]:
    """本番DBを変更せず、固定マスタに基づくプレイヤー能力初期値を履歴保存する。"""
    main_db_hash_before = file_sha256(master_db)
    charts = load_chart_master(master_db, min_chart_constant)
    if not charts:
        raise ValueError("校正対象の譜面マスタがありません")

    master_hash = canonical_hash(charts)
    master_version_id = f"master-{master_hash[:16]}"
    config = {
        "target_rank": "SSS",
        "min_items": min_items,
        "min_class_count": min_class_count,
        "min_chart_constant": min_chart_constant,
        "prior_mean": 1500.0,
        "prior_sigma": 500.0,
        "theta_bounds": [0.0, 4000.0],
    }
    config_json = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    with CalibrationStore(str(calibration_db)) as store:
        store.save_chart_master_snapshot(
            version_id=master_version_id,
            content_hash=master_hash,
            source_name=master_db.name,
            charts=charts,
        )
        observations_by_player, data_hash = load_ability_observations(store, master_version_id)
        player_count = store.connection.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        run_key = canonical_hash({
            "model_version": ABILITY_MODEL_VERSION,
            "master_version_id": master_version_id,
            "data_hash": data_hash,
            "config": config,
        })
        run_id, should_execute = store.start_or_resume_estimation_run(
            run_key=run_key,
            model_version=ABILITY_MODEL_VERSION,
            master_version_id=master_version_id,
            data_hash=data_hash,
            config_json=config_json,
            player_count=player_count,
        )

        if should_execute:
            estimated_count = 0
            unestimated_count = 0
            try:
                all_subject_keys = sorted(store.subject_keys())
                for subject_key in all_subject_keys:
                    observations = observations_by_player.get(subject_key, [])
                    estimate = estimate_player_ability(
                        observations,
                        min_observation_count=min_items,
                        min_class_count=min_class_count,
                    )
                    store.save_player_ability_estimate(
                        run_id=run_id,
                        subject_key=subject_key,
                        estimate=estimate,
                        coverage=len(observations) / len(charts),
                    )
                    if estimate.is_estimable:
                        estimated_count += 1
                    else:
                        unestimated_count += 1
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

        report = store.ability_run_report(run_id)
        report.update({
            "mode": "calibration_only",
            "main_database_written": False,
            "reused_completed_run": not should_execute,
            "master_chart_count": len(charts),
            "matched_observation_count": sum(len(items) for items in observations_by_player.values()),
        })

    main_db_hash_after = file_sha256(master_db)
    if main_db_hash_before != main_db_hash_after:
        raise RuntimeError("読み取り専用のメインDBが処理中に変更されました")
    report["main_database_hash_unchanged"] = True
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="校正DBのプレイヤー能力初期値をSSS成否から推定する")
    parser.add_argument("--calibration-db", type=Path, default=DEFAULT_CALIBRATION_DB)
    parser.add_argument("--master-db", type=Path, default=DEFAULT_MASTER_DB)
    parser.add_argument("--min-items", type=int, default=20)
    parser.add_argument("--min-class-count", type=int, default=3)
    parser.add_argument("--min-chart-constant", type=float, default=MIN_CHART_CONSTANT)
    args = parser.parse_args()

    report = build_ability_report(
        args.calibration_db,
        args.master_db,
        min_items=args.min_items,
        min_class_count=args.min_class_count,
        min_chart_constant=args.min_chart_constant,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
