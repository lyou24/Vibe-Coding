import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.models import Chart, DifficultyEnum

def seed_charts():
    db_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "opi_database.sqlite")
    engine = create_engine(f'sqlite:///{db_file}', echo=False)
    Session = sessionmaker(bind=engine)
    session = Session()

    # 初期テスト用楽曲データ（難易度13+以上、定数13.7以上）
    # ※実際のシステムでは外部APIやWikiからスクレイピングして一括更新する
    sample_charts = [
        {"chart_id": "starring_stars_mas", "title": "Starring Stars", "difficulty": DifficultyEnum.MASTER, "level": "13+", "chart_constant": 13.7},
        {"chart_id": "kanjou_acceleration_mas", "title": "感情アクセラレイション", "difficulty": DifficultyEnum.MASTER, "level": "14", "chart_constant": 14.0},
        {"chart_id": "trrricksters_mas", "title": "Trrricksters!!", "difficulty": DifficultyEnum.MASTER, "level": "14+", "chart_constant": 14.8},
        {"chart_id": "op1_fear_titan_mas", "title": "Op.I《fear-TITΛN-》", "difficulty": DifficultyEnum.MASTER, "level": "15", "chart_constant": 15.1},
        {"chart_id": "lateral_arc_mas", "title": "光焔のラテラルアーク", "difficulty": DifficultyEnum.MASTER, "level": "15", "chart_constant": 15.3},
        {"chart_id": "recoil_mas", "title": "Recoil", "difficulty": DifficultyEnum.MASTER, "level": "15+", "chart_constant": 15.7},
        {"chart_id": "apollo_mas", "title": "Apollo", "difficulty": DifficultyEnum.MASTER, "level": "15+", "chart_constant": 15.8},
        {"chart_id": "ongeki_mas", "title": "怨撃", "difficulty": DifficultyEnum.LUNATIC, "level": "15+", "chart_constant": 15.9},
    ]

    for c_data in sample_charts:
        # 重複チェック
        exists = session.query(Chart).filter_by(chart_id=c_data["chart_id"]).first()
        if not exists:
            chart = Chart(
                chart_id=c_data["chart_id"],
                title=c_data["title"],
                difficulty=c_data["difficulty"],
                level=c_data["level"],
                chart_constant=c_data["chart_constant"]
            )
            # 初期OPIパラメータの仮設定 (アンカー: 14.0 SSS = 1500)
            # 実際にはデータ解析後に更新される
            chart.opi_sss_x = 1500.0 + (c_data["chart_constant"] - 14.0) * 200.0
            chart.opi_sss_y = 40.0
            
            session.add(chart)
    
    session.commit()
    print("Seeding completed.")
    session.close()

if __name__ == "__main__":
    seed_charts()
