"""Unit tests for the verdict logic and HTML generation, using small synthetic data."""

from evaluation_tools.build_summary import (
    classify,
    evaluate_rows,
    resolve,
    tally_counts,
    verdict_rows_html,
)


def test_resolve_indexes_lists_and_dotted_keys():
    documents = {"a.json": {"strehl": {"1.1": [0.8, 0.5, 0.1]}}}
    assert resolve("a.json:strehl/1.1/0", documents) == 0.8
    assert resolve("a.json:strehl/1.1/-1", documents) == 0.1


def test_classify_absolute_difference():
    row = {"mode": "abs", "tol": 0.001, "partial_tol": 0.1}
    assert classify([1.0], [1.0005], row)[0] == "match"
    assert classify([1.0], [1.05], row)[0] == "partial"
    assert classify([1.0], [1.5], row)[0] == "fail"


def test_classify_ratio_is_symmetric():
    row = {"mode": "ratio", "tol": 0.1, "partial_tol": 5}
    assert classify([1.0], [1.05], row)[0] == "match"
    assert classify([1.0], [3.0], row)[0] == "partial"
    assert classify([3.0], [1.0], row)[0] == "partial"
    assert classify([0.01], [10.0], row)[0] == "fail"


def test_worst_value_decides_when_several_wavelengths():
    row = {"mode": "abs", "tol": 0.01, "partial_tol": 0.2}
    status, worst = classify([1.0, 1.0, 1.0], [1.0, 1.0, 0.85], row)
    assert status == "partial"
    assert abs(worst - 0.15) < 1e-12


def test_rows_with_manual_status_and_tally():
    comparison = {
        "rows": [
            {"label": "layout", "status": "match"},
            {
                "label": "x",
                "zemax": [1.0],
                "optiland": ["r.json:x/0"],
                "mode": "abs",
                "tol": 0.01,
                "partial_tol": 0.1,
                "decimals": 2,
            },
        ]
    }
    rows = evaluate_rows(comparison, {"r.json": {"x": [2.0]}})
    assert [r["result"] for r in rows] == ["match", "fail"]
    assert tally_counts(rows) == {"match": 1, "partial": 0, "fail": 1}
    assert "chip bad" in verdict_rows_html(rows)


def test_small_ratio_differences_are_shown_as_percent():
    row = {
        "id": "x",
        "label": "x",
        "zemax": [10.0],
        "optiland": ["r.json:v/0"],
        "mode": "ratio",
        "tol": 0.005,
        "partial_tol": 1.05,
        "decimals": 3,
    }
    rows = evaluate_rows({"rows": [row]}, {"r.json": {"v": [10.014]}})
    assert rows[0]["difference_text"] == "0.14%"
    assert rows[0]["result"] == "match"
