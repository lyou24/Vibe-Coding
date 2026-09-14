import pytest
import numpy as np
import os
import tempfile
from datetime import datetime

from src.database.models import init_db, get_session_maker, Chart, Player, ScoreLog, DifficultyEnum
from src.analyzer.opi_calculator import OPICalculator
from src.recommender.recommender import OPIRecommender

class TestM2ChallengerAdversarial:
    # 1. 全曲達成（全AP）
    def test_massive_all_ap_mle_convergence(self):
        calc = OPICalculator()
        achievements = []
        for i in range(300):
            base_x = 1100.0 + (i * 4.0)
            for rank_offset in [0.0, 150.0, 250.0, 350.0, 470.0]:
                achievements.append({
                    'x': base_x + rank_offset,
                    'y': 40.0 + (i % 20),
                    'achieved': 1
                })

        initial_thetas = [1500.0, 0.0, 500.0, 3000.0, 10000.0, -1000.0]
        results = []
        for init_t in initial_thetas:
            opi = calc.estimate_user_opi(achievements, initial_theta=init_t)
            assert np.isfinite(opi), f'Infinite/NaN OPI with init {init_t}: {opi}'
            assert 2500.0 <= opi <= 3200.0, f'OPI out of range with init {init_t}: {opi}'
            results.append(opi)

        for opi in results:
            assert abs(opi - results[0]) < 0.5, f'Init dependence discrepancy: {opi} vs {results[0]}'

    def test_single_chart_all_ap_mle(self):
        calc = OPICalculator()
        achievements = [
            {'x': 1250.0, 'y': 40.0, 'achieved': 1},
            {'x': 1500.0, 'y': 40.0, 'achieved': 1},
            {'x': 1650.0, 'y': 40.0, 'achieved': 1},
            {'x': 1750.0, 'y': 40.0, 'achieved': 1},
            {'x': 1870.0, 'y': 40.0, 'achieved': 1},
        ]
        opi = calc.estimate_user_opi(achievements, initial_theta=1500.0)
        assert np.isfinite(opi)
        assert 1500.0 < opi < 2000.0

    # 2. 全曲未達成（全0点）
    def test_massive_all_failed_mle_convergence(self):
        calc = OPICalculator()
        achievements = []
        for i in range(300):
            base_x = 1100.0 + (i * 4.0)
            for rank_offset in [0.0, 150.0, 250.0, 350.0, 470.0]:
                achievements.append({
                    'x': base_x + rank_offset,
                    'y': 40.0 + (i % 20),
                    'achieved': 0
                })

        initial_thetas = [1500.0, 0.0, 500.0, 3000.0, 10000.0, -1000.0]
        results = []
        for init_t in initial_thetas:
            opi = calc.estimate_user_opi(achievements, initial_theta=init_t)
            assert np.isfinite(opi), f'Infinite/NaN OPI with init {init_t}: {opi}'
            assert 500.0 <= opi <= 950.0, f'OPI out of range with init {init_t}: {opi}'
            results.append(opi)

        for opi in results:
            assert abs(opi - results[0]) < 0.5, f'Init dependence discrepancy: {opi} vs {results[0]}'

    def test_single_chart_all_failed_mle(self):
        calc = OPICalculator()
        achievements = [
            {'x': 1250.0, 'y': 40.0, 'achieved': 0},
            {'x': 1500.0, 'y': 40.0, 'achieved': 0},
            {'x': 1650.0, 'y': 40.0, 'achieved': 0},
            {'x': 1750.0, 'y': 40.0, 'achieved': 0},
            {'x': 1870.0, 'y': 40.0, 'achieved': 0},
        ]
        opi = calc.estimate_user_opi(achievements, initial_theta=1500.0)
        assert np.isfinite(opi)
        assert 1000.0 < opi < 1300.0

    # 3. リコメンド勝率境界外の厳密除外
    def test_recommender_win_rate_boundary_exclusion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_recom.sqlite')
            engine = init_db(db_path)
            Session = get_session_maker(engine)
            session = Session()

            calc = OPICalculator()
            theta = 2000.0

            def calc_x_for_prob(p: float, y: float = 40.0) -> float:
                return 2000.0 + y * np.log((1.0 - p) / p)

            test_cases = [
                ('chart_20', 0.20, False),
                ('chart_28', 0.28, False),
                ('chart_29', 0.29, False),
                ('chart_299', 0.299, False),
                ('chart_300', 0.300, True),
                ('chart_350', 0.350, True),
                ('chart_500', 0.500, True),
                ('chart_650', 0.650, True),
                ('chart_700', 0.700, True),
                ('chart_701', 0.701, False),
                ('chart_710', 0.710, False),
                ('chart_800', 0.800, False),
            ]

            charts = []
            for cid, target_p, expected_included in test_cases:
                req_x = calc_x_for_prob(target_p, 40.0)
                charts.append(Chart(
                    chart_id=cid,
                    title=f'Title_{cid}',
                    difficulty=DifficultyEnum.MASTER,
                    level='15',
                    chart_constant=15.0,
                    opi_sss_x=req_x,
                    opi_sss_y=40.0
                ))
            session.add_all(charts)

            player = Player(user_id=12345, player_name='BoundaryUser', rating=19.5, total_opi=theta)
            session.add(player)
            session.commit()

            recommender = OPIRecommender(db_path)
            recs = recommender.get_recommendations(user_id=12345, target_rank='SSS', limit=50)

            rec_ids = {r['chart_id'] for r in recs}

            for cid, target_p, expected_included in test_cases:
                if expected_included:
                    assert cid in rec_ids, f'Win rate {target_p*100:.1f}% ({cid}) should be included'
                else:
                    assert cid not in rec_ids, f'Win rate {target_p*100:.1f}% ({cid}) should be excluded'

            for r in recs:
                assert 0.30 <= r['win_rate'] <= 0.70

            session.close()
            engine.dispose()
            recommender.engine.dispose()

    # 4. リコメンドソート順
    def test_recommender_sorting_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_sort.sqlite')
            engine = init_db(db_path)
            Session = get_session_maker(engine)
            session = Session()

            theta = 2000.0
            player = Player(user_id=111, player_name='SortUser', rating=19.5, total_opi=theta)
            session.add(player)

            charts = [
                Chart(chart_id='c1', title='T1', difficulty=DifficultyEnum.MASTER, level='15', chart_constant=15.0, opi_sss_x=2020.0, opi_sss_y=40.0),
                Chart(chart_id='c2', title='T2', difficulty=DifficultyEnum.MASTER, level='15', chart_constant=15.0, opi_sss_x=1995.0, opi_sss_y=40.0),
                Chart(chart_id='c3', title='T3', difficulty=DifficultyEnum.MASTER, level='15', chart_constant=15.0, opi_sss_x=2002.0, opi_sss_y=40.0),
                Chart(chart_id='c4', title='T4', difficulty=DifficultyEnum.MASTER, level='15', chart_constant=15.0, opi_sss_x=1975.0, opi_sss_y=40.0),
                Chart(chart_id='c5', title='T5', difficulty=DifficultyEnum.MASTER, level='15', chart_constant=15.0, opi_sss_x=2000.0, opi_sss_y=40.0),
                Chart(chart_id='c6', title='T6', difficulty=DifficultyEnum.MASTER, level='15', chart_constant=15.0, opi_sss_x=2008.0, opi_sss_y=40.0),
            ]
            session.add_all(charts)
            session.commit()

            recommender = OPIRecommender(db_path)
            recs = recommender.get_recommendations(user_id=111, target_rank='SSS', limit=10)

            assert len(recs) == 6
            expected_order = ['c5', 'c3', 'c2', 'c6', 'c1', 'c4']
            actual_order = [r['chart_id'] for r in recs]
            assert actual_order == expected_order, f'Sorting mismatch: expected {expected_order}, got {actual_order}'

            diffs = [r['opi_diff'] for r in recs]
            assert diffs == sorted(diffs), f'opi_diff not sorted: {diffs}'

            session.close()
            engine.dispose()
            recommender.engine.dispose()

    # 5. 複合フィルタ
    def test_recommender_combined_filters_consistency(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_filter.sqlite')
            engine = init_db(db_path)
            Session = get_session_maker(engine)
            session = Session()

            charts = [
                Chart(chart_id='target_1', title='Target 1', difficulty=DifficultyEnum.MASTER, level='15+', chart_constant=15.7, opi_sss_x=1640.0, opi_abp_x=2010.0, opi_sss_y=40.0),
                Chart(chart_id='target_2', title='Target 2', difficulty=DifficultyEnum.MASTER, level='15+', chart_constant=15.8, opi_sss_x=1650.0, opi_abp_x=2020.0, opi_sss_y=40.0),
                Chart(chart_id='diff_level', title='Diff Level', difficulty=DifficultyEnum.MASTER, level='15', chart_constant=15.7, opi_sss_x=1640.0, opi_abp_x=2010.0, opi_sss_y=40.0),
                Chart(chart_id='diff_const_low', title='Diff Const Low', difficulty=DifficultyEnum.MASTER, level='15+', chart_constant=15.6, opi_sss_x=1640.0, opi_abp_x=2010.0, opi_sss_y=40.0),
                Chart(chart_id='diff_const_high', title='Diff Const High', difficulty=DifficultyEnum.MASTER, level='15+', chart_constant=15.9, opi_sss_x=1640.0, opi_abp_x=2010.0, opi_sss_y=40.0),
                Chart(chart_id='already_ap', title='Already AP', difficulty=DifficultyEnum.MASTER, level='15+', chart_constant=15.7, opi_sss_x=1640.0, opi_abp_x=2010.0, opi_sss_y=40.0),
            ]
            session.add_all(charts)

            player = Player(user_id=222, player_name='FilterUser', rating=19.5, total_opi=2000.0)
            session.add(player)

            session.add(ScoreLog(user_id=222, chart_id='target_2', score=1008000, is_all_break=True, is_full_bell=True, achieve_ss=True, achieve_sss=True, achieve_sssp=True, achieve_s=True, achieve_abp=False))
            session.add(ScoreLog(user_id=222, chart_id='already_ap', score=1010000, is_all_break=True, is_full_bell=True, achieve_ss=True, achieve_sss=True, achieve_sssp=True, achieve_s=True, achieve_abp=True))
            session.commit()

            recommender = OPIRecommender(db_path)

            recs = recommender.get_recommendations(
                user_id=222,
                target_rank='AB+',
                level='15+',
                chart_constant_min=15.7,
                chart_constant_max=15.8,
                current_rank='ABFB止まり'
            )

            rec_ids = [r['chart_id'] for r in recs]
            assert rec_ids == ['target_2'], f'Combined filter mismatch: {rec_ids}'

            recs_unplay = recommender.get_recommendations(
                user_id=222,
                target_rank='AB+',
                level='15+',
                chart_constant_min=15.7,
                chart_constant_max=15.8,
                current_rank='未SS'
            )
            assert [r['chart_id'] for r in recs_unplay] == ['target_1']

            recs_empty = recommender.get_recommendations(
                user_id=222,
                target_rank='AB+',
                chart_constant_min=15.9,
                chart_constant_max=15.7
            )
            assert recs_empty == []

            session.close()
            engine.dispose()
            recommender.engine.dispose()

    # 6. 5段階目標ランクごとの既達成除外
    def test_all_five_target_ranks_already_achieved_exclusion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_exclusion.sqlite')
            engine = init_db(db_path)
            Session = get_session_maker(engine)
            session = Session()

            charts = [
                Chart(chart_id=f'chart_r_{r}', title=f'Rank_{r}', difficulty=DifficultyEnum.MASTER, level='15', chart_constant=15.0,
                      opi_ss_x=1400.0, opi_sss_x=1650.0, opi_sssp_x=1800.0, opi_s_x=1900.0, opi_abp_x=2020.0, opi_sss_y=40.0)
                for r in ['ss', 'sss', 'sssp', 's', 'abp']
            ]
            session.add_all(charts)

            player = Player(user_id=333, player_name='RankUser', rating=19.5, total_opi=2000.0)
            session.add(player)

            session.add(ScoreLog(user_id=333, chart_id='chart_r_ss', score=995000, achieve_ss=True))
            session.add(ScoreLog(user_id=333, chart_id='chart_r_sss', score=1002000, achieve_ss=True, achieve_sss=True))
            session.add(ScoreLog(user_id=333, chart_id='chart_r_sssp', score=1008000, is_all_break=False, achieve_ss=True, achieve_sss=True, achieve_sssp=True))
            session.add(ScoreLog(user_id=333, chart_id='chart_r_abfb', score=1008500, is_all_break=True, is_full_bell=True, achieve_ss=True, achieve_sss=True, achieve_sssp=True, achieve_s=True))
            session.add(ScoreLog(user_id=333, chart_id='chart_r_ap', score=1010000, is_all_break=True, is_full_bell=True, achieve_ss=True, achieve_sss=True, achieve_sssp=True, achieve_s=True, achieve_abp=True))
            session.commit()

            recommender = OPIRecommender(db_path)

            assert recommender.get_recommendations(user_id=333, target_rank='SS', win_rate_min=0.0, win_rate_max=1.0) == []

            recs_sss = recommender.get_recommendations(user_id=333, target_rank='SSS', win_rate_min=0.0, win_rate_max=1.0)
            assert [r['chart_id'] for r in recs_sss] == ['chart_r_ss']

            recs_sssp = recommender.get_recommendations(user_id=333, target_rank='SSS+', win_rate_min=0.0, win_rate_max=1.0)
            assert set(r['chart_id'] for r in recs_sssp) == {'chart_r_ss', 'chart_r_sss'}

            recs_abfb = recommender.get_recommendations(user_id=333, target_rank='S', win_rate_min=0.0, win_rate_max=1.0)
            assert set(r['chart_id'] for r in recs_abfb) == {'chart_r_ss', 'chart_r_sss', 'chart_r_sssp'}

            recs_ap = recommender.get_recommendations(user_id=333, target_rank='AB+', win_rate_min=0.0, win_rate_max=1.0)
            assert set(r['chart_id'] for r in recs_ap) == {'chart_r_ss', 'chart_r_sss', 'chart_r_sssp', 'chart_r_abfb'}

            session.close()
            engine.dispose()
            recommender.engine.dispose()

    # 7. 異常系・堅牢性
    def test_corrupted_achievements_robustness(self):
        calc = OPICalculator()
        corrupted_data = [
            None,
            {},
            {'x': None, 'y': 40.0, 'achieved': 1},
            {'x': 1500.0, 'y': None, 'achieved': 1},
            {'x': 1600.0, 'y': -10.0, 'achieved': 0},
            {'x': 1700.0, 'y': 0.0, 'achieved': 1},
            (1400.0,),
            (1450.0, 40.0, 1),
            {'x': 1550.0, 'y': 40.0, 'achieved': 1},
        ]
        opi = calc.estimate_user_opi(corrupted_data, initial_theta=1500.0)
        assert np.isfinite(opi)
        assert 1400.0 <= opi <= 1700.0

    def test_recommender_unusual_parameters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_unusual.sqlite')
            engine = init_db(db_path)
            Session = get_session_maker(engine)
            session = Session()

            chart = Chart(chart_id='c1', title='T1', difficulty=DifficultyEnum.MASTER, level='15', chart_constant=15.0, opi_sss_x=1500.0, opi_sss_y=40.0)
            session.add(chart)
            player = Player(user_id=999, player_name='Test', rating=18.0, total_opi=1500.0)
            session.add(player)
            session.commit()

            recommender = OPIRecommender(db_path)

            assert recommender.get_recommendations(user_id=999, win_rate_min=0.80, win_rate_max=0.20) == []
            assert recommender.get_recommendations(user_id=999, limit=0) == []
            assert recommender.get_recommendations(user_id=999, limit=-5) == []
            assert recommender.get_recommendations(user_id=888888) == []

            player_no_opi = Player(user_id=777, player_name='NoOPI', rating=18.0, total_opi=None)
            session.add(player_no_opi)
            session.commit()
            assert recommender.get_recommendations(user_id=777) == []
            assert recommender.get_recommendations() == []

            session.close()
            engine.dispose()
            recommender.engine.dispose()
