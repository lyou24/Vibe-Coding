import json
import sqlite3

from src.database.ongeki_metadata import apply_metadata, load_records, normalize_title


def test_normalize_title_absorbs_width_case_and_spaces():
    assert normalize_title(" ＡＢ C ") == normalize_title("ab c")


def test_apply_metadata_adds_columns_and_updates_matching_charts(tmp_path):
    db_path = tmp_path / "opi.sqlite"
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE charts (chart_id TEXT PRIMARY KEY, title TEXT NOT NULL)")
    connection.executemany(
        "INSERT INTO charts(chart_id, title) VALUES (?, ?)",
        [("matched", "テスト 曲"), ("unmatched", "未収録曲")],
    )
    connection.commit()
    connection.close()

    source_path = tmp_path / "music.json"
    source_path.write_text(
        json.dumps([{"title": "テスト曲", "version": "bright", "category": "POPS＆ANIME"}], ensure_ascii=False),
        encoding="utf-8",
    )

    report = apply_metadata(db_path, load_records([source_path]))

    connection = sqlite3.connect(db_path)
    row = connection.execute(
        "SELECT version, genre FROM charts WHERE chart_id = 'matched'"
    ).fetchone()
    columns = {item[1] for item in connection.execute("PRAGMA table_info(charts)")}
    connection.close()

    assert row == ("bright", "POPS＆ANIME")
    assert {"version", "genre"} <= columns
    assert report == {
        "chart_count": 2,
        "matched_chart_count": 1,
        "matched_title_count": 1,
        "unmatched_title_count": 1,
    }
