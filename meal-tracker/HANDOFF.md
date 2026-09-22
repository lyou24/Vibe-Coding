---
title: 食事ログ 実装引き継ぎ書
category: 設定
tags: [AI作成, 開発引き継ぎ]
created_at: "2026-09-22 13:31"
updated_at: "2026-09-22 15:30"
summary: 実装済み機能、未接続の外部機能、検証結果、次の担当者への作業順を記録する。
related_notes:
  - "REQUIREMENTS.md"
  - "PROJECT_SPEC.md"
  - "COST_ESTIMATE.md"
---

# 食事ログ 実装引き継ぎ書

## 現在の状態

作業ルートは `C:/Users/lyoul/AI_Project/90_Git/meal-tracker/`。Next.js 16 / React 19 / TypeScriptによるスマートフォン向けの初期実装が動作する。

ローカル開発起動は `pnpm dev`。この環境では通常の `npm` が壊れた参照先を持つため使わない。`pnpm` 実行時に依存関係を再生成しようとする場合は、まず `CI=true pnpm install` を実行する。直接検証コマンドは以下。

```powershell
.\node_modules\.bin\eslint.cmd .
.\node_modules\.bin\tsc.cmd --noEmit
.\node_modules\.bin\next.cmd build
```

## 実装済み

- Notion風のiPhone優先画面。「今日」「よく食べるもの」「設定」の3画面。
- 手入力による食事追加。カロリー、P/F/C、糖質、食物繊維、食塩相当量の7項目を保存・日計表示。
- 当日の食事明細を編集できる。料理名、食事区分、栄養7項目を修正すると、同じ記録IDの日計を更新する。
- よく食べるものの登録・編集・削除とワンタップ追加（初期例：プロテインドリンク）。定番編集は過去の食事へ波及しない。
- カロリー/PFCの目標設定。保存日のAsia/Tokyo日付から有効、前日以前は目標未設定または旧履歴を維持。同日再設定はrevisionを追記し最後の値を採用。
- 食事・定型・目標履歴を端末のlocalStorageに保存。JSONバックアップを出力し、形式検証と置換確認を経て復元できる。
- 食事1件ごとの栄養7項目をCSVで出力。Excel等で開けるUTF-8 BOM付き形式。
- Gemini解析の画面とサーバー側API。料理名・補足・JPEG/PNG/WebP写真を構造化した栄養7項目の下書きへ変換し、編集後に保存する。写真は最大辺1600pxに再エンコードしてEXIFメタデータを除去してから送信する。
- Supabase向けのクラウドデータ定義。食事、定番、目標履歴、添付画像、Obsidian同期イベントのRLSとprivate画像バケットポリシーを`supabase/schema.sql`に用意。
- Supabase公式SDKと、環境変数設定後に使える本人用マジックリンクログイン導線。未設定時は端末内版を維持する。
- ログイン後の端末内スナップショットのクラウド保存と、確認付きクラウド取得。旧定番IDはUUIDへ自動移行する。
- iPhoneホーム画面追加のためのiOS standalone・safe area metadata。
- Obsidian同期用のSupabaseイベントトリガーと`sync_to_obsidian.py`。PCの環境変数から接続し、追記専用の`01_Config/12_memory/meal_log.md`へ反映する。
- 実運用はPython不要の`sync-to-obsidian.mjs`を使う。`pnpm sync:obsidian`で実行でき、未設定の環境変数では安全に停止する。
- PWA用manifestとfavicon。

## 明確に未実装

- Gemini APIの実リクエスト検証（`GEMINI_API_KEY`未設定）。
- 写真の履歴保存。
- 本人専用認証、クラウドDB/Storage、複数端末同期。
- Obsidianへの自動取り込み。
- 日付横断の食事履歴画面。
- 比率からのPFC目標入力。現状はg入力のみ。

未実装部分を「動作している」と表示しない。画面上でもAI解析は準備中と明示している。

## 検証済み

- ESLint：合格。
- TypeScript：合格。
- 本番ビルド：合格（Next.js 16.3.4）。
- ブラウザ確認：手入力した架空の「鶏むね肉とご飯」の7栄養項目が日計に反映されることを確認。目標の保存後に当日へ目標が表示され、前日に移動すると目標未設定になることを確認。定番管理、JSON/CSV導線、390px幅、既存値を表示する食事編集フォームを確認。コンソールエラー・警告なし。

## 重要な仕様と禁止事項

- 糖質・食物繊維はCの内訳。Cと内訳を二重に足さない。未知値を0として保存しない。
- 目標変更は当日から。過去へ遡及させない。食事の実績値は目標変更で変えない。
- 定型の編集は過去の食事に波及させない。
- 食事データ・写真・APIキーをGitやソースコードへ保存しない。`.env`を作成・編集しない。
- Gemini無料枠での解析方針とデータ利用条件はユーザー了承済み。ただしAPIキー作成や外部サービスのアカウント設定は未実施。
- `nutrisnap` はワークスペース直下に存在する別フォルダ。由来未確認のため触らない。
- 実アカウントのセットアップは`CLOUD_SETUP.md`に限定し、環境変数の値を会話・Git・`.env`へ書かない。

## 次の実装順

1. Gemini APIキーをホスティングのサーバー環境変数へ設定し、実画像・料理名・メニュー表で下書きと上限時の手入力を確認する。値をソースや会話へ保存しない。
2. クラウド基盤の無料枠・認証・画像保存を公式資料で確認し、`PROJECT_SPEC.md` の技術構成を確定する。
3. 認証・DB・Storageのスキーマとアクセス制御を実装する。端末内データの移行・失敗時の保持も設計する。
4. CSVをサーバーデータモデルの全項目へ拡張し、Obsidianへ食事・目標変更イベントを追記する同期処理を実装する。
5. iPhone実機でカメラ、ホーム画面起動、通信断、復元、日付境界を検証する。

## 今回の変更ファイル

- `src/app/page.tsx`、`src/app/layout.tsx`、`src/app/globals.css`
- `src/components/meal-tracker.tsx`
- `src/app/api/analyze/route.ts`、`supabase/schema.sql`、`CLOUD_SETUP.md`
- `src/lib/supabase-browser.ts`、`.env.example`
- `src/lib/cloud-data.ts`
- `scripts/sync_to_obsidian.py`
- `scripts/sync-to-obsidian.mjs`
- `public/manifest.webmanifest`、`public/favicon.svg`
- `package.json`、`pnpm-lock.yaml`、設定ファイル
- `HANDOFF.md`

要件・仕様の正本は `REQUIREMENTS.md`、`PROJECT_SPEC.md`、費用・工数は `COST_ESTIMATE.md`。変更時は三者と本書を同期する。
