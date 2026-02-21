from __future__ import annotations

from types import ModuleType
import sys

from graham.market_data import DefeatBetaTickerAdapter, create_ticker, resolve_market_data_provider


def test_resolve_market_data_provider_aliases(monkeypatch) -> None:
    monkeypatch.setenv("GRAHAM_MARKET_DATA_PROVIDER", "defeatbeta-api")
    assert resolve_market_data_provider() == "defeatbeta"
    monkeypatch.setenv("GRAHAM_MARKET_DATA_PROVIDER", "yfinance")
    assert resolve_market_data_provider() == "yfinance"


def test_create_ticker_prefers_defeatbeta_when_available(monkeypatch) -> None:
    class FakeDBTicker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def summary(self) -> dict[str, object]:
            return {"name": "Demo Inc", "price": 123.0}

    db_root = ModuleType("defeatbeta_api")
    db_data = ModuleType("defeatbeta_api.data")
    db_ticker = ModuleType("defeatbeta_api.data.ticker")
    setattr(db_ticker, "Ticker", FakeDBTicker)
    monkeypatch.setitem(sys.modules, "defeatbeta_api", db_root)
    monkeypatch.setitem(sys.modules, "defeatbeta_api.data", db_data)
    monkeypatch.setitem(sys.modules, "defeatbeta_api.data.ticker", db_ticker)

    ticker, source = create_ticker("AAPL", provider="defeatbeta", yfinance_fallback=False)

    assert source == "defeatbeta"
    assert isinstance(ticker, DefeatBetaTickerAdapter)
    assert ticker.info["currentPrice"] == 123.0


def test_create_ticker_defeatbeta_falls_back_to_yfinance(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "defeatbeta_api", raising=False)
    monkeypatch.delitem(sys.modules, "defeatbeta_api.data", raising=False)
    monkeypatch.delitem(sys.modules, "defeatbeta_api.data.ticker", raising=False)

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str) -> object:
            return {"symbol": symbol}

    monkeypatch.setitem(sys.modules, "yfinance", FakeYF)

    ticker, source = create_ticker("MSFT", provider="defeatbeta", yfinance_fallback=True)

    assert source == "yfinance"
    assert ticker == {"symbol": "MSFT"}


def test_defeatbeta_adapter_exposes_statement_frames() -> None:
    class FakeDBTicker:
        def income_statement(self) -> dict[str, dict[str, float]]:
            return {"Diluted EPS": {"2023": 3.0, "2024": 4.0}}

        def quarterly_income_statement(self) -> list[dict[str, object]]:
            return [
                {"period": "2024-Q1", "Diluted EPS": 1.0},
                {"period": "2024-Q2", "Diluted EPS": 1.2},
            ]

        def balance_sheet(self) -> dict[str, dict[str, float]]:
            return {"Total Debt": {"2024": 100.0}}

    adapter = DefeatBetaTickerAdapter("TEST", FakeDBTicker())

    assert adapter.income_stmt is not None
    assert "Diluted EPS" in adapter.income_stmt.index
    assert adapter.quarterly_income_stmt is not None
    assert adapter.balance_sheet is not None
