import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine
import logging

logger = logging.getLogger(__name__)

class OPIVisualizer:
    def __init__(self, db_path: str):
        self.engine = create_engine(f'sqlite:///{db_path}')

    def load_player_data(self) -> pd.DataFrame:
        query = "SELECT user_id, rating, total_opi FROM players WHERE rating IS NOT NULL AND total_opi IS NOT NULL"
        df = pd.read_sql(query, self.engine)
        return df

    def create_distribution_plot(self, output_path: str = "distribution.png"):
        """
        要件: レート18.0以上のユーザーを0.5刻みの基準値とし、各基準値 ±0.25の帯域ごとに
        分布図（箱ひげ図やバイオリンプロットなど）を作成する。
        """
        df = self.load_player_data()
        if df.empty:
            logger.warning("No data available for visualization.")
            return

        # 対象を17.75以上（18.0の-0.25帯域を含む）に絞る
        df = df[df['rating'] >= 17.75].copy()

        # レーティングの基準値を0.5刻みで生成 (18.0, 18.5, 19.0, ...)
        def get_band_label(rating):
            # 例: 18.0 band is [17.75, 18.25)
            # つまり、ratingに0.25を足して0.5で割った商を0.5倍すると中心値になる
            center = round((rating + 0.25) * 2 - 0.5) / 2
            # 18.0未満(17.5など)は除外したい場合
            if center < 18.0:
                return None
            return f"{center:.1f}"

        df['rating_band'] = df['rating'].apply(get_band_label)
        df_filtered = df.dropna(subset=['rating_band'])

        if df_filtered.empty:
            logger.warning("No data available in the target rating bands.")
            return

        # プロット作成
        plt.figure(figsize=(12, 7))
        sns.set_theme(style="whitegrid")
        
        # バイオリンプロット（分布形状）+ ストリッププロット（各点の散布）の複合
        sns.violinplot(x="rating_band", y="total_opi", data=df_filtered, 
                       order=sorted(df_filtered['rating_band'].unique()), inner="quartile", color="lightblue")
        sns.stripplot(x="rating_band", y="total_opi", data=df_filtered, 
                      order=sorted(df_filtered['rating_band'].unique()), color="darkblue", alpha=0.4, jitter=True)

        plt.title("OPI Distribution by Rating Band (±0.25)")
        plt.xlabel("Rating Band (Center)")
        plt.ylabel("Estimated Total OPI")
        plt.tight_layout()

        plt.savefig(output_path)
        logger.info(f"Distribution plot saved to {output_path}")

if __name__ == "__main__":
    db_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "opi_database.sqlite")
    vis = OPIVisualizer(db_file)
    vis.create_distribution_plot("opi_distribution.png")
