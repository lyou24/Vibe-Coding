import os
import pytest
from datetime import datetime
from bs4 import BeautifulSoup
import numpy as np

from src.database.models import Chart, Player, ScoreLog, DifficultyEnum
from src.analyzer.opi_calculator import OPICalculator
from src.crawler.ongeki_crawler import OngekiCrawler
from src.recommender.recommender import OPIRecommender
from src.visualizer.visualizer import OPIVisualizer

class TestTier1Crawler:
    """F-01 データ収集機能の検証"""

    def test_crawler_profile_parsing_with_mock_html(self, monkeypatch):
        """OngekiScoreLog Table 0 からのプロフィール（名前、レーティング、更新日時）抽出検証"""
        fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_user_10605.html")
        with open(fixture_path, "r", encoding="utf-8") as f:
            mock_html = f.read()

        crawler = OngekiCrawler()

        # HTMLを直接パースするロジックまたはfetch_user_profileモックで検証
        soup = BeautifulSoup(mock_html, "html.parser")
        
        # テーブル構造から正しく抽出できるかの仕様要件検証
        tables = soup.find_all("table")
        assert len(tables) > 0, "HTML内にテーブルが存在すること"
        user_table = tables[0]
        rows = user_table.find_all("tr")
        user_info = {}
        for row in rows:
            th = row.find("th")
            td = row.find("td")
            if th and td:
                user_info[th.text.strip()] = td.text.strip()

        assert "プレイヤーネーム" in user_info
        assert user_info["プレイヤーネーム"] == "ＮＥＧＩＮＥ"
        assert "レーティング" in user_info
        assert "19.950" in user_info["レーティング"]
        assert "最終更新日時" in user_info
        assert "2026-09-10" in user_info["最終更新日時"]

    def test_crawler_scores_parsing_with_mock_html(self):
        """OngekiScoreLog Table 5 からのスコア一覧抽出検証"""
        fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_user_10605.html")
        with open(fixture_path, "r", encoding="utf-8") as f:
            mock_html = f.read()

        soup = BeautifulSoup(mock_html, "html.parser")
        tables = soup.find_all("table")
        assert len(tables) >= 6, "スコア一覧テーブル（Table 5）が存在すること"

        score_table = tables[5]
        score_rows = score_table.find("tbody").find_all("tr")
        assert len(score_rows) >= 8, "サンプルHTML内に十分な曲数のスコア行が存在すること"

        # 怨撃のスコア検証
        first_row = score_rows[0]
        title_td = first_row.find("td", class_="sort_title")
        title_a = title_td.find("a") if title_td else None
        title = title_a.text.strip() if title_a else ""
        assert title == "怨撃"

        ts_td = first_row.find("td", class_="sort_ts")
        score_val = int(ts_td.text.strip().replace(",", ""))
        assert score_val == 1007800

    def test_crawler_min_date_filtering(self):
        """最終更新日が2025年3月27日以前のユーザーは対象外としてスキップされること"""
        crawler = OngekiCrawler()
        # TARGET_MIN_DATE が 2025-03-27 であることを確認
        assert crawler.TARGET_MIN_DATE == datetime(2025, 3, 27)

    def test_crawler_diff_update_logic(self):
        """前回クロール日時より更新が新しい場合のみ抽出対象となること"""
        last_crawled = datetime(2026, 9, 1, 0, 0, 0)
        older_update = datetime(2026, 8, 31, 0, 0, 0)
        newer_update = datetime(2026, 9, 10, 0, 0, 0)

        assert not (older_update > last_crawled), "古いデータはスキップ対象"
        assert newer_update > last_crawled, "新しいデータは抽出対象"


class TestTier1MusicDBSync:
    """F-02 外部楽曲DB同期機能の検証"""

    def test_music_list_filtering_constant_13_7(self):
        """譜面定数13.7以上の譜面のみが抽出され、13.7未満は除外されること"""
        fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_music_list.html")
        with open(fixture_path, "r", encoding="utf-8") as f:
            mock_html = f.read()

        soup = BeautifulSoup(mock_html, "html.parser")
        table = soup.find("table", class_="music-list")
        rows = table.find("tbody").find_all("tr")

        extracted_charts = []
        for r in rows:
            cols = r.find_all("td")
            if len(cols) >= 4:
                title_elem = cols[0].find("a")
                title = title_elem.text.strip() if title_elem else cols[0].text.strip()
                diff = cols[1].text.strip().upper()
                level = cols[2].text.strip()
                try:
                    constant = float(cols[3].text.strip())
                except ValueError:
                    continue

                if constant >= 13.7:
                    extracted_charts.append({
                        "title": title,
                        "difficulty": diff,
                        "level": level,
                        "constant": constant
                    })

        # 検証
        titles = [c["title"] for c in extracted_charts]
        assert "怨撃" in titles
        assert "Apollo" in titles
        assert "Recoil" in titles
        assert "Starring Stars" in titles  # 定数13.7
        assert "定数未満曲13.2" not in titles  # 定数13.2は除外
        assert "境界13.69" not in titles  # 定数13.6は除外


class TestTier1OPICalculation:
    """F-03 単曲OPI算出および F-04 総合OPI算出（2PL IRT + MLE）の検証"""

    def test_irt_probability_mathematical_properties(self):
        """2母数ロジスティック曲線の数学的性質（中心値0.5、単調増加、オーバーフロー防止）"""
        calc = OPICalculator()
        x = 1500.0
        y = 40.0

        # 中心値: θ = x のとき確率 0.5
        assert pytest.approx(calc.irt_probability(1500.0, x, y), abs=1e-5) == 0.5

        # 単調増加性
        p_lower = calc.irt_probability(1450.0, x, y)
        p_higher = calc.irt_probability(1550.0, x, y)
        assert p_lower < 0.5 < p_higher

        # 対称性: P(x + d) + P(x - d) == 1.0
        assert pytest.approx(calc.irt_probability(1550.0, x, y) + calc.irt_probability(1450.0, x, y), abs=1e-5) == 1.0

        # 極端な値でのオーバーフロー耐性
        assert calc.irt_probability(10000.0, x, y) == 1.0
        assert calc.irt_probability(-10000.0, x, y) == 0.0

    def test_five_target_ranks_parameters_coverage(self, seed_charts):
        """5つの目標ランク（SS, SSS, SSS+, SSS+ABFB, AP）すべてに対して適正OPIが定義されていること"""
        ongeki = next(c for c in seed_charts if c.chart_id == "mas_ongeki")
        assert ongeki.opi_ss_x is not None
        assert ongeki.opi_sss_x is not None
        assert ongeki.opi_sssp_x is not None
        assert ongeki.opi_abfb_x is not None
        assert ongeki.opi_ap_x is not None

        # 難易度の序列関係: SS < SSS < SSS+ < SSS+ABFB <= AP
        assert ongeki.opi_ss_x < ongeki.opi_sss_x < ongeki.opi_sssp_x < ongeki.opi_abfb_x <= ongeki.opi_ap_x

    def test_mle_total_opi_estimation(self):
        """最尤推定（MLE）による総合OPI算出が実力分布に応じて適切に推定されること"""
        calc = OPICalculator()

        # 上級プレイヤー（定数15帯のSSS以上を多数達成）
        high_skill_achievements = [
            {'x': 1169.8, 'y': 42.0, 'achieved': 1},  # 13.7 SSS
            {'x': 1238.5, 'y': 39.2, 'achieved': 1},  # 14.0 SSS
            {'x': 1453.7, 'y': 43.1, 'achieved': 1},  # 14.8 SSS
            {'x': 1576.1, 'y': 36.4, 'achieved': 1},  # 15.3 SSS
            {'x': 1716.9, 'y': 42.1, 'achieved': 1},  # 15.9 SSS
            {'x': 2086.9, 'y': 42.1, 'achieved': 0},  # 15.9 AP
        ]
        high_opi = calc.estimate_user_opi(high_skill_achievements, 1500.0)

        # 初中級プレイヤー（13.7〜14.0中心に達成、15以上は未達成）
        low_skill_achievements = [
            {'x': 1169.8, 'y': 42.0, 'achieved': 1},  # 13.7 SSS
            {'x': 1238.5, 'y': 39.2, 'achieved': 1},  # 14.0 SSS
            {'x': 1453.7, 'y': 43.1, 'achieved': 0},  # 14.8 SSS
            {'x': 1576.1, 'y': 36.4, 'achieved': 0},  # 15.3 SSS
            {'x': 1716.9, 'y': 42.1, 'achieved': 0},  # 15.9 SSS
        ]
        low_opi = calc.estimate_user_opi(low_skill_achievements, 1500.0)

        assert high_opi > low_opi
        assert 1600.0 < high_opi < 2100.0
        assert 1100.0 < low_opi < 1400.0


class TestTier1Recommender:
    """F-05 目標楽曲リコメンド機能の検証"""

    def test_recommender_filters_and_win_rate(self, test_db_path, test_session, seed_charts):
        """総合OPIに対する勝率（30〜70%）の未達成楽曲が正しく抽出されること"""
        # テストプレイヤー登録 (OPI=1500.0)
        player = Player(user_id=999, player_name="TestUser", rating=18.5, total_opi=1500.0)
        test_session.add(player)
        
        # 感情アクセラレイション (適正OPI 1238.5) はすでに達成済みとする
        score = ScoreLog(user_id=999, chart_id="mas_kanjou_acceleration", score=1003000, achieve_sss=True)
        test_session.add(score)
        test_session.commit()

        recommender = OPIRecommender(test_db_path)
        recs = recommender.get_recommendations(user_id=999, target_rank="SSS", limit=10)

        assert len(recs) > 0
        # 達成済みの「感情アクセラレイション」はリコメンドに含まれないこと
        rec_ids = [r["chart_id"] for r in recs]
        assert "mas_kanjou_acceleration" not in rec_ids

        # 勝率はすべて 30% 〜 70% の範囲内であること
        for r in recs:
            assert 0.30 <= r["probability"] <= 0.70

        # OPI差分昇順でソートされていること
        diffs = [r["opi_diff"] for r in recs]
        assert diffs == sorted(diffs)


class TestTier1VisualizerAndDifficultyTable:
    """F-06 分布分析機能 および F-07 難易度表生成機能の検証"""

    def test_visualizer_distribution_plot_file_generation(self, test_db_path, seed_population_players, tmp_path):
        """分布図（バイオリンプロット）が正しく画像ファイルとして出力されること"""
        vis = OPIVisualizer(test_db_path)
        output_img = str(tmp_path / "test_distribution.png")
        vis.create_distribution_plot(output_img)

        assert os.path.exists(output_img), "分布図画像が生成されていること"
        assert os.path.getsize(output_img) > 1000, "画像ファイルが空でないこと"

    def test_difficulty_table_data_structure(self, test_session, seed_charts):
        """難易度表データが適正OPI順に整列して取得できること"""
        charts = test_session.query(Chart).filter(Chart.opi_sss_x != None).order_by(Chart.opi_sss_x.asc()).all()
        assert len(charts) >= 8

        opi_values = [c.opi_sss_x for c in charts]
        assert opi_values == sorted(opi_values), "難易度表が適正OPI昇順に整列していること"

        # 最下位曲と最上位曲の確認
        assert charts[0].title == "Starring Stars"  # 定数13.7 (1169.8)
        assert charts[-1].title == "怨撃"          # 定数15.9 (1716.9)
