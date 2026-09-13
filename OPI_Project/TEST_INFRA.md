# E2E Test Infra: OPI Web Application

## Test Philosophy
- 要求仕様駆動・オパークボックス検証。
- 4層階層型テストスイート（Category-Partition + BVA + Pairwise + Real-World Workload）。
- 受入基準（AC1〜AC3）の完全網羅。

---

## Feature Inventory & Test Coverage
| # | Feature | Source | Tier 1 (Feature) | Tier 2 (Boundary) | Tier 3 (Pairwise) | Tier 4 (Scenario) |
|---|---------|--------|:----------------:|:-----------------:|:-----------------:|:-----------------:|
| 1 | 2PL IRT OPI算出ロジック | 要件定義書 2.2 | 5 tests | 5 tests | 3 tests | 2 tests |
| 2 | リコメンドエンジン | 要件定義書 2.3 | 5 tests | 5 tests | 3 tests | 2 tests |
| 3 | クローラー・差分更新 | 要件定義書 1.2 | 4 tests | 3 tests | 2 tests | 2 tests |
| 4 | DB・データ整合性 | 要件定義書 2.1 | 4 tests | 3 tests | 2 tests | 1 test |
| 5 | 可視化・分布図生成 | 要件定義書 3.2 | 4 tests | 3 tests | 2 tests | 1 test |
| 6 | 第三者配布性 (AC2) | 要件定義書 AC2 | - | - | - | 1 test (`test_ac2`) |
| 7 | ID 10605 総合動作 (AC1) | 要件定義書 AC1 | - | - | - | 1 test (`test_ac1`) |
| 8 | 要件定義書非破壊更新 (AC3) | 要件定義書 AC3 | - | - | - | 1 test (`test_ac3`) |

---

## Test Architecture
- **Runner**: `pytest` (`.venv\Scripts\python.exe -m pytest tests -v`)
- **Pass/Fail Criteria**:
  - 全テスト合格（exit code 0）
  - AC1〜AC3 すべて PASS
- **Test Layout**:
  - `tests/test_tier1_feature_coverage.py`: 20 tests (単体・機能検証)
  - `tests/test_tier2_boundary_corner.py`: 20 tests (極値・空配列・例外)
  - `tests/test_tier3_pairwise_combinations.py`: 12 tests (複数機能結合)
  - `tests/test_tier4_realworld_acceptance.py`: 18 tests (実シナリオ・AC1〜3検証)

---

## Acceptance Thresholds
- 全70テスト PASS
- ID 10605 総合OPI: 2000.0〜2100.0（ハイレベルログ時）
- `run_opi.bat` に `python -m venv`、`pip install -r requirements.txt`、`streamlit run app.py` が正しく記述されていること
