import pytest
import os
import sys
from datetime import datetime
import numpy as np

# プロジェクトルートを sys.path に追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.database.models import Base, Chart, Player, ScoreLog, DifficultyEnum, init_db, get_session_maker
from src.analyzer.opi_calculator import OPICalculator

@pytest.fixture
def test_db_path(tmp_path):
    """テスト専用のSQLiteデータベースファイルパス（テーブル初期化済み）"""
    db_file = str(tmp_path / "test_opi.sqlite")
    init_db(db_file)
    return db_file

@pytest.fixture
def test_engine(test_db_path):
    """テスト用DBエンジン"""
    return init_db(test_db_path)

@pytest.fixture
def test_session(test_engine):
    """テスト用DBセッション（トランザクション終了時に破棄）"""
    Session = get_session_maker(test_engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture
def seed_charts(test_session):
    """要件定義書 §3.4 に記載された代表譜面マスタを登録"""
    charts = [
        Chart(
            chart_id="mas_ongeki",
            title="怨撃",
            difficulty=DifficultyEnum.MASTER,
            level="15+",
            chart_constant=15.9,
            opi_ss_x=1350.0, opi_ss_y=42.1,
            opi_sss_x=1716.9, opi_sss_y=42.1,
            opi_sssp_x=1850.0, opi_sssp_y=42.1,
            opi_s_x=1950.0, opi_s_y=42.1,
            opi_abp_x=2086.9, opi_abp_y=42.1
        ),
        Chart(
            chart_id="mas_apollo",
            title="Apollo",
            difficulty=DifficultyEnum.MASTER,
            level="15+",
            chart_constant=15.8,
            opi_ss_x=1340.0, opi_ss_y=55.9,
            opi_sss_x=1700.7, opi_sss_y=55.9,
            opi_sssp_x=1830.0, opi_sssp_y=55.9,
            opi_s_x=1930.0, opi_s_y=55.9,
            opi_abp_x=2070.7, opi_abp_y=55.9
        ),
        Chart(
            chart_id="mas_recoil",
            title="Recoil",
            difficulty=DifficultyEnum.MASTER,
            level="15+",
            chart_constant=15.7,
            opi_ss_x=1330.0, opi_ss_y=55.3,
            opi_sss_x=1697.1, opi_sss_y=55.3,
            opi_sssp_x=1820.0, opi_sssp_y=55.3,
            opi_s_x=1920.0, opi_s_y=55.3,
            opi_abp_x=2060.0, opi_abp_y=55.3
        ),
        Chart(
            chart_id="mas_lateral_arc",
            title="光焔のラテラルアーク",
            difficulty=DifficultyEnum.MASTER,
            level="15",
            chart_constant=15.3,
            opi_ss_x=1260.0, opi_ss_y=36.4,
            opi_sss_x=1576.1, opi_sss_y=36.4,
            opi_sssp_x=1710.0, opi_sssp_y=36.4,
            opi_s_x=1810.0, opi_s_y=36.4,
            opi_abp_x=1946.1, opi_abp_y=36.4
        ),
        Chart(
            chart_id="mas_op1_titan",
            title="Op.I《fear-TITΛN-》",
            difficulty=DifficultyEnum.MASTER,
            level="15",
            chart_constant=15.1,
            opi_ss_x=1220.0, opi_ss_y=46.2,
            opi_sss_x=1528.3, opi_sss_y=46.2,
            opi_sssp_x=1660.0, opi_sssp_y=46.2,
            opi_s_x=1760.0, opi_s_y=46.2,
            opi_abp_x=1890.0, opi_abp_y=46.2
        ),
        Chart(
            chart_id="mas_trrricksters",
            title="Trrricksters!!",
            difficulty=DifficultyEnum.MASTER,
            level="14+",
            chart_constant=14.8,
            opi_ss_x=1150.0, opi_ss_y=43.1,
            opi_sss_x=1453.7, opi_sss_y=43.1,
            opi_sssp_x=1580.0, opi_sssp_y=43.1,
            opi_s_x=1680.0, opi_s_y=43.1,
            opi_abp_x=1823.7, opi_abp_y=43.1
        ),
        Chart(
            chart_id="mas_kanjou_acceleration",
            title="感情アクセラレイション",
            difficulty=DifficultyEnum.MASTER,
            level="14",
            chart_constant=14.0,
            opi_ss_x=1020.0, opi_ss_y=39.2,
            opi_sss_x=1238.5, opi_sss_y=39.2,
            opi_sssp_x=1360.0, opi_sssp_y=39.2,
            opi_s_x=1460.0, opi_s_y=39.2,
            opi_abp_x=1608.5, opi_abp_y=39.2
        ),
        Chart(
            chart_id="mas_starring_stars",
            title="Starring Stars",
            difficulty=DifficultyEnum.MASTER,
            level="13+",
            chart_constant=13.7,
            opi_ss_x=980.0, opi_ss_y=42.0,
            opi_sss_x=1169.8, opi_sss_y=42.0,
            opi_sssp_x=1290.0, opi_sssp_y=42.0,
            opi_s_x=1390.0, opi_s_y=42.0,
            opi_abp_x=1539.8, opi_abp_y=42.0
        ),
        Chart(
            chart_id="mas_titania",
            title="Titania",
            difficulty=DifficultyEnum.MASTER,
            level="15",
            chart_constant=15.4,
            opi_ss_x=1280.0, opi_ss_y=40.0,
            opi_sss_x=1610.0, opi_sss_y=40.0,
            opi_sssp_x=1750.0, opi_sssp_y=40.0,
            opi_s_x=1850.0, opi_s_y=40.0,
            opi_abp_x=1980.0, opi_abp_y=40.0
        ),
        Chart(
            chart_id="mas_marble_blue",
            title="MarbleBlue",
            difficulty=DifficultyEnum.MASTER,
            level="15",
            chart_constant=15.3,
            opi_ss_x=1260.0, opi_ss_y=38.0,
            opi_sss_x=1580.0, opi_sss_y=38.0,
            opi_sssp_x=1720.0, opi_sssp_y=38.0,
            opi_s_x=1820.0, opi_s_y=38.0,
            opi_abp_x=1950.0, opi_abp_y=38.0
        ),
        Chart(
            chart_id="mas_viyellas_tears",
            title="Viyella's Tears",
            difficulty=DifficultyEnum.MASTER,
            level="15",
            chart_constant=15.0,
            opi_ss_x=1200.0, opi_ss_y=42.0,
            opi_sss_x=1510.0, opi_sss_y=42.0,
            opi_sssp_x=1650.0, opi_sssp_y=42.0,
            opi_s_x=1750.0, opi_s_y=42.0,
            opi_abp_x=1880.0, opi_abp_y=42.0
        ),
        Chart(
            chart_id="mas_stargazing",
            title="Stargazing Dreamer",
            difficulty=DifficultyEnum.MASTER,
            level="14+",
            chart_constant=14.9,
            opi_ss_x=1170.0, opi_ss_y=43.0,
            opi_sss_x=1470.0, opi_sss_y=43.0,
            opi_sssp_x=1600.0, opi_sssp_y=43.0,
            opi_s_x=1700.0, opi_s_y=43.0,
            opi_abp_x=1840.0, opi_abp_y=43.0
        ),
        Chart(
            chart_id="mas_meteorsnow",
            title="MeteorSnow",
            difficulty=DifficultyEnum.MASTER,
            level="14+",
            chart_constant=14.7,
            opi_ss_x=1130.0, opi_ss_y=41.0,
            opi_sss_x=1430.0, opi_sss_y=41.0,
            opi_sssp_x=1560.0, opi_sssp_y=41.0,
            opi_s_x=1660.0, opi_s_y=41.0,
            opi_abp_x=1800.0, opi_abp_y=41.0
        ),
        Chart(
            chart_id="mas_dftm",
            title="Don't Fight The Music",
            difficulty=DifficultyEnum.MASTER,
            level="15",
            chart_constant=15.6,
            opi_ss_x=1300.0, opi_ss_y=45.0,
            opi_sss_x=1680.0, opi_sss_y=45.0,
            opi_sssp_x=1800.0, opi_sssp_y=45.0,
            opi_s_x=1900.0, opi_s_y=45.0,
            opi_abp_x=2030.0, opi_abp_y=45.0
        ),
    ]
    for c in charts:
        test_session.add(c)
    test_session.commit()
    return charts

@pytest.fixture
def mock_10605_html():
    """
    OngekiScoreLog の ID 10605 実DOM構造を再現したモックHTML。
    - Table 0: プレイヤー情報（プレイヤーネーム: ＮＥＧＩＮＥ, レーティング: 19.950, 最終更新: 2026-09-10）
    - Table 5: 楽曲スコアテーブル（実在する曲のスコア）
    """
    html = """<!DOCTYPE html>
<html>
<head><title>OngekiScoreLog - ＮＥＧＩＮＥ</title></head>
<body>
  <!-- Table 0: ユーザー情報 -->
  <table class="table is-striped">
    <tbody>
      <tr><th>プレイヤーネーム</th><td>ＮＥＧＩＮＥ</td></tr>
      <tr><th>コメント</th><td>よろしくお願いします</td></tr>
      <tr><th>バトルポイント</th><td>12,345,678</td></tr>
      <tr><th>ハイスコア合計</th><td>50,000,000</td></tr>
      <tr><th>レーティング</th><td>19.950 (MAX 19.950)</td></tr>
      <tr><th>最終更新日時</th><td>2026-09-10 18:30:00</td></tr>
    </tbody>
  </table>

  <!-- ダミーテーブル群 -->
  <table class="table dummy-1"></table>
  <table class="table dummy-2"></table>
  <table class="table dummy-3"></table>
  <table class="table dummy-4"></table>

  <!-- Table 5: スコア一覧 -->
  <table class="table">
    <thead>
      <tr>
        <th data-sort="sort_title">Title</th>
        <th>Category</th>
        <th>Dif</th>
        <th>Lv</th>
        <th>Lamp</th>
        <th>評価</th>
        <th>Rank</th>
        <th>BS</th>
        <th>OD</th>
        <th>TS</th>
        <th>Update</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td class="sort_title"><span class="sort-key">怨撃</span><a href="/music/1001/master">怨撃</a></td>
        <td class="sort_category">オンゲキ</td>
        <td class="sort_difficulty">Master</td>
        <td class="sort_level">15+</td>
        <td><span class="badge-lamp">Clear</span></td>
        <td><span class="badge-bell">FB</span></td>
        <td class="sort_rank">SSS</td>
        <td>9900</td>
        <td>100</td>
        <td class="sort_ts">1,002,500</td>
        <td>2026-09-10</td>
      </tr>
      <tr>
        <td class="sort_title"><span class="sort-key">Apollo</span><a href="/music/1002/master">Apollo</a></td>
        <td class="sort_category">オンゲキ</td>
        <td class="sort_difficulty">Master</td>
        <td class="sort_level">15+</td>
        <td><span class="badge-lamp">AB</span></td>
        <td><span class="badge-bell">FB</span></td>
        <td class="sort_rank">SSS+</td>
        <td>9950</td>
        <td>100</td>
        <td class="sort_ts">1,008,200</td>
        <td>2026-09-10</td>
      </tr>
      <tr>
        <td class="sort_title"><span class="sort-key">Recoil</span><a href="/music/1003/master">Recoil</a></td>
        <td class="sort_category">オンゲキ</td>
        <td class="sort_difficulty">Master</td>
        <td class="sort_level">15+</td>
        <td><span class="badge-lamp">Clear</span></td>
        <td></td>
        <td class="sort_rank">SSS</td>
        <td>9920</td>
        <td>90</td>
        <td class="sort_ts">1,003,100</td>
        <td>2026-09-10</td>
      </tr>
      <tr>
        <td class="sort_title"><span class="sort-key">光焔のラテラルアーク</span><a href="/music/1004/master">光焔のラテラルアーク</a></td>
        <td class="sort_category">オンゲキ</td>
        <td class="sort_difficulty">Master</td>
        <td class="sort_level">15</td>
        <td><span class="badge-lamp">AB</span></td>
        <td><span class="badge-bell">FB</span></td>
        <td class="sort_rank">SSS+</td>
        <td>9980</td>
        <td>100</td>
        <td class="sort_ts">1,008,900</td>
        <td>2026-09-10</td>
      </tr>
      <tr>
        <td class="sort_title"><span class="sort-key">Op.I《fear-TITΛN-》</span><a href="/music/1005/master">Op.I《fear-TITΛN-》</a></td>
        <td class="sort_category">オンゲキ</td>
        <td class="sort_difficulty">Master</td>
        <td class="sort_level">15</td>
        <td><span class="badge-lamp">AB</span></td>
        <td><span class="badge-bell">FB</span></td>
        <td class="sort_rank">SSS+</td>
        <td>9970</td>
        <td>100</td>
        <td class="sort_ts">1,007,800</td>
        <td>2026-09-10</td>
      </tr>
      <tr>
        <td class="sort_title"><span class="sort-key">Trrricksters!!</span><a href="/music/1006/master">Trrricksters!!</a></td>
        <td class="sort_category">オンゲキ</td>
        <td class="sort_difficulty">Master</td>
        <td class="sort_level">14+</td>
        <td><span class="badge-lamp">AB</span></td>
        <td><span class="badge-bell">FB</span></td>
        <td class="sort_rank">AP</td>
        <td>10000</td>
        <td>100</td>
        <td class="sort_ts">1,010,000</td>
        <td>2026-09-10</td>
      </tr>
      <tr>
        <td class="sort_title"><span class="sort-key">感情アクセラレイション</span><a href="/music/1007/master">感情アクセラレイション</a></td>
        <td class="sort_category">オンゲキ</td>
        <td class="sort_difficulty">Master</td>
        <td class="sort_level">14</td>
        <td><span class="badge-lamp">AB</span></td>
        <td><span class="badge-bell">FB</span></td>
        <td class="sort_rank">AP</td>
        <td>10000</td>
        <td>100</td>
        <td class="sort_ts">1,010,000</td>
        <td>2026-09-10</td>
      </tr>
      <tr>
        <td class="sort_title"><span class="sort-key">Starring Stars</span><a href="/music/1008/master">Starring Stars</a></td>
        <td class="sort_category">オンゲキ</td>
        <td class="sort_difficulty">Master</td>
        <td class="sort_level">13+</td>
        <td><span class="badge-lamp">AB</span></td>
        <td><span class="badge-bell">FB</span></td>
        <td class="sort_rank">AP</td>
        <td>10000</td>
        <td>100</td>
        <td class="sort_ts">1,010,000</td>
        <td>2026-09-10</td>
      </tr>
    </tbody>
  </table>
</body>
</html>
"""
    return html

@pytest.fixture
def mock_music_html():
    """
    ongeki-score.net/music のテーブル構造を再現したモックHTML。
    定数13.7以上の全譜面同期テスト用。
    """
    html = """<!DOCTYPE html>
<html>
<body>
  <table class="table music-list">
    <thead>
      <tr><th>Title</th><th>Dif</th><th>Lv</th><th>Extra</th></tr>
    </thead>
    <tbody>
      <tr>
        <td class="sort_title"><span class="sort-key">怨撃</span><a href="/music/1001/master">怨撃</a></td>
        <td>Master</td>
        <td class="sort_level">15+</td>
        <td class="table-hidden-data sort_extra_level">15.9</td>
      </tr>
      <tr>
        <td class="sort_title"><span class="sort-key">Apollo</span><a href="/music/1002/master">Apollo</a></td>
        <td>Master</td>
        <td class="sort_level">15+</td>
        <td class="table-hidden-data sort_extra_level">15.8</td>
      </tr>
      <tr>
        <td class="sort_title"><span class="sort-key">低定数テスト曲</span><a href="/music/1009/master">低定数テスト曲</a></td>
        <td>Master</td>
        <td class="sort_level">13</td>
        <td class="table-hidden-data sort_extra_level">13.2</td>
      </tr>
      <tr>
        <td class="sort_title"><span class="sort-key">境界テスト曲13.7</span><a href="/music/1010/master">境界テスト曲13.7</a></td>
        <td>Master</td>
        <td class="sort_level">13+</td>
        <td class="table-hidden-data sort_extra_level">13.7</td>
      </tr>
      <tr>
        <td class="sort_title"><span class="sort-key">境界テスト曲13.6</span><a href="/music/1011/master">境界テスト曲13.6</a></td>
        <td>Master</td>
        <td class="sort_level">13+</td>
        <td class="table-hidden-data sort_extra_level">13.6</td>
      </tr>
    </tbody>
  </table>
</body>
</html>
"""
    return html

@pytest.fixture
def seed_population_players(test_session):
    """
    要件定義書 §3.2 に記載された母集団統計に基づくシミュレーションプレイヤー群
    (レート18.0〜21.0、各帯域の中央値およびIQRに準拠)
    """
    band_specs = [
        # (center_rate, median_opi, count)
        (18.0, 1480.2, 30),
        (18.5, 1632.5, 30),
        (19.0, 1791.0, 30),
        (19.5, 1942.3, 30),
        (20.0, 2076.8, 30),
        (20.5, 2235.1, 20),
        (21.0, 2310.5, 10),
    ]
    players = []
    user_id_seq = 100000
    for center_rate, median_opi, count in band_specs:
        np.random.seed(int(center_rate * 100))
        rates = np.random.uniform(center_rate - 0.24, center_rate + 0.24, count)
        opis = np.random.normal(median_opi, 30.0, count)
        for r, o in zip(rates, opis):
            user_id_seq += 1
            p = Player(
                user_id=user_id_seq,
                player_name=f"Player_{user_id_seq}",
                rating=float(round(r, 3)),
                total_opi=float(round(o, 1)),
                log_updated_at=datetime(2026, 9, 10)
            )
            test_session.add(p)
            players.append(p)
    test_session.commit()
    return players
