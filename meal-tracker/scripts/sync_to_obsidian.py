"""Supabaseの未配信イベントをObsidianの追記専用食事ログへ反映する。"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
LOG_PATH = ROOT / "lyou_Obsidian" / "01_Config" / "12_memory" / "meal_log.md"


def request_json(method: str, path: str, *, data: object | None = None) -> list[dict]:
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": "return=representation"}
    payload = None if data is None else json.dumps(data).encode("utf-8")
    with urlopen(Request(f"{base}/rest/v1/{path}", data=payload, headers=headers, method=method), timeout=20) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else []


def ensure_log() -> None:
    if LOG_PATH.exists():
        return
    LOG_PATH.write_text(
        "---\ntitle: 食事ログ\ncategory: 記録\ntags: [AI作成, 食事, 栄養]\ncreated_at: \"2026-09-22 15:10\"\nupdated_at: \"2026-09-22 15:10\"\nsummary: 食事記録アプリから取り込んだ食事と目標変更の追記ログ。\nrelated_notes:\n  - \"[[01_Config/11_profiles/fitness]]\"\n---\n\n# 食事ログ\n",
        encoding="utf-8",
    )


def format_event(event: dict, row: dict | None) -> str:
    event_type = event["entity_type"]
    when = event["occurred_at"][:16].replace("T", " ")
    if event["operation"] == "delete":
        return f"\n- {when}｜削除｜{event_type} `{event['entity_id']}`\n"
    if event_type == "meal_item" and row:
        return f"\n- {row['recorded_date']}｜{row['meal_type']}｜{row['name']}｜{row['energy_kcal']}kcal / P{row['protein_g']} F{row['fat_g']} C{row['carbohydrate_g']}｜糖質 {row['sugar_g'] if row['sugar_g'] is not None else '—'}g・食物繊維 {row['fiber_g'] if row['fiber_g'] is not None else '—'}g・食塩相当量 {row['salt_g'] if row['salt_g'] is not None else '—'}g\n"
    if event_type == "nutrition_target" and row:
        return f"\n- {when}｜目標変更｜{row['effective_from']}から {row['energy_kcal']}kcal / P{row['protein_g']} F{row['fat_g']} C{row['carbohydrate_g']}（revision {row['revision']}）\n"
    if event_type == "favorite" and row:
        return f"\n- {when}｜定番更新｜{row['name']}｜{row['energy_kcal']}kcal / P{row['protein_g']} F{row['fat_g']} C{row['carbohydrate_g']}\n"
    return f"\n- {when}｜更新｜{event_type} `{event['entity_id']}`\n"


def main() -> None:
    user_id = os.environ["MEAL_TRACKER_USER_ID"]
    events = request_json("GET", "obsidian_sync_events?" + urlencode({"user_id": f"eq.{user_id}", "delivered_at": "is.null", "order": "occurred_at.asc"}))
    if not events:
        print("未配信イベントはありません。")
        return
    tables = {"meal_item": "meal_items", "favorite": "favorites", "nutrition_target": "nutrition_targets"}
    ensure_log()
    lines: list[str] = []
    for event in events:
        row: dict | None = None
        if event["operation"] == "upsert":
            found = request_json("GET", f"{tables[event['entity_type']]}?" + urlencode({"id": f"eq.{event['entity_id']}", "limit": "1"}))
            row = found[0] if found else None
        lines.append(format_event(event, row))
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.writelines(lines)
    request_json("PATCH", "obsidian_sync_events?" + urlencode({"id": "in.(" + ",".join(event["id"] for event in events) + ")"}), data={"delivered_at": datetime.utcnow().isoformat() + "Z"})
    print(f"{len(events)}件を{LOG_PATH}へ追記しました（{now}）。")


if __name__ == "__main__":
    main()
