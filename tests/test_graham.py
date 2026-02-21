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


def test_scan_fundamentals_caches_yfinance_calls_for_15_minutes(monkeypatch) -> None:
    import graham.graham as graham_module

    engine = GrahamEngine()
    engine.set_universe(["AAPL"])
    assert engine._fundamentals_cache_ttl_seconds == 900

    calls = {"ticker": 0, "analyze": 0}
    current_time = {"value": 1_000_000.0}

    class DummyTicker:
        pass

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str) -> DummyTicker:
            calls["ticker"] += 1
            return DummyTicker()

    def fake_analyze(symbol: str, ticker: object, y: float, require_dividend: bool) -> StockAnalysis:
        calls["analyze"] += 1
        return StockAnalysis(ticker=symbol, company_name=symbol, score=0.5)

    monkeypatch.setitem(__import__("sys").modules, "yfinance", FakeYF)
    monkeypatch.setattr(graham_module, "_configure_yfinance_cache", lambda yf_module: None)
    monkeypatch.setattr(graham_module, "_configure_yfinance_logging", lambda: None)
    monkeypatch.setattr(graham_module, "analyze_symbol", fake_analyze)
    monkeypatch.setattr(graham_module.time, "time", lambda: current_time["value"])

    engine.scan_fundamentals()
    engine.scan_fundamentals()
    assert calls["ticker"] == 1
    assert calls["analyze"] == 1

    current_time["value"] += 901
    engine.scan_fundamentals()
    assert calls["analyze"] == 2


def test_scan_fundamentals_loads_tickers_in_batches_of_30(monkeypatch) -> None:
    import graham.graham as graham_module

    engine = GrahamEngine()
    engine.set_universe([f"T{i:03d}" for i in range(65)])
    batch_sizes: list[int] = []

    class DummyTicker:
        pass

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str) -> DummyTicker:
            return DummyTicker()

    class FakeExecutor:
        def __init__(self, max_workers: int) -> None:
            self.max_workers = max_workers

        def __enter__(self) -> "FakeExecutor":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def map(self, fn, iterable):
            items = list(iterable)
            batch_sizes.append(len(items))
            return [fn(item) for item in items]

    monkeypatch.setitem(__import__("sys").modules, "yfinance", FakeYF)
    monkeypatch.setattr(graham_module, "_configure_yfinance_cache", lambda yf_module: None)
    monkeypatch.setattr(graham_module, "_configure_yfinance_logging", lambda: None)
    monkeypatch.setattr(
        graham_module,
        "analyze_symbol",
        lambda symbol, ticker, y, require_dividend: StockAnalysis(ticker=symbol, company_name=symbol, score=0.5),
    )
    monkeypatch.setattr(graham_module, "ThreadPoolExecutor", FakeExecutor)

    ranked = engine.scan_fundamentals()

    assert len(ranked) == 65
    assert batch_sizes == [30, 30, 5]


def test_scan_fundamentals_uses_defeatbeta_provider_when_enabled(monkeypatch) -> None:
    import graham.graham as graham_module

    engine = GrahamEngine()
    engine.set_universe(["AAPL"])
    calls = {"create": 0}

    class DummyTicker:
        pass

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str) -> DummyTicker:
            return DummyTicker()

    def fake_create_ticker(symbol: str, provider: str | None = None, yfinance_fallback: bool = True):
        calls["create"] += 1
        return DummyTicker(), "defeatbeta"

    monkeypatch.setitem(__import__("sys").modules, "yfinance", FakeYF)
    monkeypatch.setattr(graham_module, "_configure_yfinance_cache", lambda yf_module: None)
    monkeypatch.setattr(graham_module, "_configure_yfinance_logging", lambda: None)
    monkeypatch.setattr(graham_module, "resolve_market_data_provider", lambda: "defeatbeta")
    monkeypatch.setattr(graham_module, "create_ticker", fake_create_ticker)
    monkeypatch.setattr(
        graham_module,
        "analyze_symbol",
        lambda symbol, ticker, y, require_dividend: StockAnalysis(ticker=symbol, company_name=symbol, score=0.6),
    )

    ranked = engine.scan_fundamentals()

    assert len(ranked) == 1
    assert calls["create"] == 1


def test_scan_fundamentals_falls_back_to_yfinance_when_defeatbeta_is_sparse(monkeypatch) -> None:
    import graham.graham as graham_module

    engine = GrahamEngine()
    engine.set_universe(["AAPL"])
    calls = {"create": 0, "yf": 0}

    class DefeatTicker:
        pass

    class YFTicker:
        pass

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str) -> YFTicker:
            calls["yf"] += 1
            return YFTicker()

    def fake_create_ticker(symbol: str, provider: str | None = None, yfinance_fallback: bool = True):
        calls["create"] += 1
        return DefeatTicker(), "defeatbeta"

    def fake_analyze(symbol: str, ticker: object, y: float, require_dividend: bool) -> StockAnalysis:
        if isinstance(ticker, DefeatTicker):
            return StockAnalysis(ticker=symbol, company_name=symbol, score=0.1, criteria=[])
        return StockAnalysis(
            ticker=symbol,
            company_name="Apple Inc",
            score=0.7,
            price=120.0,
            pe=10.0,
            criteria=[CriterionResult(index=1, label="c1", status=PASS, note="ok")],
        )

    monkeypatch.setitem(__import__("sys").modules, "yfinance", FakeYF)
    monkeypatch.setattr(graham_module, "_configure_yfinance_cache", lambda yf_module: None)
    monkeypatch.setattr(graham_module, "_configure_yfinance_logging", lambda: None)
    monkeypatch.setattr(graham_module, "resolve_market_data_provider", lambda: "defeatbeta")
    monkeypatch.setattr(graham_module, "create_ticker", fake_create_ticker)
    monkeypatch.setattr(graham_module, "analyze_symbol", fake_analyze)

    ranked = engine.scan_fundamentals()

    assert len(ranked) == 1
    assert calls["create"] == 1
    assert calls["yf"] >= 1
    assert ranked[0].company_name == "Apple Inc"
    assert ranked[0].score == 0.7
