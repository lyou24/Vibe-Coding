# [実装計画] マイデータ表示タブ（ランプ・ランク統計＆レベル別達成率マトリックス）の追加

ユーザーのプレイデータから「クリアランプ＆スコアランク達成率分布」および「レベル別達成状況マトリックス（プログレスバー付き）」を集計し、フロントエンドに新設する「マイデータ」タブで可視化・表示します。

---

## ユーザーレビューが必要な項目

> [!IMPORTANT]
> **追加されるタブと機能の概要**
> 1. **マイデータ タブの追加**: ヘッダーのタブ切り替えに「マイデータ」を追加します。
> 2. **クリアランプ & スコアランク達成分布 (セクション 1)**:
>    - AB+, AB, FC, CLEAR のプレイ楽曲数内訳と割合（カラフルなマルチセクションプログレスバー）
>    - SSS+, SSS, SS, S, Other のスコアランク内訳と割合
> 3. **レベル別達成状況マトリックス (セクション 2)**:
>    - `Lv 12`, `Lv 12+`, `Lv 13`, `Lv 13+`, `Lv 14`, `Lv 14+`, `Lv 15`, `Lunatic` ごとのクリア状況
>    - 各レベル帯での **プレイ率**, **SSS/SSS+ 達成率**, **FC/AB 達成率** を視覚的なプログレスバーと数値パーセンテージで表示
>    - 各レベル帯での平均テクニカルスコア

---

## 提案する変更内容

### バックエンド

#### [MODIFY] [recommend_engine.py](file:///c:/Users/takahiro/Documents/OngekiRecommendApp/backend/recommend_engine.py)
- `RecommendEngine` 内にターゲットユーザーの全プレイデータおよび全楽曲マスター (`music_dict`) から以下を集計する `compute_my_data_stats()` を追加：
  - 総プレイ楽曲数 (`total_played`)
  - ランプ別カウント (`ab_plus`, `ab`, `fc`, `clear`)
  - スコアランク別カウント (`sssp`, `sss`, `ss`, `s`, `other`)
  - レベル帯別集計リスト (`level_matrix`):
    - レベル名 (`level`), 全楽曲数 (`total_charts`), プレイ済楽曲数 (`played_charts`)
    - `sss_count`, `sssp_count`, `fc_count`, `ab_count`
    - 平均スコア (`avg_ts`)
- 出力データ `export_data` に `my_data` オブジェクトを含めてエクスポート。

---

### フロントエンド

#### [MODIFY] [App.tsx](file:///c:/Users/takahiro/Documents/OngekiRecommendApp/frontend/src/App.tsx)
- 型定義 `MyDataStats`, `LevelMatrixItem`, `AppData` を追加・更新。
- `activeTab` に `'mydata'` を追加し、ナビゲーションバーに「マイデータ」タブボタン（アイコン付き）を配置。
- 「マイデータ」タブ選択時の描画コンポーネントを実装：
  - **サマリーカード**: 総プレイ数、AB+件数、SSS+件数などのハイライト
  - **ランプ＆ランクプログレスバーカード**: 全体に占める比率を示すプログレスバー表示
  - **レベル別達成率カード**: レベル帯（Lv 12〜15/Lunatic）ごとのプログレスバー（プレイ率、SSS+率、SSS率、FC/AB率）と平均スコアのテーブル/グリッドレイアウト

---

## 検証計画

### 自動テスト / バックエンド計算テスト
- `python backend/recommend_engine.py` を実行し、`recommend_data.json` に `my_data` 統計データが正しく出力されることを確認。

### フロントエンドビルドテスト
- `cd frontend && npm run build` を実行し、TypeScriptの型チェックおよびViteビルドがエラーなく成功することを確認。
