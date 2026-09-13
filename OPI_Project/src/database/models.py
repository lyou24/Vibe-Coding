import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import enum

Base = declarative_base()

class DifficultyEnum(enum.Enum):
    BASIC = "BASIC"
    ADVANCED = "ADVANCED"
    EXPERT = "EXPERT"
    MASTER = "MASTER"
    LUNATIC = "LUNATIC"

class Chart(Base):
    """楽曲マスタ (charts)"""
    __tablename__ = 'charts'

    chart_id = Column(String(64), primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    difficulty = Column(Enum(DifficultyEnum), nullable=False, default=DifficultyEnum.MASTER)
    level = Column(String(8), nullable=False)  # 例: '13+', '14'
    chart_constant = Column(Float, nullable=False) # 譜面定数
    is_active = Column(Boolean, default=True)

    # 難易度パラメータ (OPI用) - 算出後に更新する
    opi_ss_x = Column(Float, nullable=True)
    opi_ss_y = Column(Float, nullable=True)
    opi_sss_x = Column(Float, nullable=True)
    opi_sss_y = Column(Float, nullable=True)
    opi_sssp_x = Column(Float, nullable=True)
    opi_sssp_y = Column(Float, nullable=True)
    opi_abfb_x = Column(Float, nullable=True)
    opi_abfb_y = Column(Float, nullable=True)
    opi_ap_x = Column(Float, nullable=True)
    opi_ap_y = Column(Float, nullable=True)

    scores = relationship("ScoreLog", back_populates="chart")


class Player(Base):
    """プレイヤーマスタ (players)"""
    __tablename__ = 'players'

    user_id = Column(Integer, primary_key=True, index=True) # OngekiScoreLogのユーザーID
    player_name = Column(String(64), nullable=False)
    rating = Column(Float, nullable=True)
    total_opi = Column(Float, nullable=True)
    
    log_updated_at = Column(DateTime, nullable=True) # OngekiScoreLog側の最終更新日時
    system_updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    scores = relationship("ScoreLog", back_populates="player", cascade="all, delete-orphan")


class ScoreLog(Base):
    """スコアログ (score_logs)"""
    __tablename__ = 'score_logs'
    __table_args__ = (
        UniqueConstraint("user_id", "chart_id", name="uq_user_chart"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('players.user_id'), nullable=False, index=True)
    chart_id = Column(String(64), ForeignKey('charts.chart_id'), nullable=False, index=True)
    
    score = Column(Integer, nullable=False)
    is_all_break = Column(Boolean, default=False)
    is_full_bell = Column(Boolean, default=False)
    
    # 達成フラグ
    achieve_ss = Column(Boolean, default=False)
    achieve_sss = Column(Boolean, default=False)
    achieve_sssp = Column(Boolean, default=False)
    achieve_abfb = Column(Boolean, default=False)
    achieve_ap = Column(Boolean, default=False)

    player = relationship("Player", back_populates="scores")
    chart = relationship("Chart", back_populates="scores")


def get_engine(db_path: str):
    """DBエンジンを取得する"""
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    return engine

def init_db(db_path: str):
    """データベースを初期化し、テーブルを作成する"""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return engine

def get_session_maker(engine):
    return sessionmaker(bind=engine)

if __name__ == "__main__":
    # 単体テスト用: 実行されたらDBファイルを作成
    db_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "opi_database.sqlite")
    print(f"Initializing database at: {db_file}")
    engine = init_db(db_file)
    print("Database initialized successfully.")
