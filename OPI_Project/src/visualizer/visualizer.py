import os
import math
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.graph_objects as go
from sqlalchemy import create_engine
import logging

from src.analyzer.player_recalibration import AAA_ABILITY_MODEL_VERSION

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "opi_database.sqlite"
)
DEFAULT_CALIBRATION_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "opi_calibration.sqlite",
)

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
    def get_latest_calibrated_ability_run(
        calibration_db_path: str = DEFAULT_CALIBRATION_DB_PATH,
    ) -> dict | None:
        """AAA以上・最新単曲パラメータによる最新の完了runを返す。"""
        path = Path(calibration_db_path)
        if not path.is_file():
            return None
        connection = sqlite3.connect(
            f"file:{path.resolve().as_posix()}?mode=ro",
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        try:
            run = connection.execute(
                """
                SELECT run_id, model_version, parent_run_id, player_count,
                       estimated_player_count, unestimated_player_count,
                       completed_at, config_json
                  FROM estimation_runs
                 WHERE status = 'completed' AND model_version = ?
                 ORDER BY run_id DESC
                 LIMIT 1
                """,
                (AAA_ABILITY_MODEL_VERSION,),
            ).fetchone()
            return dict(run) if run else None
        except sqlite3.DatabaseError:
            return None
        finally:
            connection.close()

    @classmethod
    def load_latest_calibrated_player_data(
        cls,
        calibration_db_path: str = DEFAULT_CALIBRATION_DB_PATH,
    ) -> pd.DataFrame:
        """最新AAA以上再推定runのレーティングと総合OPIを読み込む。"""
        run = cls.get_latest_calibrated_ability_run(calibration_db_path)
        if run is None:
            return pd.DataFrame(columns=["rating", "total_opi"])
        path = Path(calibration_db_path)
        connection = sqlite3.connect(
            f"file:{path.resolve().as_posix()}?mode=ro",
            uri=True,
        )
        try:
            return pd.read_sql_query(
                """
                SELECT player.rating AS rating, estimate.theta AS total_opi
                  FROM player_ability_estimates AS estimate
                  JOIN players AS player
                    ON player.subject_key = estimate.subject_key
                 WHERE estimate.run_id = ?
                   AND estimate.is_estimable = 1
                   AND player.rating IS NOT NULL
                   AND estimate.theta IS NOT NULL
                """,
                connection,
                params=(int(run["run_id"]),),
            )
        finally:
            connection.close()

    @classmethod
    def get_target_distribution_table(
        cls,
        calibration_db_path: str = DEFAULT_CALIBRATION_DB_PATH,
    ) -> pd.DataFrame:
        """最新のAAA以上再推定結果からレーティング帯別統計を返す。"""
        return cls.build_distribution_table(
            cls.load_latest_calibrated_player_data(calibration_db_path)
        )

    @classmethod
    def build_distribution_table(cls, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()

        df = df.dropna(subset=["rating", "total_opi"]).copy()
        df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
        df["total_opi"] = pd.to_numeric(df["total_opi"], errors="coerce")
        df = df.dropna(subset=["rating", "total_opi"]).copy()
        df = df[
            np.isfinite(df["rating"])
            & np.isfinite(df["total_opi"])
            & (df["rating"] >= 17.75)
        ].copy()
        if df.empty:
            return pd.DataFrame()

        df["rating_band"] = df["rating"].apply(cls.get_band_label)
        df = df.dropna(subset=["rating_band"])
        records = []
        for band in sorted(df["rating_band"].unique(), key=lambda value: float(value)):
            band_float = float(band)
            values = df[df["rating_band"] == band]["total_opi"]
            records.append(
                {
                    "対象レート": f"{band_float:.1f}",
                    "集計帯域（レート）": f"{band_float - 0.25:.2f} 〜 {band_float + 0.24:.2f}",
                    "サンプル人数": f"{len(values)}人",
                    "目標総合OPI（中央値）": round(float(values.median()), 1),
                    "平均総合OPI": round(float(values.mean()), 1),
                    "25%点 〜 75%点 (IQR)": (
                        f"{float(values.quantile(0.25)):.1f} 〜 "
                        f"{float(values.quantile(0.75)):.1f}"
                    ),
                }
            )
        return pd.DataFrame(records)

    def calculate_current_distribution_table(self) -> pd.DataFrame:
        """
        データベース内の実プレイヤーデータから、レーティング帯別の分布統計
        （サンプル人数、中央値、平均、25%点〜75%点 IQR）を集計して返却する。
        """
        return self.build_distribution_table(self.load_player_data())

    def create_distribution_plot(self, output_path: str = "distribution.png"):
        """
        生のレーティング値と総合OPIの関係を散布図として作成する。
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

        # プロット作成
        plt.figure(figsize=(12, 7))
        sns.set_theme(style="whitegrid")

        sns.scatterplot(
            x="rating",
            y="total_opi",
            data=df,
            color="darkblue",
            alpha=0.45,
            s=28,
            edgecolor=None,
        )

        plt.title("Rating and Total OPI")
        plt.xlabel("Rating")
        plt.ylabel("Estimated Total OPI")
        plt.tight_layout()

        plt.savefig(output_path)
        plt.close()
        logger.info(f"Distribution plot saved to {output_path}")

    # メソッド名のエイリアス
    plot_distribution = create_distribution_plot

    def create_distribution_figure(
        self,
        player_rating: float | None = None,
        player_opi: float | None = None,
        player_name: str = "あなた",
        player_data: pd.DataFrame | None = None,
    ) -> go.Figure:
        """
        要件 R4: 横軸をレーティング生値、縦軸を総合OPIとした動的散布図 (Plotly) を生成する。
        選択中のユーザーが存在する場合、赤色の星型マーカーで現在位置をハイライト表示する。
        """
        df = player_data.copy() if player_data is not None else self.load_player_data()
        fig = go.Figure()

        if not df.empty:
            df = df.dropna(subset=['rating', 'total_opi']).copy()
            df['rating'] = pd.to_numeric(df['rating'], errors='coerce')
            df['total_opi'] = pd.to_numeric(df['total_opi'], errors='coerce')
            df = df.dropna(subset=['rating', 'total_opi']).copy()
            df = df[np.isfinite(df['rating']) & np.isfinite(df['total_opi']) & (df['rating'] >= 17.75)].copy()

            if not df.empty:
                plot_df = (
                    df.sample(n=2500, random_state=42).sort_index()
                    if len(df) > 2500
                    else df
                )
                # 全プレイヤー散布図
                fig.add_trace(go.Scatter(
                    x=plot_df['rating'],
                    y=plot_df['total_opi'],
                    mode='markers',
                    marker=dict(
                        size=6,
                        color='rgba(31, 119, 180, 0.45)',
                    ),
                    name='実プレイヤー（表示サンプル）' if len(plot_df) < len(df) else '実プレイヤー',
                    hovertemplate='Rating: %{x:.2f}<br>総合OPI: %{y:.1f}<extra></extra>'
                ))

        # 選択ユーザーのハイライト（星型マーカー）
        if player_rating is not None and player_opi is not None:
            fig.add_trace(go.Scatter(
                x=[float(player_rating)],
                y=[float(player_opi)],
                mode='markers+text',
                marker=dict(
                    size=14,
                    color='crimson',
                    symbol='star',
                    line=dict(width=2, color='white')
                ),
                name=f"{player_name} (現在地)",
                text=[f"★ {player_name}"],
                textposition="top center",
                hovertemplate=f"<b>{player_name}</b><br>レーティング: %{{x:.2f}}<br>総合OPI: %{{y:.1f}}<extra></extra>"
            ))

        fig.update_layout(
            title="レーティング vs 総合OPI 動的分布図",
            xaxis_title="レーティング",
            yaxis_title="総合OPI",
            template="plotly_white",
            hovermode="closest",
            margin=dict(l=40, r=40, t=50, b=40),
        )
        return fig


def create_distribution_figure(
    player_rating: float | None = None,
    player_opi: float | None = None,
    player_name: str = "あなた",
    db_path: str = DEFAULT_DB_PATH,
) -> go.Figure:
    """モジュールレベル関数としての create_distribution_figure ラッパー"""
    vis = OPIVisualizer(db_path)
    return vis.create_distribution_figure(
        player_rating=player_rating,
        player_opi=player_opi,
        player_name=player_name,
    )


if __name__ == "__main__":
    db_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "opi_database.sqlite")
    vis = OPIVisualizer(db_file)
    vis.create_distribution_plot("opi_distribution.png")
