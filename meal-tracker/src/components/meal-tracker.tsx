"use client";

import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { getSupabaseBrowserClient } from "@/lib/supabase-browser";
import { downloadSnapshot, uploadSnapshot } from "@/lib/cloud-data";

interface Nutrition {
  energy: number;
  protein: number;
  fat: number;
  carbohydrate: number;
  sugar: number | null;
  fiber: number | null;
  salt: number | null;
}

interface MealItem {
  id: string;
  name: string;
  mealType: string;
  recordedAt: string;
  nutrition: Nutrition;
}

interface Favorite {
  id: string;
  name: string;
  mealType: string;
  nutrition: Nutrition;
}

interface Target {
  id: string;
  effectiveFrom: string;
  revision: number;
  energy: number;
  protein: number;
  fat: number;
  carbohydrate: number;
}

const storageKey = "meal-tracker-v1";
const dateFormatter = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Tokyo" });
const today = dateFormatter.format(new Date());
const defaultNutrition: Nutrition = { energy: 0, protein: 0, fat: 0, carbohydrate: 0, sugar: null, fiber: null, salt: null };
const defaultFavorite: Favorite = {
  id: "00000000-0000-4000-8000-000000000001",
  name: "プロテインドリンク",
  mealType: "間食",
  nutrition: { energy: 120, protein: 24, fat: 1.5, carbohydrate: 4, sugar: 3, fiber: 0, salt: 0.2 },
};

function createId() {
  return crypto.randomUUID();
}

function normalizeFavoriteIds(favorites: Favorite[]) {
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  return favorites.map((favorite) => uuid.test(favorite.id) ? favorite : { ...favorite, id: createId() });
}

function csvCell(value: string | number | null) {
  const text = value === null ? "" : String(value);
  const protectedText = /^[=+\-@]/.test(text) ? `'${text}` : text;
  return `"${protectedText.replaceAll('"', '""')}"`;
}

function isNutrition(value: unknown): value is Nutrition {
  if (!value || typeof value !== "object") return false;
  const nutrition = value as Record<string, unknown>;
  return ["energy", "protein", "fat", "carbohydrate"].every((key) => typeof nutrition[key] === "number" && Number.isFinite(nutrition[key]))
    && ["sugar", "fiber", "salt"].every((key) => nutrition[key] === null || (typeof nutrition[key] === "number" && Number.isFinite(nutrition[key])));
}

function isBackup(value: unknown): value is { items: MealItem[]; favorites: Favorite[]; targets: Target[] } {
  if (!value || typeof value !== "object") return false;
  const backup = value as Record<string, unknown>;
  return Array.isArray(backup.items) && Array.isArray(backup.favorites) && Array.isArray(backup.targets)
    && backup.items.every((item) => typeof item?.id === "string" && typeof item?.name === "string" && typeof item?.recordedAt === "string" && isNutrition(item?.nutrition))
    && backup.favorites.every((favorite) => typeof favorite?.id === "string" && typeof favorite?.name === "string" && isNutrition(favorite?.nutrition))
    && backup.targets.every((target) => typeof target?.id === "string" && typeof target?.effectiveFrom === "string" && ["energy", "protein", "fat", "carbohydrate", "revision"].every((key) => typeof target?.[key] === "number"));
}

function sumNutrition(items: MealItem[]): Nutrition {
  function sumOptional(key: "sugar" | "fiber" | "salt") {
    if (items.some((item) => item.nutrition[key] === null)) return null;
    return items.reduce((total, item) => total + (item.nutrition[key] ?? 0), 0);
  }

  return {
    energy: items.reduce((total, item) => total + item.nutrition.energy, 0),
    protein: items.reduce((total, item) => total + item.nutrition.protein, 0),
    fat: items.reduce((total, item) => total + item.nutrition.fat, 0),
    carbohydrate: items.reduce((total, item) => total + item.nutrition.carbohydrate, 0),
    sugar: sumOptional("sugar"),
    fiber: sumOptional("fiber"),
    salt: sumOptional("salt"),
  };
}

function formatNumber(value: number | null, digits = 1) {
  return value === null ? "—" : value.toLocaleString("ja-JP", { maximumFractionDigits: digits });
}

function useLocalData() {
  const [items, setItems] = useState<MealItem[]>([]);
  const [favorites, setFavorites] = useState<Favorite[]>([defaultFavorite]);
  const [targets, setTargets] = useState<Target[]>([]);
  const [isHydrated, setIsHydrated] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const raw = window.localStorage.getItem(storageKey);
      if (raw) {
        try {
          const parsed = JSON.parse(raw) as { items?: MealItem[]; favorites?: Favorite[]; targets?: Target[] };
          setItems(parsed.items ?? []);
          const nextFavorites = normalizeFavoriteIds(parsed.favorites?.length ? parsed.favorites : [defaultFavorite]);
          setFavorites(nextFavorites);
          setTargets(parsed.targets ?? []);
          window.localStorage.setItem(storageKey, JSON.stringify({ schemaVersion: 1, items: parsed.items ?? [], favorites: nextFavorites, targets: parsed.targets ?? [] }));
        } catch {
          window.localStorage.removeItem(storageKey);
        }
      }
      setIsHydrated(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  function persist(nextItems: MealItem[], nextFavorites: Favorite[], nextTargets: Target[]) {
    setItems(nextItems); setFavorites(nextFavorites); setTargets(nextTargets);
    window.localStorage.setItem(storageKey, JSON.stringify({ schemaVersion: 1, items: nextItems, favorites: nextFavorites, targets: nextTargets }));
  }

  return { items, favorites, targets, isHydrated, persist };
}

export function MealTracker() {
  const { items, favorites, targets, isHydrated, persist } = useLocalData();
  const [selectedDate, setSelectedDate] = useState(today);
  const [activeView, setActiveView] = useState<"today" | "favorites" | "settings">("today");
  const [isEntryOpen, setIsEntryOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<MealItem | undefined>();
  const [analysisDraft, setAnalysisDraft] = useState<Omit<MealItem, "id" | "recordedAt"> | undefined>();
  const [isAnalysisOpen, setIsAnalysisOpen] = useState(false);
  const [isTargetOpen, setIsTargetOpen] = useState(false);
  const [isFavoriteOpen, setIsFavoriteOpen] = useState(false);
  const [editingFavorite, setEditingFavorite] = useState<Favorite | undefined>();
  const [message, setMessage] = useState("");
  const importRef = useRef<HTMLInputElement>(null);

  const dayItems = useMemo(() => items.filter((item) => item.recordedAt === selectedDate), [items, selectedDate]);
  const summary = useMemo(() => sumNutrition(dayItems), [dayItems]);
  const target = useMemo(() => [...targets].filter((entry) => entry.effectiveFrom <= selectedDate).sort((a, b) => b.effectiveFrom.localeCompare(a.effectiveFrom) || b.revision - a.revision)[0], [selectedDate, targets]);

  if (!isHydrated) return <main className="shell"><p className="loading">記録を読み込んでいます…</p></main>;

  function addItem(item: Omit<MealItem, "id">) {
    const nextItems = [...items, { ...item, id: createId() }];
    persist(nextItems, favorites, targets);
    setMessage(`${item.name}を追加しました`);
  }

  function saveItem(item: Omit<MealItem, "id" | "recordedAt">) {
    if (editingItem) {
      persist(items.map((current) => current.id === editingItem.id ? { ...current, ...item } : current), favorites, targets);
      setMessage(`${item.name}を更新しました`);
    } else {
      addItem({ ...item, recordedAt: selectedDate });
    }
    setEditingItem(undefined);
    setAnalysisDraft(undefined);
    setIsEntryOpen(false);
  }

  function addFavorite(favorite: Favorite) {
    addItem({ name: favorite.name, mealType: favorite.mealType, recordedAt: selectedDate, nutrition: favorite.nutrition });
  }

  function removeItem(id: string) {
    persist(items.filter((item) => item.id !== id), favorites, targets);
  }

  function saveTarget(next: Omit<Target, "id" | "revision" | "effectiveFrom">) {
    const revisionsToday = targets.filter((entry) => entry.effectiveFrom === today);
    const nextTarget: Target = { ...next, id: createId(), effectiveFrom: today, revision: revisionsToday.length + 1 };
    persist(items, favorites, [...targets, nextTarget]);
    setIsTargetOpen(false);
    setMessage(`${today}からの目標を保存しました`);
  }

  function exportJson() {
    const payload = JSON.stringify({ schemaVersion: 1, exportedAt: new Date().toISOString(), items, favorites, targets }, null, 2);
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([payload], { type: "application/json" }));
    link.download = `meal-tracker-${today}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
    setMessage("JSONバックアップを作成しました");
  }

  function exportCsv() {
    const header = ["食事ID", "記録日", "食事区分", "料理名", "カロリー_kcal", "たんぱく質_g", "脂質_g", "炭水化物_g", "糖質_g", "食物繊維_g", "食塩相当量_g"];
    const rows = items.map((item) => [item.id, item.recordedAt, item.mealType, item.name, item.nutrition.energy, item.nutrition.protein, item.nutrition.fat, item.nutrition.carbohydrate, item.nutrition.sugar, item.nutrition.fiber, item.nutrition.salt]);
    const payload = [header, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([`\uFEFF${payload}`], { type: "text/csv;charset=utf-8" }));
    link.download = `meal-records-${today}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
    setMessage("CSVを作成しました");
  }

  async function importJson(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const parsed: unknown = JSON.parse(await file.text());
      if (!isBackup(parsed)) throw new Error("形式が一致しません");
      const accepted = window.confirm(`このバックアップで端末内の食事 ${items.length} 件、定型 ${favorites.length} 件、目標履歴 ${targets.length} 件を置き換えます。続けますか？`);
      if (!accepted) return;
      persist(parsed.items, normalizeFavoriteIds(parsed.favorites.length ? parsed.favorites : [defaultFavorite]), parsed.targets);
      setMessage("JSONバックアップを復元しました");
    } catch {
      setMessage("復元できませんでした。食事ログのJSONバックアップを選んでください。");
    }
  }

  function saveFavorite(next: Omit<Favorite, "id">) {
    const favorite = { ...next, id: editingFavorite?.id ?? createId() };
    const nextFavorites = editingFavorite ? favorites.map((item) => item.id === favorite.id ? favorite : item) : [...favorites, favorite];
    persist(items, nextFavorites, targets);
    setEditingFavorite(undefined);
    setIsFavoriteOpen(false);
    setMessage(`${favorite.name}をよく食べるものへ保存しました`);
  }

  function removeFavorite(id: string) {
    const favorite = favorites.find((item) => item.id === id);
    persist(items, favorites.filter((item) => item.id !== id), targets);
    setMessage(`${favorite?.name ?? "定型"}を一覧から外しました`);
  }

  function openFavorite(favorite?: Favorite) {
    setEditingFavorite(favorite);
    setIsFavoriteOpen(true);
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div><p className="eyebrow">PERSONAL NUTRITION LOG</p><h1>食事ログ</h1></div>
        <button className="icon-button" type="button" aria-label="設定を開く" onClick={() => setActiveView("settings")}>⚙</button>
      </header>
      <nav className="tabs" aria-label="画面切替">
        <button className={activeView === "today" ? "active" : ""} onClick={() => setActiveView("today")}>今日</button>
        <button className={activeView === "favorites" ? "active" : ""} onClick={() => setActiveView("favorites")}>よく食べるもの</button>
        <button className={activeView === "settings" ? "active" : ""} onClick={() => setActiveView("settings")}>設定</button>
      </nav>
      {message ? <p className="notice" role="status">{message}</p> : null}
      {activeView === "today" ? <TodayView selectedDate={selectedDate} setSelectedDate={setSelectedDate} summary={summary} target={target} items={dayItems} favorites={favorites} onAddFavorite={addFavorite} onRemove={removeItem} onEdit={(item) => { setAnalysisDraft(undefined); setEditingItem(item); setIsEntryOpen(true); }} onOpenEntry={() => { setAnalysisDraft(undefined); setEditingItem(undefined); setIsEntryOpen(true); }} onOpenTarget={() => setIsTargetOpen(true)} onOpenFavorites={() => setActiveView("favorites")} onOpenAnalysis={() => setIsAnalysisOpen(true)} /> : null}
      {activeView === "favorites" ? <FavoritesView favorites={favorites} onAdd={addFavorite} onCreate={() => openFavorite()} onEdit={openFavorite} onRemove={removeFavorite} /> : null}
      {activeView === "settings" ? <SettingsView items={items} favorites={favorites} targets={targets} onRestoreCloud={(snapshot) => persist(snapshot.items, snapshot.favorites.length ? snapshot.favorites : [defaultFavorite], snapshot.targets)} onExportJson={exportJson} onExportCsv={exportCsv} onImport={() => importRef.current?.click()} onOpenTarget={() => setIsTargetOpen(true)} /> : null}
      {isEntryOpen ? <EntryDialog item={editingItem ?? analysisDraft} onClose={() => { setAnalysisDraft(undefined); setEditingItem(undefined); setIsEntryOpen(false); }} onSave={saveItem} /> : null}
      {isAnalysisOpen ? <AnalysisDialog onClose={() => setIsAnalysisOpen(false)} onUseDraft={(draft) => { setIsAnalysisOpen(false); setEditingItem(undefined); setAnalysisDraft(draft); setIsEntryOpen(true); }} /> : null}
      {isTargetOpen ? <TargetDialog target={[...targets].filter((entry) => entry.effectiveFrom <= today).sort((a, b) => b.effectiveFrom.localeCompare(a.effectiveFrom) || b.revision - a.revision)[0]} onClose={() => setIsTargetOpen(false)} onSave={saveTarget} /> : null}
      {isFavoriteOpen ? <FavoriteDialog favorite={editingFavorite} onClose={() => { setEditingFavorite(undefined); setIsFavoriteOpen(false); }} onSave={saveFavorite} /> : null}
      <input ref={importRef} className="visually-hidden" type="file" accept="application/json,.json" onChange={importJson} />
    </main>
  );
}

interface TodayViewProps { selectedDate: string; setSelectedDate: (date: string) => void; summary: Nutrition; target?: Target; items: MealItem[]; favorites: Favorite[]; onAddFavorite: (favorite: Favorite) => void; onRemove: (id: string) => void; onEdit: (item: MealItem) => void; onOpenEntry: () => void; onOpenTarget: () => void; onOpenFavorites: () => void; onOpenAnalysis: () => void; }
function TodayView({ selectedDate, setSelectedDate, summary, target, items, favorites, onAddFavorite, onRemove, onEdit, onOpenEntry, onOpenTarget, onOpenFavorites, onOpenAnalysis }: TodayViewProps) {
  return <section className="content">
    <div className="date-row"><button type="button" onClick={() => setSelectedDate(new Date(new Date(`${selectedDate}T12:00:00`).getTime() - 86400000).toISOString().slice(0, 10))}>‹</button><input aria-label="記録日" type="date" value={selectedDate} onChange={(event) => setSelectedDate(event.target.value)} /><button type="button" onClick={() => setSelectedDate(new Date(new Date(`${selectedDate}T12:00:00`).getTime() + 86400000).toISOString().slice(0, 10))}>›</button></div>
    <section className="summary-card"><div className="summary-head"><div><p className="label">ENERGY</p><strong>{formatNumber(summary.energy, 0)} <small>kcal</small></strong></div><button type="button" className="text-button" onClick={onOpenTarget}>{target ? "目標を変更" : "目標を設定"}</button></div>
    <div className="macro-grid"><Macro label="P" value={summary.protein} target={target?.protein} /><Macro label="F" value={summary.fat} target={target?.fat} /><Macro label="C" value={summary.carbohydrate} target={target?.carbohydrate} /></div>
    <div className="detail-grid"><span>糖質 <b>{formatNumber(summary.sugar)}g</b></span><span>食物繊維 <b>{formatNumber(summary.fiber)}g</b></span><span>食塩相当量 <b>{formatNumber(summary.salt)}g</b></span></div>
    {target ? <p className="target-note">目標 {formatNumber(target.energy, 0)}kcal / P{target.protein} F{target.fat} C{target.carbohydrate}</p> : <p className="target-note">目標は未設定です</p>}</section>
    <section><div className="section-title"><h2>記録</h2><button type="button" className="primary-button" onClick={onOpenEntry}>＋ 追加</button></div>{items.length ? <ul className="item-list">{items.map((item) => <li key={item.id}><div><strong>{item.name}</strong><p>{item.mealType} · {formatNumber(item.nutrition.energy, 0)} kcal · P{formatNumber(item.nutrition.protein)} F{formatNumber(item.nutrition.fat)} C{formatNumber(item.nutrition.carbohydrate)}</p></div><div className="card-actions"><button className="secondary-button" type="button" onClick={() => onEdit(item)}>編集</button><button aria-label={`${item.name}を削除`} type="button" className="remove-button" onClick={() => onRemove(item.id)}>×</button></div></li>)}</ul> : <p className="empty">まだ記録はありません。食べたものを追加してください。</p>}</section>
    <section><div className="section-title"><h2>よく食べるもの</h2><button type="button" className="text-button" onClick={onOpenFavorites}>すべて見る</button></div><div className="favorite-row">{favorites.slice(0, 3).map((favorite) => <button key={favorite.id} className="favorite-chip" type="button" onClick={() => onAddFavorite(favorite)}><b>＋</b>{favorite.name}<small>{formatNumber(favorite.nutrition.energy, 0)} kcal</small></button>)}</div></section>
    <section className="ai-card"><span>✦</span><div><strong>AIで食事を下書き</strong><p>写真・料理名・メニュー表を送ると、推定結果を編集してから保存できます。</p></div><button className="secondary-button" type="button" onClick={onOpenAnalysis}>解析</button></section>
  </section>;
}

function Macro({ label, value, target }: { label: string; value: number; target?: number }) { const ratio = target ? Math.min((value / target) * 100, 100) : 0; return <div className="macro"><p>{label}</p><strong>{formatNumber(value)}<small>g</small></strong><div className="progress"><i style={{ width: `${ratio}%` }} /></div>{target ? <small>目標 {target}g</small> : <small>目標 —</small>}</div>; }

function FavoritesView({ favorites, onAdd, onCreate, onEdit, onRemove }: { favorites: Favorite[]; onAdd: (favorite: Favorite) => void; onCreate: () => void; onEdit: (favorite: Favorite) => void; onRemove: (id: string) => void }) { return <section className="content"><div className="section-title"><div><p className="eyebrow">QUICK ADD</p><h2>よく食べるもの</h2></div><button className="primary-button" type="button" onClick={onCreate}>＋ 登録</button></div><p className="empty">確認済みの食事を登録すると、AI解析なしで追加できます。</p><div className="favorite-list">{favorites.map((favorite) => <article key={favorite.id}><div><strong>{favorite.name}</strong><p>{favorite.mealType} · {formatNumber(favorite.nutrition.energy, 0)} kcal</p><p>P{formatNumber(favorite.nutrition.protein)} / F{formatNumber(favorite.nutrition.fat)} / C{formatNumber(favorite.nutrition.carbohydrate)}</p></div><div className="card-actions"><button className="secondary-button" type="button" onClick={() => onEdit(favorite)}>編集</button><button className="primary-button" type="button" onClick={() => onAdd(favorite)}>追加</button><button className="remove-button" aria-label={`${favorite.name}を一覧から外す`} type="button" onClick={() => onRemove(favorite.id)}>×</button></div></article>)}</div></section>; }

function SettingsView({ items, favorites, targets, onRestoreCloud, onExportJson, onExportCsv, onImport, onOpenTarget }: { items: MealItem[]; favorites: Favorite[]; targets: Target[]; onRestoreCloud: (snapshot: { items: MealItem[]; favorites: Favorite[]; targets: Target[] }) => void; onExportJson: () => void; onExportCsv: () => void; onImport: () => void; onOpenTarget: () => void }) { return <section className="content"><p className="eyebrow">SETTINGS & DATA</p><h2>設定</h2><CloudConnection items={items} favorites={favorites} targets={targets} onRestore={onRestoreCloud} /><article className="settings-card"><div><strong>カロリー・PFC目標</strong><p>変更した日から新しい目標を使い、過去の表示は変えません。</p></div><button className="primary-button" type="button" onClick={onOpenTarget}>設定</button></article><article className="settings-card"><div><strong>データ出力</strong><p>JSONは完全バックアップ、CSVは表計算ソフト用の食事明細です。</p></div><div className="card-actions"><button className="secondary-button" type="button" onClick={onExportJson}>JSON</button><button className="secondary-button" type="button" onClick={onExportCsv}>CSV</button></div></article><article className="settings-card"><div><strong>JSONを復元</strong><p>選んだバックアップで現在の端末内データを置き換えます。</p></div><button className="secondary-button" type="button" onClick={onImport}>復元</button></article><section><div className="section-title"><h2>目標履歴</h2></div>{targets.length ? <ol className="history-list">{[...targets].sort((a, b) => b.effectiveFrom.localeCompare(a.effectiveFrom) || b.revision - a.revision).map((target) => <li key={target.id}><strong>{target.effectiveFrom}から</strong><span>{target.energy}kcal / P{target.protein} F{target.fat} C{target.carbohydrate}</span></li>)}</ol> : <p className="empty">まだ目標は設定されていません。</p>}</section></section>; }

function CloudConnection({ items, favorites, targets, onRestore }: { items: MealItem[]; favorites: Favorite[]; targets: Target[]; onRestore: (snapshot: { items: MealItem[]; favorites: Favorite[]; targets: Target[] }) => void }) {
  const [email, setEmail] = useState(""); const [status, setStatus] = useState(""); const [isSending, setIsSending] = useState(false); const [userEmail, setUserEmail] = useState<string | undefined>();
  const supabase = getSupabaseBrowserClient();
  useEffect(() => { if (!supabase) return; void supabase.auth.getUser().then(({ data }) => setUserEmail(data.user?.email)); }, [supabase]);
  async function sendLink(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!supabase) return; setIsSending(true); setStatus(""); const { error } = await supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: window.location.origin } }); setIsSending(false); setStatus(error ? `送信できませんでした: ${error.message}` : "ログインリンクを送信しました。メールからこのアプリへ戻ってください。"); }
  if (!supabase) return <article className="settings-card"><div><strong>クラウド保存</strong><p>SupabaseのURLと匿名キーをホスティング環境変数へ設定すると、本人専用ログインを有効にできます。</p></div><span className="status-badge">未接続</span></article>;
  async function upload() { if (!supabase) return; setStatus("同期中です…"); try { await uploadSnapshot(supabase, { items, favorites, targets }); setStatus("この端末の記録をクラウドへ保存しました。"); } catch { setStatus("保存できませんでした。ログインと接続を確認してください。"); } }
  async function download() { if (!supabase) return; setStatus("取得中です…"); try { const snapshot = await downloadSnapshot(supabase); if (!window.confirm(`クラウドの食事 ${snapshot.items.length} 件、定番 ${snapshot.favorites.length} 件、目標 ${snapshot.targets.length} 件で端末内データを置き換えます。続けますか？`)) { setStatus(""); return; } onRestore(snapshot); setStatus("クラウドの記録をこの端末へ反映しました。"); } catch { setStatus("取得できませんでした。ログインと接続を確認してください。"); } }
  if (userEmail) return <article className="settings-card"><div><strong>クラウド保存</strong><p>{userEmail} としてログインしています。</p><div className="card-actions"><button className="secondary-button" type="button" onClick={upload}>この端末を保存</button><button className="secondary-button" type="button" onClick={download}>クラウドから取得</button></div>{status ? <p role="status">{status}</p> : null}</div><span className="status-badge">ログイン済み</span></article>;
  return <article className="settings-card cloud-login"><div><strong>クラウド保存</strong><p>本人のメールアドレスへログインリンクを送ります。</p><form onSubmit={sendLink}><input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /><button className="secondary-button" disabled={isSending}>{isSending ? "送信中…" : "リンクを送る"}</button></form>{status ? <p role="status">{status}</p> : null}</div></article>;
}

function EntryDialog({ item, onClose, onSave }: { item?: Omit<MealItem, "id" | "recordedAt">; onClose: () => void; onSave: (item: Omit<MealItem, "id" | "recordedAt">) => void }) {
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = new FormData(event.currentTarget); const number = (key: string) => Number(form.get(key) || 0); const nullable = (key: string) => form.get(key) === "" ? null : number(key); onSave({ name: String(form.get("name")), mealType: String(form.get("mealType")), nutrition: { energy: number("energy"), protein: number("protein"), fat: number("fat"), carbohydrate: number("carbohydrate"), sugar: nullable("sugar"), fiber: nullable("fiber"), salt: nullable("salt") } }); }
  return <Dialog title={item ? "食事を編集" : "食事を追加"} onClose={onClose}><form onSubmit={submit}><label>料理名<input required name="name" defaultValue={item?.name} placeholder="例：鶏むね肉の定食" /></label><label>食事区分<select name="mealType" defaultValue={item?.mealType ?? "朝食"}><option>朝食</option><option>昼食</option><option>夕食</option><option>間食</option></select></label><div className="form-grid"><NumberInput label="カロリー (kcal)" name="energy" defaultValue={item?.nutrition.energy} required /><NumberInput label="P (g)" name="protein" defaultValue={item?.nutrition.protein} required /><NumberInput label="F (g)" name="fat" defaultValue={item?.nutrition.fat} required /><NumberInput label="C (g)" name="carbohydrate" defaultValue={item?.nutrition.carbohydrate} required /><NumberInput label="糖質 (g)" name="sugar" defaultValue={item?.nutrition.sugar ?? undefined} /><NumberInput label="食物繊維 (g)" name="fiber" defaultValue={item?.nutrition.fiber ?? undefined} /><NumberInput label="食塩相当量 (g)" name="salt" defaultValue={item?.nutrition.salt ?? undefined} /></div><div className="dialog-actions"><button type="button" className="secondary-button" onClick={onClose}>キャンセル</button><button className="primary-button">保存</button></div></form></Dialog>;
}

type AnalysisDraft = Omit<MealItem, "id" | "recordedAt"> & { assumptions: string[] };

async function preparePhoto(file: File) {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type)) throw new Error("写真はJPEG・PNG・WebPを選んでください。");
  const url = URL.createObjectURL(file);
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => { const next = new Image(); next.onload = () => resolve(next); next.onerror = () => reject(new Error("写真を読み込めませんでした。")); next.src = url; });
    const scale = Math.min(1, 1600 / Math.max(image.naturalWidth, image.naturalHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(image.naturalWidth * scale); canvas.height = Math.round(image.naturalHeight * scale);
    canvas.getContext("2d")?.drawImage(image, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
    if (!blob) throw new Error("写真を準備できませんでした。");
    const data = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1] ?? ""); reader.onerror = () => reject(new Error("写真を読み込めませんでした。")); reader.readAsDataURL(blob); });
    return { mimeType: "image/jpeg", data };
  } finally { URL.revokeObjectURL(url); }
}

function AnalysisDialog({ onClose, onUseDraft }: { onClose: () => void; onUseDraft: (draft: Omit<MealItem, "id" | "recordedAt">) => void }) {
  const [prompt, setPrompt] = useState(""); const [photo, setPhoto] = useState<File | undefined>(); const [draft, setDraft] = useState<AnalysisDraft | undefined>(); const [error, setError] = useState(""); const [isAnalyzing, setIsAnalyzing] = useState(false);
  async function analyze(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setError(""); setDraft(undefined); setIsAnalyzing(true); try { const image = photo ? await preparePhoto(photo) : undefined; const response = await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt, image }) }); const payload = await response.json() as { draft?: AnalysisDraft; error?: string }; if (!response.ok || !payload.draft) throw new Error(payload.error || "解析できませんでした。"); setDraft(payload.draft); } catch (reason) { setError(reason instanceof Error ? reason.message : "解析できませんでした。"); } finally { setIsAnalyzing(false); } }
  return <Dialog title="AIで食事を下書き" onClose={onClose}><form onSubmit={analyze}><p className="dialog-note">写真は位置情報などのメタデータを除いた縮小画像としてGeminiへ送信します。結果は必ず保存前に編集できます。</p><label>料理名・補足<input value={prompt} onChange={(event) => setPrompt(event.target.value)} name="prompt" placeholder="例：鶏むね肉の定食、ご飯は少なめ" /></label><label>食事写真・メニュー表<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setPhoto(event.target.files?.[0])} /><small>{photo ? photo.name : "JPEG・PNG・WebPのみ。写真なしで料理名だけでも解析できます。"}</small></label>{error ? <p className="form-error" role="alert">{error}</p> : null}{draft ? <section className="analysis-result"><strong>{draft.name}</strong><p>{draft.mealType} · {formatNumber(draft.nutrition.energy, 0)} kcal · P{formatNumber(draft.nutrition.protein)} F{formatNumber(draft.nutrition.fat)} C{formatNumber(draft.nutrition.carbohydrate)}</p><p>前提: {draft.assumptions.length ? draft.assumptions.join("／") : "なし"}</p><button className="primary-button" type="button" onClick={() => onUseDraft(draft)}>編集して保存</button></section> : null}<div className="dialog-actions"><button type="button" className="secondary-button" onClick={onClose}>キャンセル</button><button className="primary-button" disabled={isAnalyzing}>{isAnalyzing ? "解析中…" : "解析する"}</button></div></form></Dialog>;
}

function TargetDialog({ target, onClose, onSave }: { target?: Target; onClose: () => void; onSave: (target: Omit<Target, "id" | "revision" | "effectiveFrom">) => void }) { function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = new FormData(event.currentTarget); onSave({ energy: Number(form.get("energy")), protein: Number(form.get("protein")), fat: Number(form.get("fat")), carbohydrate: Number(form.get("carbohydrate")) }); } return <Dialog title="カロリー・PFC目標" onClose={onClose}><p className="dialog-note">今日から適用します。昨日以前の目標は変更しません。</p><form onSubmit={submit}><div className="form-grid"><NumberInput label="カロリー (kcal)" name="energy" defaultValue={target?.energy} required /><NumberInput label="P (g)" name="protein" defaultValue={target?.protein} required /><NumberInput label="F (g)" name="fat" defaultValue={target?.fat} required /><NumberInput label="C (g)" name="carbohydrate" defaultValue={target?.carbohydrate} required /></div><div className="dialog-actions"><button type="button" className="secondary-button" onClick={onClose}>キャンセル</button><button className="primary-button">今日から保存</button></div></form></Dialog>; }
function FavoriteDialog({ favorite, onClose, onSave }: { favorite?: Favorite; onClose: () => void; onSave: (favorite: Omit<Favorite, "id">) => void }) { function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = new FormData(event.currentTarget); const number = (key: string) => Number(form.get(key) || 0); const nullable = (key: string) => form.get(key) === "" ? null : number(key); onSave({ name: String(form.get("name")), mealType: String(form.get("mealType")), nutrition: { energy: number("energy"), protein: number("protein"), fat: number("fat"), carbohydrate: number("carbohydrate"), sugar: nullable("sugar"), fiber: nullable("fiber"), salt: nullable("salt") } }); } return <Dialog title={favorite ? "定番を編集" : "よく食べるものを登録"} onClose={onClose}><form onSubmit={submit}><label>名前<input required name="name" defaultValue={favorite?.name} /></label><label>食事区分<select name="mealType" defaultValue={favorite?.mealType ?? "朝食"}><option>朝食</option><option>昼食</option><option>夕食</option><option>間食</option></select></label><div className="form-grid"><NumberInput label="カロリー (kcal)" name="energy" defaultValue={favorite?.nutrition.energy} required /><NumberInput label="P (g)" name="protein" defaultValue={favorite?.nutrition.protein} required /><NumberInput label="F (g)" name="fat" defaultValue={favorite?.nutrition.fat} required /><NumberInput label="C (g)" name="carbohydrate" defaultValue={favorite?.nutrition.carbohydrate} required /><NumberInput label="糖質 (g)" name="sugar" defaultValue={favorite?.nutrition.sugar ?? undefined} /><NumberInput label="食物繊維 (g)" name="fiber" defaultValue={favorite?.nutrition.fiber ?? undefined} /><NumberInput label="食塩相当量 (g)" name="salt" defaultValue={favorite?.nutrition.salt ?? undefined} /></div><div className="dialog-actions"><button type="button" className="secondary-button" onClick={onClose}>キャンセル</button><button className="primary-button">保存</button></div></form></Dialog>; }
function NumberInput({ label, name, required, defaultValue }: { label: string; name: string; required?: boolean; defaultValue?: number }) { return <label>{label}<input required={required} min="0" step="0.1" type="number" name={name} defaultValue={defaultValue} /></label>; }
function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) { return <div className="dialog-backdrop" role="presentation"><section className="dialog" role="dialog" aria-modal="true" aria-label={title}><div className="dialog-header"><h2>{title}</h2><button type="button" className="icon-button" aria-label="閉じる" onClick={onClose}>×</button></div>{children}</section></div>; }
