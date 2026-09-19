import argparse
import json
import os
from collections import Counter, defaultdict
from dataclasses import asdict
from typing import Any

from src.analyzer.item_parameter_estimator import (
    MODEL_VERSION,
    ItemObservation,
    estimate_item_parameters,
)
from src.analyzer.opi_calculator import TARGET_RANKS, is_solo_version
from src.database.models import Chart, Player, ScoreLog, get_engine, get_session_maker


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_FILE = os.path.join(PROJECT_ROOT, "data", "opi_database.sqlite")

RANK_ACHIEVEMENT_FIELDS = {
    "S": "achieve_s",
    "SS": "achieve_ss",
    "SSS": "achieve_sss",
    "SSS+": "achieve_sssp",
    "AB+": "achieve_abp",
}


def build_estimation_report(
    db_path: str,
    *,
    min_sample_size: int = 50,
    min_class_count: int = 5,
) -> dict[str, Any]:
    """DBを変更せず、譜面・目標ランク別の推定可否と推定値を返す。"""
    engine = get_engine(db_path)
    Session = get_session_maker(engine)
    session = Session()

    try:
        rows = session.query(ScoreLog, Player.total_opi, Chart.title).join(
            Player,
            ScoreLog.user_id == Player.user_id,
        ).join(
            Chart,
            ScoreLog.chart_id == Chart.chart_id,
        ).filter(Player.total_opi.isnot(None)).all()

        grouped_observations: dict[tuple[str, str], list[ItemObservation]] = defaultdict(list)
        user_ids = set()
        included_score_count = 0
        for score_log, total_opi, chart_title in rows:
            if is_solo_version(chart_title):
                continue
            included_score_count += 1
            user_ids.add(score_log.user_id)
            for target_rank in TARGET_RANKS:
                field_name = RANK_ACHIEVEMENT_FIELDS[target_rank]
                grouped_observations[(score_log.chart_id, target_rank)].append(
                    ItemObservation(
                        theta=float(total_opi),
                        achieved=bool(getattr(score_log, field_name, False)),
                    )
                )

        estimates = []
        reason_counts: Counter[str] = Counter()
        for chart_id, target_rank in sorted(
            grouped_observations,
            key=lambda item: (item[0], TARGET_RANKS.index(item[1])),
        ):
            estimate = estimate_item_parameters(
                grouped_observations[(chart_id, target_rank)],
                min_sample_size=min_sample_size,
                min_class_count=min_class_count,
            )
            if estimate.reason:
                reason_counts[estimate.reason] += 1
            estimates.append({
                "chart_id": chart_id,
                "target_rank": target_rank,
                **asdict(estimate),
            })

        estimable_count = sum(item["is_estimable"] for item in estimates)
        return {
            "model_version": MODEL_VERSION,
            "mode": "dry_run",
            "database_written": False,
            "player_count": len(user_ids),
            "score_count": included_score_count,
            "item_count": len(estimates),
            "estimable_count": estimable_count,
            "unestimable_count": len(estimates) - estimable_count,
            "unestimable_reasons": dict(sorted(reason_counts.items())),
            "estimates": estimates,
        }
    finally:
        session.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="譜面・目標ランク別2PLパラメータの推定可否を読み取り専用で検証する"
    )
    parser.add_argument("--db", default=DEFAULT_DB_FILE, help="読み取るSQLite DBのパス")
    parser.add_argument("--min-samples", type=int, default=50, help="最低サンプル数")
    parser.add_argument("--min-class-count", type=int, default=5, help="達成・未達成それぞれの最低件数")
    parser.add_argument("--summary-only", action="store_true", help="個別推定値を省略して集計結果だけを表示する")
    args = parser.parse_args()

    report = build_estimation_report(
        args.db,
        min_sample_size=args.min_samples,
        min_class_count=args.min_class_count,
    )
    if args.summary_only:
        report = {key: value for key, value in report.items() if key != "estimates"}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
