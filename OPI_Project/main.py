import os
import asyncio
import logging
from src.crawler.ongeki_crawler import OngekiCrawler
from src.analyzer.opi_calculator import OPICalculator
from src.database.models import init_db, get_session_maker, Player, ScoreLog, Chart

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# DB設定
DB_FILE = os.path.join(os.path.dirname(__file__), "data", "opi_database.sqlite")

async def run_crawling_task():
    logger.info("Starting crawling task...")
    
    engine = init_db(DB_FILE)
    Session = get_session_maker(engine)
    session = Session()

    crawler = OngekiCrawler()
    
    # 実際にはDB等から巡回対象のユーザーIDリストを取得する
    target_user_ids = [1, 2, 3] 
    
    for user_id in target_user_ids:
        # DB上の最終更新日時を取得
        player_db = session.query(Player).filter_by(user_id=user_id).first()
        last_crawled_at = player_db.log_updated_at if player_db else None

        profile = await crawler.fetch_user_profile(user_id, last_crawled_at=last_crawled_at)
        
        if profile:
            logger.info(f"Fetched profile for user {user_id}: {profile['player_name']} (Rating: {profile['rating']})")
            
            # DBのプレイヤー情報を更新または作成
            if not player_db:
                player_db = Player(user_id=user_id)
                session.add(player_db)
            player_db.player_name = profile['player_name']
            player_db.rating = profile['rating']
            player_db.log_updated_at = profile['updated_at']

            # スコア取得
            scores = await crawler.fetch_user_scores(user_id)
            if scores:
                logger.info(f"Fetched {len(scores)} scores for user {user_id}")
                
                # 対象のChartのキャッシュ（chart_id または (title, difficulty) による厳密照合）
                all_charts = session.query(Chart).all()
                chart_by_id = {c.chart_id: c for c in all_charts}
                chart_by_title_diff = {
                    (c.title, c.difficulty.name if hasattr(c.difficulty, "name") else str(c.difficulty).upper()): c
                    for c in all_charts
                }
                
                for s in scores:
                    chart = None
                    if s.get("chart_id") and s["chart_id"] in chart_by_id:
                        chart = chart_by_id[s["chart_id"]]
                    elif (s.get("title"), str(s.get("difficulty", "")).upper()) in chart_by_title_diff:
                        chart = chart_by_title_diff[(s.get("title"), str(s.get("difficulty", "")).upper())]
                    
                    if not chart:
                        continue
                    
                    # スコアログの更新または作成
                    score_log = session.query(ScoreLog).filter_by(user_id=user_id, chart_id=chart.chart_id).first()
                    if not score_log:
                        score_log = ScoreLog(user_id=user_id, chart_id=chart.chart_id)
                        session.add(score_log)
                    
                    score_val = s['score']
                    score_log.score = score_val
                    score_log.is_all_break = s['is_all_break']
                    score_log.is_full_bell = s['is_full_bell']
                    score_log.achieve_s = score_val >= 975000
                    score_log.achieve_ss = score_val >= 990000
                    score_log.achieve_sss = score_val >= 1000000
                    score_log.achieve_sssp = score_val >= 1007500
                    score_log.achieve_abp = score_val >= 1010000

            session.commit()
            
        # サーバー負荷軽減のためインターバルを入れる
        await asyncio.sleep(1)
        
    await crawler.close()
    session.close()
    logger.info("Crawling task completed.")

def run_analysis_task():
    logger.info("Starting analysis task...")
    engine = init_db(DB_FILE)
    Session = get_session_maker(engine)
    session = Session()

    calc = OPICalculator()
    all_charts = session.query(Chart).all()
    
    players = session.query(Player).all()
    for player in players:
        scores = session.query(ScoreLog).filter_by(user_id=player.user_id).all()
        achievements = calc.build_user_achievements(all_charts, scores)
            
        if achievements:
            est_opi = calc.estimate_user_opi(achievements, initial_theta=player.total_opi or 1500.0)
            player.total_opi = est_opi
            logger.info(f"User {player.user_id} - Estimated OPI: {est_opi:.1f} (Based on {len(achievements)} data points)")
        else:
            logger.info(f"User {player.user_id} - Not enough data for OPI estimation.")
            
    session.commit()
    session.close()
    logger.info("Analysis task completed.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OPI System")
    parser.add_argument("--task", choices=["crawl", "analyze", "recommend", "visualize"], help="Task to run")
    args = parser.parse_args()
    
    task = args.task

    # 引数がない場合は対話メニューを表示
    if not task:
        print("="*30)
        print(" OPI システム メニュー")
        print("="*30)
        print("1: データ収集 (Crawl)")
        print("2: OPI分析 (Analyze)")
        print("3: リコメンド抽出 (Recommend)")
        print("4: 分布図作成 (Visualize)")
        print("="*30)
        choice = input("実行するタスクの番号を入力してください (1-4): ").strip()
        
        if choice == '1':
            task = "crawl"
        elif choice == '2':
            task = "analyze"
        elif choice == '3':
            task = "recommend"
        elif choice == '4':
            task = "visualize"
        else:
            print("無効な入力です。終了します。")
            exit(1)
            
    if task == "crawl":
        asyncio.run(run_crawling_task())
    elif task == "analyze":
        run_analysis_task()
    elif task == "recommend":
        # リコメンドは現状引数が必要なため、テスト用ユーザー(ID=1)で呼び出す例
        from src.recommender.recommender import OPIRecommender
        import os
        db_file = os.path.join(os.path.dirname(__file__), "data", "opi_database.sqlite")
        recommender = OPIRecommender(db_file)
        user_id = input("リコメンド対象のユーザーIDを入力してください (デフォルト: 1): ").strip()
        user_id = int(user_id) if user_id.isdigit() else 1
        recs = recommender.get_recommendations(user_id=user_id)
        print(f"\n--- ユーザー {user_id} 向けリコメンド ---")
        for i, r in enumerate(recs, 1):
            print(f"{i}. {r['title']} (Lv.{r['level']} / {r['constant']}) - 目標OPI: {r['target_opi']:.1f}")
    elif task == "visualize":
        from src.visualizer.visualizer import OPIVisualizer
        import os
        db_file = os.path.join(os.path.dirname(__file__), "data", "opi_database.sqlite")
        vis = OPIVisualizer(db_file)
        out_path = os.path.join(os.path.dirname(__file__), "data", "opi_distribution.png")
        vis.create_distribution_plot(out_path)
        print(f"分布図を生成しました: {out_path}")
    else:
        logger.info(f"Task '{task}' is not fully implemented yet.")
