import os
import sys
import tempfile
import pytest
import asyncio
from datetime import datetime
from sqlalchemy.exc import IntegrityError
import socket
from unittest.mock import patch

# プロジェクトルートの追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.database.models import init_db, get_session_maker, Chart, Player, ScoreLog, DifficultyEnum
from src.crawler.ongeki_crawler import OngekiCrawler
from seed import seed_database, calculate_initial_chart_params


class TestDBUniqueConstraintAndTransactions:
    """DBの一意制約 (UniqueConstraint) およびトランザクション・整合性ストレステスト"""

    @pytest.fixture
    def temp_db(self):
        tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(tmpdir.name, "test_unique.sqlite")
        engine = init_db(db_path)
        yield db_path, engine
        engine.dispose()
        try:
            tmpdir.cleanup()
        except Exception:
            pass

    def test_direct_duplicate_insert_raises_integrity_error(self, temp_db):
        """同一 (user_id, chart_id) を直接INSERTした際にIntegrityErrorが発生することを実証"""
        db_path, engine = temp_db
        Session = get_session_maker(engine)
        session = Session()

        # マスタ準備
        chart = Chart(
            chart_id="1001_master",
            title="Test Song",
            difficulty=DifficultyEnum.MASTER,
            level="14",
            chart_constant=14.0
        )
        player = Player(user_id=1, player_name="TestPlayer", rating=15.0)
        session.add(chart)
        session.add(player)
        session.commit()

        # 1回目のスコアINSERT
        score1 = ScoreLog(user_id=1, chart_id="1001_master", score=1000000)
        session.add(score1)
        session.commit()

        # 2回目のスコアINSERT（同一 user_id, chart_id） -> IntegrityError を期待
        score2 = ScoreLog(user_id=1, chart_id="1001_master", score=1005000)
        session.add(score2)
        with pytest.raises(IntegrityError) as exc_info:
            session.commit()
        
        session.rollback()
        assert "UNIQUE constraint failed" in str(exc_info.value) or "uq_user_chart" in str(exc_info.value)
        session.close()

    def test_different_chart_same_user_allowed(self, temp_db):
        """同一ユーザーであっても異なる譜面（chart_id）であれば複数登録可能であることを実証"""
        db_path, engine = temp_db
        Session = get_session_maker(engine)
        session = Session()

        chart1 = Chart(chart_id="song_exp", title="Song", difficulty=DifficultyEnum.EXPERT, level="13+", chart_constant=13.7)
        chart2 = Chart(chart_id="song_mas", title="Song", difficulty=DifficultyEnum.MASTER, level="15", chart_constant=15.4)
        player = Player(user_id=2, player_name="Player2", rating=16.0)
        session.add_all([chart1, chart2, player])
        session.commit()

        s1 = ScoreLog(user_id=2, chart_id="song_exp", score=1009000)
        s2 = ScoreLog(user_id=2, chart_id="song_mas", score=995000)
        session.add_all([s1, s2])
        session.commit()

        count = session.query(ScoreLog).filter_by(user_id=2).count()
        assert count == 2
        session.close()

    def test_seeding_with_duplicate_scores_in_input_stream(self, temp_db):
        """シード入力リスト内に同一譜面の重複エントリが含まれていた場合のハンドリング耐性検証"""
        db_path, engine = temp_db

        seed_data = {
            "music_master": [
                {"chart_id": "test_chart_1", "title": "Dupe Song", "difficulty": "MASTER", "level": "14", "chart_constant": 14.2}
            ],
            "test_user": {
                "profile": {"user_id": 999, "player_name": "DupeTester", "rating": 17.5},
                "scores": [
                    {"chart_id": "test_chart_1", "title": "Dupe Song", "difficulty": "MASTER", "score": 990000},
                    {"chart_id": "test_chart_1", "title": "Dupe Song", "difficulty": "MASTER", "score": 1005000} # 重複
                ]
            }
        }

        # 重複データがあってもクラッシュせずに後勝ちまたは正常にUpsertされること
        seed_database(seed_data, db_path=db_path, include_population=False)

        Session = get_session_maker(engine)
        session = Session()
        logs = session.query(ScoreLog).filter_by(user_id=999, chart_id="test_chart_1").all()
        assert len(logs) == 1
        # 後勝ち更新されていること
        assert logs[0].score == 1005000
        assert logs[0].achieve_sss is True
        session.close()


class TestOfflineResilienceAndIsolation:
    """完全オフライン環境下での初期化・シード・独立性検証"""

    @pytest.fixture
    def temp_db(self):
        tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(tmpdir.name, "test_offline.sqlite")
        yield db_path
        try:
            tmpdir.cleanup()
        except Exception:
            pass

    def test_seed_database_strictly_zero_network_calls(self, temp_db):
        """ソケット作成を完全に遮断した状態（完全オフライン）でも seed_database が正常完了すること"""
        def blocked_socket(*args, **kwargs):
            raise OSError("Network call blocked in offline stress test")

        seed_data = {
            "music_master": [
                {"chart_id": "c1", "title": "Offline Song 1", "difficulty": "MASTER", "level": "14", "chart_constant": 14.0},
                {"chart_id": "c2", "title": "Offline Song 2", "difficulty": "MASTER", "level": "14+", "chart_constant": 14.5}
            ],
            "test_user": {
                "profile": {"user_id": 888, "player_name": "OfflineUser", "rating": 18.0},
                "scores": [
                    {"chart_id": "c1", "title": "Offline Song 1", "difficulty": "MASTER", "score": 1000000},
                    {"chart_id": "c2", "title": "Offline Song 2", "difficulty": "MASTER", "score": 1007500, "is_all_break": True, "is_full_bell": True}
                ]
            },
            "population_samples": [
                {"user_id": 90001, "player_name": "Pop1", "rating": 18.0, "total_opi": 1500.0}
            ]
        }

        with patch("socket.socket", side_effect=blocked_socket):
            # ソケット利用不能でもDB初期化およびシード投入が完結すること
            seed_database(seed_data, db_path=temp_db, include_population=True)

        engine = init_db(temp_db)
        Session = get_session_maker(engine)
        session = Session()
        assert session.query(Chart).count() == 2
        assert session.query(Player).count() == 2 # 888 + 90001
        assert session.query(ScoreLog).count() == 2
        session.close()
        engine.dispose()


class TestCrawlerAsyncContextManagerRobustness:
    """クローラーの非同期コンテキストマネージャ (__aenter__ / __aexit__) の高負荷・例外耐性検証"""

    @pytest.mark.asyncio
    async def test_crawler_context_manager_rapid_lifecycle(self):
        """100回連続で async with を実行してもセッションが正常にクローズされリークしないこと"""
        for _ in range(100):
            async with OngekiCrawler() as crawler:
                assert crawler.session is not None
                assert not crawler.session.closed
            assert crawler.session.closed

    @pytest.mark.asyncio
    async def test_crawler_context_manager_exception_safety(self):
        """コンテキスト内部で予期せぬ例外が発生しても必ずセッションがcloseされること"""
        crawler_ref = None
        try:
            async with OngekiCrawler() as crawler:
                crawler_ref = crawler
                assert not crawler.session.closed
                raise RuntimeError("Intentional error inside crawler context")
        except RuntimeError:
            pass

        assert crawler_ref is not None
        assert crawler_ref.session.closed


class TestProductionDataAndSpecParamsAudit:
    """実稼働シードデータ (seed_data.json) および本番DB (opi_database.sqlite) の厳密パラメータ監査"""

    def test_recollect_lines_uses_constant_based_params(self):
        """曲名別上書きを使わず、定数15.7から一貫した暫定値を生成すること"""
        params = calculate_initial_chart_params("Recollect Lines", 15.7)
        same_constant_params = calculate_initial_chart_params("別の曲", 15.7)
        assert params == same_constant_params
        assert params["opi_sss_x"] == 1840.0
        assert params["opi_sss_y"] == 40.0
        assert params["opi_abp_x"] == 2080.0
        assert params["opi_abp_y"] == 40.0

    def test_production_db_recollect_lines_record(self):
        """本番DBに Recollect Lines (MASTER) の定数ベース暫定値が反映されていること"""
        db_path = os.path.join(PROJECT_ROOT, "data", "opi_database.sqlite")
        if not os.path.exists(db_path):
            pytest.skip("Production DB not found")

        engine = init_db(db_path)
        Session = get_session_maker(engine)
        session = Session()

        recollect_master = session.query(Chart).filter(
            Chart.title == "Recollect Lines",
            Chart.difficulty == DifficultyEnum.MASTER
        ).first()
        assert recollect_master is not None, "Recollect Lines (MASTER) chart not found in production DB"
        assert recollect_master.chart_constant == 15.7
        assert recollect_master.opi_sss_x == 1840.0
        assert recollect_master.opi_abp_x == 2080.0
        session.close()
        engine.dispose()

    def test_production_db_no_duplicate_user_chart_pairs(self):
        """本番DBの全 score_logs テーブルにおいて (user_id, chart_id) の重複が0件であることを実証"""
        db_path = os.path.join(PROJECT_ROOT, "data", "opi_database.sqlite")
        if not os.path.exists(db_path):
            pytest.skip("Production DB not found")

        engine = init_db(db_path)
        Session = get_session_maker(engine)
        session = Session()

        from sqlalchemy import func
        duplicates = session.query(
            ScoreLog.user_id, ScoreLog.chart_id, func.count(ScoreLog.id)
        ).group_by(ScoreLog.user_id, ScoreLog.chart_id).having(func.count(ScoreLog.id) > 1).all()

        assert len(duplicates) == 0, f"Duplicate score logs found: {duplicates}"
        session.close()
        engine.dispose()


class TestScoreAchievementFlagsBoundaries:
    """各スコア境界値における達成フラグ（SS, SSS, SSS+, ABFB, AP）の厳密検証"""

    @pytest.fixture
    def temp_db(self):
        tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(tmpdir.name, "test_flags.sqlite")
        engine = init_db(db_path)
        yield db_path, engine
        engine.dispose()
        try:
            tmpdir.cleanup()
        except Exception:
            pass

    def test_score_achievement_boundary_conditions(self, temp_db):
        """990000, 1000000, 1007500, 1010000 の境界値におけるフラグ変化を実証"""
        db_path, engine = temp_db

        test_cases = [
            # (score, is_ab, is_fb, exp_s, exp_ss, exp_sss, exp_sssp, exp_abp)
            (974999, False, False, False, False, False, False, False),
            (975000, False, False, True,  False, False, False, False),
            (989999, False, False, True,  False, False, False, False),
            (990000, False, False, True,  True,  False, False, False),
            (999999, False, False, True,  True,  False, False, False),
            (1000000, False, False, True,  True,  True,  False, False),
            (1007499, True,  True,  True,  True,  True,  False, False),
            (1007500, False, False, True,  True,  True,  True,  False),
            (1007500, True,  True,  True,  True,  True,  True,  False),
            (1009999, True,  True,  True,  True,  True,  True,  False),
            (1010000, True,  True,  True,  True,  True,  True,  True),
        ]

        music_master = [
            {"chart_id": f"c_{i}", "title": f"Song {i}", "difficulty": "MASTER", "level": "14", "chart_constant": 14.0}
            for i in range(len(test_cases))
        ]
        scores = [
            {
                "chart_id": f"c_{i}",
                "title": f"Song {i}",
                "difficulty": "MASTER",
                "score": tc[0],
                "is_all_break": tc[1],
                "is_full_bell": tc[2]
            }
            for i, tc in enumerate(test_cases)
        ]

        seed_data = {
            "music_master": music_master,
            "test_user": {
                "profile": {"user_id": 555, "player_name": "BoundaryUser", "rating": 19.0},
                "scores": scores
            }
        }

        seed_database(seed_data, db_path=db_path, include_population=False)

        Session = get_session_maker(engine)
        session = Session()

        for i, tc in enumerate(test_cases):
            cid = f"c_{i}"
            log = session.query(ScoreLog).filter_by(user_id=555, chart_id=cid).first()
            assert log is not None
            assert log.achieve_s == tc[3], f"Case {i} S mismatch"
            assert log.achieve_ss == tc[4], f"Case {i} SS mismatch"
            assert log.achieve_sss == tc[5], f"Case {i} SSS mismatch"
            assert log.achieve_sssp == tc[6], f"Case {i} SSSP mismatch"
            assert log.achieve_abp == tc[7], f"Case {i} ABP mismatch"

        session.close()


class TestLargeScaleLoadStress:
    """10,000件規模の大量レコード投入負荷検証"""

    @pytest.fixture
    def temp_db(self):
        tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(tmpdir.name, "test_scale.sqlite")
        engine = init_db(db_path)
        yield db_path, engine
        engine.dispose()
        try:
            tmpdir.cleanup()
        except Exception:
            pass

    def test_heavy_population_and_score_load_seeding(self, temp_db):
        """母集団2500人超 + 譜面500件 + スコア1000件規模の一括シード処理が安定完了すること"""
        db_path, engine = temp_db

        charts = [
            {"chart_id": f"chart_{i}", "title": f"Song_{i}", "difficulty": "MASTER", "level": "14", "chart_constant": 14.0 + (i % 20) * 0.1}
            for i in range(500)
        ]
        scores = [
            {"chart_id": f"chart_{i}", "title": f"Song_{i}", "difficulty": "MASTER", "score": 1000000 + (i % 10000)}
            for i in range(500)
        ]
        pop = [
            {"user_id": 90000 + i, "player_name": f"P_{i}", "rating": 18.0 + (i % 30) * 0.1, "total_opi": 1500.0 + i}
            for i in range(2500)
        ]

        seed_data = {
            "music_master": charts,
            "test_user": {
                "profile": {"user_id": 7777, "player_name": "ScaleTester", "rating": 20.0},
                "scores": scores
            },
            "population_samples": pop
        }

        # 大規模シード投入
        seed_database(seed_data, db_path=db_path, include_population=True)

        Session = get_session_maker(engine)
        session = Session()

        assert session.query(Chart).count() == 500
        assert session.query(Player).count() == 2501 # 7777 + 2500 pop
        assert session.query(ScoreLog).count() == 500

        session.close()
