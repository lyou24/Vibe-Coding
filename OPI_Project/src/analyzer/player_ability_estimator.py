"""固定済みSSS項目パラメータからプレイヤーの初期能力値を推定する。

このモジュールはDBやWebへアクセスしない。譜面マスタのフォールバック ``x`` / ``y``
とSSS達成成否を呼び出し側から受け取り、正規事前分布を用いたMAP推定を行う。
"""

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
from scipy.optimize import minimize_scalar


ABILITY_MODEL_VERSION = "player-ability-map-sss-v1"
DEFAULT_MIN_OBSERVATION_COUNT = 30
DEFAULT_MIN_CLASS_COUNT = 5


@dataclass(frozen=True)
class AbilityObservation:
    """1譜面の固定済みSSS項目パラメータと達成成否。"""

    x: float
    y: float
    achieved: bool


@dataclass(frozen=True)
class PlayerAbilityEstimate:
    """初期能力値の推定結果と、採用可否を判断するための診断値。"""

    model_version: str
    item_count: int
    achieved_count: int
    unachieved_count: int
    is_estimable: bool
    reason: Optional[str]
    convergence_status: str
    converged: bool
    theta: Optional[float]
    negative_log_likelihood: Optional[float]
    negative_log_posterior: Optional[float]
    boundary_reached: bool
    theta_lower_bound: float
    theta_upper_bound: float


def estimate_player_ability(
    observations: Iterable[AbilityObservation],
    *,
    min_observation_count: int = DEFAULT_MIN_OBSERVATION_COUNT,
    min_class_count: int = DEFAULT_MIN_CLASS_COUNT,
    prior_mean: float = 1500.0,
    prior_standard_deviation: float = 500.0,
    theta_lower_bound: float = 0.0,
    theta_upper_bound: float = 4000.0,
) -> PlayerAbilityEstimate:
    """固定SSS項目パラメータに対する1次元MAP推定を行う。

    データ不足は例外にせず、``is_estimable=False`` と安定した ``reason`` で返す。
    非数値、非正の ``y``、不正な達成値など入力自体の異常は例外にする。
    """

    configuration = _validate_configuration(
        min_observation_count=min_observation_count,
        min_class_count=min_class_count,
        prior_mean=prior_mean,
        prior_standard_deviation=prior_standard_deviation,
        theta_lower_bound=theta_lower_bound,
        theta_upper_bound=theta_upper_bound,
    )
    prior_mean_value, prior_sd_value, lower_bound, upper_bound = configuration
    normalized = _normalize_observations(observations)

    observation_count = len(normalized)
    achieved_count = sum(achieved for _, _, achieved in normalized)
    unachieved_count = observation_count - achieved_count

    def unable(reason: str) -> PlayerAbilityEstimate:
        return PlayerAbilityEstimate(
            model_version=ABILITY_MODEL_VERSION,
            item_count=observation_count,
            achieved_count=achieved_count,
            unachieved_count=unachieved_count,
            is_estimable=False,
            reason=reason,
            convergence_status="not_run",
            converged=False,
            theta=None,
            negative_log_likelihood=None,
            negative_log_posterior=None,
            boundary_reached=False,
            theta_lower_bound=lower_bound,
            theta_upper_bound=upper_bound,
        )

    if observation_count < min_observation_count:
        return unable("insufficient_observations")
    if achieved_count == 0 or unachieved_count == 0:
        return unable("single_class")
    if min(achieved_count, unachieved_count) < min_class_count:
        return unable("insufficient_class_observations")

    x_values = np.asarray([x for x, _, _ in normalized], dtype=float)
    y_values = np.asarray([y for _, y, _ in normalized], dtype=float)
    responses = np.asarray([achieved for _, _, achieved in normalized], dtype=float)

    def likelihood_loss(theta: float) -> float:
        logits = (float(theta) - x_values) / y_values
        return float(np.sum(np.logaddexp(0.0, logits) - responses * logits))

    def objective(theta: float) -> float:
        prior_loss = 0.5 * ((float(theta) - prior_mean_value) / prior_sd_value) ** 2
        return likelihood_loss(theta) + float(prior_loss)

    try:
        result = minimize_scalar(
            objective,
            bounds=(lower_bound, upper_bound),
            method="bounded",
        )
    except Exception:
        return _optimization_failure(
            item_count=observation_count,
            achieved_count=achieved_count,
            unachieved_count=unachieved_count,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
        )

    if not result.success or not np.isfinite(result.x) or not np.isfinite(result.fun):
        return _optimization_failure(
            item_count=observation_count,
            achieved_count=achieved_count,
            unachieved_count=unachieved_count,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
        )

    theta = float(result.x)
    negative_log_likelihood = likelihood_loss(theta)
    posterior_loss = objective(theta)
    if not np.isfinite(negative_log_likelihood) or not np.isfinite(posterior_loss):
        return _optimization_failure(
            item_count=observation_count,
            achieved_count=achieved_count,
            unachieved_count=unachieved_count,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
        )

    boundary_tolerance = max(1e-6, (upper_bound - lower_bound) * 1e-6)
    theta_at_boundary = (
        theta - lower_bound <= boundary_tolerance
        or upper_bound - theta <= boundary_tolerance
    )
    return PlayerAbilityEstimate(
        model_version=ABILITY_MODEL_VERSION,
        item_count=observation_count,
        achieved_count=achieved_count,
        unachieved_count=unachieved_count,
        is_estimable=not theta_at_boundary,
        reason="theta_at_boundary" if theta_at_boundary else None,
        convergence_status="boundary" if theta_at_boundary else "converged",
        converged=True,
        theta=theta,
        negative_log_likelihood=negative_log_likelihood,
        negative_log_posterior=posterior_loss,
        boundary_reached=theta_at_boundary,
        theta_lower_bound=lower_bound,
        theta_upper_bound=upper_bound,
    )


def _optimization_failure(
    *,
    item_count: int,
    achieved_count: int,
    unachieved_count: int,
    lower_bound: float,
    upper_bound: float,
) -> PlayerAbilityEstimate:
    return PlayerAbilityEstimate(
        model_version=ABILITY_MODEL_VERSION,
        item_count=item_count,
        achieved_count=achieved_count,
        unachieved_count=unachieved_count,
        is_estimable=False,
        reason="optimization_failed",
        convergence_status="failed",
        converged=False,
        theta=None,
        negative_log_likelihood=None,
        negative_log_posterior=None,
        boundary_reached=False,
        theta_lower_bound=lower_bound,
        theta_upper_bound=upper_bound,
    )


def _normalize_observations(
    observations: Iterable[AbilityObservation],
) -> tuple[tuple[float, float, int], ...]:
    if observations is None:
        raise TypeError("observationsは反復可能なAbilityObservationである必要があります。")

    try:
        items = tuple(observations)
    except TypeError as exc:
        raise TypeError(
            "observationsは反復可能なAbilityObservationである必要があります。"
        ) from exc

    normalized: list[tuple[float, float, int]] = []
    for index, observation in enumerate(items):
        if not isinstance(observation, AbilityObservation):
            raise TypeError(f"observations[{index}]はAbilityObservationではありません。")

        x_value = _finite_float(observation.x, f"observations[{index}].x")
        y_value = _finite_float(observation.y, f"observations[{index}].y")
        if y_value <= 0:
            raise ValueError(f"observations[{index}].yは0より大きい必要があります。")

        achieved = observation.achieved
        if isinstance(achieved, (bool, np.bool_)):
            achieved_value = int(achieved)
        elif isinstance(achieved, (int, np.integer)) and achieved in (0, 1):
            achieved_value = int(achieved)
        else:
            raise ValueError(
                f"observations[{index}].achievedはboolまたは0/1である必要があります。"
            )
        normalized.append((x_value, y_value, achieved_value))

    return tuple(normalized)


def _validate_configuration(
    *,
    min_observation_count: int,
    min_class_count: int,
    prior_mean: float,
    prior_standard_deviation: float,
    theta_lower_bound: float,
    theta_upper_bound: float,
) -> tuple[float, float, float, float]:
    if isinstance(min_observation_count, bool) or not isinstance(min_observation_count, int):
        raise TypeError("min_observation_countは整数である必要があります。")
    if min_observation_count < 2:
        raise ValueError("min_observation_countは2以上である必要があります。")
    if isinstance(min_class_count, bool) or not isinstance(min_class_count, int):
        raise TypeError("min_class_countは整数である必要があります。")
    if min_class_count < 1:
        raise ValueError("min_class_countは1以上である必要があります。")

    prior_mean_value = _finite_float(prior_mean, "prior_mean")
    prior_sd_value = _finite_float(prior_standard_deviation, "prior_standard_deviation")
    lower_bound = _finite_float(theta_lower_bound, "theta_lower_bound")
    upper_bound = _finite_float(theta_upper_bound, "theta_upper_bound")
    if prior_sd_value <= 0:
        raise ValueError("prior_standard_deviationは0より大きい必要があります。")
    if upper_bound <= lower_bound:
        raise ValueError("theta境界はlower < upperを満たす必要があります。")
    if not lower_bound <= prior_mean_value <= upper_bound:
        raise ValueError("prior_meanはtheta境界内である必要があります。")
    return prior_mean_value, prior_sd_value, lower_bound, upper_bound


def _finite_float(value: float, field_name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{field_name}は数値である必要があります。")
    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name}は数値である必要があります。") from exc
    if not np.isfinite(numeric_value):
        raise ValueError(f"{field_name}は有限値である必要があります。")
    return numeric_value
