import argparse
import os
import sqlite3
from pathlib import Path
from collections import defaultdict


PROJECT_ROOT = Path(__file__).resolve().parent
CALIBRATION_DB = PROJECT_ROOT / "data" / "opi_calibration.sqlite"
MASTER_DB = PROJECT_ROOT / "data" / "opi_database.sqlite"

RANK_TO_COLUMN_PREFIX = {
    "SS": "opi_ss",
    "SSS": "opi_sss",
    "SSS+": "opi_sssp",
    "SSS+ABFB": "opi_abfb",
    "AP": "opi_ap",
}


def main():
    parser = argparse.ArgumentParser(description="校正DBから本番DBへ推計パラメータを反映し、マークダウン表を出力する")
    parser.add_argument("--markdown-out", type=str, default="opi_table.md", help="出力するマークダウンファイルのパス")
    args = parser.parse_args()

    cal_conn = sqlite3.connect(f"file:{CALIBRATION_DB.as_posix()}?mode=ro", uri=True)
    cal_conn.row_factory = sqlite3.Row

    # 最新の項目推定runを取得
    run = cal_conn.execute(
        """
        SELECT run_id FROM estimation_runs
         WHERE status = 'completed'
           AND model_version LIKE '2pl-item-%'
         ORDER BY run_id DESC
         LIMIT 1
        """
    ).fetchone()
    
    if not run:
        raise ValueError("完了済みの項目パラメータ推定runがありません")
    
    run_id = run["run_id"]
    
    # 推定結果を取得
    estimates = cal_conn.execute(
        """
        SELECT chart_id, target_rank, x, y
          FROM item_parameter_estimates
         WHERE run_id = ? AND is_estimable = 1
        """,
        (run_id,)
    ).fetchall()
    
    # 本番DBを更新
    master_conn = sqlite3.connect(MASTER_DB)
    master_cursor = master_conn.cursor()
    
    update_counts = 0
    chart_params = defaultdict(dict)
    
    for row in estimates:
        chart_id = row["chart_id"]
        target_rank = row["target_rank"]
        x = row["x"]
        y = row["y"]
        
        prefix = RANK_TO_COLUMN_PREFIX[target_rank]
        
        master_cursor.execute(
            f"""
            UPDATE charts
               SET {prefix}_x = ?, {prefix}_y = ?
             WHERE chart_id = ?
            """,
            (x, y, chart_id)
        )
        update_counts += master_cursor.rowcount
        chart_params[chart_id][target_rank] = x
        chart_params[chart_id]["chart_id"] = chart_id

    master_conn.commit()
    
    # 譜面のメタデータを取得してマークダウン出力用データを作成
    master_conn.row_factory = sqlite3.Row
    charts = master_conn.execute(
        "SELECT chart_id, title, difficulty, level, chart_constant FROM charts"
    ).fetchall()
    
    chart_meta = {c["chart_id"]: dict(c) for c in charts}
    
    table_data = []
    for chart_id, params in chart_params.items():
        meta = chart_meta.get(chart_id)
        if not meta:
            continue
            
        table_data.append({
            "title": meta["title"],
            "difficulty": meta["difficulty"],
            "level": meta["level"],
            "constant": meta["chart_constant"],
            "ss": params.get("SS", None),
            "sss": params.get("SSS", None),
            "ap": params.get("AP", None),
        })
        
    # SSSのOPI（適正値）の降順でソート
    table_data.sort(key=lambda x: x["sss"] or 0, reverse=True)
    
    with open(args.markdown_out, "w", encoding="utf-8") as f:
        f.write("# OPI 難易度表（データ推計値）\n\n")
        f.write("実データから推定された楽曲ごとのOPI基準値です。SSSランク達成のOPIで降順にソートしています。\n\n")
        f.write("| 楽曲名 | 難易度 | 定数 | SS適正OPI | SSS適正OPI | AP適正OPI |\n")
        f.write("|---|---|---|---|---|---|\n")
        
        for row in table_data:
            title = row["title"]
            diff = row["difficulty"]
            const = f"{row['constant']:.1f}"
            
            ss_str = f"{row['ss']:.1f}" if row["ss"] is not None else "-"
            sss_str = f"{row['sss']:.1f}" if row["sss"] is not None else "-"
            ap_str = f"{row['ap']:.1f}" if row["ap"] is not None else "-"
            
            f.write(f"| {title} | {diff} | {const} | {ss_str} | {sss_str} | {ap_str} |\n")
            
    print(f"Update applied to {update_counts} rank parameters in production DB.")
    print(f"Markdown table exported to {args.markdown_out}.")
    
    cal_conn.close()
    master_conn.close()


if __name__ == "__main__":
    main()
