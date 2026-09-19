# タスクリスト: ランク目標リコメンド機能（定数13.7以上限定）の追加

- [ ] `recommend_engine.py` の拡張
  - [ ] 定数13.7以上フィルタリングの組み込み
  - [ ] 他ユーザーの SSS(100万) / SSS+(100.75万) 達成率の集計
  - [ ] `rec_rank_sss` (SS→SSS狙い) および `rec_rank_sssp` (SSS→SSS+狙い) リストの作成
- [ ] `App.tsx` の拡張
  - [ ] 型定義 (`RecommendItem`, `GroupResult`) にランク目標用プロパティを追加
  - [ ] UIに「ランク目標」タブと「SS→SSS」「SSS→SSS+」切り替えサブボタンを追加
  - [ ] テーブル表示（現状スコア、目標スコア、目標まであと点数、達成率）の実装
- [ ] `ExportControls.tsx` の調整
  - [ ] ランク目標タブ選択時の画像/PDF出力ラベルの対応
- [ ] 動作確認・検証
  - [ ] recommend_engine 単体テスト
  - [ ] フロントエンド表示確認
