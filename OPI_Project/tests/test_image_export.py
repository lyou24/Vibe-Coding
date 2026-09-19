import io
from datetime import date

from PIL import Image

from src.export.full_image_export import FULL_HD_SIZE, build_full_hd_image


def test_full_hd_export_is_single_fixed_size_png():
    cards = [
        {
            "title": f"楽曲 {index}",
            "metadata": "bright / POPS＆ANIME",
            "details": ["MASTER Lv.14+（定数 14.9）", "目標 SSS・OPI 1680.0"],
        }
        for index in range(10)
    ]

    payload = build_full_hd_image(
        "OPI難易度表",
        ["目標ランク: SSS"],
        cards,
        generated_on=date(2026, 9, 15),
    )

    with Image.open(io.BytesIO(payload)) as image:
        assert image.size == FULL_HD_SIZE
        assert image.format == "PNG"


def test_full_hd_export_keeps_many_cards_in_one_image():
    cards = [
        {"title": f"楽曲 {index}", "summary": "MASTER / OPI 1600.0"}
        for index in range(350)
    ]
    payload = build_full_hd_image("OPI難易度表", ["目標ランク: SSS"], cards)

    with Image.open(io.BytesIO(payload)) as image:
        assert image.size == FULL_HD_SIZE
