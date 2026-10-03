# FC / AB 目標リコメンド機能（定数13.7以上）の実装計画

ユーザーがフルコンボ（FC）やオールブレイク（AB）を効率的に達成できるよう、**定数13.7以上**の楽曲を対象とした「FC / AB 目標リコメンド機能」を追加します。

---

## ユーザーレビューが必要な事項

> [!IMPORTANT]
> - **対象定数範囲**: **定数13.7以上**の楽曲に限定します。
> - **目標カテゴリの定義**:
>   - **FC 狙い**: 自分がまだ FC 未達成（ランプに FC も AB も付いていない）の楽曲で、他ユーザーの FC 達成率が高いおすすめ曲。
>   - **AB 狙い**: 自分がまだ AB 未達成（ランプに AB が付いていない）の楽曲で、他ユーザーの AB 達成率が高いおすすめ曲。
> - **UI配置**:
>   - 既存の「ランク目標(13.7+)」タブを **「ランク・ランプ目標(13.7+)」** タブへと統合・拡張し、サブ切替ボタンで以下4つをスムーズに切り替えられるようにします：
>     1. **[SS → SSS (100万)]**
>     2. **[SSS → SSS+ (100.75万)]**
>     3. **[FC 狙い]**
>     4. **[AB 狙い]**

---

## 変更内容の概要

### 1. [backend] リコメンドエンジンの拡張
#### [MODIFY] [recommend_engine.py](file:///c:/Users/takahiro/Documents/OngekiRecommendApp/backend/recommend_engine.py)
- 定数 `13.7` 以上の楽曲を対象に、母集団ユーザーの FC 達成率 (ランプに FC または AB を含む) および AB 達成率 (ランプに AB を含む) を集計するロジックを追加。
- ターゲットユーザーの現状ランプに基づき、以下の2つのリストを生成して返却データに含める：
  - `rec_lamp_fc`: 定数 >= 13.7、現状 FC未達成の楽曲（他ユーザーの FC 達成率 と 現状スコアを提示）
  - `rec_lamp_ab`: 定数 >= 13.7、現状 AB未達成の楽曲（他ユーザーの AB 達成率 と 現状スコアを提示）

---

### 2. [frontend] UI拡張
#### [MODIFY] [App.tsx](file:///c:/Users/takahiro/Documents/OngekiRecommendApp/frontend/src/App.tsx)
- `GroupResult` 型定義に `rec_lamp_fc`, `rec_lamp_ab` を追加。
- タブ切り替え名を **「ランク・ランプ(13.7+)」** に変更。
- サブボタンに **[FC 狙い]** と **[AB 狙い]** を追加。
- テーブル表示を調整（FC / AB 狙い選択時には「目標ランプ」「達成率」を表示）。

#### [MODIFY] [ExportControls.tsx](file:///c:/Users/takahiro/Documents/OngekiRecommendApp/frontend/src/ExportControls.tsx)
- FC / AB 狙い表示時の Markdown コピー・PNG 画像ダウンロード対応。

---

## 検証計画

### 1. バックエンド計算テスト
- `python backend/recommend_engine.py` を実行し、`rec_lamp_fc` および `rec_lamp_ab` が定数13.7以上の未達成曲で正しく生成されるか確認。

### 2. フロントエンド動作確認・ビルド
- `npm run build` でTypeScript型チェックとビルドが正常に通るか確認。
- ブラウザ画面で「FC 狙い」「AB 狙い」の表示、ソート、他ユーザー達成率が正しく表示されるか確認。
