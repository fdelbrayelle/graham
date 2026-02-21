from graham_agent.graham import (
    CriterionResult,
    PASS,
    NA,
    StockAnalysis,
    compute_intrinsic_value,
    compute_margin_of_safety,
    compute_score,
    rank_analyses,
)


def test_intrinsic_value_formula() -> None:
    value = compute_intrinsic_value(eps=4.0, growth_percent=5.0, y=4.4)
    assert value == 74.0


def test_margin_of_safety() -> None:
    mos = compute_margin_of_safety(intrinsic_value=100.0, price=80.0)
    assert mos == 0.25


def test_score_excludes_na() -> None:
    criteria = [
        CriterionResult(index=1, label="c1", status=NA, note="na"),
        CriterionResult(index=2, label="c2", status=PASS, note="ok"),
        CriterionResult(index=3, label="c3", status="FAIL", note="ko"),
    ]
    assert compute_score(criteria) == 0.5


def test_ranking_order() -> None:
    a = StockAnalysis(ticker="AAA", score=0.8, mos=0.1, pe=8.0)
    b = StockAnalysis(ticker="BBB", score=0.8, mos=0.2, pe=9.0)
    c = StockAnalysis(ticker="CCC", score=0.6, mos=0.5, pe=5.0)
    ranked = rank_analyses([a, b, c])
    assert [item.ticker for item in ranked] == ["BBB", "AAA", "CCC"]
