"""OTOGE DB の公開データからオンゲキ楽曲メタデータを反映する。"""

from __future__ import annotations

import argparse
import json
import sqlite3
import unicodedata
import urllib.request
from pathlib import Path
from typing import Iterable


OTOGE_DB_SOURCES = (
    "https://raw.githubusercontent.com/zvuc/otoge-db/master/ongeki/data/music-ex.json",
    "https://raw.githubusercontent.com/zvuc/otoge-db/master/ongeki/data/music-ex-deleted.json",
)


def normalize_title(title: str) -> str:
    """照合用に表記幅・大文字小文字・空白を統一する。"""
    normalized = unicodedata.normalize("NFKC", title or "").casefold()
    return "".join(character for character in normalized if not character.isspace())


def load_records(source_paths: Iterable[str | Path] | None = None) -> list[dict]:
    """ローカルファイル、または公式公開元から楽曲レコードを読み込む。"""
    records: list[dict] = []
    if source_paths:
        payloads = [Path(path).read_bytes() for path in source_paths]
    else:
        payloads = []
        for url in OTOGE_DB_SOURCES:
            with urllib.request.urlopen(url, timeout=30) as response:
                payloads.append(response.read())

    for payload in payloads:
        data = json.loads(payload.decode("utf-8-sig"))
        if not isinstance(data, list):
            raise ValueError("OTOGE DB の楽曲データ形式が想定と異なります。")
        records.extend(data)
    return records


def apply_metadata(db_path: str | Path, records: Iterable[dict]) -> dict[str, int]:
    """既存DBの楽曲名に一致するバージョン・ジャンルを更新する。"""
    metadata_by_title: dict[str, tuple[str | None, str | None]] = {}
    for record in records:
        key = normalize_title(str(record.get("title", "")))
        if key:
            metadata_by_title[key] = (record.get("version"), record.get("category"))

    connection = sqlite3.connect(str(db_path))
    try:
        existing_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(charts)").fetchall()
        }
        if "version" not in existing_columns:
            connection.execute("ALTER TABLE charts ADD COLUMN version VARCHAR(64)")
        if "genre" not in existing_columns:
            connection.execute("ALTER TABLE charts ADD COLUMN genre VARCHAR(64)")

        rows = connection.execute("SELECT chart_id, title FROM charts").fetchall()
        matched_chart_count = 0
        matched_titles: set[str] = set()
        unmatched_titles: set[str] = set()
        for chart_id, title in rows:
            key = normalize_title(title)
            metadata = metadata_by_title.get(key)
            if metadata:
                connection.execute(
                    "UPDATE charts SET version = ?, genre = ? WHERE chart_id = ?",
                    (*metadata, chart_id),
                )
                matched_chart_count += 1
                matched_titles.add(title)
            else:
                unmatched_titles.add(title)
        connection.commit()
        return {
            "chart_count": len(rows),
            "matched_chart_count": matched_chart_count,
            "matched_title_count": len(matched_titles),
            "unmatched_title_count": len(unmatched_titles),
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="OTOGE DB の楽曲メタデータをOPI DBへ反映します。")
    parser.add_argument("db_path", help="opi_database.sqlite のパス")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="取得済みJSONのパス（複数指定可）。未指定時は公開元から取得します。",
    )
    args = parser.parse_args()
    report = apply_metadata(args.db_path, load_records(args.source or None))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
