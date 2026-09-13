import os
from typing import Any, Dict, List, Optional, Union
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pandas as pd
import logging
from src.database.models import Chart, Player, ScoreLog
from src.analyzer.opi_calculator import OPICalculator

logger = logging.getLogger(__name__)

class OPIRecommender:
    def __init__(self, db_path: str):
        self.engine = create_engine(f'sqlite:///{db_path}')
        self.Session = sessionmaker(bind=self.engine)
        self.calc = OPICalculator()

    def _determine_current_rank(self, score_log: Optional[ScoreLog]) -> tuple[str, str]:
        """
        スコアログから現在の達成状況カテゴリと表示用文字列を判定する。
        戻り値: (カテゴリ, 表示文字列)
        カテゴリ例: "未SS", "SS止まり", "SSS止まり", "SSS+止まり", "ABFB止まり", "AP"
        """
        if not score_log:
            return "未SS", "未プレイ"

        score = score_log.score or 0
        is_ab = getattr(score_log, "is_all_break", False)
        is_fb = getattr(score_log, "is_full_bell", False)

        if score >= 1010000 or getattr(score_log, "achieve_ap", False):
            return "AP", f"AP ({score:,})"
        if (score >= 1007500 and is_ab and is_fb) or getattr(score_log, "achieve_abfb", False):
            return "ABFB止まり", f"SSS+ABFB ({score:,})"
        if score >= 1007500 or getattr(score_log, "achieve_sssp", False):
            return "SSS+止まり", f"SSS+ ({score:,})"
        if score >= 1000000 or getattr(score_log, "achieve_sss", False):
            return "SSS止まり", f"SSS ({score:,})"
        if score >= 990000 or getattr(score_log, "achieve_ss", False):
            return "SS止まり", f"SS ({score:,})"
        
        return "未SS", f"未SS ({score:,})"

    def _is_target_achieved(self, score_log: Optional[ScoreLog], norm_target_rank: str) -> bool:
        """指定した目標ランクを既に達成しているかどうか判定する"""
        if not score_log:
            return False

        score = score_log.score or 0
        is_ab = getattr(score_log, "is_all_break", False)
        is_fb = getattr(score_log, "is_full_bell", False)

        if norm_target_rank == "SS":
            return bool(getattr(score_log, "achieve_ss", False) or score >= 990000)
        elif norm_target_rank == "SSS":
            return bool(getattr(score_log, "achieve_sss", False) or score >= 1000000)
        elif norm_target_rank == "SSS+":
            return bool(getattr(score_log, "achieve_sssp", False) or score >= 1007500)
        elif norm_target_rank == "SSS+ABFB":
            return bool(getattr(score_log, "achieve_abfb", False) or (score >= 1007500 and is_ab and is_fb))
        elif norm_target_rank == "AP":
            return bool(getattr(score_log, "achieve_ap", False) or score >= 1010000)

        return False

    def _matches_current_rank_filter(self, current_cat: str, filter_rank: Optional[str]) -> bool:
        """current_rank フィルターにマッチするか判定する"""
        if not filter_rank:
            return True

        f = filter_rank.strip()
        # 表記ゆれの吸収
        if f in ("未SS", "未達成", "未プレイ", "None"):
            return current_cat == "未SS"
        if f in ("SS止まり", "SS"):
            return current_cat == "SS止まり"
        if f in ("SSS止まり", "SSS"):
            return current_cat == "SSS止まり"
        if f in ("SSS+止まり", "SSS+", "SSSP", "SSSP止まり"):
            return current_cat == "SSS+止まり"
        if f in ("ABFB止まり", "SSS+ABFB", "ABFB", "SSSP_ABFB"):
            return current_cat == "ABFB止まり"
        if f in ("AP", "理論値"):
            return current_cat == "AP"

        return f.lower() in current_cat.lower()

    def get_recommendations(
        self,
        user_id: Optional[int] = None,
        target_rank: str = "SSS",
        level: Optional[Union[str, List[str]]] = None,
        chart_constant_min: Optional[float] = None,
        chart_constant_max: Optional[float] = None,
        current_rank: Optional[str] = None,
        win_rate_min: float = 0.30,
        win_rate_max: float = 0.70,
        limit: int = 10,
        player_opi: Optional[float] = None,
        constant_min: Optional[float] = None,
        constant_max: Optional[float] = None,
        current_rank_filter: Optional[str] = None,
        user_scores: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        指定したユーザーに対する適正挑戦枠（勝率30〜70%）の楽曲をリコメンドする。
        - target_rank: "SS", "SSS", "SSS+", "SSS+ABFB", "AP" に対応
        - level: "13+", "14", "14+", "15", "15+" 等
        - chart_constant_min / chart_constant_max: 譜面定数範囲
        - current_rank: 現在の達成状況（"未SS", "SS止まり", "SSS止まり", "SSS+止まり" 等）
        - win_rate_min / win_rate_max: 勝率範囲（デフォルト 0.30 〜 0.70）
        - ソート順: |theta - x| 昇順
        """
        # エイリアス引数の正規化
        c_min = chart_constant_min if chart_constant_min is not None else constant_min
        c_max = chart_constant_max if chart_constant_max is not None else constant_max
        c_rank_filter = current_rank if current_rank is not None else current_rank_filter
        norm_target_rank = self.calc.normalize_rank(target_rank)

        session = self.Session()
        try:
            # ユーザーの総合OPIの決定
            theta = None
            if player_opi is not None:
                theta = float(player_opi)
            elif user_id is not None:
                player = session.query(Player).filter_by(user_id=user_id).first()
                if not player or player.total_opi is None:
                    logger.warning(f"Player {user_id} not found or OPI not calculated.")
                    return []
                theta = float(player.total_opi)
            else:
                return []

            # ユーザーのスコアログを取得
            scores_map = {}
            if user_id is not None:
                scores = session.query(ScoreLog).filter_by(user_id=user_id).all()
                for s in scores:
                    scores_map[s.chart_id] = s
            elif user_scores:
                scores_map = user_scores

            # 全譜面をクエリ
            query = session.query(Chart)
            charts = query.all()
            recommendations = []

            for chart in charts:
                score_log = scores_map.get(chart.chart_id)

                # 1. 達成済み判定（目標ランクを既に達成している場合は除外）
                if self._is_target_achieved(score_log, norm_target_rank):
                    continue

                # 2. level フィルター
                if level is not None:
                    if isinstance(level, (list, tuple, set)):
                        if chart.level not in level:
                            continue
                    elif isinstance(level, str):
                        allowed_levels = [l.strip() for l in level.split(",") if l.strip()]
                        if allowed_levels and chart.level not in allowed_levels:
                            continue

                # 3. 譜面定数フィルター
                if c_min is not None and chart.chart_constant < c_min:
                    continue
                if c_max is not None and chart.chart_constant > c_max:
                    continue

                # 4. current_rank フィルター
                current_cat, current_display = self._determine_current_rank(score_log)
                if not self._matches_current_rank_filter(current_cat, c_rank_filter):
                    continue

                # 5. 対象ランクのOPIパラメータを取得（動的切替・補完）
                x, y = self.calc.get_chart_rank_params(chart, norm_target_rank)
                if x is None:
                    continue

                # 6. 達成確率（勝率）の計算
                prob = self.calc.irt_probability(theta, x, y)

                # 7. 勝率範囲判定
                if win_rate_min <= prob <= win_rate_max:
                    opi_diff = abs(theta - x)
                    diff_str = chart.difficulty.value if hasattr(chart.difficulty, 'value') else str(chart.difficulty)
                    recommendations.append({
                        "chart_id": chart.chart_id,
                        "title": chart.title,
                        "difficulty": diff_str,
                        "level": chart.level,
                        "constant": chart.chart_constant,
                        "chart_constant": chart.chart_constant,
                        "target_rank": norm_target_rank,
                        "target_opi": x,
                        "opi_val": x,
                        "individual_y": y,
                        "probability": prob,
                        "win_rate": prob,
                        "current_status": current_display,
                        "current_rank": current_cat,
                        "opi_diff": opi_diff
                    })

            # 8. ソート: 自身のOPIと目標OPIの絶対値差 (|theta - x|) 昇順
            recommendations.sort(key=lambda item: item['opi_diff'])

            return recommendations[:limit]

        finally:
            session.close()

if __name__ == "__main__":
    db_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "opi_database.sqlite")
    recommender = OPIRecommender(db_file)
    recs = recommender.get_recommendations(user_id=1)
    for i, r in enumerate(recs, 1):
        print(f"{i}. {r['title']} (Lv.{r['level']} / {r['constant']}) - Target OPI: {r['target_opi']:.1f} (Win Rate: {r['probability']*100:.1f}%)")

