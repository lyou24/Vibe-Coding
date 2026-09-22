import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const logPath = resolve(root, "lyou_Obsidian", "01_Config", "12_memory", "meal_log.md");
const { SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, MEAL_TRACKER_USER_ID } = process.env;

if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY || !MEAL_TRACKER_USER_ID) {
  throw new Error("SUPABASE_URL、SUPABASE_SERVICE_ROLE_KEY、MEAL_TRACKER_USER_IDをOS環境変数に設定してください。");
}

async function requestJson(method, path, body) {
  const response = await fetch(`${SUPABASE_URL.replace(/\/$/, "")}/rest/v1/${path}`, {
    method,
    headers: { apikey: SUPABASE_SERVICE_ROLE_KEY, Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`, "Content-Type": "application/json", Prefer: "return=representation" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(`Supabase同期に失敗しました (${response.status})。`);
  const text = await response.text();
  return text ? JSON.parse(text) : [];
}

async function ensureLog() {
  try { await readFile(logPath, "utf8"); }
  catch {
    await mkdir(dirname(logPath), { recursive: true });
    await writeFile(logPath, "---\ntitle: 食事ログ\ncategory: 記録\ntags: [AI作成, 食事, 栄養]\ncreated_at: \"2026-09-22 15:25\"\nupdated_at: \"2026-09-22 15:25\"\nsummary: 食事記録アプリから取り込んだ食事と目標変更の追記ログ。\nrelated_notes:\n  - \"[[01_Config/11_profiles/fitness]]\"\n---\n\n# 食事ログ\n", "utf8");
  }
}

function formatEvent(event, row) {
  const when = event.occurred_at.slice(0, 16).replace("T", " ");
  if (event.operation === "delete") return `\n- ${when}｜削除｜${event.entity_type} \`${event.entity_id}\`\n`;
  if (event.entity_type === "meal_item" && row) return `\n- ${row.recorded_date}｜${row.meal_type}｜${row.name}｜${row.energy_kcal}kcal / P${row.protein_g} F${row.fat_g} C${row.carbohydrate_g}｜糖質 ${row.sugar_g ?? "—"}g・食物繊維 ${row.fiber_g ?? "—"}g・食塩相当量 ${row.salt_g ?? "—"}g\n`;
  if (event.entity_type === "nutrition_target" && row) return `\n- ${when}｜目標変更｜${row.effective_from}から ${row.energy_kcal}kcal / P${row.protein_g} F${row.fat_g} C${row.carbohydrate_g}（revision ${row.revision}）\n`;
  if (event.entity_type === "favorite" && row) return `\n- ${when}｜定番更新｜${row.name}｜${row.energy_kcal}kcal / P${row.protein_g} F${row.fat_g} C${row.carbohydrate_g}\n`;
  return `\n- ${when}｜更新｜${event.entity_type} \`${event.entity_id}\`\n`;
}

const eventQuery = new URLSearchParams({ user_id: `eq.${MEAL_TRACKER_USER_ID}`, delivered_at: "is.null", order: "occurred_at.asc" });
const events = await requestJson("GET", `obsidian_sync_events?${eventQuery}`);
if (!events.length) {
  console.log("未配信イベントはありません。");
  process.exit(0);
}

const tables = { meal_item: "meal_items", favorite: "favorites", nutrition_target: "nutrition_targets" };
const lines = [];
for (const event of events) {
  let row;
  if (event.operation === "upsert") {
    const query = new URLSearchParams({ id: `eq.${event.entity_id}`, limit: "1" });
    [row] = await requestJson("GET", `${tables[event.entity_type]}?${query}`);
  }
  lines.push(formatEvent(event, row));
}
await ensureLog();
await appendFile(logPath, lines.join(""), "utf8");
const deliveryQuery = new URLSearchParams({ id: `in.(${events.map((event) => event.id).join(",")})` });
await requestJson("PATCH", `obsidian_sync_events?${deliveryQuery}`, { delivered_at: new Date().toISOString() });
console.log(`${events.length}件を${logPath}へ追記しました。`);
