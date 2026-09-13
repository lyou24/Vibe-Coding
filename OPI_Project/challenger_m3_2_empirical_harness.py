import os, sys, math, time, json, itertools
import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Tuple

from src.database.models import init_db, get_session_maker, Player, ScoreLog, Chart, DifficultyEnum
from src.analyzer.opi_calculator import OPICalculator
from src.recommender.recommender import OPIRecommender

def run_all_tests():
    print('='*70)
    print('CHALLENGER M3-2 EMPIRICAL ADVERSARIAL VERIFICATION START')
    print('='*70)

    db_path = os.path.join('data', 'opi_database.sqlite')
    engine = init_db(db_path)
    Session = get_session_maker(engine)
    calc = OPICalculator()

    # SECTION 1: ID 10605 安定性 and 初期値感度分析
    print('>>> [SECTION 1] ID 10605 OPI Calculation and Sensitivity Analysis')
    fixture_path = os.path.join('tests', 'fixtures', 'sample_user_10605.html')
    assert os.path.exists(fixture_path), 'Fixture sample_user_10605.html not found!'

    with open(fixture_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    tables = soup.find_all('table')
    assert len(tables) >= 6, f'Expected at least 6 tables, found {len(tables)}'
    score_table = tables[5]
    score_rows = score_table.find('tbody').find_all('tr')

    session = Session()
    charts = session.query(Chart).all()
    chart_map = {c.title: c for c in charts}

    achievements_10605 = []
    parsed_songs = []
    for row in score_rows:
        title_elem = row.find('td', class_='sort_title').find('a')
        title = title_elem.text.strip()
        ts_elem = row.find('td', class_='sort_ts')
        score_val = int(ts_elem.text.strip().replace(',', ''))
        lamp_elem = row.find(class_='badge-lamp')
        bell_elem = row.find(class_='badge-bell')
        is_ab = bool(lamp_elem and 'AB' in lamp_elem.text)
        is_fb = bool(bell_elem and 'FB' in bell_elem.text)

        chart = chart_map.get(title)
        if not chart:
            continue
        parsed_songs.append((title, chart.chart_constant, score_val, is_ab, is_fb))

        ach_ss = score_val >= 990000
        ach_sss = score_val >= 1000000
        ach_sssp = score_val >= 1007500
        ach_abfb = (score_val >= 1007500 and is_ab and is_fb)
        ach_ap = score_val == 1010000

        rank_checks = [
            (chart.opi_ss_x, chart.opi_ss_y, ach_ss),
            (chart.opi_sss_x, chart.opi_sss_y, ach_sss),
            (chart.opi_sssp_x, chart.opi_sssp_y, ach_sssp),
            (chart.opi_abfb_x, chart.opi_abfb_y, ach_abfb),
            (chart.opi_ap_x, chart.opi_ap_y, ach_ap),
        ]
        for x_val, y_val, ach in rank_checks:
            if x_val is not None:
                achievements_10605.append({
                    'x': x_val,
                    'y': y_val or 40.0,
                    'achieved': 1 if ach else 0
                })

    print(f'Parsed {len(parsed_songs)} high-level songs from Table 5 for user 10605.')
    print(f'Constructed {len(achievements_10605)} 2PL IRT response items.')

    base_opi = calc.estimate_user_opi(achievements_10605, initial_theta=1500.0)
    print(f'Base OPI (initial_theta=1500.0): {base_opi:.4f}')
    assert abs(base_opi - 2084.29) < 0.1, f'Base OPI unexpected: {base_opi}'

    test_initials = [
        -100000.0, -10000.0, -1000.0, -500.0, 0.0, 500.0, 1000.0,
        1400.0, 1500.0, 1800.0, 2000.0, 2084.29, 2200.0, 2500.0,
        3000.0, 5000.0, 10000.0, 100000.0
    ]

    sensitivity_results = []
    for init_t in test_initials:
        est = calc.estimate_user_opi(achievements_10605, initial_theta=init_t)
        diff = abs(est - base_opi)
        sensitivity_results.append((init_t, est, diff))
        print(f'    init={init_t:>9.1f} -> est={est:9.4f} (diff={diff:8.6f})')
        assert diff < 1e-2, f'Sensitivity failure: init={init_t}, est={est}, diff={diff}'

    print(f'[PASS] Initial theta sensitivity tested across {len(test_initials)} points [-100000, +100000].')
    print(f'       Max deviation from base OPI: {max(r[2] for r in sensitivity_results):.6e}')

    nan_est = calc.estimate_user_opi(achievements_10605, initial_theta=float('nan'))
    inf_est = calc.estimate_user_opi(achievements_10605, initial_theta=float('inf'))
    ninf_est = calc.estimate_user_opi(achievements_10605, initial_theta=float('-inf'))
    assert abs(nan_est - base_opi) < 1e-2, f'NaN init failed: {nan_est}'
    assert abs(inf_est - base_opi) < 1e-2, f'Inf init failed: {inf_est}'
    assert abs(ninf_est - base_opi) < 1e-2, f'-Inf init failed: {ninf_est}'
    print('[PASS] Non-finite initial_theta gracefully handled.')

    # 凸性の数値検証
    mu_0 = 1500.0
    sigma_0 = 500.0
    def nll_derivatives(theta):
        grad = (theta - mu_0) / (sigma_0 ** 2)
        hess = 1.0 / (sigma_0 ** 2)
        for itm in achievements_10605:
            x = itm['x']
            y = itm['y']
            r = itm['achieved']
            p = calc.irt_probability(theta, x, y)
            grad += (p - r) / y
            hess += (p * (1.0 - p)) / (y ** 2)
        return grad, hess

    grad_at_mle, hess_at_mle = nll_derivatives(base_opi)
    print(f'At MLE ({base_opi:.4f}): Gradient = {grad_at_mle:.8e}, Hessian = {hess_at_mle:.8f}')
    assert abs(grad_at_mle) < 1e-4, f'Gradient at MLE is not zero: {grad_at_mle}'
    assert hess_at_mle > 0, f'Hessian at MLE is not positive: {hess_at_mle}'
    print('[PASS] Strict convexity (Hessian > 0) and first-order optimality (Grad ~ 0) proved.')

    # SECTION 2: ID 10605 DBデータ (397曲) vs Table 5 (11曲) 分析
    print('>>> [SECTION 2] ID 10605 DB Data vs High-Level Subset Analysis')
    db_scores_10605 = session.query(ScoreLog).filter_by(user_id=10605).all()
    print(f'Total score logs in DB for user 10605: {len(db_scores_10605)}')

    if db_scores_10605:
        scores_ach = calc.build_user_achievements(charts, db_scores_10605)
        full_opi = calc.estimate_user_opi(scores_ach, initial_theta=1500.0)
        print(f'Full DB scores OPI for 10605: {full_opi:.4f}')

        scores_val = [s.score or 0 for s in db_scores_10605]
        count_zero = sum(1 for s in scores_val if s == 0)
        count_sub_ss = sum(1 for s in scores_val if 0 < s < 990000)
        count_ss = sum(1 for s in scores_val if 990000 <= s < 1000000)
        count_sss = sum(1 for s in scores_val if 1000000 <= s < 1007500)
        count_sssp = sum(1 for s in scores_val if 1007500 <= s < 1010000)
        count_ap = sum(1 for s in scores_val if s == 1010000)
        print(f'Score distribution for 10605 full DB:')
        print(f'  Zero / Unplayed: {count_zero}')
        print(f'  < SS (Failed):    {count_sub_ss}')
        print(f'  SS:              {count_ss}')
        print(f'  SSS:             {count_sss}')
        print(f'  SSS+:            {count_sssp}')
        print(f'  AP:              {count_ap}')

    # SECTION 3: スコアログの極端なケース
    print('>>> [SECTION 3] Extreme Data Scenarios and Scale Stress Testing')
    empty_opi = calc.estimate_user_opi([], initial_theta=1650.0)
    assert empty_opi == 1650.0, f'Empty log should return initial_theta: {empty_opi}'
    print('[PASS] Empty score log returns initial_theta cleanly.')

    single_ap = [{'x': 2000.0, 'y': 40.0, 'achieved': 1} for _ in range(5)]
    single_ap_opi = calc.estimate_user_opi(single_ap, initial_theta=1500.0)
    assert 1500.0 < single_ap_opi < 2500.0
    print(f'[PASS] Single chart 5-rank all achieved OPI: {single_ap_opi:.2f}')

    # 3.3 単曲全敗 (難度別検証)
    # 高難度(2000)全敗: P(1500)≈0のためベイズ更新量が極小となり事前分布(1500)近傍に留まる
    single_fail_2000 = [{'x': 2000.0, 'y': 40.0, 'achieved': 0} for _ in range(5)]
    opi_fail_2000 = calc.estimate_user_opi(single_fail_2000, initial_theta=1500.0)
    assert 1490.0 <= opi_fail_2000 <= 1510.0

    # 適正難度(1500)全敗: 期待勝率50%の曲で負けたため下方修正される
    single_fail_1500 = [{'x': 1500.0, 'y': 40.0, 'achieved': 0} for _ in range(5)]
    opi_fail_1500 = calc.estimate_user_opi(single_fail_1500, initial_theta=1500.0)
    assert 1200.0 <= opi_fail_1500 < 1500.0

    # 低難度(1000)全敗: 当然勝つべき曲で負けたため大幅に下方修正される
    single_fail_1000 = [{'x': 1000.0, 'y': 40.0, 'achieved': 0} for _ in range(5)]
    opi_fail_1000 = calc.estimate_user_opi(single_fail_1000, initial_theta=1500.0)
    assert 700.0 <= opi_fail_1000 < 1000.0
    print(f'[PASS] Single chart all failed by difficulty: 2000->{opi_fail_2000:.1f}, 1500->{opi_fail_1500:.1f}, 1000->{opi_fail_1000:.1f}')

    massive_ap = [{'x': 1200.0 + (i % 50) * 20.0, 'y': 40.0, 'achieved': 1} for i in range(500)]
    massive_ap_opi = calc.estimate_user_opi(massive_ap, initial_theta=1500.0)
    assert 2200.0 < massive_ap_opi < 4000.0
    assert np.isfinite(massive_ap_opi)
    print(f'[PASS] Massive 500 items all achieved OPI: {massive_ap_opi:.2f}')

    massive_fail = [{'x': 1200.0 + (i % 50) * 20.0, 'y': 40.0, 'achieved': 0} for i in range(500)]
    massive_fail_opi = calc.estimate_user_opi(massive_fail, initial_theta=1500.0)
    assert 0.0 < massive_fail_opi < 1200.0
    assert np.isfinite(massive_fail_opi)
    print(f'[PASS] Massive 500 items all failed OPI: {massive_fail_opi:.2f}')

    t0 = time.time()
    heavy_items = [{'x': 1000.0 + (i % 500) * 2.5, 'y': 35.0 + (i % 20), 'achieved': 1 if (i % 3 != 0) else 0} for i in range(25000)]
    heavy_opi = calc.estimate_user_opi(heavy_items, initial_theta=1500.0)
    t_elapsed = time.time() - t0
    assert np.isfinite(heavy_opi)
    assert t_elapsed < 5.0
    print(f'[PASS] Heavy scale stress test (25,000 items) converged safely in {t_elapsed:.3f}s: OPI = {heavy_opi:.2f}')

    corrupted_items = [
        {'x': None, 'y': 40.0, 'achieved': 1},
        {'x': 1500.0, 'y': None, 'achieved': 1},
        {'x': 1500.0, 'y': -10.0, 'achieved': 1},
        {'x': 1500.0, 'y': 0.0, 'achieved': 0},
        ('invalid_tuple',),
        'totally_corrupted_string',
        None,
        {'x': 1600.0, 'y': 40.0, 'achieved': 1},
        {'x': 1700.0, 'y': 40.0, 'achieved': 0},
    ]
    corrupted_opi = calc.estimate_user_opi(corrupted_items, initial_theta=1500.0)
    assert np.isfinite(corrupted_opi)
    print(f'[PASS] Corrupted items test passed: OPI = {corrupted_opi:.2f}')

    # SECTION 4: リコメンドエンジンの組み合わせストレステスト
    print('>>> [SECTION 4] Recommender Combinatorial Stress Test')
    recommender = OPIRecommender(db_path)

    target_ranks = ['SS', 'SSS', 'SSS+', 'SSS+ABFB', 'AP']
    levels = [None, '13+', '14', '14+', '15', '15+', ['14', '15'], '14, 15', '99']
    constant_ranges = [
        (None, None),
        (13.7, 14.5),
        (14.5, 15.0),
        (15.0, 16.0),
        (15.5, 14.5),
        (-5.0, 25.0)
    ]
    current_ranks = [None, '未SS', 'SS止まり', 'SSS止まり', 'SSS+止まり', 'ABFB止まり', 'AP', 'invalid_rank']
    win_rate_ranges = [
        (0.30, 0.70),
        (0.0, 1.0),
        (0.40, 0.60),
        (0.70, 0.30),
        (-0.5, 1.5)
    ]

    total_tested = 0
    test_grid = list(itertools.product(
        target_ranks,
        levels[:5],
        constant_ranges[:4],
        current_ranks[:5],
        win_rate_ranges[:3],
        [10]
    ))
    edge_grid = [
        ('SSS', '99', None, None, '未SS', 0.30, 0.70, 10),
        ('SSS', None, 15.5, 14.5, None, 0.30, 0.70, 10),
        ('AP', None, None, None, 'invalid_rank', 0.30, 0.70, 10),
        ('SS', None, None, None, None, 0.70, 0.30, 10),
        ('SSS+', None, None, None, None, 0.30, 0.70, 0),
        ('SSS', None, None, None, None, 0.30, 0.70, -1),
    ]

    for tr, lvl, (cmin, cmax), cr, (wmin, wmax), lim in test_grid:
        total_tested += 1
        recs = recommender.get_recommendations(
            player_opi=2084.29,
            user_id=10605,
            target_rank=tr,
            level=lvl,
            chart_constant_min=cmin,
            chart_constant_max=cmax,
            current_rank=cr,
            win_rate_min=wmin,
            win_rate_max=wmax,
            limit=lim
        )

        assert isinstance(recs, list)
        if lim > 0:
            assert len(recs) <= lim

        for r in recs:
            assert r['target_rank'] == calc.normalize_rank(tr)
            if lvl is not None:
                if isinstance(lvl, list):
                    assert r['level'] in lvl
                elif isinstance(lvl, str):
                    allowed = [x.strip() for x in lvl.split(',')]
                    assert r['level'] in allowed
            if cmin is not None:
                assert r['constant'] >= cmin
            if cmax is not None:
                assert r['constant'] <= cmax
            if cr is not None:
                assert recommender._matches_current_rank_filter(r['current_rank'], cr)
            assert wmin <= r['win_rate'] <= wmax
            expected_diff = abs(2084.29 - r['target_opi'])
            assert abs(r['opi_diff'] - expected_diff) < 1e-6

        for i in range(len(recs) - 1):
            assert recs[i]['opi_diff'] <= recs[i+1]['opi_diff'] + 1e-9

    for tr, lvl, cmin, cmax, cr, wmin, wmax, lim in edge_grid:
        total_tested += 1
        recs = recommender.get_recommendations(
            player_opi=2084.29,
            user_id=10605,
            target_rank=tr,
            level=lvl,
            chart_constant_min=cmin,
            chart_constant_max=cmax,
            current_rank=cr,
            win_rate_min=wmin,
            win_rate_max=wmax,
            limit=lim
        )
        assert isinstance(recs, list)
        if cmin is not None and cmax is not None and cmin > cmax:
            assert len(recs) == 0
        if wmin > wmax:
            assert len(recs) == 0
        if lim == 0:
            assert len(recs) == 0

    print(f'[PASS] Recommender passed {total_tested}/{total_tested} stress tests with 100% invariant compliance.')

    # SECTION 5: 要件定義書 2.2〜2.3 計算式・抜け穴実証
    print('>>> [SECTION 5] Formula and Edge Invariants Verification (Spec 2.2-2.3)')
    test_charts = session.query(Chart).limit(10).all()
    c1, c2, c3, c4, c5 = test_charts[:5]

    mock_scores = {
        c1.chart_id: ScoreLog(user_id=99999, chart_id=c1.chart_id, score=990000, is_all_break=False, is_full_bell=False, achieve_ss=True),
        c2.chart_id: ScoreLog(user_id=99999, chart_id=c2.chart_id, score=1000000, is_all_break=False, is_full_bell=False, achieve_ss=True, achieve_sss=True),
        c3.chart_id: ScoreLog(user_id=99999, chart_id=c3.chart_id, score=1007500, is_all_break=True, is_full_bell=False, achieve_ss=True, achieve_sss=True, achieve_sssp=True),
        c4.chart_id: ScoreLog(user_id=99999, chart_id=c4.chart_id, score=1007500, is_all_break=True, is_full_bell=True, achieve_ss=True, achieve_sss=True, achieve_sssp=True, achieve_abfb=True),
        c5.chart_id: ScoreLog(user_id=99999, chart_id=c5.chart_id, score=1010000, is_all_break=True, is_full_bell=True, achieve_ss=True, achieve_sss=True, achieve_sssp=True, achieve_abfb=True, achieve_ap=True),
    }

    assert recommender._is_target_achieved(mock_scores[c1.chart_id], 'SS') is True
    assert recommender._is_target_achieved(mock_scores[c2.chart_id], 'SS') is True
    assert recommender._is_target_achieved(mock_scores[c5.chart_id], 'SS') is True

    assert recommender._is_target_achieved(mock_scores[c1.chart_id], 'SSS') is False
    assert recommender._is_target_achieved(mock_scores[c2.chart_id], 'SSS') is True
    assert recommender._is_target_achieved(mock_scores[c3.chart_id], 'SSS') is True

    assert recommender._is_target_achieved(mock_scores[c2.chart_id], 'SSS+') is False
    assert recommender._is_target_achieved(mock_scores[c3.chart_id], 'SSS+') is True

    assert recommender._is_target_achieved(mock_scores[c3.chart_id], 'SSS+ABFB') is False
    assert recommender._is_target_achieved(mock_scores[c4.chart_id], 'SSS+ABFB') is True
    assert recommender._is_target_achieved(mock_scores[c5.chart_id], 'SSS+ABFB') is True

    assert recommender._is_target_achieved(mock_scores[c4.chart_id], 'AP') is False
    assert recommender._is_target_achieved(mock_scores[c5.chart_id], 'AP') is True
    print('[PASS] Achievement state boundaries verified strictly.')

    p_zero_y = calc.irt_probability(1500.0, 1500.0, 0.0)
    assert p_zero_y == 0.5
    p_neg_y = calc.irt_probability(1500.0, 1500.0, -10.0)
    assert p_neg_y == 0.5
    p_none_y = calc.irt_probability(1500.0, 1500.0, None)
    assert p_none_y == 0.5

    p_extreme_hard = calc.irt_probability(1000.0, 10000.0, 40.0)
    assert p_extreme_hard == 0.0
    p_extreme_easy = calc.irt_probability(10000.0, 1000.0, 40.0)
    assert p_extreme_easy == 1.0
    print('[PASS] IRT probability boundary safety verified.')

    session.close()
    print('='*70)
    print('ALL EMPIRICAL ADVERSARIAL STRESS TESTS COMPLETED WITH 100% SUCCESS!')
    print('='*70)

if __name__ == '__main__':
    run_all_tests()
