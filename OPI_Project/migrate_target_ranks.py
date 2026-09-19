import sqlite3
import os
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parent
CALIBRATION_DB = PROJECT_ROOT / "data" / "opi_calibration.sqlite"
MASTER_DB = PROJECT_ROOT / "data" / "opi_database.sqlite"

def update_db_schema():
    print("Migrating databases...")
    
    # 1. Main DB
    if MASTER_DB.exists():
        with sqlite3.connect(MASTER_DB) as conn:
            # Check if columns exist
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(charts)")
            cols = [c[1] for c in cur.fetchall()]
            if 'opi_abfb_x' in cols:
                conn.execute("ALTER TABLE charts RENAME COLUMN opi_abfb_x TO opi_s_x")
                conn.execute("ALTER TABLE charts RENAME COLUMN opi_abfb_y TO opi_s_y")
            if 'opi_ap_x' in cols:
                conn.execute("ALTER TABLE charts RENAME COLUMN opi_ap_x TO opi_abp_x")
                conn.execute("ALTER TABLE charts RENAME COLUMN opi_ap_y TO opi_abp_y")
                
            cur.execute("PRAGMA table_info(score_logs)")
            cols = [c[1] for c in cur.fetchall()]
            if 'achieve_abfb' in cols:
                conn.execute("ALTER TABLE score_logs RENAME COLUMN achieve_abfb TO achieve_s")
            if 'achieve_ap' in cols:
                conn.execute("ALTER TABLE score_logs RENAME COLUMN achieve_ap TO achieve_abp")
            
            # Update score_logs logic
            conn.execute("UPDATE score_logs SET achieve_s = 1 WHERE score >= 970000")
            conn.execute("UPDATE score_logs SET achieve_s = 0 WHERE score < 970000")
            conn.execute("UPDATE score_logs SET achieve_abp = 1 WHERE score >= 1010000")
            conn.execute("UPDATE score_logs SET achieve_abp = 0 WHERE score < 1010000")
            print("Main DB migrated.")

    # 2. Calibration DB
    if CALIBRATION_DB.exists():
        with sqlite3.connect(CALIBRATION_DB) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(scores)")
            cols = [c[1] for c in cur.fetchall()]
            if 'achieve_abfb' in cols:
                conn.execute("ALTER TABLE scores RENAME COLUMN achieve_abfb TO achieve_s")
            if 'achieve_ap' in cols:
                conn.execute("ALTER TABLE scores RENAME COLUMN achieve_ap TO achieve_abp")
                
            conn.execute("UPDATE scores SET achieve_s = 1 WHERE score >= 970000")
            conn.execute("UPDATE scores SET achieve_s = 0 WHERE score < 970000")
            conn.execute("UPDATE scores SET achieve_abp = 1 WHERE score >= 1010000")
            conn.execute("UPDATE scores SET achieve_abp = 0 WHERE score < 1010000")
            
            # Reset estimation runs
            conn.execute("DELETE FROM estimation_runs")
            print("Calibration DB migrated and estimation runs cleared.")

def update_python_files():
    print("Updating python files...")
    
    # models.py
    f = PROJECT_ROOT / "src" / "database" / "models.py"
    content = f.read_text("utf-8")
    content = content.replace("opi_abfb_x", "opi_s_x").replace("opi_abfb_y", "opi_s_y")
    content = content.replace("opi_ap_x", "opi_abp_x").replace("opi_ap_y", "opi_abp_y")
    content = content.replace("achieve_abfb", "achieve_s").replace("achieve_ap", "achieve_abp")
    f.write_text(content, "utf-8")

    # calibration_store.py
    f = PROJECT_ROOT / "src" / "database" / "calibration_store.py"
    content = f.read_text("utf-8")
    content = content.replace("achieve_abfb", "achieve_s").replace("achieve_ap", "achieve_abp")
    content = content.replace(
        "score_value >= 1_007_500 and is_ab and is_fb,",
        "score_value >= 975_000,"
    )
    f.write_text(content, "utf-8")

    # opi_policy.py
    f = PROJECT_ROOT / "src" / "analyzer" / "opi_policy.py"
    content = f.read_text("utf-8")
    content = re.sub(
        r'RANK_OFFSETS = \{.*?\}',
        'RANK_OFFSETS = {\n    "S": -240.0,\n    "SS": -120.0,\n    "SSS": 0.0,\n    "SSS+": 120.0,\n    "AB+": 240.0,\n}',
        content,
        flags=re.DOTALL
    )
    content = re.sub(
        r'column_names = \{.*?\}',
        'column_names = {\n        "S": "s",\n        "SS": "ss",\n        "SSS": "sss",\n        "SSS+": "sssp",\n        "AB+": "abp",\n    }',
        content,
        flags=re.DOTALL
    )
    f.write_text(content, "utf-8")

    # opi_calculator.py
    f = PROJECT_ROOT / "src" / "analyzer" / "opi_calculator.py"
    content = f.read_text("utf-8")
    content = content.replace('["SS", "SSS", "SSS+", "SSS+ABFB", "AP"]', '["S", "SS", "SSS", "SSS+", "AB+"]')
    content = content.replace('if r in ("SSS+ABFB", "SSS+ ABFB", "ABFB", "SSSP_ABFB"):', 'if r in ("AB+", "ABP"):')
    content = content.replace('return "SSS+ABFB"', 'return "AB+"')
    content = content.replace('if r in ("AP", "ALL_PERFECT"):', 'if r in ("S",):')
    content = content.replace('return "AP"', 'return "S"')
    content = content.replace('achieve_abfb', 'achieve_s').replace('achieve_ap', 'achieve_abp')
    content = content.replace('opi_abfb', 'opi_s').replace('opi_ap', 'opi_abp')
    f.write_text(content, "utf-8")

    # evaluate_predictive_performance.py
    f = PROJECT_ROOT / "evaluate_predictive_performance.py"
    content = f.read_text("utf-8")
    content = content.replace('["SS", "SSS", "SSS+", "SSS+ABFB", "AP"]', '["S", "SS", "SSS", "SSS+", "AB+"]')
    content = content.replace('"SSS+ABFB": "achieve_abfb"', '"S": "achieve_s"')
    content = content.replace('"AP": "achieve_ap"', '"AB+": "achieve_abp"')
    content = content.replace('achieve_abfb', 'achieve_s').replace('achieve_ap', 'achieve_abp')
    f.write_text(content, "utf-8")

    # apply_calibrated_parameters.py
    f = PROJECT_ROOT / "apply_calibrated_parameters.py"
    content = f.read_text("utf-8")
    content = content.replace('"SSS+ABFB": "opi_abfb"', '"S": "opi_s"')
    content = content.replace('"AP": "opi_ap"', '"AB+": "opi_abp"')
    content = content.replace('| SS適正OPI | SSS適正OPI | AP適正OPI |', '| S適正OPI | SS適正OPI | SSS適正OPI | SSS+適正OPI | AB+適正OPI |')
    content = content.replace('"ap": params.get("AP", None),', '"s": params.get("S", None),\n            "sssp": params.get("SSS+", None),\n            "abp": params.get("AB+", None),')
    content = content.replace('ap_str = f"{row[\'ap\']:.1f}" if row["ap"] is not None else "-"', 's_str = f"{row[\'s\']:.1f}" if row["s"] is not None else "-"\n            sssp_str = f"{row[\'sssp\']:.1f}" if row["sssp"] is not None else "-"\n            abp_str = f"{row[\'abp\']:.1f}" if row["abp"] is not None else "-"')
    content = content.replace('f"| {title} | {diff} | {const} | {ss_str} | {sss_str} | {ap_str} |\\n"', 'f"| {title} | {diff} | {const} | {s_str} | {ss_str} | {sss_str} | {sssp_str} | {abp_str} |\\n"')
    f.write_text(content, "utf-8")

if __name__ == "__main__":
    update_db_schema()
    update_python_files()
    print("Migration completed.")
