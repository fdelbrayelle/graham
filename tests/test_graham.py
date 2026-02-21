from graham.graham import (
    CriterionResult,
    GrahamEngine,
    PASS,
    NA,
    StockAnalysis,
    analyze_symbol,
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


def test_engine_analyses_follow_active_universe() -> None:
    engine = GrahamEngine()
    engine._analyses = {
        "AAA": StockAnalysis(ticker="AAA", score=0.2),
        "BBB": StockAnalysis(ticker="BBB", score=0.3),
    }
    engine.set_universe(["BBB"])
    assert [item.ticker for item in engine.analyses] == ["BBB"]


def test_configure_yfinance_cache_uses_writable_location(tmp_path, monkeypatch) -> None:
    import graham.graham as graham_module

    calls: dict[str, str] = {}

    class FakeCache:
        def set_cache_location(self, path: str) -> None:
            calls["cache"] = path

    class FakeYF:
        cache = FakeCache()

        def set_tz_cache_location(self, path: str) -> None:
            calls["tz"] = path

    monkeypatch.setattr(graham_module, "_YFINANCE_CACHE_CONFIGURED", False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(graham_module.Path, "home", lambda: tmp_path)

    graham_module._configure_yfinance_cache(FakeYF())

    assert "cache" in calls
    assert "tz" in calls
    assert graham_module._YFINANCE_CACHE_CONFIGURED is True


def test_analyze_symbol_keeps_price_when_info_fails() -> None:
    class BrokenInfoTicker:
        @property
        def info(self) -> dict:
            raise RuntimeError("info unavailable")

        @property
        def fast_info(self) -> dict:
            return {"last_price": 123.45, "regular_market_time": 1_700_000_000}

    analysis = analyze_symbol("TEST", BrokenInfoTicker())
    assert analysis.ticker == "TEST"
    assert analysis.company_name == "TEST"
    assert analysis.price == 123.45
    assert analysis.price_time is not None


def test_engine_applies_company_override_when_analysis_name_is_symbol(monkeypatch) -> None:
    import graham.graham as graham_module

    engine = GrahamEngine()
    engine.set_universe(["AI.PA"])
    engine.set_company_name_overrides({"AI.PA": "Air Liquide"})

    class DummyTicker:
        pass

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str) -> DummyTicker:
            return DummyTicker()

    monkeypatch.setitem(__import__("sys").modules, "yfinance", FakeYF)
    monkeypatch.setattr(graham_module, "_configure_yfinance_cache", lambda yf_module: None)
    monkeypatch.setattr(
        graham_module,
        "analyze_symbol",
        lambda symbol, ticker, y, require_dividend: StockAnalysis(ticker=symbol, company_name=symbol),
    )

    ranked = engine.scan_fundamentals()
    assert ranked[0].company_name == "Air Liquide"
