# タスクリスト: FC / AB 目標リコメンド機能（定数13.7以上限定）の追加

- [ ] `recommend_engine.py` の拡張
  - [ ] 他ユーザーの FC 達成率および AB 達成率の集計
  - [ ] `rec_lamp_fc` (FC狙い) および `rec_lamp_ab` (AB狙い) リストの作成
- [ ] `App.tsx` の拡張
  - [ ] `GroupResult` 型定義の更新
  - [ ] サブ切替ボタンに `[FC 狙い]` と `[AB 狙い]` を追加
  - [ ] テーブル表示（現状ランプ、目標ランプ、達成率）の対応
- [ ] `ExportControls.tsx` の調整
  - [ ] FC / AB 狙い表示時の Markdown / PNG エクスポート対応
- [ ] 動作確認・検証
  - [ ] recommend_engine 単体実行確認
  - [ ] npm run build テスト
