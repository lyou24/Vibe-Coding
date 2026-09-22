import type { SupabaseClient } from "@supabase/supabase-js";

export type CloudNutrition = { energy: number; protein: number; fat: number; carbohydrate: number; sugar: number | null; fiber: number | null; salt: number | null };
export type CloudMealItem = { id: string; name: string; mealType: string; recordedAt: string; nutrition: CloudNutrition; source?: "manual" | "favorite" | "ai"; assumptions?: string[] };
export type CloudFavorite = { id: string; name: string; mealType: string; nutrition: CloudNutrition };
export type CloudTarget = { id: string; effectiveFrom: string; revision: number; energy: number; protein: number; fat: number; carbohydrate: number };

export type CloudSnapshot = { items: CloudMealItem[]; favorites: CloudFavorite[]; targets: CloudTarget[] };

const dateFormatter = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Tokyo" });

export async function uploadSnapshot(client: SupabaseClient, snapshot: CloudSnapshot) {
  const meals = snapshot.items.map((item) => ({ id: item.id, recorded_at: `${item.recordedAt}T12:00:00+09:00`, recorded_date: item.recordedAt, meal_type: item.mealType, name: item.name, energy_kcal: item.nutrition.energy, protein_g: item.nutrition.protein, fat_g: item.nutrition.fat, carbohydrate_g: item.nutrition.carbohydrate, sugar_g: item.nutrition.sugar, fiber_g: item.nutrition.fiber, salt_g: item.nutrition.salt, source: item.source ?? "manual", assumptions: item.assumptions ?? [] }));
  const favorites = snapshot.favorites.map((item) => ({ id: item.id, name: item.name, meal_type: item.mealType, energy_kcal: item.nutrition.energy, protein_g: item.nutrition.protein, fat_g: item.nutrition.fat, carbohydrate_g: item.nutrition.carbohydrate, sugar_g: item.nutrition.sugar, fiber_g: item.nutrition.fiber, salt_g: item.nutrition.salt }));
  const targets = snapshot.targets.map((item) => ({ id: item.id, effective_from: item.effectiveFrom, revision: item.revision, energy_kcal: item.energy, protein_g: item.protein, fat_g: item.fat, carbohydrate_g: item.carbohydrate }));
  const operations = [
    meals.length ? client.from("meal_items").upsert(meals, { onConflict: "id" }) : Promise.resolve({ error: null }),
    favorites.length ? client.from("favorites").upsert(favorites, { onConflict: "id" }) : Promise.resolve({ error: null }),
    targets.length ? client.from("nutrition_targets").upsert(targets, { onConflict: "id" }) : Promise.resolve({ error: null }),
  ];
  const result = await Promise.all(operations);
  const error = result.find((entry) => entry.error)?.error;
  if (error) throw error;
}

export async function downloadSnapshot(client: SupabaseClient): Promise<CloudSnapshot> {
  const [meals, favorites, targets] = await Promise.all([client.from("meal_items").select("*").order("recorded_date", { ascending: false }), client.from("favorites").select("*").order("created_at"), client.from("nutrition_targets").select("*").order("effective_from").order("revision")]);
  const error = meals.error || favorites.error || targets.error;
  if (error) throw error;
  return {
    items: (meals.data ?? []).map((item) => ({ id: item.id, name: item.name, mealType: item.meal_type, recordedAt: item.recorded_date ?? dateFormatter.format(new Date(item.recorded_at)), nutrition: { energy: Number(item.energy_kcal), protein: Number(item.protein_g), fat: Number(item.fat_g), carbohydrate: Number(item.carbohydrate_g), sugar: item.sugar_g === null ? null : Number(item.sugar_g), fiber: item.fiber_g === null ? null : Number(item.fiber_g), salt: item.salt_g === null ? null : Number(item.salt_g) }, source: item.source, assumptions: Array.isArray(item.assumptions) ? (item.assumptions as unknown[]).filter((value): value is string => typeof value === "string") : [] })),
    favorites: (favorites.data ?? []).map((item) => ({ id: item.id, name: item.name, mealType: item.meal_type, nutrition: { energy: Number(item.energy_kcal), protein: Number(item.protein_g), fat: Number(item.fat_g), carbohydrate: Number(item.carbohydrate_g), sugar: item.sugar_g === null ? null : Number(item.sugar_g), fiber: item.fiber_g === null ? null : Number(item.fiber_g), salt: item.salt_g === null ? null : Number(item.salt_g) } })),
    targets: (targets.data ?? []).map((item) => ({ id: item.id, effectiveFrom: item.effective_from, revision: item.revision, energy: Number(item.energy_kcal), protein: Number(item.protein_g), fat: Number(item.fat_g), carbohydrate: Number(item.carbohydrate_g) })),
  };
}
