from types import SimpleNamespace

from src.analyzer.opi_calculator import OPICalculator
from src.analyzer.opi_policy import calculate_initial_chart_params
from src.database.models import DifficultyEnum, ScoreLog
from src.recommender.recommender import OPIRecommender


def make_chart(chart_id: str, constant: float):
    return SimpleNamespace(
        chart_id=chart_id,
        chart_constant=constant,
        opi_ss_x=None,
        opi_ss_y=None,
        opi_sss_x=None,
        opi_sss_y=None,
        opi_sssp_x=None,
        opi_sssp_y=None,
        opi_abfb_x=None,
        opi_abfb_y=None,
        opi_ap_x=None,
        opi_ap_y=None,
    )


def test_seed_params_and_calculator_fallback_are_identical():
    calc = OPICalculator()
    chart = make_chart("chart_15_7", 15.7)
    generated = calculate_initial_chart_params(15.7)
    column_names = {
        "SS": "ss",
        "SSS": "sss",
        "SSS+": "sssp",
        "SSS+ABFB": "abfb",
        "AP": "ap",
    }

    for rank, column_name in column_names.items():
        x, y = calc.get_chart_rank_params(chart, rank)
        assert x == generated[f"opi_{column_name}_x"]
        assert y == generated[f"opi_{column_name}_y"]


def test_achievement_filters_are_explicit_at_score_and_constant_boundaries():
    calc = OPICalculator()
    charts = [make_chart("below_constant", 13.9), make_chart("target", 14.0)]
    scores = [
        ScoreLog(chart_id="below_constant", score=1000000),
        ScoreLog(chart_id="target", score=969999),
    ]

    standard = calc.build_user_achievements(charts, scores, min_score=None)
    qualified = calc.build_user_achievements(charts, scores, min_score=970000)
    assert len(standard) == 5
    assert qualified == []

    scores[1].score = 970000
    qualified_at_boundary = calc.build_user_achievements(
        charts,
        scores,
        min_score=970000,
    )
    assert len(qualified_at_boundary) == 5


def test_current_rank_filter_accepts_multiple_values(tmp_path):
    recommender = OPIRecommender(str(tmp_path / "empty.sqlite"))
    assert recommender._matches_current_rank_filter("SS止まり", ["SS", "SSS"])
    assert not recommender._matches_current_rank_filter("未SS", ["SS", "SSS"])
