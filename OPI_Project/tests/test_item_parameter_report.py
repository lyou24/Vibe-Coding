from src.database.models import Chart, DifficultyEnum, Player, ScoreLog
from estimate_item_parameters import build_estimation_report


def test_dry_run_report_estimates_each_rank_without_writing(
    test_db_path,
    test_session,
):
    chart = Chart(
        chart_id="report_chart",
        title="推定レポート検証曲",
        difficulty=DifficultyEnum.MASTER,
        level="15",
        chart_constant=15.0,
    )
    test_session.add(chart)

    for index in range(60):
        user_id = 70000 + index
        theta = 1200.0 + index * 10.0
        achieved = index >= 30
        test_session.add(Player(
            user_id=user_id,
            player_name=f"ReportPlayer{index}",
            rating=18.0,
            total_opi=theta,
        ))
        test_session.add(ScoreLog(
            user_id=user_id,
            chart_id=chart.chart_id,
            score=1010000 if achieved else 900000,
            achieve_ss=achieved,
            achieve_sss=achieved,
            achieve_sssp=achieved,
            achieve_s=achieved,
            achieve_abp=achieved,
        ))
    test_session.commit()
    before_score_count = test_session.query(ScoreLog).count()

    report = build_estimation_report(
        test_db_path,
        min_sample_size=50,
        min_class_count=5,
    )

    assert report["mode"] == "dry_run"
    assert report["database_written"] is False
    assert report["player_count"] == 60
    assert report["score_count"] == 60
    assert report["item_count"] == 5
    assert report["estimable_count"] == 5
    assert [item["target_rank"] for item in report["estimates"]] == [
        "SS",
        "SSS",
        "SSS+",
        "S",
        "AB+",
    ]
    assert test_session.query(ScoreLog).count() == before_score_count


def test_dry_run_report_explains_insufficient_data(test_db_path):
    report = build_estimation_report(test_db_path)

    assert report["player_count"] == 0
    assert report["score_count"] == 0
    assert report["estimable_count"] == 0
    assert report["estimates"] == []
