from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from scipy.optimize import minimize, minimize_scalar
import logging
import unicodedata

from src.analyzer.opi_overrides import get_fixed_rank_opi
from src.analyzer.opi_policy import calculate_fallback_rank_params

logger = logging.getLogger(__name__)

TARGET_RANKS = ["S", "SS", "SSS", "SSS+", "AB+"]
MIN_TARGET_CONSTANT = 14.0
MIN_ELIGIBLE_SCORE = 970000


def is_solo_version(title: str) -> bool:
    """表記幅や大文字小文字にかかわらずソロ版を判定する。"""
    normalized = unicodedata.normalize("NFKC", title or "").casefold()
    return "ソロver" in normalized

def normalize_rank(rank: str) -> str:
    """目標ランク文字列を正規化する"""
    if not rank:
        return "SSS"
    r = rank.strip().upper()
    if r in ("S",):
        return "S"
    if r in ("SS",):
        return "SS"
    if r in ("SSS",):
        return "SSS"
    if r in ("SSS+", "SSSP", "SSS_PLUS"):
        return "SSS+"
    if r in ("AB+", "ABP", "AP", "ALL PERFECT", "ALLPERFECT"):
        return "AB+"
    return r

class OPICalculator:
    def __init__(self):
        pass

    @staticmethod
    def normalize_rank(rank: str) -> str:
        return normalize_rank(rank)

    def get_chart_rank_params(self, chart: Any, target_rank: str = "SSS") -> Tuple[Optional[float], float]:
        """
        Chartモデルから指定目標ランクの適正OPI(x)および個人差度(y)を取得する。
        DBのカラムが未設定(None)の場合は、譜面定数および基準アンカーに基づいて補完する。
        - 基準アンカー: 定数14.0 SSS = 1500.0
        初期パラメータと同じ共通ポリシーから補完する。
        """
        norm_rank = normalize_rank(target_rank)
        fixed_x = get_fixed_rank_opi(getattr(chart, "chart_id", None), norm_rank)
        
        # 1. カラムから直接取得
        x = None
        y = None
        if norm_rank == "S":
            x = getattr(chart, "opi_s_x", None)
            y = getattr(chart, "opi_s_y", None)
        elif norm_rank == "SS":
            x = getattr(chart, "opi_ss_x", None)
            y = getattr(chart, "opi_ss_y", None)
        elif norm_rank == "SSS":
            x = getattr(chart, "opi_sss_x", None)
            y = getattr(chart, "opi_sss_y", None)
        elif norm_rank == "SSS+":
            x = getattr(chart, "opi_sssp_x", None)
            y = getattr(chart, "opi_sssp_y", None)
        elif norm_rank == "AB+":
            x = getattr(chart, "opi_abp_x", None)
            y = getattr(chart, "opi_abp_y", None)

        # 実データでは安定推定できない指定譜面のAB+は明示値を優先する。
        if fixed_x is not None:
            x = fixed_x

        # 2. 個人差度 y のフォールバック
        if y is None or y <= 0:
            y = getattr(chart, "opi_sss_y", None) or 40.0
            if y is None or y <= 0:
                y = 40.0

        # 3. 適正OPI x の補完（カラム値が存在しない場合）
        if x is None:
            constant = getattr(chart, "chart_constant", None)
            if constant is None:
                # 譜面定数もない場合は補完不可
                return None, float(y)
            
            if norm_rank in TARGET_RANKS:
                x, fallback_y = calculate_fallback_rank_params(constant, norm_rank)
                if y is None or y <= 0:
                    y = fallback_y
            else:
                x, _ = calculate_fallback_rank_params(constant, "SSS")

        return float(x), float(y)

    def irt_probability(self, theta: float, x: float, y: float) -> float:
        """
        項目応答理論(2母数ロジスティックモデル)による達成確率計算
        P(θ) = 1 / (1 + exp(-(θ - x) / y))
        theta: プレイヤーの総合OPI
        x: 適正OPI（難易度パラメータ）
        y: 個人差度（識別力パラメータの逆数的な扱い。大きいほど傾きが緩やか）
        """
        if y is None or y <= 0:
            y = 40.0
            
        # オーバーフロー対策
        z = -(theta - x) / y
        if z > 100.0:
            return 0.0
        if z < -100.0:
            return 1.0
        return float(1.0 / (1.0 + np.exp(z)))

    def estimate_user_opi(
        self,
        achievements: List[Union[Dict[str, Any], Tuple[float, float, int], List[Any]]],
        initial_theta: float = 1500.0
    ) -> float:
        """
        最尤推定（MLE）を用いてユーザーの総合OPIを推定する。
        achievements:
            - [{'x': 1450.0, 'y': 40.0, 'achieved': 1}, ...] の形式
            - または [(x, y, achieved), ...] の形式
        正規事前分布（μ0=1500.0, σ0=500.0）によるL2正則化付き負の対数尤度を最小化。
        """
        if not achievements:
            return float(initial_theta)

        # データの正規化
        clean_items = []
        for item in achievements:
            if isinstance(item, dict):
                x_val = item.get('x')
                y_val = item.get('y', 40.0)
                r_val = item.get('achieved', 0)
            elif isinstance(item, (tuple, list)) and len(item) >= 3:
                x_val, y_val, r_val = item[0], item[1], item[2]
            else:
                continue

            if x_val is None:
                continue
            y_val = 40.0 if (y_val is None or y_val <= 0) else float(y_val)
            r_val = 1 if r_val else 0
            clean_items.append((float(x_val), float(y_val), r_val))

        if not clean_items:
            return float(initial_theta)

        mu_0 = 1500.0
        sigma_0 = 500.0

        def negative_log_likelihood(theta_val: float) -> float:
            if isinstance(theta_val, (list, np.ndarray)):
                t = float(theta_val[0])
            else:
                t = float(theta_val)

            nll = 0.0
            for x, y, r in clean_items:
                p = self.irt_probability(t, x, y)
                # ログの0割れ・アンダーフロー防止
                p = max(min(p, 1.0 - 1e-12), 1e-12)
                if r == 1:
                    nll -= np.log(p)
                else:
                    nll -= np.log(1.0 - p)

            # L2正則化項 (MAP推定 / 正規事前分布)
            nll += 0.5 * ((t - mu_0) / sigma_0) ** 2
            return float(nll)

        # 最適化の実行 (BFGSで探索し、失敗時は有界スカラー最小化へフォールバック)
        try:
            init_val = float(initial_theta) if np.isfinite(initial_theta) else 1500.0
            result = minimize(negative_log_likelihood, [init_val], method='BFGS')
            if result.success and np.isfinite(result.x[0]):
                return float(result.x[0])
        except Exception as e:
            logger.warning(f"BFGS optimization raised exception: {e}")

        # フォールバック: minimize_scalar (bounded)
        try:
            res_scalar = minimize_scalar(negative_log_likelihood, bounds=(0.0, 4000.0), method='bounded')
            if res_scalar.success and np.isfinite(res_scalar.x):
                return float(res_scalar.x)
        except Exception as e:
            logger.warning(f"Scalar optimization failed: {e}")

        return float(initial_theta)

    def build_user_achievements(
        self,
        charts: List[Any],
        scores: List[Any],
        min_score: Optional[int] = None,
        min_chart_constant: Optional[float] = MIN_TARGET_CONSTANT,
    ) -> List[Dict[str, Any]]:
        """
        譜面マスタとユーザーのスコアログから、5段階全目標ランク（SS, SSS, SSS+, SSS+ABFB, AP）の
        達成成否ベクトルを構築する。

        ``min_score`` を指定すると、その点数未満の譜面を「十分に詰めていない可能性が
        ある譜面」として除外できる。選択バイアスを避けるため、既定値は全プレイを使う
        ``None`` とする。譜面定数は既定で14.0以上のみを対象とする。
        """
        chart_map = {c.chart_id: c for c in charts}
        achievements = []

        for s in scores:
            chart = chart_map.get(s.chart_id)
            if not chart:
                continue

            # ソロver.楽曲はOPI算出対象外
            chart_title = getattr(chart, "title", "")
            if is_solo_version(chart_title):
                continue

            score_val = getattr(s, "score", 0) or 0
            chart_constant = getattr(chart, "chart_constant", None)
            if min_score is not None and score_val < min_score:
                continue
            if (
                min_chart_constant is not None
                and (chart_constant is None or float(chart_constant) < min_chart_constant)
            ):
                continue
            is_ab = getattr(s, "is_all_break", False)
            is_fb = getattr(s, "is_full_bell", False)

            ach_s = getattr(s, "achieve_s", False) or (score_val >= 970000)
            ach_ss = getattr(s, "achieve_ss", False) or (score_val >= 990000)
            ach_sss = getattr(s, "achieve_sss", False) or (score_val >= 1000000)
            ach_sssp = getattr(s, "achieve_sssp", False) or (score_val >= 1007500)
            ach_abp = getattr(s, "achieve_abp", False) or (score_val >= 1010000)

            rank_status = [
                ("S", ach_s),
                ("SS", ach_ss),
                ("SSS", ach_sss),
                ("SSS+", ach_sssp),
                ("AB+", ach_abp),
            ]

            for rank_name, ach in rank_status:
                x, y = self.get_chart_rank_params(chart, rank_name)
                if x is not None:
                    achievements.append({
                        'chart_id': chart.chart_id,
                        'rank': rank_name,
                        'x': x,
                        'y': y,
                        'achieved': 1 if ach else 0
                    })

        return achievements

if __name__ == "__main__":
    calc = OPICalculator()
    sample_data = [
        {'x': 1200.0, 'y': 30.0, 'achieved': 1},
        {'x': 1400.0, 'y': 40.0, 'achieved': 1},
        {'x': 1600.0, 'y': 50.0, 'achieved': 0},
    ]
    est_opi = calc.estimate_user_opi(sample_data, 1500.0)
    print(f"Estimated OPI: {est_opi:.1f}")
