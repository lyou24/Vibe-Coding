import argparse
import hashlib
import json
import logging
from collections import defaultdict
from pathlib import Path

import numpy as np

from src.analyzer.item_parameter_estimator import (
    DEFAULT_MIN_CLASS_COUNT,
    DEFAULT_MIN_SAMPLE_SIZE,
    ItemObservation,
    estimate_item_parameters,
    two_pl_probability,
)
from src.analyzer.opi_calculator import TARGET_RANKS
from src.analyzer.opi_policy import calculate_fallback_rank_params
from src.database.calibration_store import CalibrationStore


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CALIBRATION_DB = PROJECT_ROOT / "data" / "opi_calibration.sqlite"

RANK_FIELDS = {
    "SS": "achieve_ss",
    "SSS": "achieve_sss",
    "SSS+": "achieve_sssp",
    "S": "achieve_s",
    "AB+": "achieve_abp",
}


def is_train(subject_key: str, train_ratio: int = 80) -> bool:
    """決定論的な学習・検証分割（ハッシュ値のモジュロ）"""
    h = hashlib.md5(subject_key.encode("utf-8")).hexdigest()
    return int(h, 16) % 100 < train_ratio


def evaluate_predictive_performance(
    calibration_db: Path,
    min_samples: int = DEFAULT_MIN_SAMPLE_SIZE,
    min_class_count: int = DEFAULT_MIN_CLASS_COUNT,
) -> dict:
    with CalibrationStore(str(calibration_db)) as store:
        # 最新の能力推定runを取得
        ability_run = store.connection.execute(
            """
            SELECT * FROM estimation_runs
             WHERE status = 'completed'
               AND model_version LIKE 'player-ability-%'
             ORDER BY run_id DESC
             LIMIT 1
            """
        ).fetchone()

        if not ability_run:
            raise ValueError("完了済みのプレイヤー能力推定runがありません")

        ability_run_id = ability_run["run_id"]
        master_version_id = ability_run["master_version_id"]

        # プレイヤーの推定能力値を取得
        players = store.connection.execute(
            """
            SELECT subject_key, theta
              FROM player_ability_estimates
             WHERE run_id = ? AND is_estimable = 1
            """,
            (ability_run_id,),
        ).fetchall()

        train_players = {}
        val_players = {}
        for p in players:
            sk = p["subject_key"]
            if is_train(sk):
                train_players[sk] = float(p["theta"])
            else:
                val_players[sk] = float(p["theta"])

        # スコアと譜面定数の取得
        scores = store.connection.execute(
            """
            SELECT s.subject_key, s.chart_id, s.achieve_ss, s.achieve_sss, s.achieve_sssp,
                   s.achieve_s, s.achieve_abp, m.chart_constant
              FROM scores AS s
              JOIN chart_master_items AS m
                ON m.version_id = ? AND m.chart_id = s.chart_id
            """,
            (master_version_id,),
        ).fetchall()

        train_obs = defaultdict(list)
        val_obs = defaultdict(list)
        chart_constants = {}

        for row in scores:
            sk = row["subject_key"]
            cid = row["chart_id"]
            cc = float(row["chart_constant"])
            chart_constants[cid] = cc

            if sk in train_players:
                theta = train_players[sk]
                obs_dict = train_obs
            elif sk in val_players:
                theta = val_players[sk]
                obs_dict = val_obs
            else:
                continue

            for rank in TARGET_RANKS:
                achieved = bool(row[RANK_FIELDS[rank]])
                obs_dict[(cid, rank)].append(
                    ItemObservation(theta=theta, achieved=achieved)
                )

        # 項目パラメータ推定と評価
        estimable_count = 0
        total_eval_samples = 0
        brier_est_sum = 0.0
        brier_fall_sum = 0.0
        logloss_est_sum = 0.0
        logloss_fall_sum = 0.0
        
        # ランク別統計
        rank_stats = {rank: {"eval_samples": 0, "brier_est": 0.0, "brier_fall": 0.0, "logloss_est": 0.0, "logloss_fall": 0.0} for rank in TARGET_RANKS}

        for (cid, rank), observations in train_obs.items():
            estimate = estimate_item_parameters(
                observations,
                min_sample_size=min_samples,
                min_class_count=min_class_count,
            )

            if not estimate.is_estimable:
                continue

            estimable_count += 1
            x_est = estimate.x
            y_est = estimate.y
            cc = chart_constants[cid]
            x_fall, y_fall = calculate_fallback_rank_params(cc, rank)

            # 検証データで評価
            val_items = val_obs.get((cid, rank), [])
            for obs in val_items:
                theta = obs.theta
                achieved = float(obs.achieved)

                # 推定モデル
                p_est = two_pl_probability(theta, x_est, y_est)
                # クリップして0除算回避
                p_est = np.clip(p_est, 1e-15, 1 - 1e-15)
                brier_est = (p_est - achieved)**2
                logloss_est = -np.log(p_est) if achieved else -np.log(1.0 - p_est)

                # フォールバックモデル
                p_fall = two_pl_probability(theta, x_fall, y_fall)
                p_fall = np.clip(p_fall, 1e-15, 1 - 1e-15)
                brier_fall = (p_fall - achieved)**2
                logloss_fall = -np.log(p_fall) if achieved else -np.log(1.0 - p_fall)

                # 集計
                total_eval_samples += 1
                brier_est_sum += brier_est
                brier_fall_sum += brier_fall
                logloss_est_sum += logloss_est
                logloss_fall_sum += logloss_fall
                
                rank_stats[rank]["eval_samples"] += 1
                rank_stats[rank]["brier_est"] += brier_est
                rank_stats[rank]["brier_fall"] += brier_fall
                rank_stats[rank]["logloss_est"] += logloss_est
                rank_stats[rank]["logloss_fall"] += logloss_fall

        # 平均化
        def mean_safe(total, count):
            return float(total / count) if count > 0 else None

        report = {
            "split": {
                "train_players": len(train_players),
                "val_players": len(val_players),
            },
            "estimation": {
                "estimable_items": estimable_count,
            },
            "evaluation": {
                "val_samples": total_eval_samples,
                "overall": {
                    "brier_score_estimated": mean_safe(brier_est_sum, total_eval_samples),
                    "brier_score_fallback": mean_safe(brier_fall_sum, total_eval_samples),
                    "logloss_estimated": mean_safe(logloss_est_sum, total_eval_samples),
                    "logloss_fallback": mean_safe(logloss_fall_sum, total_eval_samples),
                },
                "by_rank": {}
            }
        }
        
        for rank in TARGET_RANKS:
            cnt = rank_stats[rank]["eval_samples"]
            if cnt > 0:
                report["evaluation"]["by_rank"][rank] = {
                    "val_samples": cnt,
                    "brier_score_estimated": mean_safe(rank_stats[rank]["brier_est"], cnt),
                    "brier_score_fallback": mean_safe(rank_stats[rank]["brier_fall"], cnt),
                    "logloss_estimated": mean_safe(rank_stats[rank]["logloss_est"], cnt),
                    "logloss_fallback": mean_safe(rank_stats[rank]["logloss_fall"], cnt),
                }

        return report


def main() -> None:
    parser = argparse.ArgumentParser(description="学習/検証分割による2PL項目の予測性能評価")
    parser.add_argument("--calibration-db", type=Path, default=DEFAULT_CALIBRATION_DB)
    parser.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLE_SIZE)
    parser.add_argument("--min-class-count", type=int, default=DEFAULT_MIN_CLASS_COUNT)
    args = parser.parse_args()

    report = evaluate_predictive_performance(
        args.calibration_db,
        min_samples=args.min_samples,
        min_class_count=args.min_class_count,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
