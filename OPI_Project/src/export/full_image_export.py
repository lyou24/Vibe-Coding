"""一覧データを1920×1080の1枚のPNGへ変換する。"""

from __future__ import annotations

import io
import math
from datetime import date
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


FULL_HD_SIZE = (1920, 1080)
PAGE_BACKGROUND = "#0f172a"
DEFAULT_CARD = {"background": "#f8fafc", "border": "#cbd5e1", "text": "#0f172a"}
FONT_CANDIDATES = {
    "regular": (
        Path("C:/Windows/Fonts/YuGothM.ttc"),
        Path("C:/Windows/Fonts/meiryo.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ),
    "bold": (
        Path("C:/Windows/Fonts/YuGothB.ttc"),
        Path("C:/Windows/Fonts/meiryob.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    ),
}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES["bold" if bold else "regular"]:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    value = str(text)
    if draw.textlength(value, font=font) <= max_width:
        return value
    suffix = "…"
    while value and draw.textlength(value + suffix, font=font) > max_width:
        value = value[:-1]
    return value + suffix


def build_full_hd_image(
    title: str,
    settings: Iterable[str],
    cards: Iterable[dict],
    generated_on: date | None = None,
) -> bytes:
    """全項目を固定1920×1080のPNG 1枚に収める。"""
    generated_on = generated_on or date.today()
    settings = [str(setting) for setting in settings]
    cards = list(cards)

    width, height = FULL_HD_SIZE
    image = Image.new("RGB", FULL_HD_SIZE, PAGE_BACKGROUND)
    draw = ImageDraw.Draw(image)

    title_font = _font(30, bold=True)
    setting_font = _font(14)
    footer_font = _font(12)
    draw.text((24, 16), title, fill="#ffffff", font=title_font)

    settings_text = "  ｜  ".join(settings)
    draw.text(
        (26, 58),
        _fit_text(draw, settings_text, setting_font, width - 52),
        fill="#cbd5e1",
        font=setting_font,
    )

    content_top = 88
    content_bottom = 1048
    margin_x = 24
    column_gap = 7
    row_gap = 3
    max_rows = 36
    column_count = max(1, math.ceil(len(cards) / max_rows))
    row_count = max(1, math.ceil(len(cards) / column_count))
    column_width = int(
        (width - margin_x * 2 - column_gap * (column_count - 1)) / column_count
    )
    row_height = int(
        (content_bottom - content_top - row_gap * (row_count - 1)) / row_count
    )

    if column_width >= 260:
        title_size, detail_size = 14, 11
    elif column_width >= 190:
        title_size, detail_size = 12, 9
    else:
        title_size, detail_size = 10, 8
    card_title_font = _font(title_size, bold=True)
    card_detail_font = _font(detail_size)

    for index, card in enumerate(cards):
        column = index // row_count
        row = index % row_count
        x = margin_x + column * (column_width + column_gap)
        y = content_top + row * (row_height + row_gap)

        background = card.get("background", DEFAULT_CARD["background"])
        border = card.get("border", DEFAULT_CARD["border"])
        text_color = card.get("text", DEFAULT_CARD["text"])
        draw.rounded_rectangle(
            (x, y, x + column_width, y + row_height),
            radius=4,
            fill=background,
            outline=border,
            width=1,
        )

        inner_width = max(1, column_width - 10)
        title_text = _fit_text(draw, card.get("title", ""), card_title_font, inner_width)
        draw.text((x + 5, y + 1), title_text, fill=text_color, font=card_title_font)

        summary = card.get("summary")
        if not summary:
            details = card.get("details", [])
            summary = details[-1] if details else card.get("metadata", "")
        detail_text = _fit_text(draw, summary, card_detail_font, inner_width)
        detail_y = min(y + row_height - detail_size - 2, y + title_size + 2)
        draw.text((x + 5, detail_y), detail_text, fill=text_color, font=card_detail_font)

    footer = f"{generated_on:%Y-%m-%d}  全{len(cards)}件  1920×1080"
    draw.text((width - 260, height - 19), footer, fill="#94a3b8", font=footer_font)

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
