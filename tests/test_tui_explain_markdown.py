import asyncio
from types import SimpleNamespace

import pytest

from graham.graham import CriterionResult, StockAnalysis

pytest.importorskip("rich.markdown")
pytest.importorskip("textual")
from graham.tui import GrahamApp


class DummyExplainApp:
    def __init__(self, analysis: StockAnalysis) -> None:
        self.engine = SimpleNamespace(analyses=[analysis])
        self.model = "openai/gpt-5"
        self.language = "en"
        self.logged: list[tuple[str, bool, bool]] = []
        self._line_count = 0
        self.queued_scroll_line: int | None = None

    def tr(self, text: str) -> str:
        return text

    def write_log(
        self, message: str, translate: bool = True, markdown: bool = False
    ) -> tuple[int, int]:
        self.logged.append((message, translate, markdown))
        start = self._line_count
        line_count = max(1, len(message.splitlines()))
        self._line_count += line_count
        return start, self._line_count

    def _queue_log_scroll_to_absolute_line(self, absolute_line: int) -> None:
        self.queued_scroll_line = absolute_line


def test_explain_ticker_renders_llm_response_as_markdown(monkeypatch) -> None:
    analysis = StockAnalysis(
        ticker="MSFT",
        score=0.86,
        price=100.0,
        intrinsic_value=140.0,
        mos=0.4,
        criteria=[CriterionResult(index=1, label="Test", status="PASS", note="ok")],
    )
    app = DummyExplainApp(analysis)

    monkeypatch.setattr("graham.tui.ask_model", lambda *_args, **_kwargs: "## Summary\n- Point A")

    result = asyncio.run(GrahamApp.explain_ticker(app, "MSFT", "What matters now?"))

    assert result == "LLM explanation written to log."
    assert app.logged[0] == ("[LLM openai/gpt-5 /explain MSFT]", False, False)
    assert app.logged[1] == ("## Summary\n- Point A", False, True)
    assert app.queued_scroll_line == 1


def test_moat_ticker_queues_scroll_to_markdown_start(monkeypatch) -> None:
    analysis = StockAnalysis(ticker="MSFT")
    app = DummyExplainApp(analysis)

    monkeypatch.setattr("graham.tui.ask_model", lambda *_args, **_kwargs: "# Moat\n- Durable")
    monkeypatch.setattr("graham.tui.build_moat_prompt", lambda _ticker, _lang: "Prompt")
    monkeypatch.setattr("graham.tui.load_persisted_language", lambda _lang: "en")

    result = asyncio.run(GrahamApp.moat_ticker(app, "msft"))

    assert result == "LLM moat analysis written to log."
    assert app.logged[0] == ("Generating moat analysis for MSFT with model openai/gpt-5...", False, False)
    assert app.logged[1] == ("[LLM openai/gpt-5 /moat MSFT]", False, False)
    assert app.logged[2] == ("# Moat\n- Durable", False, True)
    assert app.queued_scroll_line == 2
