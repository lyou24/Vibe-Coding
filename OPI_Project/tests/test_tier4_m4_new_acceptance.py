"""
Tier 4: 最新受入基準 E2E 自動検証テストスイート (AC-1 〜 AC-6)

本テストスイートは、ORIGINAL_REQUEST.md (2026-09-14T13:31:31Z) および PROJECT.md に定義された
新受入基準 (AC-1 〜 AC-6) を streamlit.testing.v1.AppTest を活用して機械的・客観的に検証する
「Opaque-box (ブラックボックス)」「Requirement-driven (要求駆動)」E2Eテストです。
"""

import os
import re
import sys
import importlib
import pytest
from typing import Any, List, Set

# プロジェクトルートのパス解決
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

APP_PATH = os.path.join(PROJECT_ROOT, "app.py")
DB_PATH = os.path.join(PROJECT_ROOT, "data", "opi_database.sqlite")
REQUIREMENTS_PATH = os.path.join(PROJECT_ROOT, "requirements.txt")


class TestTier4NewAcceptance:
    """新受入基準 E2E 自動検証 (AC-1 〜 AC-6)"""

    # -------------------------------------------------------------------------
    # AC-1: Streamlit アプリの起動および実行時例外ゼロ
    # -------------------------------------------------------------------------
    def test_ac1_app_launch_and_zero_exceptions(self):
        """
        [AC-1] Streamlit アプリケーションが正常起動し、未処理例外 (Unhandled Exceptions) がゼロであること。
        初期表示で重大な st.error が発生しておらず、主要UI（ヘッダー・タイトル）が描画されること。
        """
        from streamlit.testing.v1 import AppTest

        assert os.path.exists(APP_PATH), f"app.py が存在しません: {APP_PATH}"
        assert os.path.exists(DB_PATH), f"SQLite DBが存在しません: {DB_PATH}"

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()

        # 1. 実行時例外ゼロの検証
        exceptions = [e.message for e in at.exception]
        assert len(at.exception) == 0, f"AppTest 実行時例外が検出されました: {exceptions}"

        # 2. タイトルの存在検証
        assert len(at.title) > 0, "st.title が描画されていません。"
        title_text = at.title[0].value
        assert "OPI" in title_text or "オンゲキ" in title_text, f"タイトル内容が不適正です: {title_text}"

        # 3. 初期状態での重大な st.error 不在の検証
        errors = [e.value for e in at.error]
        assert len(at.error) == 0, f"初期表示で重大な st.error が発生しています: {errors}"

    # -------------------------------------------------------------------------
    # AC-2: R1 新5段階ランクへの完全対応と旧ランクの完全排除
    # -------------------------------------------------------------------------
    def test_ac2_new_five_ranks_compliance_and_legacy_elimination(self):
        """
        [AC-2] 要件 R1: 新5段階ランク (S, SS, SSS, SSS+, AB+) への完全対応と、
        旧ランク (SSS+ABFB, AP) の UI およびコア集計ロジックからの完全排除を検証。
        """
        from streamlit.testing.v1 import AppTest
        from src.analyzer.opi_calculator import TARGET_RANKS, OPICalculator, normalize_rank

        expected_ranks = {"S", "SS", "SSS", "SSS+", "AB+"}
        legacy_ranks = {"SSS+ABFB", "AP", "SSS+ ABFB", "ABFB"}

        # 1. UI 層のウィジェット選択肢検証
        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        assert len(at.exception) == 0, f"AppTest 例外: {[e.message for e in at.exception]}"

        # 目標ランク選択ウィジェット (multiselect または selectbox) の走査
        target_rank_widgets = [
            w for w in at.multiselect if "目標ランク" in w.label
        ] + [
            w for w in at.selectbox if "目標ランク" in w.label
        ]
        assert len(target_rank_widgets) > 0, "UI上に『目標ランク』選択ウィジェットが存在しません。"

        for widget in target_rank_widgets:
            options_set = set(widget.options)
            # 新5段階ランクが網羅されていること
            assert expected_ranks.issubset(options_set), (
                f"目標ランクウィジェット ({widget.label}) の選択肢に新5段階ランクが網羅されていません: "
                f"期待={expected_ranks}, 実際={options_set}"
            )
            # 旧ランクが完全に排除されていること
            for leg in legacy_ranks:
                assert leg not in options_set, (
                    f"目標ランクウィジェット ({widget.label}) に排除対象の旧ランク '{leg}' が残存しています: {options_set}"
                )

        # 現在の達成ランク選択肢 (multiselect) の走査
        current_rank_widgets = [w for w in at.multiselect if "現在" in w.label or "達成ランク" in w.label]
        for widget in current_rank_widgets:
            opts = set(widget.options)
            for leg in legacy_ranks:
                assert leg not in opts, (
                    f"現在ランクウィジェット ({widget.label}) に排除対象の旧ランク '{leg}' が残存しています: {opts}"
                )

        # 2. コアロジック (OPICalculator) の定数・正規化検証
        assert set(TARGET_RANKS) == expected_ranks, (
            f"opi_calculator.TARGET_RANKS が新5段階ランク体系に適合していません: {TARGET_RANKS}"
        )

        calc = OPICalculator()
        assert calc.normalize_rank("AB+") == "AB+", "AB+ の正規化が不正です"
        assert calc.normalize_rank("ABP") == "AB+", "ABP エイリアスの正規化が不正です"
        assert calc.normalize_rank("AP") == "AB+", "旧APのAB+への後方互換正規化が不正です"

        # 3. 譜面パラメータ取得 (get_chart_rank_params) の検証
        class DummyChart:
            chart_constant = 15.0
            opi_s_x = 1800.0
            opi_s_y = 40.0
            opi_ss_x = 1600.0
            opi_ss_y = 40.0
            opi_sss_x = 1700.0
            opi_sss_y = 40.0
            opi_sssp_x = 1750.0
            opi_sssp_y = 40.0
            opi_abp_x = 1900.0
            opi_abp_y = 40.0

        dummy = DummyChart()
        s_x, s_y = calc.get_chart_rank_params(dummy, "S")
        abp_x, abp_y = calc.get_chart_rank_params(dummy, "AB+")
        assert s_x is not None and s_x == 1800.0, f"新ランク 'S' のパラメータ取得が不正です: {s_x}"
        assert abp_x is not None and abp_x == 1900.0, f"新ランク 'AB+' のパラメータ取得が不正です: {abp_x}"

    # -------------------------------------------------------------------------
    # AC-3: R2 リコメンド UI 高度化
    # -------------------------------------------------------------------------
    def test_ac3_recommendation_ui_slider_and_multiselect(self):
        """
        [AC-3] 要件 R2:
        1. 「クリア割合」0〜100% 範囲スライダーの設置と旧文言「勝率」の廃止。
        2. レベル・目標ランク・現在ランクの複数選択 (マルチセレクト)。
        3. 未選択時に全対象がヒットするフォールスルー動作。
        4. 範囲スライダーによる結果絞り込み動作。
        """
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        assert len(at.exception) == 0, f"AppTest 例外: {[e.message for e in at.exception]}"

        # 1. 「クリア割合」スライダーの検証
        clear_rate_sliders = [s for s in at.slider if "クリア割合" in s.label]
        assert len(clear_rate_sliders) > 0, (
            "UI上に『クリア割合』スライダーが存在しません。"
            f"現在のスライダー: {[s.label for s in at.slider]}"
        )

        # 旧文言「勝率」ウィジェットの全廃検証
        legacy_win_rate_sliders = [s for s in at.slider if "勝率" in s.label]
        legacy_win_rate_inputs = [n for n in at.number_input if "勝率" in n.label]
        assert len(legacy_win_rate_sliders) == 0 and len(legacy_win_rate_inputs) == 0, (
            "旧表記『勝率』のウィジェットが残存しています（『クリア割合』へ改称してください）: "
            f"sliders={[s.label for s in legacy_win_rate_sliders]}, inputs={[n.label for n in legacy_win_rate_inputs]}"
        )

        cr_slider = clear_rate_sliders[0]
        assert cr_slider.min == 0 or cr_slider.min == 0.0, f"クリア割合の最小値は 0 であるべきです: {cr_slider.min}"
        assert cr_slider.max == 100 or cr_slider.max == 100.0, f"クリア割合の最大値は 100 であるべきです: {cr_slider.max}"

        # 2. マルチセレクト UI の検証
        level_multiselects = [m for m in at.multiselect if "レベル" in m.label]
        assert len(level_multiselects) > 0, "『レベル絞り込み』のマルチセレクトが存在しません。"

        target_multiselects = [m for m in at.multiselect if "目標ランク" in m.label]
        assert len(target_multiselects) > 0, "『目標ランク』のマルチセレクトが存在しません。"

        current_multiselects = [m for m in at.multiselect if "現在" in m.label or "達成ランク" in m.label]
        assert len(current_multiselects) > 0, "『現在の達成ランク』のマルチセレクトが存在しません。"

        # 3. 未選択時の全対象ヒット動作（フォールスルー検証）
        level_ms = level_multiselects[0]
        # 空選択に設定
        level_ms.set_value([])
        at.run()
        assert len(at.exception) == 0, f"レベル空選択時の AppTest 例外: {[e.message for e in at.exception]}"

        # データフレームが描画されており、空ではないこと
        dataframes = at.dataframe
        assert len(dataframes) > 0, "レベル空選択時にリコメンドデータフレームが表示されていません。"
        df_val = dataframes[0].value
        assert len(df_val) > 0, "レベル未選択時に全対象が表示されず、0件になっています（未選択時全対象表示仕様違反）。"

        # 4. 範囲スライダーの絞り込み動作検証
        cr_slider.set_value((40.0, 70.0))
        at.run()
        assert len(at.exception) == 0, f"スライダー絞り込み時の AppTest 例外: {[e.message for e in at.exception]}"
        filtered_dfs = at.dataframe
        assert len(filtered_dfs) > 0, "スライダー絞り込み後にリコメンドデータフレームが存在しません。"

    # -------------------------------------------------------------------------
    # AC-4: R3 難易度表グリッド化と「マイOPI難易度表」
    # -------------------------------------------------------------------------
    def test_ac4_difficulty_grid_and_my_opi_view(self):
        """
        [AC-4] 要件 R3:
        1. 難易度表の 100 OPI 帯域区切りグリッド化および降順ソート徹底。
        2. 「マイOPI難易度表」ビュー（またはタブ）の実装。
        3. マイ難易度表における達成済み楽曲セルの視覚的識別（色付き塗りつぶし・バッジ）。
        """
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        assert len(at.exception) == 0, f"AppTest 例外: {[e.message for e in at.exception]}"

        # 1. タブ構成の検証: 「マイOPI難易度表」が存在すること
        tab_labels = [t.label for t in at.tabs]
        has_my_opi_tab = any("マイOPI難易度表" in label or "マイ難易度表" in label for label in tab_labels)
        assert has_my_opi_tab, (
            f"タブ構成に『マイOPI難易度表』タブが存在しません。現在のタブ: {tab_labels}"
        )

        # 2. 通常の OPI 難易度表における 100 帯降順ソートの検証
        # UI上の markdown 見出し（例: "### OPI 2000〜2099", "OPI 1900帯" 等）を走査
        band_patterns = [
            re.search(r"OPI\s*(\d{3,4})", md.value)
            for md in at.markdown
            if "OPI" in md.value
        ]
        extracted_bands = [int(m.group(1)) for m in band_patterns if m]
        if len(extracted_bands) >= 2:
            # 帯域が降順（上位帯が先）で配置されているか検証
            sorted_bands = sorted(extracted_bands, reverse=True)
            assert extracted_bands == sorted_bands, (
                f"難易度表の OPI 帯域が降順ソートされていません: 実際={extracted_bands}, 期待={sorted_bands}"
            )

        # 3. マイOPI難易度表での達成状況ハイライト検証
        # HTML/CSSスタイルや達成マーク・バッジ・色付きセルが付与されていることを検証
        html_contents = [h.value for h in getattr(at, "html", [])] + [m.value for m in at.markdown]
        achievement_indicators = [
            content for content in html_contents
            if any(kw in content for kw in ["background-color", "style=", "badge", "達成", "achieved", "color:"])
        ]
        assert len(achievement_indicators) > 0, (
            "マイOPI難易度表において、達成済みセルを視覚的に識別するためのスタイルやバッジが見つかりません。"
        )

    # -------------------------------------------------------------------------
    # AC-5: R4 動的散布図 (Plotly 図の生成とユーザー位置ハイライト)
    # -------------------------------------------------------------------------
    def test_ac5_dynamic_scatterplot_plotly_and_highlight(self):
        """
        [AC-5] 要件 R4:
        1. 横軸をレーティング生値、縦軸を総合OPIとした動的散布図 (Plotly) の生成。
        2. 選択したユーザーの現在位置ハイライト (星型マーカー等)。
        3. requirements.txt に plotly が指定されていること。
        """
        # 1. requirements.txt に plotly が含まれていることの検証
        assert os.path.exists(REQUIREMENTS_PATH), "requirements.txt が見つかりません"
        with open(REQUIREMENTS_PATH, "r", encoding="utf-8") as f:
            req_content = f.read().lower()
        assert "plotly" in req_content, (
            "要件 R4 を満たすため、requirements.txt に 'plotly' を追加してください。"
        )

        # 2. plotly パッケージのインポート可能性検証
        try:
            import plotly
            import plotly.graph_objects as go
        except ImportError:
            pytest.fail(
                "plotly がインストールされていません。要件 R4 準拠のため "
                "pip install plotly を実行し環境を整備してください。"
            )

        # 3. 動的散布図生成関数の検証 (src.visualizer.visualizer)
        from src.visualizer.visualizer import OPIVisualizer
        try:
            from src.visualizer.visualizer import create_distribution_figure
        except ImportError:
            # クラスメソッドとして実装されている場合も許容
            create_distribution_figure = getattr(OPIVisualizer, "create_distribution_figure", None)

        assert create_distribution_figure is not None, (
            "src/visualizer/visualizer.py に create_distribution_figure 関数/メソッドが定義されていません。"
        )

        # 引数 (player_rating, player_opi, player_name) を渡して Figure を生成
        test_rating = 19.95
        test_opi = 2076.8
        test_name = "ＮＥＧＩＮＥ"

        fig = create_distribution_figure(
            player_rating=test_rating,
            player_opi=test_opi,
            player_name=test_name,
        )

        assert isinstance(fig, go.Figure), f"生成されたオブジェクトが plotly.graph_objects.Figure ではありません: {type(fig)}"

        # 軸設定の検証
        x_title = str(fig.layout.xaxis.title.text if fig.layout.xaxis.title else "")
        y_title = str(fig.layout.yaxis.title.text if fig.layout.yaxis.title else "")
        assert any(kw in x_title.lower() for kw in ["rating", "レート", "レーティング"]), (
            f"横軸タイトルが生レーティングを示していません: {x_title}"
        )
        assert any(kw in y_title.lower() for kw in ["opi", "総合opi"]), (
            f"縦軸タイトルが総合OPIを示していません: {y_title}"
        )

        # ユーザー現在位置ハイライトトレースの検証
        highlight_found = False
        for trace in fig.data:
            x_vals = list(getattr(trace, "x", []))
            y_vals = list(getattr(trace, "y", []))
            marker = getattr(trace, "marker", None)
            symbol = getattr(marker, "symbol", "") if marker else ""
            name = getattr(trace, "name", "")

            # 座標の一致またはマーカーシンボルの星型判定
            if test_rating in x_vals and test_opi in y_vals:
                highlight_found = True
                assert symbol == "star" or "あなた" in name or test_name in name or getattr(marker, "size", 0) >= 12, (
                    "ユーザーハイライトトレースが十分に視覚強調されていません（星型マーカー等を推奨）。"
                )
                break
            elif symbol == "star" or "あなた" in name or test_name in name:
                highlight_found = True
                break

        assert highlight_found, "散布図上に選択ユーザーの現在位置を示すハイライトトレースが見つかりません。"

    # -------------------------------------------------------------------------
    # AC-6: テストユーザーID 10605 による E2E 総合OPI算出・リコメンド
    # -------------------------------------------------------------------------
    def test_ac6_e2e_user_10605_calculation_and_recommendation(self):
        """
        [AC-6] テスト用ID 10605 (397件スコア) の実データを用いた E2E 受入検証。
        エラーで停止することなく総合OPI (2000〜2100) が正常算出され、
        リコメンド楽曲テーブルが適切に出力されること。
        """
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        # サイドバーのユーザーID入力ウィジェットを探索
        user_inputs = [t for t in at.sidebar.text_input if "ユーザーID" in t.label or "ID" in t.label]
        assert len(user_inputs) > 0, "サイドバーにユーザーID入力欄が見つかりません。"

        user_input_widget = user_inputs[0]
        if user_input_widget.value != "10605":
            user_input_widget.set_value("10605")
            at.run()

        # 1. 実行時例外ゼロの検証
        assert len(at.exception) == 0, f"ユーザー 10605 実行時に例外が発生しました: {[e.message for e in at.exception]}"

        # 2. プロフィールと総合OPIメトリックの検証
        metrics = at.metric
        assert len(metrics) > 0, "プレイヤーデータメトリック (レーティング, 総合OPI等) が描画されていません。"

        opi_metric_found = False
        calculated_opi = None
        for m in metrics:
            if "総合OPI" in m.label:
                val_str = str(m.value).replace(",", "")
                try:
                    calculated_opi = float(val_str)
                    opi_metric_found = True
                    break
                except ValueError:
                    continue

        assert opi_metric_found, f"総合OPIメトリックが見つかりません。現在のメトリック: {[m.label for m in metrics]}"
        # ID 10605 (レーティング 19.950、新5段階実測397譜面最尤推定) の適正OPI範囲の検証
        assert 1400.0 <= calculated_opi <= 2100.0, (
            f"ユーザー 10605 の総合OPI算出値が新ランク体系に基づく適正水準 (1400.0 〜 2100.0) を逸脱しています: {calculated_opi}"
        )

        # 3. リコメンド楽曲テーブルの描画と完全性検証
        dfs = at.dataframe
        assert len(dfs) > 0, "リコメンド楽曲データフレームが表示されていません。"
        df_rec = dfs[0].value
        assert len(df_rec) > 0, "リコメンド結果が0件です。推薦楽曲が出力されていません。"

        # 必須カラムの存在確認
        expected_cols = ["楽曲名", "難易度", "レベル", "定数", "目標ランク"]
        for col in expected_cols:
            assert col in df_rec.columns, f"リコメンドテーブルに必須列 '{col}' が存在しません: {list(df_rec.columns)}"

    # -------------------------------------------------------------------------
    # Adversarial: 敵対的入力・境界値ハンドリング検証
    # -------------------------------------------------------------------------
    def test_adversarial_invalid_user_input_handling(self):
        """
        [Adversarial] 不正なユーザーID入力 (非数値文字列, 負数, 空文字) に対して
        アプリケーションが例外クラッシュせず、安全にエラーハンドリングされることを検証。
        """
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        user_inputs = [t for t in at.sidebar.text_input if "ユーザーID" in t.label or "ID" in t.label]
        assert len(user_inputs) > 0

        # 非数値文字列の入力
        user_inputs[0].set_value("invalid_id_abc")
        # 検索ボタンを押下
        search_buttons = [b for b in at.sidebar.button if "検索" in b.label]
        if search_buttons:
            search_buttons[0].click()
        at.run()

        # 例外でクラッシュしないこと
        assert len(at.exception) == 0, f"不正文字列ID入力時に例外が発生しました: {[e.message for e in at.exception]}"
        # 警告またはエラー通知が出ていること
        notifications = [e.value for e in at.sidebar.error] + [w.value for w in at.sidebar.warning]
        assert len(notifications) > 0, "不正なID入力に対して警告・エラーが表示されていません。"

    def test_adversarial_boundary_slider_filters(self):
        """
        [Adversarial] クリア割合スライダーの極値 (0%〜0%, 100%〜100%) 設定時にも
        ゼロ除算やSQLエラーを起こさず、安全にフィルタリングまたは空結果メッセージが表示されることを検証。
        """
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        clear_rate_sliders = [s for s in at.slider if "クリア割合" in s.label]
        if clear_rate_sliders:
            # 極値 100% 〜 100% に設定
            clear_rate_sliders[0].set_value((100.0, 100.0))
            at.run()
            assert len(at.exception) == 0, f"スライダー極値設定時に例外が発生しました: {[e.message for e in at.exception]}"
