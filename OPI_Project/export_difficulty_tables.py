"""校正済み単曲OPIからPDFとCSVの難易度表を生成する。"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import unicodedata
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from src.analyzer.opi_overrides import ABP_FIXED_CHART_IDS, ABP_FIXED_OPI
from src.database.calibrated_parameters import sync_latest_calibrated_parameters


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_MASTER_DB = PROJECT_ROOT / "data" / "opi_database.sqlite"
DEFAULT_CALIBRATION_DB = PROJECT_ROOT / "data" / "opi_calibration.sqlite"
MIN_TARGET_CONSTANT = 14.0
RANK_COLUMNS = {
    "S": "opi_s",
    "SS": "opi_ss",
    "SSS": "opi_sss",
    "SSS+": "opi_sssp",
    "AB+": "opi_abp",
}


def is_solo_version(title: str | None) -> bool:
    normalized = unicodedata.normalize("NFKC", title or "").casefold()
    return "ソロver" in normalized


def _register_pdf_font() -> str:
    candidates = (
        Path("C:/Windows/Fonts/YuGothM.ttc"),
        Path("C:/Windows/Fonts/meiryo.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    )
    for path in candidates:
        if path.exists():
            pdfmetrics.registerFont(TTFont("OPIJapanese", str(path), subfontIndex=0))
            return "OPIJapanese"
    return "Helvetica"


def load_difficulty_rows(master_db: Path) -> list[dict]:
    """本番DBから対象譜面を読み込み、SSS適正OPIの降順で返す。"""
    with sqlite3.connect(f"file:{master_db.resolve().as_posix()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT chart_id, title, version, genre, difficulty, level, chart_constant,
                   opi_s_x, opi_s_y, opi_ss_x, opi_ss_y,
                   opi_sss_x, opi_sss_y, opi_sssp_x, opi_sssp_y,
                   opi_abp_x, opi_abp_y
              FROM charts
             WHERE is_active = 1 AND chart_constant >= ?
            """,
            (MIN_TARGET_CONSTANT,),
        ).fetchall()
    output = [dict(row) for row in rows if not is_solo_version(row["title"])]
    for row in output:
        if row["chart_id"] in ABP_FIXED_CHART_IDS:
            row["opi_abp_x"] = ABP_FIXED_OPI
    output.sort(
        key=lambda row: (
            row["opi_sss_x"] is not None,
            row["opi_sss_x"] or 0.0,
            row["chart_constant"],
            row["title"],
        ),
        reverse=True,
    )
    return output


def build_table_records(rows: list[dict]) -> list[dict]:
    return [
        {
                "chart_id": row["chart_id"],
                "楽曲名": row["title"],
                "バージョン": row["version"] or "不明",
                "ジャンル": row["genre"] or "不明",
                "難易度": row["difficulty"],
                "レベル": row["level"],
                "定数": row["chart_constant"],
                **{
                    f"{rank}適正OPI": row[f"{prefix}_x"]
                    for rank, prefix in RANK_COLUMNS.items()
                },
                **{
                    f"{rank}個人差度": row[f"{prefix}_y"]
                    for rank, prefix in RANK_COLUMNS.items()
                },
        }
        for row in rows
    ]


def export_csv(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "chart_id", "楽曲名", "バージョン", "ジャンル", "難易度", "レベル", "定数",
        "S適正OPI", "S個人差度", "SS適正OPI", "SS個人差度",
        "SSS適正OPI", "SSS個人差度", "SSS+適正OPI", "SSS+個人差度",
        "AB+適正OPI", "AB+個人差度",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(build_table_records(rows))


def export_pdf(rows: list[dict], output_path: Path, generated_on: date) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    font_name = _register_pdf_font()
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A3),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title="OPI 難易度表",
        author="Ongeki Power Indicator",
    )
    title_style = ParagraphStyle(
        "title", fontName=font_name, fontSize=16, leading=20, textColor=colors.HexColor("#0f172a")
    )
    note_style = ParagraphStyle(
        "note", fontName=font_name, fontSize=8, leading=10, textColor=colors.HexColor("#475569")
    )
    cell_style = ParagraphStyle(
        "cell", fontName=font_name, fontSize=6.5, leading=8, alignment=TA_LEFT
    )
    center_style = ParagraphStyle(
        "center", parent=cell_style, alignment=TA_CENTER
    )

    def value(row: dict, prefix: str) -> str:
        number = row[f"{prefix}_x"]
        return "—" if number is None else f"{number:.1f}"

    header = ["楽曲名", "バージョン", "ジャンル", "難易度", "Lv.", "定数", *RANK_COLUMNS]
    table_rows = [[Paragraph(item, center_style) for item in header]]
    for row in rows:
        table_rows.append([
            Paragraph(str(row["title"]), cell_style),
            Paragraph(str(row["version"] or "不明"), cell_style),
            Paragraph(str(row["genre"] or "不明"), cell_style),
            Paragraph(str(row["difficulty"]), center_style),
            Paragraph(str(row["level"]), center_style),
            f"{row['chart_constant']:.1f}",
            *[value(row, prefix) for prefix in RANK_COLUMNS.values()],
        ])

    table = LongTable(
        table_rows,
        repeatRows=1,
        colWidths=[74 * mm, 27 * mm, 31 * mm, 18 * mm, 11 * mm, 13 * mm, *([18 * mm] * 5)],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 1), (-1, -1), 6.5),
        ("ALIGN", (3, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#0f172a")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.2, colors.HexColor("#cbd5e1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    def page_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font_name, 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawRightString(
            landscape(A3)[0] - 10 * mm,
            5 * mm,
            f"{generated_on:%Y-%m-%d}  |  {doc.page}ページ",
        )
        canvas.restoreState()

    story = [
        Paragraph("OPI 難易度表（校正済み単曲OPI）", title_style),
        Spacer(1, 2 * mm),
        Paragraph(
            f"譜面定数{MIN_TARGET_CONSTANT:.1f}以上・ソロver.除外・全{len(rows)}譜面。SSS適正OPI降順。校正値を優先し、指定12譜面のAB+適正OPIは2500固定です。",
            note_style,
        ),
        Spacer(1, 3 * mm),
        table,
    ]
    document.build(story, onFirstPage=page_footer, onLaterPages=page_footer)


def main() -> None:
    from src.database.models import init_db

    generated_on = date.today()
    parser = argparse.ArgumentParser(description="校正済み単曲OPIの難易度表をPDFとCSVで出力する")
    parser.add_argument("--master-db", type=Path, default=DEFAULT_MASTER_DB)
    parser.add_argument("--calibration-db", type=Path, default=DEFAULT_CALIBRATION_DB)
    parser.add_argument(
        "--pdf-out",
        type=Path,
        default=PROJECT_ROOT / "output" / "pdf" / f"opi_difficulty_table_{generated_on:%Y%m%d}.pdf",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        default=PROJECT_ROOT / "output" / "table" / f"opi_difficulty_table_{generated_on:%Y%m%d}.csv",
    )
    args = parser.parse_args()

    init_db(str(args.master_db)).dispose()
    sync_report = sync_latest_calibrated_parameters(args.calibration_db, args.master_db)
    rows = load_difficulty_rows(args.master_db)
    export_pdf(rows, args.pdf_out, generated_on)
    export_csv(rows, args.csv_out)
    print(
        f"run #{sync_report.get('run_id')} / {len(rows)}譜面を出力しました: "
        f"{args.pdf_out} / {args.csv_out}"
    )


if __name__ == "__main__":
    main()
