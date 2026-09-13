import os, sys, tempfile
sys.path.insert(0, os.path.abspath("."))
from bs4 import BeautifulSoup
from src.analyzer.opi_calculator import OPICalculator
from src.database.models import init_db, get_session_maker, Chart, Player, ScoreLog
from src.recommender.recommender import OPIRecommender

test_db = os.path.join(tempfile.gettempdir(), 'test_verify_rec.sqlite')
if os.path.exists(test_db):
    os.remove(test_db)
engine = init_db(test_db)
Session = get_session_maker(engine)
session = Session()

orig_engine = init_db('data/opi_database.sqlite')
OrigSession = get_session_maker(orig_engine)
orig_session = OrigSession()
for c in orig_session.query(Chart).all():
    session.merge(c)
session.commit()

fixture_path = 'tests/fixtures/sample_user_10605.html'
with open(fixture_path, 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

tables = soup.find_all('table')
score_table = tables[5]
score_rows = score_table.find('tbody').find_all('tr')
chart_map = {c.title: c for c in session.query(Chart).all()}

player = Player(user_id=10605, player_name='ＮＥＧＩＮＥ', rating=19.950)
session.add(player)

achievements = []
calc = OPICalculator()

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

    s_log = ScoreLog(
        user_id=10605, chart_id=chart.chart_id, score=score_val,
        is_all_break=is_ab, is_full_bell=is_fb,
        achieve_ss=score_val >= 990000, achieve_sss=score_val >= 1000000,
        achieve_sssp=score_val >= 1007500,
        achieve_abfb=(score_val >= 1007500 and is_ab and is_fb),
        achieve_ap=score_val == 1010000
    )
    session.add(s_log)

    rank_checks = [
        (chart.opi_ss_x, chart.opi_ss_y, s_log.achieve_ss),
        (chart.opi_sss_x, chart.opi_sss_y, s_log.achieve_sss),
        (chart.opi_sssp_x, chart.opi_sssp_y, s_log.achieve_sssp),
        (chart.opi_abfb_x, chart.opi_abfb_y, s_log.achieve_abfb),
        (chart.opi_ap_x, chart.opi_ap_y, s_log.achieve_ap),
    ]
    for xv, yv, ach in rank_checks:
        if xv is not None:
            achievements.append({'x': xv, 'y': yv or 40.0, 'achieved': 1 if ach else 0})

session.commit()
total_opi = calc.estimate_user_opi(achievements, initial_theta=1500.0)
player.total_opi = total_opi
session.commit()

recommender = OPIRecommender(test_db)
recs = recommender.get_recommendations(user_id=10605, target_rank='AP', limit=10)
print(f'User OPI: {total_opi:.2f}')
print(f'AP recommendations count: {len(recs)}')
for r in recs:
    print(f"  {r['title']} ({r['difficulty']} {r['level']} {r['constant']}) target_opi={r['target_opi']:.1f} prob={r['probability']*100:.1f}%")
