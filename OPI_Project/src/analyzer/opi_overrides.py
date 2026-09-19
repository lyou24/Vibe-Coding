"""実データで安定推定できない譜面に対する明示的なOPI定義。"""

from __future__ import annotations


ABP_FIXED_OPI = 2500.0
ABP_FIXED_CHART_IDS = frozenset(
    {
        "808_master",
        "805_master",
        "804_lunatic",
        "1133_master",
        "1152_master",
        "1182_master",
        "574_master",
        "1062_master",
        "573_master",
        "870_master",
        "797_master",
        "1088_master",
    }
)


def get_fixed_rank_opi(chart_id: str | None, target_rank: str) -> float | None:
    """指定譜面・目標ランクに固定OPIがあれば返す。"""
    if target_rank == "AB+" and str(chart_id or "") in ABP_FIXED_CHART_IDS:
        return ABP_FIXED_OPI
    return None
