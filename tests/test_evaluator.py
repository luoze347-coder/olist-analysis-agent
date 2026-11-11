from scripts.evaluate import check_safety, percentile, result_matches


def test_offline_harness_checks_production_sql_guard():
    result = check_safety()
    assert result["passed"] == result["total"]
    assert result["failures"] == []


def test_latency_percentile_handles_small_samples():
    assert percentile([], 0.95) is None
    assert percentile([1.0, 2.0, 3.0], 0.95) == 3.0


def test_result_match_allows_extra_measure_but_checks_values():
    gold = {"columns": ["month", "revenue"], "rows": [["2018-01", 10.0]]}
    actual = {"columns": ["month", "sales_revenue", "orders"], "rows": [["2018-01", 10.004, 2]]}
    assert result_matches(actual, gold)
    actual["rows"][0][1] = 11.0
    assert not result_matches(actual, gold)


def test_percentage_and_max_row_modes():
    gold_pct = {"columns": ["state", "late_pct"], "rows": [["SP", 12.0]]}
    actual_pct = {"columns": ["state", "late_rate"], "rows": [["SP", 0.12]]}
    assert result_matches(actual_pct, gold_pct)
    gold_peak = {"columns": ["month", "revenue"], "rows": [["2018-02", 12.0]]}
    months = {"columns": ["month", "revenue"], "rows": [["2018-01", 10.0], ["2018-02", 12.0]]}
    assert result_matches(months, gold_peak, "max_row")


def test_grouped_mean_ignores_null_group_and_rounding_only():
    gold = {"columns": ["late", "avg"], "rows": [[False, 4.29], [True, 2.57]]}
    actual = {"columns": ["late", "orders", "avg"],
              "rows": [[False, 10, 4.294], [True, 5, 2.565], [None, 1, 4.5]]}
    assert result_matches(actual, gold, "grouped_mean")
    actual["rows"][1][2] = 2.54
    assert not result_matches(actual, gold, "grouped_mean")
