import asyncio

from graham.commands import CommandProcessor


class DummyApp:
    def __init__(self) -> None:
        self.model = "gpt-5.2"
        self.selected_ticker = None
        self.language = "en"
        self.moat_calls: list[str] = []

    def tr(self, text: str) -> str:
        return text

    def current_tickers(self) -> list[str]:
        return ["AAPL", "MSFT", "TSLA"]

    async def moat_ticker(self, ticker: str) -> str:
        self.moat_calls.append(ticker)
        return f"moat:{ticker}"


def test_moat_suggestions_use_current_tickers() -> None:
    processor = CommandProcessor(DummyApp())
    assert processor.suggestions("/moat M") == ["MSFT"]


def test_command_suggestions_include_keys() -> None:
    processor = CommandProcessor(DummyApp())
    assert "/keys" in processor.suggestions("/k")


def test_help_mentions_moat() -> None:
    processor = CommandProcessor(DummyApp())
    assert "/moat TICKER" in processor.help_text()


def test_help_mentions_keys_command() -> None:
    processor = CommandProcessor(DummyApp())
    assert "/keys" in processor.help_text()


def test_execute_keys_returns_shortcuts_text() -> None:
    processor = CommandProcessor(DummyApp())
    result = asyncio.run(processor.execute("/keys"))
    assert "Keyboard shortcuts:" in result
    assert "Ctrl+L" in result
    assert "Ctrl+R" in result
    assert "F1" in result


def test_execute_moat_requires_one_ticker() -> None:
    processor = CommandProcessor(DummyApp())
    result = asyncio.run(processor.execute("/moat"))
    assert result == "Usage: /moat TICKER"


def test_execute_moat_calls_app_handler() -> None:
    app = DummyApp()
    processor = CommandProcessor(app)
    result = asyncio.run(processor.execute("/moat MSFT"))
    assert result == "moat:MSFT"
    assert app.moat_calls == ["MSFT"]
