from typing import Dict


BASE_CHART_CONSTANT = 14.0
BASE_SSS_OPI = 1500.0
OPI_PER_CHART_CONSTANT = 200.0
DEFAULT_INDIVIDUAL_DIFFERENCE = 40.0

RANK_OFFSETS = {
    "SS": -120.0,
    "SSS": 0.0,
    "SSS+": 120.0,
    "SSS+ABFB": 240.0,
    "AP": 360.0,
}


def calculate_fallback_rank_params(
    chart_constant: float,
    target_rank: str,
) -> tuple[float, float]:
    """譜面定数から暫定OPIと個人差度を一貫した式で返す。"""
    base_sss = BASE_SSS_OPI + (
        float(chart_constant) - BASE_CHART_CONSTANT
    ) * OPI_PER_CHART_CONSTANT
    return (
        round(base_sss + RANK_OFFSETS[target_rank], 1),
        DEFAULT_INDIVIDUAL_DIFFERENCE,
    )


def calculate_initial_chart_params(chart_constant: float) -> Dict[str, float]:
    """DB登録用の全ランク暫定パラメータを生成する。"""
    params: Dict[str, float] = {}
    column_names = {
        "SS": "ss",
        "SSS": "sss",
        "SSS+": "sssp",
        "SSS+ABFB": "abfb",
        "AP": "ap",
    }

    for rank, column_name in column_names.items():
        x, y = calculate_fallback_rank_params(chart_constant, rank)
        params[f"opi_{column_name}_x"] = x
        params[f"opi_{column_name}_y"] = y

    return params
