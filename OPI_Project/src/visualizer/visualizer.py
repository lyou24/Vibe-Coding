import os
import math
import numpy as np
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

    @staticmethod
    def get_band_label(rating: float) -> str | None:
        """
        要件定義書 1.3 F-06 / 3.2:
        レーティング18.0以上のユーザーを0.5刻みの基準値（18.0, 18.5, 19.0, ...）とし、
        各基準値 ±0.25 の帯域（[center - 0.25, center + 0.25)）に厳密に分類する。
        例:
          18.0帯: 17.75 <= rating < 18.25
          18.5帯: 18.25 <= rating < 18.75
          19.0帯: 18.75 <= rating < 19.25
        17.75未満は None を返す。
        NaN, inf, -inf, None 等の異常値は例外を発生させず安全に None を返す。
        """
        try:
            if rating is None or math.isnan(rating) or math.isinf(rating):
                return None
        except (TypeError, ValueError):
            try:
                rating = float(rating)
                if math.isnan(rating) or math.isinf(rating):
                    return None
            except (TypeError, ValueError):
                return None

        if rating < 17.75:
            return None
        # 浮動小数点丸め誤差（例: 18.25 - 17.75 = 0.49999999999999956）対策として 1e-9 を加算
        band_idx = math.floor((rating - 17.75 + 1e-9) / 0.5)
        center = 18.0 + band_idx * 0.5
        return f"{center:.1f}"

    @staticmethod
    def get_target_distribution_table() -> pd.DataFrame:
        """
        要件定義書 3.2 に記載されている「レーティング別 総合OPI目標値および分布統計表」
        （対象レート、集計帯域、サンプル人数、目標総合OPI中央値、平均総合OPI、25%点〜75%点 IQR）
        を DataFrame として返却する。
        """
        data = [
            {
                "対象レート": "18.0",
                "集計帯域（レート）": "17.75 〜 18.24",
                "サンプル人数": "452人",
                "目標総合OPI（中央値）": 1480.2,
                "平均総合OPI": 1485.4,
                "25%点 〜 75%点 (IQR)": "1421.5 〜 1538.7"
            },
            {
                "対象レート": "18.5",
                "集計帯域（レート）": "18.25 〜 18.74",
                "サンプル人数": "518人",
                "目標総合OPI（中央値）": 1632.5,
                "平均総合OPI": 1637.1,
                "25%点 〜 75%点 (IQR)": "1565.3 〜 1692.8"
            },
            {
                "対象レート": "19.0",
                "集計帯域（レート）": "18.75 〜 19.24",
                "サンプル人数": "615人",
                "目標総合OPI（中央値）": 1791.0,
                "平均総合OPI": 1796.8,
                "25%点 〜 75%点 (IQR)": "1725.4 〜 1848.2"
            },
            {
                "対象レート": "19.5",
                "集計帯域（レート）": "19.25 〜 19.74",
                "サンプル人数": "437人",
                "目標総合OPI（中央値）": 1942.3,
                "平均総合OPI": 1945.5,
                "25%点 〜 75%点 (IQR)": "1882.1 〜 2005.9"
            },
            {
                "対象レート": "20.0",
                "集計帯域（レート）": "19.75 〜 20.24",
                "サンプル人数": "283人",
                "目標総合OPI（中央値）": 2076.8,
                "平均総合OPI": 2085.2,
                "25%点 〜 75%点 (IQR)": "2023.7 〜 2131.4"
            },
            {
                "対象レート": "20.5",
                "集計帯域（レート）": "20.25 〜 20.74",
                "サンプル人数": "156人",
                "目標総合OPI（中央値）": 2235.1,
                "平均総合OPI": 2228.4,
                "25%点 〜 75%点 (IQR)": "2185.0 〜 2282.6"
            },
            {
                "対象レート": "21.0",
                "集計帯域（レート）": "20.75 〜 21.24",
                "サンプル人数": "42人",
                "目標総合OPI（中央値）": 2310.5,
                "平均総合OPI": 2305.2,
                "25%点 〜 75%点 (IQR)": "2268.3 〜 2345.1"
            },
        ]
        return pd.DataFrame(data)

    def calculate_current_distribution_table(self) -> pd.DataFrame:
        """
        データベース内の実プレイヤーデータから、レーティング帯別の分布統計
        （サンプル人数、中央値、平均、25%点〜75%点 IQR）を集計して返却する。
        """
        df = self.load_player_data()
        if df.empty:
            return pd.DataFrame()

        # NaN / inf ガード: 数値化および有限値フィルタ
        df = df.dropna(subset=['rating', 'total_opi']).copy()
        df['rating'] = pd.to_numeric(df['rating'], errors='coerce')
        df['total_opi'] = pd.to_numeric(df['total_opi'], errors='coerce')
        df = df.dropna(subset=['rating', 'total_opi']).copy()
        df = df[np.isfinite(df['rating']) & np.isfinite(df['total_opi']) & (df['rating'] >= 17.75)].copy()
        if df.empty:
            return pd.DataFrame()

        df['rating_band'] = df['rating'].apply(self.get_band_label)
        df = df.dropna(subset=['rating_band'])
        if df.empty:
            return pd.DataFrame()

        records = []
        for band in sorted(df['rating_band'].unique(), key=lambda b: float(b)):
            band_float = float(band)
            sub = df[df['rating_band'] == band]['total_opi']
            cnt = len(sub)
            if cnt == 0:
                continue
            median_val = float(sub.median())
            mean_val = float(sub.mean())
            q25 = float(sub.quantile(0.25))
            q75 = float(sub.quantile(0.75))
            low_r = band_float - 0.25
            high_r = band_float + 0.24
            records.append({
                "対象レート": f"{band_float:.1f}",
                "集計帯域（レート）": f"{low_r:.2f} 〜 {high_r:.2f}",
                "サンプル人数": f"{cnt}人",
                "目標総合OPI（中央値）": round(median_val, 1),
                "平均総合OPI": round(mean_val, 1),
                "25%点 〜 75%点 (IQR)": f"{q25:.1f} 〜 {q75:.1f}"
            })
        return pd.DataFrame(records)

    def create_distribution_plot(self, output_path: str = "distribution.png"):
        """
        要件: レート18.0以上のユーザーを0.5刻みの基準値とし、各基準値 ±0.25の帯域ごとに
        分布図（箱ひげ図やバイオリンプロットなど）を作成する。
        """
        df = self.load_player_data()
        if df.empty:
            logger.warning("No data available for visualization.")
            return

        # 対象を17.75以上（18.0の-0.25帯域を含む）に絞る（NaN / inf 安全ガード）
        df = df.dropna(subset=['rating', 'total_opi']).copy()
        df['rating'] = pd.to_numeric(df['rating'], errors='coerce')
        df['total_opi'] = pd.to_numeric(df['total_opi'], errors='coerce')
        df = df.dropna(subset=['rating', 'total_opi']).copy()
        df = df[np.isfinite(df['rating']) & np.isfinite(df['total_opi']) & (df['rating'] >= 17.75)].copy()

        if df.empty:
            logger.warning("No data available in the target rating bands.")
            return

        # レーティングの基準値を0.5刻みで生成 (18.0, 18.5, 19.0, ...)
        df['rating_band'] = df['rating'].apply(self.get_band_label)
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

    # メソッド名のエイリアス
    plot_distribution = create_distribution_plot

if __name__ == "__main__":
    db_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "opi_database.sqlite")
    vis = OPIVisualizer(db_file)
    vis.create_distribution_plot("opi_distribution.png")
