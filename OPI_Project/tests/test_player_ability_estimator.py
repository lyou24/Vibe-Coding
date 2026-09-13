import numpy as np
import pytest

from src.analyzer.player_ability_estimator import (
    ABILITY_MODEL_VERSION,
    AbilityObservation,
    estimate_player_ability,
)


def _synthetic_observations(
    *,
    theta: float,
    sample_count: int,
    seed: int,
) -> list[AbilityObservation]:
    rng = np.random.default_rng(seed)
    x_values = rng.uniform(theta - 500.0, theta + 500.0, sample_count)
    y_values = rng.uniform(35.0, 110.0, sample_count)
    probabilities = 1.0 / (1.0 + np.exp(-(theta - x_values) / y_values))
    responses = rng.random(sample_count) < probabilities
    return [
        AbilityObservation(x=float(x), y=float(y), achieved=bool(achieved))
        for x, y, achieved in zip(x_values, y_values, responses)
    ]


def test_synthetic_observations_recover_player_theta() -> None:
    observations = _synthetic_observations(
        theta=1875.0,
        sample_count=3000,
        seed=20260914,
    )

    result = estimate_player_ability(observations)

    assert result.model_version == ABILITY_MODEL_VERSION
    assert result.is_estimable is True
    assert result.reason is None
    assert result.convergence_status == "converged"
    assert result.converged is True
    assert result.theta == pytest.approx(1875.0, abs=12.0)
    assert result.negative_log_likelihood is not None
    assert result.negative_log_posterior is not None
    assert result.negative_log_posterior >= result.negative_log_likelihood
    assert result.boundary_reached is False


def test_estimation_is_deterministic_and_does_not_mutate_input() -> None:
    observations = _synthetic_observations(theta=1600.0, sample_count=300, seed=7)
    before = list(observations)

    first = estimate_player_ability(observations)
    second = estimate_player_ability(observations)

    assert first == second
    assert observations == before


@pytest.mark.parametrize(
    ("observations", "expected_reason"),
    [
        (
            [AbilityObservation(x=float(index), y=40.0, achieved=index % 2 == 0) for index in range(20)],
            "insufficient_observations",
        ),
        (
            [AbilityObservation(x=float(index), y=40.0, achieved=True) for index in range(60)],
            "single_class",
        ),
        (
            [
                *[AbilityObservation(x=float(index), y=40.0, achieved=True) for index in range(4)],
                *[AbilityObservation(x=float(index), y=40.0, achieved=False) for index in range(4, 60)],
            ],
            "insufficient_class_observations",
        ),
    ],
)
def test_expected_data_shortages_return_machine_readable_result(
    observations: list[AbilityObservation],
    expected_reason: str,
) -> None:
    result = estimate_player_ability(observations)

    assert result.is_estimable is False
    assert result.reason == expected_reason
    assert result.convergence_status == "not_run"
    assert result.converged is False
    assert result.theta is None
    assert result.negative_log_likelihood is None
    assert result.negative_log_posterior is None
    assert result.boundary_reached is False


@pytest.mark.parametrize(
    "observations",
    [
        [AbilityObservation(x=np.nan, y=40.0, achieved=True)],
        [AbilityObservation(x=1500.0, y=np.inf, achieved=False)],
        [AbilityObservation(x=1500.0, y=0.0, achieved=True)],
        [AbilityObservation(x=1500.0, y=40.0, achieved=2)],
    ],
)
def test_invalid_observation_values_are_rejected(
    observations: list[AbilityObservation],
) -> None:
    with pytest.raises(ValueError):
        estimate_player_ability(observations, min_observation_count=2)


def test_invalid_observation_shape_is_rejected() -> None:
    with pytest.raises(TypeError):
        estimate_player_ability([(1500.0, 40.0, True)], min_observation_count=2)  # type: ignore[list-item]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_observation_count": 1},
        {"min_class_count": 0},
        {"prior_standard_deviation": 0.0},
        {"theta_lower_bound": 100.0, "theta_upper_bound": 100.0},
        {"prior_mean": np.nan},
    ],
)
def test_invalid_configuration_is_rejected(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        estimate_player_ability([], **kwargs)


def test_theta_boundary_is_reported_as_unestimable() -> None:
    observations = [
        *[AbilityObservation(x=1000.0, y=40.0, achieved=True) for _ in range(55)],
        *[AbilityObservation(x=1000.0, y=40.0, achieved=False) for _ in range(5)],
    ]

    result = estimate_player_ability(
        observations,
        prior_mean=50.0,
        prior_standard_deviation=1e9,
        theta_lower_bound=0.0,
        theta_upper_bound=100.0,
    )

    assert result.is_estimable is False
    assert result.reason == "theta_at_boundary"
    assert result.convergence_status == "boundary"
    assert result.converged is True
    assert result.theta is not None
    assert result.boundary_reached is True
    assert result.theta == pytest.approx(100.0, abs=1e-3)
