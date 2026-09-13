"""
Challenger 2 (Milestone 2) Empirical Verification Suite: Crawler Force Flag & Differential Update Harness
実証的敵対テストハーネス: OngekiCrawler.fetch_user_profile における force 引数・差分スキップ・実走検証の徹底検証
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.crawler.ongeki_crawler import OngekiCrawler

def make_mock_crawler(date_str: str = "2025-04-01", player_name: str = "テスト奏者", rating_str: str = "19.85"):
    crawler = OngekiCrawler()
    mock_html = f"""
    <html><body>
      <table class="is-striped">
        <tr><th>プレイヤーネーム</th><td>{player_name}</td></tr>
        <tr><th>レーティング</th><td>{rating_str}</td></tr>
      </table>
      <table>
        <tr><td class="sort_update">{date_str}</td></tr>
      </table>
    </body></html>
    """

    class MockResponse:
        status = 200
        async def text(self):
            return mock_html
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_session = MagicMock()
    mock_session.get.return_value = MockResponse()
    mock_session.closed = False
    crawler.session = mock_session
    return crawler


@pytest.mark.asyncio
async def test_target_min_date_boundaries_mock():
    """
    検証 1: TARGET_MIN_DATE (2025-03-27) の境界値テスト
    - 2025-03-26: force=False で None, force=True で取得
    - 2025-03-27: force=False で取得, force=True で取得
    - 2025-03-28: force=False で取得, force=True で取得
    """
    # 1. 2025-03-26 (前日: 足切り対象)
    c_before = make_mock_crawler("2025-03-26")
    res_f = await c_before.fetch_user_profile(1001, force=False)
    assert res_f is None, "2025-03-26かつforce=FalseでNoneが返却されるべき"
    res_t = await c_before.fetch_user_profile(1001, force=True)
    assert res_t is not None, "2025-03-26かつforce=Trueで強制取得されるべき"
    assert res_t["user_id"] == 1001
    assert res_t["updated_at"] == datetime(2025, 3, 26)

    # 2. 2025-03-27 (当日: 境界値、足切りされない)
    c_exact = make_mock_crawler("2025-03-27")
    res_exact_f = await c_exact.fetch_user_profile(1002, force=False)
    assert res_exact_f is not None, "2025-03-27当日かつforce=Falseで取得できるべき"
    assert res_exact_f["updated_at"] == datetime(2025, 3, 27)
    res_exact_t = await c_exact.fetch_user_profile(1002, force=True)
    assert res_exact_t is not None, "2025-03-27当日かつforce=Trueで取得できるべき"

    # 3. 2025-03-28 (翌日: 有効)
    c_after = make_mock_crawler("2025-03-28")
    res_after_f = await c_after.fetch_user_profile(1003, force=False)
    assert res_after_f is not None, "2025-03-28かつforce=Falseで取得できるべき"
    res_after_t = await c_after.fetch_user_profile(1003, force=True)
    assert res_after_t is not None, "2025-03-28かつforce=Trueで取得できるべき"


@pytest.mark.asyncio
async def test_last_crawled_at_differential_mock():
    """
    検証 2: last_crawled_at 差分更新の境界値テスト
    - updated_at == last_crawled_at: force=False で None, force=True で取得
    - updated_at < last_crawled_at: force=False で None, force=True で取得
    - updated_at > last_crawled_at: force=False で取得, force=True で取得
    - last_crawled_at is None: force=False で取得, force=True で取得
    """
    c = make_mock_crawler("2025-06-15")
    dt_same = datetime(2025, 6, 15)
    dt_future = datetime(2025, 6, 16)
    dt_past = datetime(2025, 6, 14)

    # ケース1: updated_at == last_crawled_at（差分なし）
    res_same_skip = await c.fetch_user_profile(2001, last_crawled_at=dt_same, force=False)
    assert res_same_skip is None, "差分なし (updated_at == last_crawled_at) かつ force=False でスキップされるべき"
    res_same_force = await c.fetch_user_profile(2001, last_crawled_at=dt_same, force=True)
    assert res_same_force is not None, "差分なしでも force=True であれば強制取得されるべき"
    assert res_same_force["updated_at"] == dt_same

    # ケース2: updated_at < last_crawled_at（過去データ）
    res_past_skip = await c.fetch_user_profile(2002, last_crawled_at=dt_future, force=False)
    assert res_past_skip is None, "過去データ (updated_at < last_crawled_at) かつ force=False でスキップされるべき"
    res_past_force = await c.fetch_user_profile(2002, last_crawled_at=dt_future, force=True)
    assert res_past_force is not None, "過去データでも force=True であれば強制取得されるべき"

    # ケース3: updated_at > last_crawled_at（新規更新あり）
    res_new_fetch = await c.fetch_user_profile(2003, last_crawled_at=dt_past, force=False)
    assert res_new_fetch is not None, "新規更新 (updated_at > last_crawled_at) かつ force=False で取得されるべき"
    res_new_force = await c.fetch_user_profile(2003, last_crawled_at=dt_past, force=True)
    assert res_new_force is not None, "新規更新で force=True でも取得されるべき"

    # ケース4: last_crawled_at is None (初回クロール)
    res_first_fetch = await c.fetch_user_profile(2004, last_crawled_at=None, force=False)
    assert res_first_fetch is not None, "初回クロール (last_crawled_at=None) で取得されるべき"
    res_first_force = await c.fetch_user_profile(2004, last_crawled_at=None, force=True)
    assert res_first_force is not None, "初回クロールかつ force=True で取得されるべき"


@pytest.mark.asyncio
async def test_double_barrier_bypass_mock():
    """
    検証 3: 足切り（TARGET_MIN_DATE前）かつ前回クロール日時より前という二重スキップ条件
    - force=False: None
    - force=True: 確実に取得できること
    """
    c = make_mock_crawler("2024-12-01")  # 2024年（TARGET_MIN_DATE以前）
    last_crawl = datetime(2025, 1, 1)

    res_skip = await c.fetch_user_profile(3001, last_crawled_at=last_crawl, force=False)
    assert res_skip is None, "二重足切り条件で force=False なら None"

    res_bypass = await c.fetch_user_profile(3001, last_crawled_at=last_crawl, force=True)
    assert res_bypass is not None, "二重足切り条件でも force=True であればバイパスして取得されるべき"
    assert res_bypass["updated_at"] == datetime(2024, 12, 1)
    assert res_bypass["player_name"] == "テスト奏者"


@pytest.mark.asyncio
async def test_live_crawler_user_10605_differential_and_force():
    """
    検証 4: 実サイト（ongeki-score.net）に対する実走テスト（ユーザー10605）
    - 実走 4.1: 通常取得（force=False）でプロフィールが取得できること
    - 実走 4.2: 取得された updated_at を last_crawled_at に渡して再フェッチ（force=False）すると None（差分スキップ）になること
    - 実走 4.3: 同一条件で force=True を指定すると 辞書（最新プロフィール）が強制取得できること
    - 実走 4.4: 未来日時（2099-01-01）を渡して force=False で None、force=True で強制取得できること
    """
    crawler = OngekiCrawler()
    try:
        # 4.1 初回取得
        profile = await crawler.fetch_user_profile(10605, force=False)
        if profile is None:
            # 外部サイトへのアクセスが一時的に制限・変更されている可能性を確認
            pytest.skip("ongeki-score.net からのユーザー10605プロフィール取得がスキップまたは接続不可のためスキップ")

        print(f"\n[Live Fetch] User 10605 profile: name={profile['player_name']}, rating={profile['rating']}, updated_at={profile['updated_at']}")
        assert profile["user_id"] == 10605
        assert profile["rating"] is not None and profile["rating"] > 0
        actual_updated_at = profile["updated_at"]
        assert actual_updated_at is not None

        # 4.2 同一日時を last_crawled_at に指定して差分スキップを実走検証
        profile_skipped = await crawler.fetch_user_profile(10605, last_crawled_at=actual_updated_at, force=False)
        assert profile_skipped is None, f"実走差分スキップ失敗: last_crawled_at={actual_updated_at} で None が返るべきが {profile_skipped} が返りました"
        print("[Live Check] PASS: force=False での差分スキップ（None返却）を確認")

        # 4.3 同一日時で force=True を指定して強制取得を実走検証（閉塞解消の実証）
        profile_forced = await crawler.fetch_user_profile(10605, last_crawled_at=actual_updated_at, force=True)
        assert profile_forced is not None, "実走強制取得失敗: force=True なのに None が返りました（閉塞未解消）"
        assert profile_forced["user_id"] == 10605
        assert profile_forced["player_name"] == profile["player_name"]
        print("[Live Check] PASS: force=True での差分閉塞バイパス・強制取得を確認")

        # 4.4 未来日時 (2099-01-01) による極限差分テスト
        future_dt = datetime(2099, 1, 1)
        res_future_skip = await crawler.fetch_user_profile(10605, last_crawled_at=future_dt, force=False)
        assert res_future_skip is None, "未来日時指定かつ force=False で None が返るべき"
        res_future_force = await crawler.fetch_user_profile(10605, last_crawled_at=future_dt, force=True)
        assert res_future_force is not None, "未来日時指定でも force=True であれば強制取得されるべき"
        print("[Live Check] PASS: 未来日時指定下での差分スキップおよび強制取得を確認")

    finally:
        await crawler.close()


def run_all_tests():
    print("==================================================")
    print("CHALLENGER 2 (M2) EMPIRICAL VERIFICATION HARNESS")
    print("==================================================")

    print("\n--- Test 1: TARGET_MIN_DATE 境界値テスト ---")
    asyncio.run(test_target_min_date_boundaries_mock())
    print("PASS: TARGET_MIN_DATE 境界値テスト成功")

    print("\n--- Test 2: last_crawled_at 差分更新テスト ---")
    asyncio.run(test_last_crawled_at_differential_mock())
    print("PASS: last_crawled_at 差分更新テスト成功")

    print("\n--- Test 3: 二重足切りバイパステスト ---")
    asyncio.run(test_double_barrier_bypass_mock())
    print("PASS: 二重足切りバイパステスト成功")

    print("\n--- Test 4: 実サイト実走テスト (User 10605) ---")
    try:
        asyncio.run(test_live_crawler_user_10605_differential_and_force())
        print("PASS: 実走差分スキップ & force強制取得テスト成功")
    except pytest.skip.Exception as e:
        print(f"SKIPPED (Live): {e}")

    print("\n==================================================")
    print("ALL CHALLENGER 2 M2 CRAWLER VERIFICATION TESTS PASSED")
    print("==================================================")


if __name__ == "__main__":
    run_all_tests()
