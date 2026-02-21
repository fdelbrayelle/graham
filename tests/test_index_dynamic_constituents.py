from __future__ import annotations

from graham.commands import CommandProcessor


class DummyApp:
    model = "none"
    selected_ticker = None
    language = "en"

    def tr(self, text: str) -> str:
        return text

    def current_tickers(self) -> list[str]:
        return []

    def available_universes(self) -> list[str]:
        return []


def _processor() -> CommandProcessor:
    return CommandProcessor(DummyApp())


def test_normalize_ticker_handles_us_dot_share_class() -> None:
    processor = _processor()
    assert processor._normalize_ticker("brk.b") == "BRK-B"
    assert processor._normalize_ticker("bf.b") == "BF-B"


def test_normalize_ticker_keeps_market_suffix() -> None:
    processor = _processor()
    assert processor._normalize_ticker("ai.pa") == "AI.PA"
    assert processor._normalize_ticker("7203.t") == "7203.T"


def test_nasdaq_rows_and_total_parses_holdings_payload() -> None:
    processor = _processor()
    payload = {
        "data": {
            "holdings": {
                "rows": [{"symbol": "AAPL"}, {"symbol": "MSFT"}],
                "totalrecords": "2",
            }
        }
    }
    rows, total = processor._nasdaq_rows_and_total(payload)
    assert len(rows) == 2
    assert total == 2


def test_is_nasdaq_symbol_candidate_filters_foreign_suffixes() -> None:
    processor = _processor()
    assert processor._is_nasdaq_symbol_candidate("SPY")
    assert processor._is_nasdaq_symbol_candidate("^GSPC")
    assert processor._is_nasdaq_symbol_candidate("BRK.B")
    assert not processor._is_nasdaq_symbol_candidate("EXSA.DE")
    assert not processor._is_nasdaq_symbol_candidate("AI.PA")


def test_fetch_nasdaq_rows_handles_pagination(monkeypatch) -> None:
    processor = _processor()
    first_page_rows = [{"symbol": f"T{i:03d}"} for i in range(250)]
    second_page_rows = [{"symbol": "AAPL"}]

    def fake_load_json(url: str, headers: dict[str, str]) -> dict:
        if "offset=0" in url:
            return {
                "data": {
                    "holdings": {"rows": first_page_rows, "totalrecords": "251"},
                }
            }
        if "offset=250" in url:
            return {
                "data": {
                    "holdings": {"rows": second_page_rows, "totalrecords": "251"},
                }
            }
        return {}

    monkeypatch.setattr(processor, "_load_json", fake_load_json)
    tickers = processor._fetch_nasdaq_rows("SPY", "holdings", "etf")
    assert len(tickers) == 251
    assert tickers[0] == "T000"
    assert tickers[-1] == "AAPL"


def test_fetch_nasdaq_constituents_falls_back_to_components(monkeypatch) -> None:
    processor = _processor()

    def fake_fetch_rows(symbol: str, endpoint: str, asset_class: str) -> list[str]:
        if endpoint == "components" and asset_class == "etf":
            return ["AAPL", "MSFT"]
        return []

    monkeypatch.setattr(processor, "_fetch_nasdaq_rows", fake_fetch_rows)
    assert processor._fetch_nasdaq_constituents("SPY") == ["AAPL", "MSFT"]


def test_extract_tickers_from_csv_text_parses_symbol_column() -> None:
    processor = _processor()
    csv_text = "\n".join(
        [
            "Header one",
            "Ticker,Name,Weight",
            "AAPL,Apple,5.1",
            "MSFT,Microsoft,4.9",
        ]
    )
    assert processor._extract_tickers_from_csv_text(csv_text) == ["AAPL", "MSFT"]


def test_find_ishares_product_url_uses_ticker_and_relative_url() -> None:
    processor = _processor()
    payload = {
        "data": {
            "rows": [
                {
                    "ticker": "URTH",
                    "productPageUrl": "/us/products/239696/ishares-msci-world-etf",
                }
            ]
        }
    }
    assert (
        processor._find_ishares_product_url(payload, "URTH")
        == "https://www.ishares.com/us/products/239696/ishares-msci-world-etf"
    )


def test_fetch_ishares_holdings_builds_holdings_url(monkeypatch) -> None:
    processor = _processor()
    monkeypatch.setattr(
        processor,
        "_resolve_ishares_product_url",
        lambda symbol: "https://www.ishares.com/us/products/239696/ishares-msci-world-etf",
    )
    monkeypatch.setattr(
        processor,
        "_load_text",
        lambda url, headers: "Ticker,Name\nAAPL,Apple\nMSFT,Microsoft" if "URTH_holdings" in url else "",
    )
    assert processor._fetch_ishares_holdings("URTH") == ["AAPL", "MSFT"]


def test_extract_tokyo_tickers_from_csv_text_reads_code_column() -> None:
    processor = _processor()
    csv_text = "\n".join(
        [
            "Code,Company,Weight",
            "7203,Toyota Motor,2.10",
            "6758,Sony Group,1.90",
            "6501,Hitachi,1.50",
        ]
    )
    assert processor._extract_tokyo_tickers_from_csv_text(csv_text) == ["7203.T", "6758.T", "6501.T"]


def test_extract_tokyo_constituents_from_csv_text_includes_company_names() -> None:
    processor = _processor()
    csv_text = "\n".join(
        [
            "Code,Company,Weight",
            "7203,Toyota Motor,2.10",
            "6758,Sony Group,1.90",
        ]
    )
    tickers, names = processor._extract_tokyo_constituents_from_csv_text(csv_text)
    assert tickers == ["7203.T", "6758.T"]
    assert names["7203.T"] == "Toyota Motor"
    assert names["6758.T"] == "Sony Group"


def test_extract_wikipedia_tickers_from_html_applies_cac_suffix() -> None:
    processor = _processor()
    html = "\n".join(
        [
            "<table class='wikitable'>",
            "<tr><th>Company</th><th>Ticker</th></tr>",
            "<tr><td>Air Liquide</td><td>AI</td></tr>",
            "<tr><td>LVMH</td><td>MC</td></tr>",
            "</table>",
        ]
    )
    assert processor._extract_wikipedia_tickers_from_html("cac40", html) == ["AI.PA", "MC.PA"]


def test_extract_wikipedia_tickers_from_html_keeps_eurostoxx_exchange_suffix() -> None:
    processor = _processor()
    html = "\n".join(
        [
            "<table class='wikitable'>",
            "<tr><th>Ticker symbol</th><th>Company</th></tr>",
            "<tr><td>AIR.PA</td><td>Airbus</td></tr>",
            "<tr><td>SAP.DE</td><td>SAP</td></tr>",
            "<tr><td>SAN</td><td>Sanofi</td></tr>",
            "</table>",
        ]
    )
    assert processor._extract_wikipedia_tickers_from_html("eurostoxx", html) == ["AIR.PA", "SAP.DE"]


def test_fetch_public_index_constituents_prefers_nikkei_source(monkeypatch) -> None:
    processor = _processor()
    monkeypatch.setattr(
        processor,
        "_fetch_nikkei_components_with_names",
        lambda: (["7203.T", "6758.T"], {"7203.T": "Toyota Motor", "6758.T": "Sony Group"}),
    )
    monkeypatch.setattr(processor, "_fetch_wikipedia_components_with_names", lambda index_name: ([], {}))
    values, note, names = processor._fetch_public_index_constituents("nikkei225")
    assert values == ["7203.T", "6758.T"]
    assert note == "nikkei:nk225"
    assert names["7203.T"] == "Toyota Motor"


def test_fetch_public_index_constituents_uses_wikipedia_for_sp500(monkeypatch) -> None:
    processor = _processor()
    monkeypatch.setattr(
        processor,
        "_fetch_wikipedia_components_with_names",
        lambda index_name: (["AAPL", "MSFT"], {"AAPL": "Apple", "MSFT": "Microsoft"}),
    )
    values, note, names = processor._fetch_public_index_constituents("sp500")
    assert values == ["AAPL", "MSFT"]
    assert note == "wikipedia:sp500"
    assert names["AAPL"] == "Apple"


def test_fetch_index_tickers_short_circuits_on_large_public_payload(monkeypatch) -> None:
    processor = _processor()
    public_values = [f"T{i:03d}" for i in range(450)]
    monkeypatch.setattr(
        processor,
        "_fetch_public_index_constituents",
        lambda index_name: (public_values, "wikipedia:sp500", {}),
    )
    calls = {"nasdaq": 0}

    def fake_nasdaq(symbol: str) -> list[str]:
        calls["nasdaq"] += 1
        return []

    monkeypatch.setattr(processor, "_fetch_nasdaq_constituents", fake_nasdaq)

    class FakeTicker:
        constituents: list[str] = []

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str) -> FakeTicker:
            return FakeTicker()

    monkeypatch.setitem(__import__("sys").modules, "yfinance", FakeYF)

    values, note, _ = processor._fetch_index_tickers("sp500")

    assert len(values) == 450
    assert "wikipedia:sp500" in note
    assert calls["nasdaq"] == 0


def test_fetch_wikipedia_components_sp500_uses_single_url_encoding(monkeypatch) -> None:
    processor = _processor()
    captured: dict[str, str] = {}

    def fake_load_json(url: str, headers: dict[str, str]) -> dict:
        captured["url"] = url
        return {"parse": {"text": "<table class='wikitable'></table>"}}

    monkeypatch.setattr(processor, "_load_json", fake_load_json)
    processor._fetch_wikipedia_components_with_names("sp500")

    url = captured["url"]
    assert "List_of_S%26P_500_companies" in url
    assert "List_of_S%2526P_500_companies" not in url


def test_api_json_cache_uses_ttl(monkeypatch) -> None:
    processor = _processor()
    calls = {"count": 0}

    def fake_http_get_bytes(url: str, headers: dict[str, str], timeout: int) -> bytes:
        calls["count"] += 1
        return b'{"data":{"rows":[{"symbol":"AAPL"}]}}'

    monkeypatch.setattr(processor, "_http_get_bytes", fake_http_get_bytes)
    headers = {"Referer": "https://example.com"}

    first = processor._load_json("https://api.example.com/test", headers)
    second = processor._load_json("https://api.example.com/test", headers)

    assert first == second
    assert calls["count"] == 1


def test_fetch_index_tickers_uses_index_cache(monkeypatch) -> None:
    processor = _processor()
    calls = {"ishares": 0, "nasdaq": 0}

    monkeypatch.setattr(
        processor,
        "_fetch_public_index_constituents",
        lambda index_name: (["AAPL"], "public:demo", {"AAPL": "Apple"}),
    )

    def fake_ishares(symbol: str) -> list[str]:
        calls["ishares"] += 1
        return ["MSFT"]

    def fake_nasdaq(symbol: str) -> list[str]:
        calls["nasdaq"] += 1
        return []

    monkeypatch.setattr(processor, "_fetch_ishares_holdings", fake_ishares)
    monkeypatch.setattr(processor, "_fetch_nasdaq_constituents", fake_nasdaq)

    class FakeTicker:
        constituents: list[str] = []

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str) -> FakeTicker:
            return FakeTicker()

    monkeypatch.setitem(__import__("sys").modules, "yfinance", FakeYF)

    first = processor._fetch_index_tickers("msci_world")
    second = processor._fetch_index_tickers("msci_world")

    assert first == second
    assert calls["ishares"] == 1
    assert calls["nasdaq"] == 1


def test_fetch_index_tickers_cache_respects_ttl(monkeypatch) -> None:
    processor = _processor()
    processor._index_cache_ttl_seconds = 0
    calls = {"ishares": 0}

    monkeypatch.setattr(processor, "_fetch_public_index_constituents", lambda index_name: ([], "", {}))
    monkeypatch.setattr(processor, "_fetch_nasdaq_constituents", lambda symbol: [])

    def fake_ishares(symbol: str) -> list[str]:
        calls["ishares"] += 1
        return ["AAPL"]

    monkeypatch.setattr(processor, "_fetch_ishares_holdings", fake_ishares)

    class FakeTicker:
        constituents: list[str] = []

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str) -> FakeTicker:
            return FakeTicker()

    monkeypatch.setitem(__import__("sys").modules, "yfinance", FakeYF)

    processor._fetch_index_tickers("msci_world")
    processor._fetch_index_tickers("msci_world")

    assert calls["ishares"] == 2


def test_fetch_index_tickers_uses_defeatbeta_provider_when_enabled(monkeypatch) -> None:
    processor = _processor()
    calls = {"create": 0}

    monkeypatch.setattr(processor, "_fetch_public_index_constituents", lambda index_name: ([], "", {}))
    monkeypatch.setattr(processor, "_fetch_nasdaq_constituents", lambda symbol: [])
    monkeypatch.setattr(processor, "_fetch_ishares_holdings", lambda symbol: [])
    monkeypatch.setattr("graham.commands.resolve_market_data_provider", lambda: "defeatbeta")

    class FakeTicker:
        constituents = ["AAPL", "MSFT"]

    def fake_create_ticker(symbol: str, provider: str | None = None, yfinance_fallback: bool = True):
        calls["create"] += 1
        return FakeTicker(), "defeatbeta"

    monkeypatch.setattr("graham.commands.create_ticker", fake_create_ticker)

    values, note, _ = processor._fetch_index_tickers("msci_world")

    assert calls["create"] >= 1
    assert "defeatbeta" in note
    assert "AAPL" in values


def test_fetch_index_tickers_falls_back_to_yfinance_when_defeatbeta_has_no_constituents(monkeypatch) -> None:
    processor = _processor()
    calls = {"defeatbeta": 0, "yfinance": 0}

    monkeypatch.setattr(processor, "_fetch_public_index_constituents", lambda index_name: ([], "", {}))
    monkeypatch.setattr(processor, "_fetch_nasdaq_constituents", lambda symbol: [])
    monkeypatch.setattr(processor, "_fetch_ishares_holdings", lambda symbol: [])
    monkeypatch.setattr("graham.commands.resolve_market_data_provider", lambda: "defeatbeta")

    class EmptyTicker:
        constituents: list[str] = []

    class FullTicker:
        constituents = ["AAPL", "MSFT"]

    def fake_create_ticker(symbol: str, provider: str | None = None, yfinance_fallback: bool = True):
        if provider == "defeatbeta":
            calls["defeatbeta"] += 1
            return EmptyTicker(), "defeatbeta"
        calls["yfinance"] += 1
        return FullTicker(), "yfinance"

    monkeypatch.setattr("graham.commands.create_ticker", fake_create_ticker)

    values, note, _ = processor._fetch_index_tickers("msci_world")

    assert calls["defeatbeta"] >= 1
    assert calls["yfinance"] >= 1
    assert "AAPL" in values
    assert "yfinance" in note
