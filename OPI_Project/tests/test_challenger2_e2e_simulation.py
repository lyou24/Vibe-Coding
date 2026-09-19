"""
Challenger 2: End-to-End Simulation & Test User 10605 Comprehensive Verifier
Adversarial & Empirical Verification Suite

検証項目:
1. Streamlit AppTest による ID 10605 実機シミュレーション (タブ切替, スライダー, マルチセレクト)
2. リコメンド楽曲テーブルの動的フィルタリング・ソート・非空出力
3. OPI難易度表の 100 帯域降順ソート徹底
4. マイOPI難易度表における ID 10605 の実績照合 (S, SSS, AB+)、色分け ([達成済]/[未達成])、メトリック一致検証
5. 散布図 (Plotly) の ID 10605 ハイライト (Rating=19.95, OPI, 星型マーカー)
6. 敵対的・境界値シナリオ検証 (SQLi耐性, 不正ID, 0件フィルター)
7. 音ゲー階層的単調性インバリアント検証 (Achieved(S) >= SS >= SSS >= SSS+ >= AB+)
"""

import os
import sys
import re
import pytest
import pandas as pd
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

APP_PATH = os.path.join(PROJECT_ROOT, "app.py")
DB_PATH = os.path.join(PROJECT_ROOT, "data", "opi_database.sqlite")


class TestChallenger2E2ESimulation:
    """ID 10605 を用いた包括的 E2E 動作実証"""

    @pytest.fixture(autouse=True)
    def setup_app(self):
        assert os.path.exists(APP_PATH), f"app.py が存在しません: {APP_PATH}"
        assert os.path.exists(DB_PATH), f"DBが存在しません: {DB_PATH}"

    def test_e2e_10605_initial_load_and_profile_metrics(self):
        """ID 10605 の初期ロード、レーティング 19.95、総合OPIの表示検証"""
        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        assert len(at.exception) == 0, f"初期ロード例外: {[e.message for e in at.exception]}"

        # ユーザーID入力確認
        user_inputs = [t for t in at.sidebar.text_input if "ユーザーID" in t.label or "ID" in t.label]
        assert len(user_inputs) > 0, "ユーザーID入力ウィジェットが存在しません"
        assert user_inputs[0].value == "10605", f"デフォルトIDが 10605 ではありません: {user_inputs[0].value}"

        # プロフィールヘッダー確認
        headers = [h.value for h in at.header]
        assert any("10605" in h or "ＮＥＧＩＮＥ" in h for h in headers), f"ヘッダーにプレイヤー名またはIDが見つかりません: {headers}"

        # メトリック検証
        metrics = {m.label: str(m.value) for m in at.metric}
        assert "レーティング" in metrics, f"レーティングメトリックが見つかりません: {metrics}"
        assert "19.95" in metrics["レーティング"], f"レーティング値が 19.95 ではありません: {metrics['レーティング']}"

        # 総合OPI（標準）の検証
        standard_opi_key = [k for k in metrics if "総合OPI（標準）" in k or "総合OPI" in k]
        assert len(standard_opi_key) > 0, f"総合OPIメトリックが見つかりません: {metrics}"
        opi_val = float(metrics[standard_opi_key[0]].replace(",", ""))
        assert 1400.0 <= opi_val <= 2100.0, f"ID 10605 の総合OPIが適正範囲外です: {opi_val}"

    def test_e2e_10605_tab1_recommendation_filtering_and_sorting(self):
        """Tab 1: リコメンドのスライダー操作、マルチセレクト操作、ソート順変更の実機シミュレーション"""
        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        assert len(at.exception) == 0

        # 1. 初期表示でリコメンドデータフレームが出力されていること
        rec_dfs = [df for df in at.dataframe if "目標ランク" in df.value.columns]
        assert len(rec_dfs) > 0, "リコメンドデータフレームが表示されていません"
        df_init = rec_dfs[0].value
        assert len(df_init) > 0, "初期リコメンド結果が空です"
        expected_cols = ["楽曲名", "難易度", "レベル", "定数", "現在の達成状況", "目標ランク", "目標OPI", "クリア割合"]
        for col in expected_cols:
            assert col in df_init.columns, f"必須列 {col} が存在しません: {list(df_init.columns)}"

        # 2. スライダー操作: クリア割合範囲を (30.0, 50.0) に変更
        cr_slider = [s for s in at.slider if "クリア割合" in s.label][0]
        cr_slider.set_value((30.0, 50.0))
        at.run()
        assert len(at.exception) == 0
        rec_dfs = [df for df in at.dataframe if "目標ランク" in df.value.columns]
        assert len(rec_dfs) > 0, "絞り込み後のリコメンド結果が存在しません"
        df_filtered = rec_dfs[0].value
        for val_str in df_filtered["クリア割合"]:
            val = float(val_str.replace("%", ""))
            assert 30.0 <= val <= 50.0 + 1e-3, f"クリア割合が範囲外です: {val}"

        # 3. マルチセレクト操作: レベルを ['14+'] に指定し、クリア割合を 0〜100% に設定
        level_ms = [m for m in at.multiselect if "レベル" in m.label][0]
        cr_slider = [s for s in at.slider if "クリア割合" in s.label][0]
        level_ms.set_value(["14+"])
        cr_slider.set_value((0.0, 100.0))
        at.run()
        assert len(at.exception) == 0
        rec_dfs = [df for df in at.dataframe if "目標ランク" in df.value.columns]
        assert len(rec_dfs) > 0, "レベル14+の楽曲が存在しません"
        df_lv = rec_dfs[0].value
        assert len(df_lv) > 0
        for lv in df_lv["レベル"]:
            assert str(lv) == "14+", f"レベルが14+以外を含みます: {lv}"

        # 4. マルチセレクト操作: 目標ランクを ['SSS+'] に限定
        level_ms = [m for m in at.multiselect if "レベル" in m.label][0]
        target_ms = [m for m in at.multiselect if "目標ランク" in m.label][0]
        level_ms.set_value([])  # レベル制限解除
        target_ms.set_value(["SSS+"])
        at.run()
        assert len(at.exception) == 0
        rec_dfs = [df for df in at.dataframe if "目標ランク" in df.value.columns]
        assert len(rec_dfs) > 0, "目標ランクSSS+のリコメンド結果が存在しません"
        df_rank = rec_dfs[0].value
        assert len(df_rank) > 0
        for r in df_rank["目標ランク"]:
            assert r == "SSS+", f"目標ランクが SSS+ 以外を含みます: {r}"

        # 5. マルチセレクトをすべて空（[]）にして全対象フォールバックを検証
        level_ms = [m for m in at.multiselect if "レベル" in m.label][0]
        target_ms = [m for m in at.multiselect if "目標ランク" in m.label][0]
        level_ms.set_value([])
        target_ms.set_value([])
        at.run()
        assert len(at.exception) == 0
        rec_dfs = [df for df in at.dataframe if "目標ランク" in df.value.columns]
        assert len(rec_dfs) > 0
        df_all = rec_dfs[0].value
        assert len(df_all) >= len(df_filtered), "全対象フォールバックで件数が減少しています"

        # 6. ソート順変更: 「クリア割合が高い順」
        sort_sb = [s for s in at.selectbox if "並び順" in s.label][0]
        sort_sb.select("クリア割合が高い順")
        at.run()
        assert len(at.exception) == 0
        rec_dfs = [df for df in at.dataframe if "目標ランク" in df.value.columns]
        assert len(rec_dfs) > 0
        df_sorted = rec_dfs[0].value
        rates = [float(s.replace("%", "")) for s in df_sorted["クリア割合"]]
        assert rates == sorted(rates, reverse=True), f"クリア割合が高い順にソートされていません: {rates[:5]}"

    def test_e2e_10605_tab2_dynamic_scatter_and_player_highlight(self):
        """Tab 2: 動的散布図 (Plotly) の生成および ID 10605 のハイライト検証"""
        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        assert len(at.exception) == 0

        from src.visualizer.visualizer import OPIVisualizer
        import plotly.graph_objects as go

        vis = OPIVisualizer(DB_PATH)
        fig = vis.create_distribution_figure(
            player_rating=19.95,
            player_opi=1423.6,
            player_name="ＮＥＧＩＮＥ",
        )
        assert isinstance(fig, go.Figure), f"生成された図が plotly.graph_objects.Figure ではありません: {type(fig)}"

        # 軸タイトルの検証
        x_title = str(fig.layout.xaxis.title.text if fig.layout.xaxis.title else "")
        y_title = str(fig.layout.yaxis.title.text if fig.layout.yaxis.title else "")
        assert any(kw in x_title.lower() for kw in ["rating", "レート", "レーティング"]), f"横軸タイトル不正: {x_title}"
        assert any(kw in y_title.lower() for kw in ["opi", "総合opi"]), f"縦軸タイトル不正: {y_title}"

        # ハイライトトレースの検証
        user_trace = None
        for trace in fig.data:
            name = getattr(trace, "name", "")
            marker = getattr(trace, "marker", None)
            symbol = getattr(marker, "symbol", "") if marker else ""
            if "あなた" in name or "ＮＥＧＩＮＥ" in name or symbol == "star":
                user_trace = trace
                break

        assert user_trace is not None, "ID 10605 のハイライトトレースが見つかりません"
        assert list(user_trace.x) == [19.95], f"ハイライトのX座標 (Rating) が 19.95 ではありません: {user_trace.x}"
        assert abs(list(user_trace.y)[0] - 1423.6) < 2.0, f"ハイライトのY座標 (OPI) が計算値と一致しません: {user_trace.y}"

    def test_e2e_10605_tab3_difficulty_grid_descending_bands(self):
        """Tab 3: OPI難易度表の 100 OPI 帯域区切りおよび降順ソート徹底の検証"""
        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        assert len(at.exception) == 0

        # 難易度表の帯域見出し（例: ### OPI 2000〜2099）を抽出
        band_patterns = [
            re.search(r"###\s*OPI\s*(\d{3,4})〜(\d{3,4})", md.value)
            for md in at.markdown
            if "OPI" in md.value
        ]
        bands = [int(m.group(1)) for m in band_patterns if m]
        assert len(bands) >= 3, f"難易度表の帯域見出しが十分に検出されませんでした: {bands}"
        assert bands == sorted(bands, reverse=True), f"難易度表の帯域が降順ソートされていません: {bands}"

    def test_e2e_10605_tab4_my_opi_grid_achievements_verification(self):
        """Tab 4: マイOPI難易度表における ID 10605 のスコア実績照合と色分け検証"""
        from src.database.models import init_db, get_session_maker, ScoreLog, Chart
        from src.analyzer.opi_calculator import MIN_TARGET_CONSTANT

        engine = init_db(DB_PATH)
        session = get_session_maker(engine)()

        # ID 10605 の SSS 達成状況を DB から直接集計
        user_scores = session.query(ScoreLog).filter_by(user_id=10605).all()
        user_score_map = {s.chart_id: s for s in user_scores}

        charts = session.query(Chart).filter(Chart.chart_constant >= MIN_TARGET_CONSTANT).all()
        db_achieved_sss_count = 0
        for c in charts:
            s = user_score_map.get(c.chart_id)
            if s and (s.score >= 1000000 or s.achieve_sss):
                db_achieved_sss_count += 1
        session.close()

        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        assert len(at.exception) == 0

        # マイOPI難易度表の目標ランク選択（デフォルト: SSS）での達成曲数メトリック
        achieve_metrics = [m for m in at.metric if "SSS 達成曲数" in m.label]
        assert len(achieve_metrics) > 0, f"マイ難易度表の達成曲数メトリックが見つかりません: {[m.label for m in at.metric]}"

        # メトリック値の検証 (例: '79 / 185 譜面')
        val_str = achieve_metrics[0].value
        match = re.search(r"(\d+)\s*/\s*(\d+)", val_str)
        assert match is not None, f"達成曲数メトリックの形式が不正です: {val_str}"
        ui_achieved_count = int(match.group(1))
        assert ui_achieved_count == db_achieved_sss_count, (
            f"UI上の達成曲数 ({ui_achieved_count}) が DB実測値 ({db_achieved_sss_count}) と一致しません"
        )

        # HTML カード内のスタイル・バッジ検証
        card_markdowns = [m.value for m in at.markdown if "background-color:" in m.value]
        assert len(card_markdowns) > 0, "マイ難易度表のカードUIが描画されていません"

        rank_colors = ("#2e7d32", "#1565c0", "#c62828", "#f9a825", "#c2410c")
        achieved_cards = [
            c for c in card_markdowns
            if any(color in c for color in rank_colors) and "[達成済]" in c
        ]
        unachieved_cards = [c for c in card_markdowns if "#f8f9fa" in c and "[未達成]" in c]

        assert len(achieved_cards) == db_achieved_sss_count, (
            f"達成済みカード数 ({len(achieved_cards)}) が DB実績 ({db_achieved_sss_count}) と一致しません"
        )
        assert len(unachieved_cards) > 0, "未達成カードが存在しません"

    def test_e2e_10605_tab4_switch_to_abp_and_s(self):
        """Tab 4: 目標ランクを 'AB+' および 'S' に切り替えた時の達成判定検証"""
        # 1. 'AB+' に切り替え (ID 10605 は 定数14以上で AB+ 達成 0件)
        at_abp = AppTest.from_file(APP_PATH, default_timeout=30).run()
        sb_abp = [s for s in at_abp.selectbox if s.key == "my_diff_target_rank_select"][0]
        sb_abp.select("AB+")
        at_abp.run()
        assert len(at_abp.exception) == 0
        abp_metrics = [m for m in at_abp.metric if "AB+ 達成曲数" in m.label]
        assert len(abp_metrics) > 0, f"AB+ 達成曲数メトリックが見つかりません: {[m.label for m in at_abp.metric]}"
        match_abp = re.search(r"(\d+)\s*/\s*(\d+)", abp_metrics[0].value)
        assert int(match_abp.group(1)) == 0, f"ID 10605 の AB+ 達成曲数が 0 ではありません: {match_abp.group(1)}"

        # 2. 'S' に切り替え (S は多数達成済み)
        at_s = AppTest.from_file(APP_PATH, default_timeout=30).run()
        sb_s = [s for s in at_s.selectbox if s.key == "my_diff_target_rank_select"][0]
        sb_s.select("S")
        at_s.run()
        assert len(at_s.exception) == 0
        s_metrics = [m for m in at_s.metric if "S 達成曲数" in m.label]
        assert len(s_metrics) > 0, f"S 達成曲数メトリックが見つかりません: {[m.label for m in at_s.metric]}"
        match_s = re.search(r"(\d+)\s*/\s*(\d+)", s_metrics[0].value)
        s_count = int(match_s.group(1))
        assert s_count >= 100, f"ID 10605 の S 達成曲数が少なすぎます: {s_count}"

    def test_e2e_10605_tab4_monotonic_hierarchy_invariant(self):
        """
        [Invariant] 音ゲー階層的単調性不変条件の検証:
        達成曲数は上位ランクほど厳格になるため、必ず以下の包含・単調関係を満たすこと:
        Count(S) >= Count(SS) >= Count(SSS) >= Count(SSS+) >= Count(AB+)
        """
        counts = {}
        target_ranks = ["S", "SS", "SSS", "SSS+", "AB+"]

        for r in target_ranks:
            at = AppTest.from_file(APP_PATH, default_timeout=30).run()
            sb = [s for s in at.selectbox if s.key == "my_diff_target_rank_select"][0]
            sb.select(r)
            at.run()
            assert len(at.exception) == 0
            m_list = [m for m in at.metric if f"{r} 達成曲数" in m.label]
            assert len(m_list) > 0, f"{r} 達成曲数メトリックが見つかりません"
            match = re.search(r"(\d+)\s*/\s*(\d+)", m_list[0].value)
            assert match is not None
            counts[r] = int(match.group(1))

        print(f"ID 10605 各ランク達成曲数 (定数14+): {counts}")
        # 単調性の検証
        assert counts["S"] >= counts["SS"], f"S({counts['S']}) < SS({counts['SS']}) 単調性崩壊"
        assert counts["SS"] >= counts["SSS"], f"SS({counts['SS']}) < SSS({counts['SSS']}) 単調性崩壊"
        assert counts["SSS"] >= counts["SSS+"], f"SSS({counts['SSS']}) < SSS+({counts['SSS+']}) 単調性崩壊"
        assert counts["SSS+"] >= counts["AB+"], f"SSS+({counts['SSS+']}) < AB+({counts['AB+']}) 単調性崩壊"

    def test_e2e_adversarial_zero_match_filter(self):
        """極端なフィルターでリコメンド 0 件になった際、UIクラッシュせず案内メッセージを表示すること"""
        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        assert len(at.exception) == 0

        cr_slider = [s for s in at.slider if "クリア割合" in s.label][0]
        cr_slider.set_value((0.0, 0.0))
        at.run()
        assert len(at.exception) == 0

        infos = [i.value for i in at.info]
        assert len(infos) > 0, "0件マッチ時に案内メッセージが表示されていません"
        assert any("見つかりませんでした" in info or "調整" in info for info in infos)

    def test_e2e_adversarial_sqli_and_malformed_inputs(self):
        """
        [Adversarial] 悪意ある入力 (SQLインジェクション風文字列, 存在しない巨大ID) に対する
        アプリケーションの耐障害性検証
        """
        # 1. SQLインジェクション風文字列
        at_sqli = AppTest.from_file(APP_PATH, default_timeout=30).run()
        inp_sqli = [t for t in at_sqli.sidebar.text_input if "ユーザーID" in t.label or "ID" in t.label][0]
        inp_sqli.set_value("10605' OR '1'='1")
        btn = [b for b in at_sqli.sidebar.button if "検索" in b.label][0]
        btn.click()
        at_sqli.run()
        assert len(at_sqli.exception) == 0, "SQLi入力で未処理例外が発生しました"
        errors = [e.value for e in at_sqli.sidebar.error]
        assert len(errors) > 0, "SQLi入力に対してバリデーションエラーが表示されていません"

        # 2. 存在しない巨大ID
        at_huge = AppTest.from_file(APP_PATH, default_timeout=30).run()
        inp_huge = [t for t in at_huge.sidebar.text_input if "ユーザーID" in t.label or "ID" in t.label][0]
        inp_huge.set_value("999999999")
        at_huge.run()
        assert len(at_huge.exception) == 0, "存在しないID入力で未処理例外が発生しました"
        warnings = [w.value for w in at_huge.warning]
        assert any("見つかりません" in w for w in warnings), "ユーザー不在時の警告が表示されていません"
