import os
import sys
import json
import asyncio
import argparse
import random
from datetime import datetime
from typing import List, Dict, Any

# プロジェクトルートをsys.pathに追加
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.database.models import init_db, get_session_maker, Chart, Player, ScoreLog, DifficultyEnum
from src.crawler.ongeki_crawler import OngekiCrawler
from src.analyzer.opi_calculator import OPICalculator
from src.analyzer.opi_policy import calculate_initial_chart_params as calculate_policy_params

DB_FILE = os.path.join(PROJECT_ROOT, "data", "opi_database.sqlite")
SEED_JSON_FILE = os.path.join(PROJECT_ROOT, "data", "seed_data.json")

# 要件定義書 3.2 のレーティング別分布統計データ（母集団サンプル生成用）
RATING_DISTRIBUTION_STATS = [
    {"target_rate": 18.0, "rate_min": 17.75, "rate_max": 18.24, "count": 452, "median_opi": 1480.2, "mean_opi": 1485.4, "iqr_min": 1421.5, "iqr_max": 1538.7},
    {"target_rate": 18.5, "rate_min": 18.25, "rate_max": 18.74, "count": 518, "median_opi": 1632.5, "mean_opi": 1637.1, "iqr_min": 1565.3, "iqr_max": 1692.8},
    {"target_rate": 19.0, "rate_min": 18.75, "rate_max": 19.24, "count": 615, "median_opi": 1791.0, "mean_opi": 1796.8, "iqr_min": 1725.4, "iqr_max": 1848.2},
    {"target_rate": 19.5, "rate_min": 19.25, "rate_max": 19.74, "count": 437, "median_opi": 1942.3, "mean_opi": 1945.5, "iqr_min": 1882.1, "iqr_max": 2005.9},
    {"target_rate": 20.0, "rate_min": 19.75, "rate_max": 20.24, "count": 283, "median_opi": 2076.8, "mean_opi": 2085.2, "iqr_min": 2023.7, "iqr_max": 2131.4},
    {"target_rate": 20.5, "rate_min": 20.25, "rate_max": 20.74, "count": 156, "median_opi": 2235.1, "mean_opi": 2228.4, "iqr_min": 2185.0, "iqr_max": 2282.6},
    {"target_rate": 21.0, "rate_min": 20.75, "rate_max": 21.24, "count": 42,  "median_opi": 2310.5, "mean_opi": 2305.2, "iqr_min": 2268.3, "iqr_max": 2345.1},
]

def generate_population_samples() -> List[Dict[str, Any]]:
    """要件定義書 3.2 に準拠した母集団サンプルプレイヤー群を生成"""
    samples = []
    user_id_counter = 90001
    random.seed(42)  # 再現性の担保

    for stat in RATING_DISTRIBUTION_STATS:
        # IQRから標準偏差の近似値（IQR ≈ 1.349 * σ）
        iqr = stat["iqr_max"] - stat["iqr_min"]
        sigma = max(iqr / 1.349, 15.0)
        mean_val = stat["mean_opi"]

        for _ in range(stat["count"]):
            r = round(random.uniform(stat["rate_min"], stat["rate_max"]), 3)
            opi = round(random.gauss(mean_val, sigma), 1)
            samples.append({
                "user_id": user_id_counter,
                "player_name": f"Player_{user_id_counter}",
                "rating": r,
                "total_opi": opi
            })
            user_id_counter += 1

    return samples

async def fetch_and_build_seed_data(crawler: OngekiCrawler) -> Dict[str, Any]:
    """実サイトから全譜面マスタおよびテストユーザー10605のデータを取得してシード辞書を構築"""
    print("実サイト(ongeki-score.net)より譜面マスタ(定数14.0以上)を取得中...")
    music_master = await crawler.fetch_music_master(min_constant=14.0)
    print(f"-> 譜面マスタ取得完了: {len(music_master)} 譜面")

    test_user_id = 10605
    print(f"実サイトよりテストユーザー ID {test_user_id} のプロフィールを取得中...")
    profile = await crawler.fetch_user_profile(test_user_id)
    if profile:
        print(f"-> プロフィール取得成功: {profile['player_name']} (Rating: {profile['rating']}, Updated: {profile['updated_at']})")
        # datetime を JSON シリアライズ可能な文字列に変換
        profile_serialized = {
            "user_id": profile["user_id"],
            "player_name": profile["player_name"],
            "rating": profile["rating"],
            "updated_at": profile["updated_at"].isoformat() if profile["updated_at"] else None
        }
    else:
        print("-> プロフィール取得失敗。フォールバック値を使用します。")
        profile_serialized = {
            "user_id": 10605,
            "player_name": "ＮＥＧＩＮＥ",
            "rating": 19.950,
            "updated_at": "2026-09-10T00:00:00"
        }

    print(f"実サイトよりテストユーザー ID {test_user_id} のスコアログを取得中...")
    scores = await crawler.fetch_user_scores(test_user_id)
    print(f"-> スコアログ取得完了: {len(scores)} 件")

    print("要件定義書3.2に基づく母集団サンプルデータを生成中...")
    population = generate_population_samples()
    print(f"-> 母集団サンプル生成完了: {len(population)} 人")

    seed_dict = {
        "generated_at": datetime.now().isoformat(),
        "music_master": music_master,
        "test_user": {
            "profile": profile_serialized,
            "scores": scores
        },
        "population_samples": population
    }

    return seed_dict

def calculate_initial_chart_params(title: str, chart_constant: float) -> Dict[str, float]:
    """譜面定数から暫定の初期OPIパラメータを算出する。"""
    return calculate_policy_params(chart_constant)

def seed_database(seed_data: Dict[str, Any], db_path: str = DB_FILE, include_population: bool = True):
    """シードデータをSQLiteデータベースに投入"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    engine = init_db(db_path)
    Session = get_session_maker(engine)
    session = Session()

    try:
        # 1. charts テーブルの投入 / 更新
        print(f"charts テーブルへ譜面マスタを登録中 ({len(seed_data['music_master'])} 件)...")
        existing_charts = {c.chart_id: c for c in session.query(Chart).all()}
        
        # 既存の文字化けサンプル曲（旧8曲等でchart_idが不一致なもの）のクリーンアップ
        master_chart_ids = set(m["chart_id"] for m in seed_data["music_master"])
        for cid, chart_obj in existing_charts.items():
            if cid not in master_chart_ids:
                session.delete(chart_obj)
        session.commit()

        for m in seed_data["music_master"]:
            cid = m["chart_id"]
            title = m["title"]
            diff_str = m["difficulty"].upper()
            try:
                diff_enum = DifficultyEnum[diff_str]
            except KeyError:
                diff_enum = DifficultyEnum.MASTER

            level = m.get("level", "")
            constant = float(m["chart_constant"])
            opi_params = calculate_initial_chart_params(title, constant)

            chart_obj = session.query(Chart).filter_by(chart_id=cid).first()
            if not chart_obj:
                chart_obj = Chart(chart_id=cid)
                session.add(chart_obj)

            chart_obj.title = title
            chart_obj.difficulty = diff_enum
            chart_obj.level = level
            chart_obj.chart_constant = constant
            chart_obj.is_active = True
            
            chart_obj.opi_ss_x = opi_params["opi_ss_x"]
            chart_obj.opi_ss_y = opi_params["opi_ss_y"]
            chart_obj.opi_sss_x = opi_params["opi_sss_x"]
            chart_obj.opi_sss_y = opi_params["opi_sss_y"]
            chart_obj.opi_sssp_x = opi_params["opi_sssp_x"]
            chart_obj.opi_sssp_y = opi_params["opi_sssp_y"]
            chart_obj.opi_abfb_x = opi_params["opi_abfb_x"]
            chart_obj.opi_abfb_y = opi_params["opi_abfb_y"]
            chart_obj.opi_ap_x = opi_params["opi_ap_x"]
            chart_obj.opi_ap_y = opi_params["opi_ap_y"]

        session.commit()
        total_charts = session.query(Chart).count()
        print(f"-> charts 登録完了 (現在レコード数: {total_charts})")

        # 2. players テーブル（テストユーザー10605）の登録
        test_user = seed_data.get("test_user", {})
        profile = test_user.get("profile", {})
        uid = profile.get("user_id", 10605)
        name = profile.get("player_name", "ＮＥＧＩＮＥ")
        rating = profile.get("rating", 19.950)
        up_str = profile.get("updated_at")
        updated_dt = datetime.fromisoformat(up_str) if up_str else datetime(2026, 9, 10)

        player_obj = session.query(Player).filter_by(user_id=uid).first()
        if not player_obj:
            player_obj = Player(user_id=uid)
            session.add(player_obj)

        player_obj.player_name = name
        player_obj.rating = rating
        player_obj.log_updated_at = updated_dt
        session.commit()
        print(f"-> テストユーザー 登録完了: {name} (ID: {uid}, Rating: {rating})")

        # 3. score_logs テーブル（ユーザー10605のスコア）の登録
        scores = test_user.get("scores", [])
        print(f"score_logs テーブルへスコアログを登録中 (対象スコア数: {len(scores)} 件)...")

        # 高速照合用マップの構築
        all_charts = session.query(Chart).all()
        chart_by_id = {c.chart_id: c for c in all_charts}
        chart_by_title_diff = {(c.title, c.difficulty.name): c for c in all_charts}

        matched_chart_ids = set()
        for s in scores:
            target_chart = None
            # 優先度1: chart_id 一致
            if s.get("chart_id") and s["chart_id"] in chart_by_id:
                target_chart = chart_by_id[s["chart_id"]]
            # 優先度2: (title, difficulty) 一致
            elif (s.get("title"), s.get("difficulty", "").upper()) in chart_by_title_diff:
                target_chart = chart_by_title_diff[(s["title"], s.get("difficulty", "").upper())]

            if not target_chart:
                continue

            matched_chart_ids.add(target_chart.chart_id)
            score_val = s["score"]
            is_ab = bool(s.get("is_all_break", False))
            is_fb = bool(s.get("is_full_bell", False))

            log_obj = session.query(ScoreLog).filter_by(user_id=uid, chart_id=target_chart.chart_id).first()
            if not log_obj:
                log_obj = ScoreLog(user_id=uid, chart_id=target_chart.chart_id)
                session.add(log_obj)

            log_obj.score = score_val
            log_obj.is_all_break = is_ab
            log_obj.is_full_bell = is_fb
            log_obj.achieve_ss = score_val >= 990000
            log_obj.achieve_sss = score_val >= 1000000
            log_obj.achieve_sssp = score_val >= 1007500
            log_obj.achieve_abfb = (score_val >= 1007500 and is_ab and is_fb)
            log_obj.achieve_ap = score_val == 1010000

        if matched_chart_ids:
            session.query(ScoreLog).filter(
                ScoreLog.user_id == uid,
                ~ScoreLog.chart_id.in_(matched_chart_ids),
            ).delete(synchronize_session=False)
        else:
            session.query(ScoreLog).filter_by(user_id=uid).delete(
                synchronize_session=False
            )

        session.commit()
        print(f"-> score_logs 登録完了 (譜面マスタ紐付け完了数: {len(matched_chart_ids)} 件)")

        # ユーザー10605の初期OPI算出・DB保存
        calc = OPICalculator()
        user_scores = session.query(ScoreLog).filter_by(user_id=uid).all()
        achievements = calc.build_user_achievements(all_charts, user_scores)
        if achievements:
            est_opi = calc.estimate_user_opi(achievements, initial_theta=player_obj.total_opi or 1500.0)
            player_obj.total_opi = est_opi
            session.commit()
            print(f"-> 初期OPI算出完了: {est_opi:.1f} (ユーザーID: {uid}, 成否ベクトル数: {len(achievements)} 件)")

        # 4. 母集団サンプル（レート分布図用）の登録（オプション）
        if include_population and "population_samples" in seed_data:
            pop_samples = seed_data["population_samples"]
            print(f"レーティング分布用 母集団サンプルプレイヤーを登録中 ({len(pop_samples)} 人)...")
            
            # 既存のサンプル（user_id >= 90000）を一度削除して再投入
            session.query(Player).filter(Player.user_id >= 90000).delete()
            session.commit()

            bulk_players = [
                Player(
                    user_id=p["user_id"],
                    player_name=p["player_name"],
                    rating=p["rating"],
                    total_opi=p["total_opi"],
                    log_updated_at=datetime(2026, 9, 10),
                    system_updated_at=datetime.now()
                )
                for p in pop_samples
            ]
            session.bulk_save_objects(bulk_players)
            session.commit()
            total_players = session.query(Player).count()
            print(f"-> 母集団プレイヤー 登録完了 (総プレイヤー数: {total_players} 人)")

        print("全シードデータのDB投入が正常に完了しました。")

    except Exception as e:
        session.rollback()
        print(f"シード投入中にエラーが発生しました: {e}")
        raise
    finally:
        session.close()

async def main():
    parser = argparse.ArgumentParser(description="OPI データベース シード投入スクリプト")
    parser.add_argument("--fetch", action="store_true", help="実サイトから最新データをフェッチして seed_data.json を更新する")
    parser.add_argument("--reset-db", action="store_true", help="既存のDBファイルを削除して新規再構築する")
    parser.add_argument("--no-population", action="store_true", help="母集団サンプルプレイヤーの登録をスキップする")
    args = parser.parse_args()

    if args.reset_db and os.path.exists(DB_FILE):
        print(f"既存DBファイル ({DB_FILE}) を削除します...")
        try:
            os.remove(DB_FILE)
            print("DBファイルを削除しました。")
        except Exception as e:
            print(f"DBファイル削除エラー: {e}")

    seed_data = None

    # 1. シードデータの用意（既存JSONのロード または 実サイトからの取得）
    if not args.fetch and os.path.exists(SEED_JSON_FILE):
        print(f"ローカルシードファイル ({SEED_JSON_FILE}) からデータを読み込みます...")
        try:
            with open(SEED_JSON_FILE, "r", encoding="utf-8") as f:
                seed_data = json.load(f)
            print(f"-> ロード成功: 譜面数 {len(seed_data.get('music_master', []))} 件, テストスコア数 {len(seed_data.get('test_user', {}).get('scores', []))} 件")
        except Exception as e:
            print(f"ローカルシードファイル読み込み失敗: {e}。実サイトからフェッチします。")
            seed_data = None

    if seed_data is None:
        print("実サイト(ongeki-score.net)からデータを取得してシードデータを新規構築します...")
        crawler = OngekiCrawler()
        try:
            seed_data = await fetch_and_build_seed_data(crawler)
            os.makedirs(os.path.dirname(SEED_JSON_FILE), exist_ok=True)
            with open(SEED_JSON_FILE, "w", encoding="utf-8") as f:
                json.dump(seed_data, f, ensure_ascii=False, indent=2)
            print(f"-> シードデータを保存しました: {SEED_JSON_FILE}")
        finally:
            await crawler.close()

    # 2. データベースへ投入
    seed_database(seed_data, db_path=DB_FILE, include_population=not args.no_population)

if __name__ == "__main__":
    asyncio.run(main())
