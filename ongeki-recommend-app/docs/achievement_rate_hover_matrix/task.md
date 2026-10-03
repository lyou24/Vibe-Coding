# タスクリスト: 楽曲別達成率マトリックス・ホバー表示機能の追加

- [ ] `backend/recommend_engine.py` の拡張
  - [ ] 各比較グループ (`±0.25`, `±0.50`, `+0.50`) での SS/SSS/FC/AB 達成率集計
  - [ ] 各目標曲アイテムへ `rate_matrix` プロパティの追加
- [ ] `frontend/src/App.tsx` の拡張
  - [ ] `RecommendItem` 型の更新
  - [ ] レコードマウスオーバー時のポップアップカードUI（Tailwind CSS）の実装
  - [ ] マトリックス表（縦軸: 比較対象レート、横軸: SS・SSS・FC・AB）の描画
- [ ] 動作確認・検証
  - [ ] `recommend_engine.py` 単体テスト
  - [ ] フロントエンドビルドおよびホバーUI動作確認
