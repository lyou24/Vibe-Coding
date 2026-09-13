import os
import pytest
from datetime import datetime

from src.database.models import Chart, Player, ScoreLog, DifficultyEnum
from src.analyzer.opi_calculator import OPICalculator
from src.recommender.recommender import OPIRecommender
from src.visualizer.visualizer import OPIVisualizer

class TestTier3CrossFeatureIntegration:
    """Tier 3: 複数機能横断の結合テスト (Sync → Crawl → Calc → Rec → Viz)"""

    def test_end_to_end_pipeline_integration(self, test_db_path, test_session, seed_charts, seed_population_players, tmp_path):
        """
        一連のデータパイプライン検証:
        1. 譜面マスタが存在
        2. ユーザー登録およびスコアログ投入
        3. 総合OPI算出
        4. リコメンド取得
        5. 母集団分布図の生成
        """
        calc = OPICalculator()

        # 1. ユーザー登録
        user_id = 7777
        player = Player(
            user_id=user_id,
            player_name="IntegrationUser",
            rating=19.200,
            log_updated_at=datetime(2026, 9, 10)
        )
        test_session.add(player)

        # 2. スコア登録（中上級者のプレイログ）
        # Starring Stars (13.7): AP
        # 感情アクセラレイション (14.0): AP
        # Trrricksters!! (14.8): SSS+
        # Op.I (15.1): SSS
        # 光焔 (15.3): SS
        # Recoil (15.7): 980k (未達成)
        # Apollo (15.8): 970k (未達成)
        # 怨撃 (15.9): 950k (未達成)
        play_data = [
            ("mas_starring_stars", 1010000, True, True),
            ("mas_kanjou_acceleration", 1010000, True, True),
            ("mas_trrricksters", 1008000, True, True),
            ("mas_op1_titan", 1002000, False, True),
            ("mas_lateral_arc", 995000, False, False),
            ("mas_recoil", 980000, False, False),
            ("mas_apollo", 970000, False, False),
            ("mas_ongeki", 950000, False, False),
        ]

        achievements = []
        for cid, score_val, ab, fb in play_data:
            chart = next(c for c in seed_charts if c.chart_id == cid)
            s_log = ScoreLog(
                user_id=user_id,
                chart_id=cid,
                score=score_val,
                is_all_break=ab,
                is_full_bell=fb,
                achieve_ss=score_val >= 990000,
                achieve_sss=score_val >= 1000000,
                achieve_sssp=score_val >= 1007500,
                achieve_abfb=(score_val >= 1007500 and ab and fb),
                achieve_ap=score_val == 1010000
            )
            test_session.add(s_log)

            # SSS達成ステータスをOPI計算用リストへ投入
            achievements.append({
                'x': chart.opi_sss_x,
                'y': chart.opi_sss_y or 40.0,
                'achieved': 1 if s_log.achieve_sss else 0
            })

        test_session.commit()

        # 3. 総合OPI算出 & 保存
        est_opi = calc.estimate_user_opi(achievements, initial_theta=1500.0)
        assert 1400.0 < est_opi < 1700.0, f"推定OPIが中上級者レンジ（1400〜1700）内にあること: 実測 {est_opi}"
        player.total_opi = est_opi
        test_session.commit()

        # 4. リコメンド実行
        recommender = OPIRecommender(test_db_path)
        recs = recommender.get_recommendations(user_id=user_id, target_rank="SSS", limit=5)
        assert len(recs) > 0, "リコメンド結果が返却されること"

        # 達成済みの Starring Stars や 感情アクセラレイション は含まれず、未達成曲（光焔やRecoilなど）が適正枠として提案されること
        rec_ids = [r["chart_id"] for r in recs]
        assert "mas_starring_stars" not in rec_ids
        assert "mas_kanjou_acceleration" not in rec_ids

        # 5. 分布図生成
        vis = OPIVisualizer(test_db_path)
        img_out = str(tmp_path / "integration_dist.png")
        vis.create_distribution_plot(img_out)
        assert os.path.exists(img_out)
        assert os.path.getsize(img_out) > 1000

    def test_user_score_progression_increases_opi(self, test_session, seed_charts):
        """プレイヤーがスコアを更新した場合に総合OPIが単調増加すること"""
        calc = OPICalculator()

        # 初期状態: 14.8までしかSSSを取れていない
        initial_achievements = [
            {'x': 1169.8, 'y': 42.0, 'achieved': 1},
            {'x': 1238.5, 'y': 39.2, 'achieved': 1},
            {'x': 1453.7, 'y': 43.1, 'achieved': 1},
            {'x': 1528.3, 'y': 46.2, 'achieved': 0},
            {'x': 1576.1, 'y': 36.4, 'achieved': 0},
            {'x': 1716.9, 'y': 42.1, 'achieved': 0},
        ]
        opi_before = calc.estimate_user_opi(initial_achievements, 1500.0)

        # 成長後: 15.1, 15.3 もSSS達成
        improved_achievements = [
            {'x': 1169.8, 'y': 42.0, 'achieved': 1},
            {'x': 1238.5, 'y': 39.2, 'achieved': 1},
            {'x': 1453.7, 'y': 43.1, 'achieved': 1},
            {'x': 1528.3, 'y': 46.2, 'achieved': 1},  # 更新
            {'x': 1576.1, 'y': 36.4, 'achieved': 1},  # 更新
            {'x': 1716.9, 'y': 42.1, 'achieved': 0},
        ]
        opi_after = calc.estimate_user_opi(improved_achievements, 1500.0)

        assert opi_after > opi_before, f"スキル向上によりOPIが増加すること: {opi_before:.1f} -> {opi_after:.1f}"

    def test_multi_player_skill_ranking_consistency(self):
        """3段階のプレイヤー層（初心者、中級者、最上級者）の間でOPIの序列が正しく維持されること"""
        calc = OPICalculator()

        novice = [
            {'x': 1169.8, 'y': 42.0, 'achieved': 1},
            {'x': 1238.5, 'y': 39.2, 'achieved': 0},
            {'x': 1453.7, 'y': 43.1, 'achieved': 0},
            {'x': 1716.9, 'y': 42.1, 'achieved': 0},
        ]
        intermediate = [
            {'x': 1169.8, 'y': 42.0, 'achieved': 1},
            {'x': 1238.5, 'y': 39.2, 'achieved': 1},
            {'x': 1453.7, 'y': 43.1, 'achieved': 1},
            {'x': 1716.9, 'y': 42.1, 'achieved': 0},
        ]
        expert = [
            {'x': 1169.8, 'y': 42.0, 'achieved': 1},
            {'x': 1238.5, 'y': 39.2, 'achieved': 1},
            {'x': 1453.7, 'y': 43.1, 'achieved': 1},
            {'x': 1716.9, 'y': 42.1, 'achieved': 1},
            {'x': 2086.9, 'y': 42.1, 'achieved': 1},  # 怨撃 AP
        ]

        opi_novice = calc.estimate_user_opi(novice, 1500.0)
        opi_intermediate = calc.estimate_user_opi(intermediate, 1500.0)
        opi_expert = calc.estimate_user_opi(expert, 1500.0)

        assert opi_novice < opi_intermediate < opi_expert
