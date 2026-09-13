import numpy as np
import pytest

from src.analyzer.item_parameter_estimator import (
    MODEL_VERSION,
    ItemObservation,
    estimate_item_parameters,
    two_pl_probability,
)


def _synthetic_observations(
    *,
    x: float,
    y: float,
    sample_count: int,
    seed: int,
) -> list[ItemObservation]:
    """既知パラメータの2PLモデルから再現可能な合成観測を作る。"""

    rng = np.random.default_rng(seed)
    theta_values = rng.uniform(x - 6.0 * y, x + 6.0 * y, sample_count)
    probabilities = 1.0 / (1.0 + np.exp(-(theta_values - x) / y))
    responses = rng.random(sample_count) < probabilities
    return [
        ItemObservation(theta=float(theta), achieved=bool(achieved))
        for theta, achieved in zip(theta_values, responses)
    ]


def test_synthetic_observations_recover_x_and_y() -> None:
    observations = _synthetic_observations(
        x=1725.0,
        y=85.0,
        sample_count=5000,
        seed=20260914,
    )

    result = estimate_item_parameters(observations)

    assert result.is_estimable is True
    assert result.reason is None
    assert result.model_version == MODEL_VERSION
    assert result.sample_count == 5000
    assert result.achieved_count + result.unachieved_count == result.sample_count
    assert result.x == pytest.approx(1725.0, abs=12.0)
    assert result.y == pytest.approx(85.0, rel=0.12)
    assert result.negative_log_likelihood is not None
    assert np.isfinite(result.negative_log_likelihood)


def test_estimation_is_deterministic_and_does_not_mutate_input() -> None:
    observations = _synthetic_observations(
        x=1500.0,
        y=120.0,
        sample_count=800,
        seed=7,
    )
    before = list(observations)

    first = estimate_item_parameters(observations)
    second = estimate_item_parameters(observations)

    assert first == second
    assert observations == before


@pytest.mark.parametrize(
    ("observations", "expected_reason"),
    [
        (
            [ItemObservation(theta=float(index), achieved=index % 2 == 0) for index in range(20)],
            "insufficient_samples",
        ),
        (
            [ItemObservation(theta=float(index), achieved=True) for index in range(60)],
            "single_class",
        ),
        (
            [
                *[ItemObservation(theta=float(index), achieved=True) for index in range(4)],
                *[ItemObservation(theta=float(index), achieved=False) for index in range(4, 60)],
            ],
            "insufficient_class_samples",
        ),
        (
            [ItemObservation(theta=1500.0, achieved=index % 2 == 0) for index in range(60)],
            "no_ability_variation",
        ),
    ],
)
def test_expected_data_shortages_return_explicit_unestimable_result(
    observations: list[ItemObservation],
    expected_reason: str,
) -> None:
    result = estimate_item_parameters(observations)

    assert result.is_estimable is False
    assert result.reason == expected_reason
    assert result.model_version == MODEL_VERSION
    assert result.sample_count == len(observations)
    assert result.x is None
    assert result.y is None
    assert result.negative_log_likelihood is None


@pytest.mark.parametrize(
    "observations",
    [
        [ItemObservation(theta=np.nan, achieved=True)],
        [ItemObservation(theta=np.inf, achieved=False)],
        [ItemObservation(theta=1500.0, achieved=2)],
    ],
)
def test_invalid_observation_values_are_rejected(
    observations: list[ItemObservation],
) -> None:
    with pytest.raises(ValueError):
        estimate_item_parameters(observations, min_sample_size=2)


def test_invalid_observation_shape_is_rejected() -> None:
    with pytest.raises(TypeError):
        estimate_item_parameters([(1500.0, True)], min_sample_size=2)  # type: ignore[list-item]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_sample_size": 1},
        {"min_class_count": 0},
        {"min_y": 0.0},
        {"min_y": 20.0, "max_y": 10.0},
    ],
)
def test_invalid_estimation_configuration_is_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        estimate_item_parameters([], **kwargs)


def test_two_pl_probability_has_expected_center_and_order() -> None:
    assert two_pl_probability(theta=1600.0, x=1600.0, y=50.0) == pytest.approx(0.5)
    assert two_pl_probability(theta=1500.0, x=1600.0, y=50.0) < 0.5
    assert two_pl_probability(theta=1700.0, x=1600.0, y=50.0) > 0.5
    assert two_pl_probability(theta=-1e9, x=1600.0, y=50.0) == pytest.approx(0.0)
    assert two_pl_probability(theta=1e9, x=1600.0, y=50.0) == pytest.approx(1.0)


def test_two_pl_probability_rejects_non_positive_y() -> None:
    with pytest.raises(ValueError):
        two_pl_probability(theta=1500.0, x=1600.0, y=0.0)
