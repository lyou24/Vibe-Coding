"""譜面・目標ランク単位の2PLパラメータを検証用に推定する。

このモジュールはDBやWebへアクセスしない。将来のバッチ処理では、呼び出し側が
プレイヤー実力値と達成成否を収集し、本モジュールへ値として渡すことを想定する。
"""

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
from scipy.optimize import minimize


MODEL_VERSION = "2pl-item-mle-v1"
DEFAULT_MIN_SAMPLE_SIZE = 50
DEFAULT_MIN_CLASS_COUNT = 5


@dataclass(frozen=True)
class ItemObservation:
    """1人のプレイヤーについての実力値と目標ランク達成成否。"""

    theta: float
    achieved: bool


@dataclass(frozen=True)
class ItemParameterEstimate:
    """2PL推定結果。推定不能時は ``x`` と ``y`` が ``None`` になる。"""

    model_version: str
    sample_count: int
    achieved_count: int
    unachieved_count: int
    is_estimable: bool
    reason: Optional[str]
    x: Optional[float]
    y: Optional[float]
    negative_log_likelihood: Optional[float]


def two_pl_probability(theta: float, x: float, y: float) -> float:
    """2PLモデルによる達成確率を、オーバーフローせずに返す。"""

    theta_value = _finite_float(theta, "theta")
    x_value = _finite_float(x, "x")
    y_value = _finite_float(y, "y")
    if y_value <= 0:
        raise ValueError("yは0より大きい値である必要があります。")

    z = (theta_value - x_value) / y_value
    if z >= 0:
        return float(1.0 / (1.0 + np.exp(-z)))

    exp_z = np.exp(z)
    return float(exp_z / (1.0 + exp_z))


def estimate_item_parameters(
    observations: Iterable[ItemObservation],
    *,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
    min_class_count: int = DEFAULT_MIN_CLASS_COUNT,
    min_y: float = 1.0,
    max_y: float = 2000.0,
) -> ItemParameterEstimate:
    """既知のプレイヤー実力値から譜面の適正OPI ``x`` と個人差度 ``y`` を推定する。

    期待される観測は、同一譜面・同一目標ランクに対する横断データである。
    最小サンプル数、両方の成否クラス、実力値の分散が不足する場合は、例外ではなく
    ``is_estimable=False`` と機械判定可能な ``reason`` を返す。非数値など入力自体が
    不正な場合は ``TypeError`` または ``ValueError`` を送出する。
    """

    _validate_configuration(min_sample_size, min_class_count, min_y, max_y)
    normalized = _normalize_observations(observations)

    sample_count = len(normalized)
    achieved_count = sum(achieved for _, achieved in normalized)
    unachieved_count = sample_count - achieved_count

    def unable(reason: str) -> ItemParameterEstimate:
        return ItemParameterEstimate(
            model_version=MODEL_VERSION,
            sample_count=sample_count,
            achieved_count=achieved_count,
            unachieved_count=unachieved_count,
            is_estimable=False,
            reason=reason,
            x=None,
            y=None,
            negative_log_likelihood=None,
        )

    if sample_count < min_sample_size:
        return unable("insufficient_samples")
    if achieved_count == 0 or unachieved_count == 0:
        return unable("single_class")
    if min(achieved_count, unachieved_count) < min_class_count:
        return unable("insufficient_class_samples")

    theta_values = np.asarray([theta for theta, _ in normalized], dtype=float)
    responses = np.asarray([achieved for _, achieved in normalized], dtype=float)
    theta_span = float(np.ptp(theta_values))
    if theta_span <= np.finfo(float).eps:
        return unable("no_ability_variation")

    # yを対数空間で探索し、最適化中も必ず正値になるようにする。
    theta_std = float(np.std(theta_values))
    initial_x = float(np.median(theta_values))
    initial_y = float(np.clip(theta_std * 0.5, min_y, max_y))
    x_margin = max(theta_span, 100.0)
    x_bounds = (
        float(np.min(theta_values) - x_margin),
        float(np.max(theta_values) + x_margin),
    )

    def objective(parameters: np.ndarray) -> float:
        x_value = float(parameters[0])
        y_value = float(np.exp(parameters[1]))
        logits = (theta_values - x_value) / y_value
        # log(1 + exp(logit)) - response * logit は安定な二値交差エントロピー。
        return float(np.sum(np.logaddexp(0.0, logits) - responses * logits))

    result = minimize(
        objective,
        x0=np.asarray([initial_x, np.log(initial_y)], dtype=float),
        method="L-BFGS-B",
        bounds=[x_bounds, (float(np.log(min_y)), float(np.log(max_y)))],
    )

    if not result.success or len(result.x) != 2 or not np.all(np.isfinite(result.x)):
        return unable("optimization_failed")

    estimated_x = float(result.x[0])
    estimated_y = float(np.exp(result.x[1]))
    nll = float(result.fun)
    if not np.isfinite(estimated_x) or not np.isfinite(estimated_y) or not np.isfinite(nll):
        return unable("optimization_failed")

    return ItemParameterEstimate(
        model_version=MODEL_VERSION,
        sample_count=sample_count,
        achieved_count=achieved_count,
        unachieved_count=unachieved_count,
        is_estimable=True,
        reason=None,
        x=estimated_x,
        y=estimated_y,
        negative_log_likelihood=nll,
    )


def _normalize_observations(
    observations: Iterable[ItemObservation],
) -> tuple[tuple[float, int], ...]:
    if observations is None:
        raise TypeError("observationsは反復可能なItemObservationである必要があります。")

    try:
        items = tuple(observations)
    except TypeError as exc:
        raise TypeError(
            "observationsは反復可能なItemObservationである必要があります。"
        ) from exc

    normalized: list[tuple[float, int]] = []
    for index, observation in enumerate(items):
        if not isinstance(observation, ItemObservation):
            raise TypeError(f"observations[{index}]はItemObservationではありません。")

        theta_value = _finite_float(observation.theta, f"observations[{index}].theta")
        achieved_value = observation.achieved
        if isinstance(achieved_value, (bool, np.bool_)):
            normalized_achieved = int(achieved_value)
        elif isinstance(achieved_value, (int, np.integer)) and achieved_value in (0, 1):
            normalized_achieved = int(achieved_value)
        else:
            raise ValueError(
                f"observations[{index}].achievedはboolまたは0/1である必要があります。"
            )
        normalized.append((theta_value, normalized_achieved))

    return tuple(normalized)


def _validate_configuration(
    min_sample_size: int,
    min_class_count: int,
    min_y: float,
    max_y: float,
) -> None:
    if isinstance(min_sample_size, bool) or not isinstance(min_sample_size, int):
        raise TypeError("min_sample_sizeは整数である必要があります。")
    if min_sample_size < 2:
        raise ValueError("min_sample_sizeは2以上である必要があります。")
    if isinstance(min_class_count, bool) or not isinstance(min_class_count, int):
        raise TypeError("min_class_countは整数である必要があります。")
    if min_class_count < 1:
        raise ValueError("min_class_countは1以上である必要があります。")

    min_y_value = _finite_float(min_y, "min_y")
    max_y_value = _finite_float(max_y, "max_y")
    if min_y_value <= 0 or max_y_value <= min_y_value:
        raise ValueError("yの探索範囲は0 < min_y < max_yを満たす必要があります。")


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
