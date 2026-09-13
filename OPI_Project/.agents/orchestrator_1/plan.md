# OPI プロジェクト開発計画 (plan.md)

## 目的
オンゲキのクリアランク達成難易度を定量化する「OPI（Ongeki Power Indicator）」Webアプリケーションの未完成プロジェクトを完成させ、Windows環境での第三者配布性、要件定義書の非破壊履歴更新、Git/GitHub管理を完遂する。

## 全体フェーズ構成
- **Phase 0: 状況調査 (Survey Phase)**
  - 3名の並列Explorerによる現状把握：
    1. Explorer 1: 既存コード（app.py, src/*）の機能実装状況と要件定義書・PROJECT.mdとの整合性調査
    2. Explorer 2: 既存テストスイート（tests/*, challenger_test_m2.py）の網羅性、実行可能性、ID 10605の挙動調査
    3. Explorer 3: 配布バッチ（run_opi.bat）、環境構築、Gitリポジトリ・リモート状態の調査
- **Phase 1: M3 WebUI・OPI/リコメンド完全統合**
  - Workerによる修正・補完（5ランク統合OPI、多次元フィルターUI、ID 10605デフォルト表示等）
  - Reviewer（2名）、Challenger（2名）、Forensic Auditor による独立検証
- **Phase 2: M4 総合E2E検証 & ドキュメント非破壊更新 & Gitプッシュ**
  - 全E2Eテスト100%パス確認
  - un_opi.bat の動作確認
  - OPI要件定義書.md の履歴保存型更新（追記・取り消し線のみ）
  - Gitコミット & GitHubプッシュの実行・確認
- **Phase 3: M5 最終フォレンジック監査 & Sentinelへの完了報告**
  - teamwork_preview_auditor による総合健全性監査
  - Sentinel への最終報告送付
