"""最新単曲パラメータとAAA以上条件によるプレイヤーOPI再推定CLI。"""

import argparse
import json
from pathlib import Path

from src.analyzer.player_recalibration import build_aaa_calibrated_ability_report


PROJECT_ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description="最新単曲OPIとAAA以上のスコアでプレイヤーOPIを再推定する")
    parser.add_argument(
        "--calibration-db",
        type=Path,
        default=PROJECT_ROOT / "data" / "opi_calibration.sqlite",
    )
    parser.add_argument(
        "--master-db",
        type=Path,
        default=PROJECT_ROOT / "data" / "opi_database.sqlite",
    )
    parser.add_argument("--min-score", type=int, default=970_000)
    parser.add_argument("--min-eligible-charts", type=int, default=20)
    parser.add_argument("--min-class-count", type=int, default=3)
    args = parser.parse_args()
    report = build_aaa_calibrated_ability_report(
        args.calibration_db,
        args.master_db,
        min_score=args.min_score,
        min_eligible_charts=args.min_eligible_charts,
        min_class_count=args.min_class_count,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
