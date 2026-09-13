import os
import sys
import json
import pytest
import sqlite3
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

# プロジェクトルートの追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.crawler.ongeki_crawler import OngekiCrawler
from src.database.models import init_db, get_session_maker, Chart, Player, ScoreLog, DifficultyEnum
from seed import seed_database, calculate_initial_chart_params

# ==============================================================================
# 1. 存在しないユーザーIDおよび不正入力のストレステスト
# ==============================================================================
class TestNonExistentUserAndBoundaries:
    """存在しないユーザーIDや極端なIDを指定したときの挙動検証"""

    @pytest.mark.asyncio
    async def test_non_existent_user_id_online_or_mock(self):
        """実サイトまたはモックによるID 99999999 の処理 (HTTP 404 / データ不在)"""
        crawler = OngekiCrawler()
        try:
            # 存在しないユーザーID（実サイトに問い合わせ）
            profile = await crawler.fetch_user_profile(99999999)
            # クラッシュせずに None が返ること
            assert profile is None, "存在しないユーザーIDのプロフィール取得は None を返すべき"

            scores = await crawler.fetch_user_scores(99999999)
            # クラッシュせずに空リストが返ること
            assert isinstance(scores, list), "存在しないユーザーIDのスコア取得はリストを返すべき"
            assert len(scores) == 0, "存在しないユーザーIDのスコアは0件であるべき"
        finally:
            await crawler.close()

    @pytest.mark.asyncio
    async def test_negative_and_zero_user_id(self):
        """負の数(-1)やゼロ(0)のユーザーIDを指定したときの挙動"""
        crawler = OngekiCrawler()
        try:
            for invalid_id in [-1, 0]:
                profile = await crawler.fetch_user_profile(invalid_id)
                assert profile is None, f"無効なユーザーID {invalid_id} は None を返すべき"

                scores = await crawler.fetch_user_scores(invalid_id)
                assert isinstance(scores, list), f"無効なユーザーID {invalid_id} はリストを返すべき"
                assert len(scores) == 0, f"無効なユーザーID {invalid_id} は0件であるべき"
        finally:
            await crawler.close()

    @pytest.mark.asyncio
    async def test_malformed_html_parsing_robustness(self):
        """破損したHTMLや予期せぬDOM構造に対する堅牢性テスト"""
        crawler = OngekiCrawler()
        try:
            # 1. テーブルが全くないHTML
            mock_resp_empty = MagicMock()
            mock_resp_empty.status = 200
            mock_resp_empty.text = AsyncMock(return_value="<html><body><div>No tables here</div></body></html>")

            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_get.return_value.__aenter__.return_value = mock_resp_empty
                
                profile = await crawler.fetch_user_profile(12345)
                assert profile is None, "テーブルがないHTMLは安全に None を返すべき"

                scores = await crawler.fetch_user_scores(12345)
                assert scores == [], "テーブルがないHTMLは安全に空リストを返すべき"

            # 2. テーブルはあるがカラムが不足しているHTML
            mock_resp_broken = MagicMock()
            mock_resp_broken.status = 200
            mock_resp_broken.text = AsyncMock(return_value="""
            <html><body>
                <table class="is-striped"><tr><td>ランダムなテキスト</td></tr></table>
                <table><tr><td>不正なテーブル</td></tr></table>
            </body></html>
            """)

            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_get.return_value.__aenter__.return_value = mock_resp_broken
                
                profile = await crawler.fetch_user_profile(12345)
                # テーブル内にプレイヤーネームも更新日もないため、デフォルト更新日(now)でprofileが構築される
                assert profile is not None
                assert profile["player_name"] == "User_12345"
                assert profile["rating"] is None

                scores = await crawler.fetch_user_scores(12345)
                assert scores == []
        finally:
            await crawler.close()


# ==============================================================================
# 2. 空スコア・特殊文字・エッジケース処理のテスト
# ==============================================================================
class TestSpecialCharactersAndScoreEdges:
    """特殊文字を含む楽曲名やスコア境界値の処理検証"""

    @pytest.mark.asyncio
    async def test_special_character_titles_and_edge_scores(self):
        """特殊文字（ギリシャ文字、引用符、HTML実体参照）やスコア境界値のパース検証"""
        sample_html = """
        <html><body>
            <table class="is-striped">
                <tr><th>プレイヤーネーム</th><td>テスト名&amp;名</td></tr>
                <tr><th>レーティング</th><td>19.850</td></tr>
            </table>
            <table>
                <tr><td class="sort_update">2026-09-10</td></tr>
            </table>
            <table>
                <thead>
                    <tr><th data-sort="sort_title">曲名</th><th class="sort_ts">TS</th></tr>
                </thead>
                <tbody>
                    <!-- 特殊文字タイトル1: ギリシャ文字と記号 -->
                    <tr>
                        <td class="sort_title">
                            <span class="sort-key">Op.I《fear-TITΛN-》</span>
                            <a href="/music/1001/master">Op.I《fear-TITΛN-》</a>
                        </td>
                        <td class="sort_difficulty">MAS</td>
                        <td class="sort_ts"><span class="sort-key">1010000</span>1,010,000</td>
                        <td class="sort_raw_lamp">AB FB</td>
                    </tr>
                    <!-- 特殊文字タイトル2: ダブルクォーテーション・コロン -->
                    <tr>
                        <td class="sort_title">
                            <a href="/music/1002/lunatic">Mini Hell: "The Moon"</a>
                        </td>
                        <td class="sort_raw_difficulty">LUN</td>
                        <td class="sort_ts">1,007,500</td>
                        <td class="sort_lamp">AB</td>
                    </tr>
                    <!-- 境界スコア: 0点 (プレイ記録ありだが途中落ち/放置) -->
                    <tr>
                        <td class="sort_title">
                            <a href="/music/1003/expert">Zero Score Song</a>
                        </td>
                        <td class="sort_raw_difficulty">EXP</td>
                        <td class="sort_ts"><span class="sort-key">0</span>0</td>
                        <td class="sort_raw_lamp"></td>
                    </tr>
                    <!-- 境界スコア: 990,000 (SS境界) -->
                    <tr>
                        <td class="sort_title">
                            <a href="/music/1004/master">SS Border Song</a>
                        </td>
                        <td class="sort_raw_difficulty">MAS</td>
                        <td class="sort_ts">990000</td>
                        <td class="sort_raw_lamp">FB</td>
                    </tr>
                    <!-- 境界スコア: 989,999 (SS未満) -->
                    <tr>
                        <td class="sort_title">
                            <a href="/music/1005/master">Sub-SS Song</a>
                        </td>
                        <td class="sort_raw_difficulty">MAS</td>
                        <td class="sort_ts">989999</td>
                        <td class="sort_raw_lamp"></td>
                    </tr>
                </tbody>
            </table>
        </body></html>
        """

        crawler = OngekiCrawler()
        try:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.text = AsyncMock(return_value=sample_html)

            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_get.return_value.__aenter__.return_value = mock_resp
                
                scores = await crawler.fetch_user_scores(10605)
                assert len(scores) == 5, f"期待件数 5件, 取得件数: {len(scores)}"

                # 1. Op.I《fear-TITΛN-》
                s0 = scores[0]
                assert s0["title"] == "Op.I《fear-TITΛN-》"
                assert s0["difficulty"] == "MASTER"
                assert s0["score"] == 1010000
                assert s0["is_all_break"] is True
                assert s0["is_full_bell"] is True
                assert s0["chart_id"] == "1001_master"

                # 2. Mini Hell: "The Moon"
                s1 = scores[1]
                assert s1["title"] == 'Mini Hell: "The Moon"'
                assert s1["difficulty"] == "LUNATIC"
                assert s1["score"] == 1007500
                assert s1["is_all_break"] is True
                assert s1["is_full_bell"] is False
                assert s1["chart_id"] == "1002_lunatic"

                # 3. 0点
                s2 = scores[2]
                assert s2["score"] == 0
                assert s2["is_all_break"] is False
                assert s2["is_full_bell"] is False

                # 4. 990,000点
                s3 = scores[3]
                assert s3["score"] == 990000
                assert s3["is_all_break"] is False
                assert s3["is_full_bell"] is True

                # 5. 989,999点
                s4 = scores[4]
                assert s4["score"] == 989999
        finally:
            await crawler.close()


# ==============================================================================
# 3. seed.py のオフライン複数回実行（冪等性・エラー有無）のストレステスト
# ==============================================================================
class TestSeedIdempotencyAndStress:
    """オフライン状態での seed.py 実行における冪等性とエラー有無の検証"""

    @pytest.fixture
    def test_seed_dict(self):
        """テスト用シードデータ"""
        return {
            "generated_at": datetime.now().isoformat(),
            "music_master": [
                {
                    "chart_id": "1001_master",
                    "title": "Op.I《fear-TITΛN-》",
                    "difficulty": "MASTER",
                    "level": "14+",
                    "chart_constant": 14.8,
                    "music_id": "1001"
                },
                {
                    "chart_id": "1002_lunatic",
                    "title": 'Mini Hell: "The Moon"',
                    "difficulty": "LUNATIC",
                    "level": "15",
                    "chart_constant": 15.2,
                    "music_id": "1002"
                },
                {
                    "chart_id": "1003_expert",
                    "title": "Zero Score Song",
                    "difficulty": "EXPERT",
                    "level": "13+",
                    "chart_constant": 13.8,
                    "music_id": "1003"
                }
            ],
            "test_user": {
                "profile": {
                    "user_id": 10605,
                    "player_name": "ＮＥＧＩＮＥ",
                    "rating": 19.95,
                    "updated_at": "2026-09-10T00:00:00"
                },
                "scores": [
                    {
                        "chart_id": "1001_master",
                        "title": "Op.I《fear-TITΛN-》",
                        "difficulty": "MASTER",
                        "score": 1010000,
                        "is_all_break": True,
                        "is_full_bell": True
                    },
                    {
                        "chart_id": "1002_lunatic",
                        "title": 'Mini Hell: "The Moon"',
                        "difficulty": "LUNATIC",
                        "score": 1007500,
                        "is_all_break": True,
                        "is_full_bell": False
                    },
                    {
                        "chart_id": "1003_expert",
                        "title": "Zero Score Song",
                        "difficulty": "EXPERT",
                        "score": 0,
                        "is_all_break": False,
                        "is_full_bell": False
                    }
                ]
            },
            "population_samples": [
                {
                    "user_id": 90001,
                    "player_name": "Player_90001",
                    "rating": 18.05,
                    "total_opi": 1485.0
                },
                {
                    "user_id": 90002,
                    "player_name": "Player_90002",
                    "rating": 19.12,
                    "total_opi": 1795.5
                }
            ]
        }

    def test_seed_database_multiple_runs_idempotency(self, test_seed_dict):
        """同一DBに対して seed_database を3回連続実行しても件数・内容が不変であること（冪等性）"""
        fd, tmp_db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)

        try:
            # 1回目実行
            seed_database(test_seed_dict, db_path=tmp_db_path, include_population=True)
            
            # DBの確認
            conn = sqlite3.connect(tmp_db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM charts")
            c1 = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM players")
            p1 = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM score_logs")
            s1 = cur.fetchone()[0]
            conn.close()

            assert c1 == 3, f"1回目 charts 件数期待値 3, 実際 {c1}"
            assert p1 == 3, f"1回目 players 件数期待値 3 (10605 + 2サンプル), 実際 {p1}"
            assert s1 == 3, f"1回目 score_logs 件数期待値 3, 実際 {s1}"

            # 2回目実行 (同一データで再実行)
            seed_database(test_seed_dict, db_path=tmp_db_path, include_population=True)
            conn = sqlite3.connect(tmp_db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM charts")
            c2 = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM players")
            p2 = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM score_logs")
            s2 = cur.fetchone()[0]
            conn.close()

            assert c2 == c1, f"2回目 charts 件数が変化している: {c2} != {c1}"
            assert p2 == p1, f"2回目 players 件数が変化している: {p2} != {p1}"
            assert s2 == s1, f"2回目 score_logs 件数が変化している: {s2} != {s1}"

            # 3回目実行
            seed_database(test_seed_dict, db_path=tmp_db_path, include_population=True)
            conn = sqlite3.connect(tmp_db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM charts")
            c3 = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM players")
            p3 = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM score_logs")
            s3 = cur.fetchone()[0]

            # 達成フラグが正しく計算されているか確認
            cur.execute("SELECT chart_id, achieve_ss, achieve_sss, achieve_sssp, achieve_abfb, achieve_ap FROM score_logs WHERE user_id = 10605")
            logs = {row[0]: row[1:] for row in cur.fetchall()}
            conn.close()

            assert c3 == c1
            assert p3 == p1
            assert s3 == s1

            # AP達成の確認: 1001_master (1010000, AB=True, FB=True)
            assert logs["1001_master"] == (1, 1, 1, 1, 1), f"1001_master flags mismatch: {logs['1001_master']}"

            # SSS+ (ABのみ, FB=False)
            assert logs["1002_lunatic"] == (1, 1, 1, 0, 0), f"1002_lunatic flags mismatch: {logs['1002_lunatic']}"

            # 0点 (すべてFalse)
            assert logs["1003_expert"] == (0, 0, 0, 0, 0), f"1003_expert flags mismatch: {logs['1003_expert']}"

        finally:
            # Windowsでのガベージコレクションとリソース解放
            import gc
            gc.collect()
            try:
                if os.path.exists(tmp_db_path):
                    os.remove(tmp_db_path)
            except Exception:
                pass

    def test_production_seed_json_offline_execution(self):
        """実リポジトリの data/seed_data.json を使ったオフラインDB投入の完全性・冪等性検証"""
        json_path = os.path.join(PROJECT_ROOT, "data", "seed_data.json")
        assert os.path.exists(json_path), "seed_data.json が存在すること"

        with open(json_path, "r", encoding="utf-8") as f:
            full_seed_data = json.load(f)

        fd, tmp_db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)

        try:
            # 1回目
            seed_database(full_seed_data, db_path=tmp_db_path, include_population=True)
            conn = sqlite3.connect(tmp_db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM charts")
            charts_count_1 = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM players")
            players_count_1 = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM score_logs WHERE user_id = 10605")
            scores_count_1 = cur.fetchone()[0]
            conn.close()

            assert charts_count_1 == 543, f"期待譜面数 543, 実際 {charts_count_1}"
            assert players_count_1 == 2504, f"期待プレイヤー数 2504, 実際 {players_count_1}"
            # 登録されたスコアログ数 (正規マッチ397件)
            assert scores_count_1 == 397, f"正規マッチスコアログが登録されていること (期待397): {scores_count_1}"

            # 2回目（上書き・再投入）
            seed_database(full_seed_data, db_path=tmp_db_path, include_population=True)
            conn = sqlite3.connect(tmp_db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM charts")
            charts_count_2 = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM players")
            players_count_2 = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM score_logs WHERE user_id = 10605")
            scores_count_2 = cur.fetchone()[0]
            conn.close()

            assert charts_count_2 == charts_count_1, f"2回目実行で譜面数が変化した: {charts_count_2} != {charts_count_1}"
            assert players_count_2 == players_count_1, f"2回目実行でプレイヤー数が変化した: {players_count_2} != {players_count_1}"
            assert scores_count_2 == scores_count_1, f"2回目実行でスコア数が変化した: {scores_count_2} != {scores_count_1}"

        finally:
            import gc
            gc.collect()
            try:
                if os.path.exists(tmp_db_path):
                    os.remove(tmp_db_path)
            except Exception:
                pass


# ==============================================================================
# 4. 差分更新・フィルタリングのストレステスト
# ==============================================================================
class TestDiffUpdateAndFiltering:
    """最終更新日（2025年3月27日）足切りおよび差分更新（last_crawled_at）の境界値検証"""

    @pytest.mark.asyncio
    async def test_skip_users_updated_before_cutoff(self):
        """2025年3月27日より前に更新されたユーザーがスキップされること"""
        old_user_html = """
        <html><body>
            <table class="is-striped">
                <tr><th>プレイヤーネーム</th><td>OldUser</td></tr>
                <tr><th>レーティング</th><td>18.50</td></tr>
            </table>
            <table>
                <tr><td class="sort_update">2025-03-26</td></tr>
            </table>
        </body></html>
        """
        crawler = OngekiCrawler()
        try:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.text = AsyncMock(return_value=old_user_html)

            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_get.return_value.__aenter__.return_value = mock_resp
                profile = await crawler.fetch_user_profile(20001)
                assert profile is None, "2025-03-26（基準日以前）のユーザーはスキップされてNoneになるべき"
        finally:
            await crawler.close()

    @pytest.mark.asyncio
    async def test_accept_users_updated_on_or_after_cutoff(self):
        """2025年3月27日当日またはそれ以降に更新されたユーザーは正常取得されること"""
        valid_user_html = """
        <html><body>
            <table class="is-striped">
                <tr><th>プレイヤーネーム</th><td>ValidUser</td></tr>
                <tr><th>レーティング</th><td>19.00</td></tr>
            </table>
            <table>
                <tr><td class="sort_update">2025-03-27</td></tr>
            </table>
        </body></html>
        """
        crawler = OngekiCrawler()
        try:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.text = AsyncMock(return_value=valid_user_html)

            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_get.return_value.__aenter__.return_value = mock_resp
                profile = await crawler.fetch_user_profile(20002)
                assert profile is not None, "2025-03-27（基準日当日）のユーザーは取得されるべき"
                assert profile["player_name"] == "ValidUser"
                assert profile["rating"] == 19.0
        finally:
            await crawler.close()

    @pytest.mark.asyncio
    async def test_incremental_crawl_last_crawled_at_boundary(self):
        """last_crawled_at を指定した差分更新境界値検証"""
        sample_html = """
        <html><body>
            <table class="is-striped">
                <tr><th>プレイヤーネーム</th><td>ActiveUser</td></tr>
                <tr><th>レーティング</th><td>19.50</td></tr>
            </table>
            <table>
                <tr><td class="sort_update">2026-09-01</td></tr>
            </table>
        </body></html>
        """
        crawler = OngekiCrawler()
        try:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.text = AsyncMock(return_value=sample_html)

            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_get.return_value.__aenter__.return_value = mock_resp

                # 1. 前回クロールが更新日より前 -> 取得される
                p1 = await crawler.fetch_user_profile(30001, last_crawled_at=datetime(2026, 8, 31))
                assert p1 is not None

                # 2. 前回クロールが更新日と同じ -> スキップされる
                p2 = await crawler.fetch_user_profile(30001, last_crawled_at=datetime(2026, 9, 1))
                assert p2 is None

                # 3. 前回クロールが更新日より後 -> スキップされる
                p3 = await crawler.fetch_user_profile(30001, last_crawled_at=datetime(2026, 9, 2))
                assert p3 is None
        finally:
            await crawler.close()


# ==============================================================================
# 5. 空スコアユーザー・未知楽曲・大量スコアのDBシード耐性テスト
# ==============================================================================
class TestEdgeCaseSeedingAndUnknownEntries:
    """空スコアユーザー、未登録譜面のスコア、大量スコア投入耐性の検証"""

    def test_empty_score_user_seeding(self):
        """スコアが0件のユーザーでもクラッシュせずPlayerのみ正常登録されること"""
        seed_data_empty_scores = {
            "music_master": [
                {"chart_id": "1_master", "title": "Song 1", "difficulty": "MASTER", "level": "14", "chart_constant": 14.0}
            ],
            "test_user": {
                "profile": {"user_id": 99999, "player_name": "NoScoresUser", "rating": 15.00},
                "scores": []  # スコア0件
            }
        }
        fd, tmp_db = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        try:
            seed_database(seed_data_empty_scores, db_path=tmp_db, include_population=False)
            conn = sqlite3.connect(tmp_db)
            cur = conn.cursor()
            cur.execute("SELECT user_id, player_name FROM players WHERE user_id = 99999")
            user = cur.fetchone()
            assert user == (99999, "NoScoresUser")
            cur.execute("SELECT COUNT(*) FROM score_logs WHERE user_id = 99999")
            score_count = cur.fetchone()[0]
            assert score_count == 0
            conn.close()
        finally:
            import gc; gc.collect()
            try: os.remove(tmp_db)
            except Exception: pass

    def test_unknown_chart_in_scores_skipped_safely(self):
        """マスタに存在しない楽曲のスコアが混入していても、安全にスキップされDB登録が成功すること"""
        seed_data_with_unknown = {
            "music_master": [
                {"chart_id": "1_master", "title": "Known Song", "difficulty": "MASTER", "level": "14", "chart_constant": 14.0}
            ],
            "test_user": {
                "profile": {"user_id": 10605, "player_name": "Tester", "rating": 19.00},
                "scores": [
                    {"chart_id": "1_master", "title": "Known Song", "difficulty": "MASTER", "score": 1000000},
                    {"chart_id": "unknown_master", "title": "Ghost Song", "difficulty": "MASTER", "score": 990000},
                    {"title": "Nonexistent Song", "difficulty": "MASTER", "score": 980000}
                ]
            }
        }
        fd, tmp_db = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        try:
            seed_database(seed_data_with_unknown, db_path=tmp_db, include_population=False)
            conn = sqlite3.connect(tmp_db)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM score_logs WHERE user_id = 10605")
            score_count = cur.fetchone()[0]
            assert score_count == 1, f"未知の譜面はスキップされ登録は1件のはず、実際: {score_count}"
            conn.close()
        finally:
            import gc; gc.collect()
            try: os.remove(tmp_db)
            except Exception: pass

    def test_heavy_score_load_seeding(self):
        """大量のスコア（1000件）を投入した場合でも正常にトランザクションが完了すること"""
        master_charts = [
            {"chart_id": f"chart_{i}_master", "title": f"Song {i}", "difficulty": "MASTER", "level": "14", "chart_constant": 14.0}
            for i in range(1, 201)
        ]
        heavy_scores = [
            {"chart_id": f"chart_{i % 200 + 1}_master", "title": f"Song {i % 200 + 1}", "difficulty": "MASTER", "score": 990000 + i * 10}
            for i in range(1000)
        ]
        seed_data_heavy = {
            "music_master": master_charts,
            "test_user": {
                "profile": {"user_id": 10605, "player_name": "HeavyTester", "rating": 20.00},
                "scores": heavy_scores
            }
        }
        fd, tmp_db = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        try:
            seed_database(seed_data_heavy, db_path=tmp_db, include_population=False)
            conn = sqlite3.connect(tmp_db)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM score_logs WHERE user_id = 10605")
            # 200曲に対して重複上書きされるためユニーク200件
            score_count = cur.fetchone()[0]
            assert score_count == 200, f"ユニーク曲数 200 件が登録されるべき、実際: {score_count}"
            conn.close()
        finally:
            import gc; gc.collect()
            try: os.remove(tmp_db)
            except Exception: pass


# ==============================================================================
# 6. 本番実DB (opi_database.sqlite) の整合性・文字コード網羅検証
# ==============================================================================
class TestRealDatabaseIntegrity:
    """本番SQLiteデータベースの文字コード、整合性、公称値の徹底検証"""

    def test_production_database_no_encoding_artifacts(self):
        """本番DB (data/opi_database.sqlite) に文字化け・不正文字が存在しないこと"""
        db_path = os.path.join(PROJECT_ROOT, "data", "opi_database.sqlite")
        assert os.path.exists(db_path), "opi_database.sqlite が存在すること"

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # 1. charts の文字化け確認（旧コードで発生していた 'ANZCV' 等の異常ASCII列や \ufffd）
        cur.execute("SELECT chart_id, title FROM charts")
        charts = cur.fetchall()
        assert len(charts) == 543, f"全譜面数 543件であること、実際: {len(charts)}"

        corrupted_titles = []
        for cid, title in charts:
            if "\ufffd" in title or "???" in title:
                corrupted_titles.append((cid, title))
            # 旧破損文字のチェック
            if title in ["ANZCV", "ANZEN", "TBD"]:
                corrupted_titles.append((cid, title))

        assert len(corrupted_titles) == 0, f"文字化け曲名が検出されました: {corrupted_titles}"

        # 2. 曲名に依存しない初期パラメータ生成のチェック
        low_params = calculate_initial_chart_params("任意の曲A", 14.0)
        high_params = calculate_initial_chart_params("任意の曲B", 15.7)
        assert low_params["opi_ss_x"] < low_params["opi_sss_x"] < low_params["opi_sssp_x"]
        assert low_params["opi_sssp_x"] < low_params["opi_abfb_x"] < low_params["opi_ap_x"]
        assert high_params["opi_ap_x"] > low_params["opi_ap_x"]


        # 3. 外部キー整合性チェック (PRAGMA foreign_key_check)
        cur.execute("PRAGMA foreign_key_check")
        fk_violations = cur.fetchall()
        assert len(fk_violations) == 0, f"外部キー制約違反が検出されました: {fk_violations}"

        # 4. テストユーザー 10605 の存在とプロファイル
        cur.execute("SELECT user_id, player_name, rating FROM players WHERE user_id = 10605")
        player = cur.fetchone()
        assert player is not None, "ユーザー10605が登録されていること"
        assert player[1] == "ＮＥＧＩＮＥ", f"プレイヤー名が ＮＥＧＩＮＥ であること、実際: {player[1]}"
        assert player[2] == 19.95, f"レーティングが 19.95 であること、実際: {player[2]}"

        # 5. テストユーザー 10605 のスコアログ数 (正規マッチ397件)
        cur.execute("SELECT COUNT(*) FROM score_logs WHERE user_id = 10605")
        score_count = cur.fetchone()[0]
        assert score_count == 397, f"ユーザー10605のスコアログ数が397件であること、実際: {score_count}"

        conn.close()

    def test_no_cross_difficulty_score_overwrite_in_seeding(self):
        """
        【重要バグ検出】
        マスタに存在しない難易度（例: 定数13.7未満のEXPERT）のスコアログが、
        seed.py の優先度3 (titleのみ一致) によって MASTER 譜面のレコードに誤爆・上書きされていないこと。
        """
        json_path = os.path.join(PROJECT_ROOT, "data", "seed_data.json")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_scores = data["test_user"]["scores"]
        db_path = os.path.join(PROJECT_ROOT, "data", "opi_database.sqlite")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        cur.execute("""
            SELECT s.chart_id, c.title, c.difficulty, s.score
            FROM score_logs s
            JOIN charts c ON s.chart_id = c.chart_id
            WHERE s.user_id = 10605
        """)
        db_records = cur.fetchall()
        conn.close()

        corrupted = []
        for cid, title, diff, db_score in db_records:
            # 本来の該当譜面 (chart_id) のスコアを探す
            exact_matches = [s for s in raw_scores if s.get("chart_id") == cid]
            if exact_matches:
                expected_score = exact_matches[0]["score"]
                if db_score != expected_score:
                    corrupted.append({
                        "chart_id": cid,
                        "title": title,
                        "chart_diff": diff,
                        "db_score": db_score,
                        "expected_score": expected_score
                    })

        assert len(corrupted) == 0, (
            f"スコアの難易度取り違え（EXPERT/LUNATICのスコアがMASTER譜面に誤爆上書き）が "
            f"{len(corrupted)} 件検出されました！例: {corrupted[:3]}"
        )

