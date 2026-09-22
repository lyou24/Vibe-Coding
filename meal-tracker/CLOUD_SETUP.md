---
title: 食事ログ クラウド接続手順
category: 設定
tags: [AI作成, 開発手順]
created_at: "2026-09-22 14:25"
updated_at: "2026-09-22 14:25"
summary: 本人専用のクラウド保存、画像保存、認証、AI解析を接続するための最小手順を示す。
related_notes:
  - "PROJECT_SPEC.md"
  - "HANDOFF.md"
  - "supabase/schema.sql"
---

# 食事ログ クラウド接続手順

月額0円を優先する構成として、Supabase Free を食事データ・写真・本人認証に使い、Gemini API を食事解析に使う。アプリはキーを画面やGitへ保存しない。

## 1. Supabase

1. Supabaseで新規プロジェクトを作成する。
2. Authenticationでメールのマジックリンクを有効にする。許可する本人のメールアドレスを最初に登録する。
3. SQL Editorで `supabase/schema.sql` を実行する。
4. Storageで `meal-photos` という**private** bucketを作り、同SQLの末尾のStorage policyを実行する。
5. Project URL と匿名公開キーを、ホスティングサービスのサーバー環境変数へ設定する。サービスロールキーはブラウザへ渡さない。

## 2. Gemini

1. Google AI StudioでGemini APIキーを作成する。
2. ホスティングサービスのサーバー環境変数 `GEMINI_API_KEY` に設定する。
3. 値は会話、Git、`.env`、CSV、Obsidianへ記載しない。

## 3. アプリへ設定する環境変数

```text
GEMINI_API_KEY=（ホスティングサービスだけに設定）
NEXT_PUBLIC_SUPABASE_URL=（ホスティングサービスだけに設定）
NEXT_PUBLIC_SUPABASE_ANON_KEY=（ホスティングサービスだけに設定）
```

ローカル開発で必要な場合も、各自の端末にだけ設定する。`.env.local`は本リポジトリに作成・共有しない。

## 4. 接続後に実施する確認

- 本人のログイン前後で、別ユーザーの食事・定番・目標・写真にアクセスできない。
- 写真、料理名、メニュー表を各1件解析し、下書きを編集して保存できる。
- Gemini上限または障害時に、手入力へ切り替えられる。
- 写真はprivate bucketに保存され、削除した食事の写真も削除される。
- CSV/JSONとObsidian同期に、目標の適用日とrevisionを含められる。

## 5. Obsidian同期（PC側）

PCの環境変数へ次を設定してから、`pnpm sync:obsidian`を実行する。サービスロールキーはPCの環境変数だけに置き、アプリやGitへ渡さない。Node.js版はPythonの導入を必要としない。

```text
SUPABASE_URL=（Supabase Project URL）
SUPABASE_SERVICE_ROLE_KEY=（PCだけのサービスロールキー）
MEAL_TRACKER_USER_ID=（Supabase Authの本人ユーザーID）
```

スクリプトは `lyou_Obsidian/01_Config/12_memory/meal_log.md` に食事・定番・目標変更・削除イベントを追記する。PC停止中のイベントはSupabaseに残り、次回実行時に取り込む。
