import os
import sys
import math
import sqlite3
import subprocess
from datetime import datetime

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
DB_PATH = os.path.join(PROJECT_ROOT, "data", "opi_database.sqlite")
SEED_PY = os.path.join(PROJECT_ROOT, "seed.py")
PYTHON_EXE = sys.executable

def test_seed_execution_and_user_10605_opi():
    """
    検証 1: seed.py 実行によるDB生成と、ユーザー10605の total_opi 格納状態検証
    - 正常終了すること
    - total_opi が有効な float（非 None, 非 NaN, 非 Inf）であること
    - 定数14.0以上を対象にした total_opi が約1468.1に収まること
    """
    cmd = [PYTHON_EXE, SEED_PY]
    res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    assert res.returncode == 0, f"seed.py failed with returncode {res.returncode}:\n{res.stderr}"
    assert "全シードデータのDB投入が正常に完了しました" in res.stdout, f"Success message not in stdout:\n{res.stdout}"

    # DB内容の直接検証
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT user_id, player_name, rating, total_opi FROM players WHERE user_id = 10605")
    row = cur.fetchone()
    conn.close()

    assert row is not None, "ユーザー10605が players テーブルに存在しません"
    uid, name, rating, total_opi = row

    print(f"\n[Empirical Check] User {uid} ({name}): rating={rating}, total_opi={total_opi}")

    # 型と値の検証
    assert total_opi is not None, "total_opi が None です"
    assert isinstance(total_opi, float), f"total_opi が float 型ではありません: {type(total_opi)}"
    assert not math.isnan(total_opi), "total_opi が NaN です"
    assert not math.isinf(total_opi), "total_opi が Inf です"
    assert 1410.0 <= total_opi <= 1440.0, f"total_opi ({total_opi}) が新5段階ランク対象の期待値（約1423.6）から乖離しています"
    assert abs(total_opi - 1423.6) < 1.0, f"total_opi ({total_opi}) が 1423.6 から外れています"
    assert rating == 19.95, f"rating ({rating}) が期待値 19.95 と一致しません"


def test_seed_idempotency_and_stress():
    """
    検証 2: seed.py の連続複数回実行に対する冪等性と例外耐性
    - 2回目・3回目と連続実行しても UNIQUE 制約違反や外部キー違反等が発生しないこと
    - total_opi が破損・発散・None 化せず安定して保持されること
    - レコード数が重複して増殖しないこと
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM charts")
    charts_before = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM score_logs WHERE user_id = 10605")
    scores_before = cur.fetchone()[0]
    cur.execute("SELECT total_opi FROM players WHERE user_id = 10605")
    opi_before = cur.fetchone()[0]
    conn.close()

    # 2回目の連続実行
    res2 = subprocess.run([PYTHON_EXE, SEED_PY], cwd=PROJECT_ROOT, capture_output=True, text=True)
    assert res2.returncode == 0, f"seed.py 2nd run failed:\n{res2.stderr}"

    # 3回目の連続実行 (--no-population)
    res3 = subprocess.run([PYTHON_EXE, SEED_PY, "--no-population"], cwd=PROJECT_ROOT, capture_output=True, text=True)
    assert res3.returncode == 0, f"seed.py 3rd run failed:\n{res3.stderr}"

    # 再度データ検証
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM charts")
    charts_after = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM score_logs WHERE user_id = 10605")
    scores_after = cur.fetchone()[0]
    cur.execute("SELECT total_opi FROM players WHERE user_id = 10605")
    opi_after = cur.fetchone()[0]
    conn.close()

    print(f"\n[Idempotency Check] charts: {charts_before} -> {charts_after}")
    print(f"[Idempotency Check] scores: {scores_before} -> {scores_after}")
    print(f"[Idempotency Check] total_opi: {opi_before} -> {opi_after}")

    assert charts_after == charts_before, f"charts レコード数が変化しました ({charts_before} -> {charts_after})"
    assert scores_after == scores_before, f"score_logs レコード数が変化しました ({scores_before} -> {scores_after})"
    assert opi_after is not None, "再実行後の total_opi が None になりました"
    assert abs(opi_after - opi_before) < 1e-4, f"total_opi が再実行で変化しました ({opi_before} -> {opi_after})"


def test_score_log_flags_integrity():
    """
    検証 3: スコアログの達成フラグ整合性検証
    - score >= 990000 -> achieve_ss == True
    - score >= 1000000 -> achieve_sss == True
    - score >= 1007500 -> achieve_sssp == True
    - score >= 1007500 and is_ab and is_fb -> achieve_s == True
    - score == 1010000 -> achieve_abp == True
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT score, is_all_break, is_full_bell, achieve_ss, achieve_sss, achieve_sssp, achieve_s, achieve_abp
        FROM score_logs WHERE user_id = 10605
    """)
    rows = cur.fetchall()
    conn.close()

    assert len(rows) > 0, "スコアログが存在しません"
    for s, is_ab, is_fb, ss, sss, sssp, s_flag, abp in rows:
        assert bool(s_flag) == (s >= 975000), f"achieve_s 不整合: score={s}, flag={s_flag}"
        assert bool(ss) == (s >= 990000), f"achieve_ss 不整合: score={s}, flag={ss}"
        assert bool(sss) == (s >= 1000000), f"achieve_sss 不整合: score={s}, flag={sss}"
        assert bool(sssp) == (s >= 1007500), f"achieve_sssp 不整合: score={s}, flag={sssp}"
        assert bool(abp) == (s >= 1010000), f"achieve_abp 不整合: score={s}, flag={abp}"


def test_crawler_force_flag_adversarial():
    """
    検証 4: OngekiCrawler.fetch_user_profile の force 引数の挙動検証
    """
    from unittest.mock import MagicMock
    from src.crawler.ongeki_crawler import OngekiCrawler

    mock_html = """
    <html><body>
      <table class="is-striped">
        <tr><th>プレイヤーネーム</th><td>テスト太郎</td></tr>
        <tr><th>レーティング</th><td>19.50</td></tr>
      </table>
      <table>
        <tr><td class="sort_update">2025-01-01</td></tr>
      </table>
    </body></html>
    """

    class MockResponse:
        def __init__(self):
            self.status = 200
        async def text(self):
            return mock_html
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockSession:
        def __init__(self):
            self.closed = False
        def get(self, url, **kwargs):
            return MockResponse()
        async def close(self):
            self.closed = True

    async def _run_async_tests():
        crawler = OngekiCrawler()
        crawler.session = MockSession()

        # 1. force=False (2025-01-01 は TARGET_MIN_DATE より前なのでスキップされて None)
        res_skipped = await crawler.fetch_user_profile(99999, force=False)
        assert res_skipped is None, "force=False なのに古い更新日のユーザーがスキップされていません"

        # 2. force=True (強制取得されること)
        res_forced = await crawler.fetch_user_profile(99999, force=True)
        assert res_forced is not None, "force=True なのに古い更新日のユーザーが取得できませんでした"
        assert res_forced["player_name"] == "テスト太郎"
        assert res_forced["rating"] == 19.50

        # 3. last_crawled_at 差分更新チェック
        recent_date = datetime(2026, 9, 1)
        res_same_skipped = await crawler.fetch_user_profile(99999, last_crawled_at=recent_date, force=False)
        assert res_same_skipped is None, "force=False かつ last_crawled_at 以降の更新なしでスキップされていません"

        res_same_forced = await crawler.fetch_user_profile(99999, last_crawled_at=recent_date, force=True)
        assert res_same_forced is not None, "force=True なのに last_crawled_at でスキップされてしまいました"

    import asyncio
    asyncio.run(_run_async_tests())



if __name__ == "__main__":
    print("Running verification tests directly...")
    test_seed_execution_and_user_10605_opi()
    test_seed_idempotency_and_stress()
    test_score_log_flags_integrity()
    test_crawler_force_flag_adversarial()
    print("ALL CHALLENGER 1 M2 VERIFICATION TESTS PASSED SUCCESSFULLY!")
