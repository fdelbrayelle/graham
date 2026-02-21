from __future__ import annotations

import asyncio
import csv
import json
from datetime import datetime
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.widgets import DataTable, Footer, Header, Input, RichLog, Static

from graham_agent.commands import CommandProcessor, discover_universe_names
from graham_agent.graham import GrahamEngine, StockAnalysis, filter_ranked, format_metric
from graham_agent.llm import LLMError, ask_model, fallback_explanation


class GrahamApp(App[None]):
    TITLE = "graham"
    CSS = """
    Screen {
        layout: vertical;
    }

    #center {
        height: 1fr;
        min-height: 16;
    }

    #ranking {
        width: 2fr;
        border: round #4c956c;
    }

    #details {
        width: 1fr;
        border: round #bc4749;
        padding: 1 1;
        overflow-y: auto;
    }

    #log {
        height: 14;
        border: round #386641;
    }

    #input-wrap {
        height: auto;
        padding: 0 0 1 0;
    }

    #prompt {
        width: 100%;
    }

    #suggestions {
        display: none;
        max-height: 8;
        border: round #6a994e;
    }

    #suggestions.visible {
        display: block;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.engine = GrahamEngine(y=4.4, require_dividend=True)
        self.model = "none"
        self.refresh_seconds = 15
        self.scan_top: int | None = None
        self.scan_min_score = 0.0
        self.selected_ticker: str | None = None
        self._current_results: list[StockAnalysis] = []
        self._suggestions: list[str] = []
        self._suggestion_index = 0
        self._refreshing = False
        self._timer = None
        self._universe_note = "sample"
        self.processor = CommandProcessor(self)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="center"):
            yield DataTable(id="ranking")
            yield Static("No row selected.", id="details")
        yield RichLog(id="log", markup=False, wrap=True)
        with Vertical(id="input-wrap"):
            yield Input(placeholder="Type /help", id="prompt")
            yield Static("", id="suggestions")
        yield Footer()

    async def on_mount(self) -> None:
        table = self.query_one("#ranking", DataTable)
        table.cursor_type = "row"
        table.add_columns("rank", "ticker", "score", "price", "V", "MoS", "P/E", "P/B", "dividend")

        tickers, note = self.processor.resolve_universe("sample")
        self.set_universe(tickers, note)
        await self.run_scan(top=None, min_score=0.0, refresh=self.refresh_seconds)

        self._timer = self.set_interval(self.refresh_seconds, self._schedule_price_refresh)
        self.write_log("Welcome to graham. Type /help")

    def write_log(self, message: str) -> None:
        logger = self.query_one("#log", RichLog)
        logger.write(message)

    def available_universes(self) -> list[str]:
        return discover_universe_names()

    def current_tickers(self) -> list[str]:
        if self._current_results:
            return [item.ticker for item in self._current_results]
        return list(self.engine.universe)

    def set_universe(self, tickers: list[str], note: str) -> None:
        cleaned = self.engine.set_universe(tickers)
        self._universe_note = note
        self.write_log(f"Active universe: {len(cleaned)} tickers ({note})")

    async def run_scan(self, top: int | None, min_score: float, refresh: int | None) -> None:
        self.scan_top = top
        self.scan_min_score = min_score
        if refresh is not None:
            self.refresh_seconds = max(3, refresh)
            self._reset_timer()

        self.write_log("Running fundamentals scan...")
        ranked = await asyncio.to_thread(self.engine.scan_fundamentals)
        self._current_results = filter_ranked(ranked, top=self.scan_top, min_score=self.scan_min_score)
        self.refresh_table()

        if not self._current_results:
            self.write_log("No results. Try /scan --min-score 0")
        else:
            self.write_log(f"Scan completed: {len(self._current_results)} results")

    async def explain_ticker(self, ticker: str, question: str) -> str:
        analysis = next((item for item in self.engine.analyses if item.ticker == ticker), None)
        if analysis is None:
            return f"Ticker not found: {ticker}"

        criteria_lines = [
            f"- {criterion.index}. {criterion.label}: {criterion.status} ({criterion.note})"
            for criterion in analysis.criteria
        ]

        if self.model != "none":
            system_prompt = (
                "You are a concise value investing analyst. "
                "Explain Benjamin Graham's 7 rules carefully and call out N/A values."
            )
            user_prompt = (
                f"Ticker: {analysis.ticker}\n"
                f"Score: {analysis.score:.2f}\n"
                f"Price: {format_metric(analysis.price)}\n"
                f"V: {format_metric(analysis.intrinsic_value)}\n"
                f"MoS: {format_metric(analysis.mos, percentage=True)}\n"
                f"Question: {question or 'Summarize the situation'}\n"
                + "\n".join(criteria_lines)
            )
            try:
                response = await asyncio.to_thread(ask_model, self.model, system_prompt, user_prompt)
                self.write_log(f"[LLM {self.model}]\n{response}")
                return "LLM explanation written to log."
            except LLMError as exc:
                fallback = fallback_explanation(
                    ticker=analysis.ticker,
                    question=question,
                    score=analysis.score,
                    mos=analysis.mos,
                    criteria_lines=criteria_lines,
                )
                self.write_log(f"LLM error: {exc}")
                self.write_log(fallback)
                return "LLM error, deterministic fallback written to log."

        fallback = fallback_explanation(
            ticker=analysis.ticker,
            question=question,
            score=analysis.score,
            mos=analysis.mos,
            criteria_lines=criteria_lines,
        )
        self.write_log(fallback)
        return "Explanation written to log."

    def export_results(self, export_format: str) -> str:
        export_dir = Path("exports")
        export_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = export_dir / f"graham_scan_{stamp}.{export_format}"

        payload = [
            {
                "ticker": item.ticker,
                "score": item.score,
                "price": item.price,
                "intrinsic_value": item.intrinsic_value,
                "mos": item.mos,
                "pe": item.pe,
                "pb": item.pb,
                "dividend_rate": item.dividend_rate,
            }
            for item in self._current_results
        ]

        if export_format == "json":
            output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return str(output)

        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["ticker", "score", "price", "intrinsic_value", "mos", "pe", "pb", "dividend_rate"],
            )
            writer.writeheader()
            writer.writerows(payload)
        return str(output)

    @on(DataTable.RowHighlighted, "#ranking")
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        row_key = event.row_key
        if row_key is None:
            return
        ticker = str(row_key.value)
        analysis = next((item for item in self._current_results if item.ticker == ticker), None)
        if analysis is None:
            return
        self._show_details(analysis)

    @on(Input.Changed, "#prompt")
    def on_input_changed(self, event: Input.Changed) -> None:
        self._suggestions = self.processor.suggestions(event.value)
        self._suggestion_index = 0
        self._render_suggestions()

    @on(Input.Submitted, "#prompt")
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._suggestions:
            current = event.value.strip()
            selected = self._suggestions[self._suggestion_index]
            if current != selected:
                self._apply_suggestion()
                return
            self._hide_suggestions()

        line = event.value.strip()
        self.query_one("#prompt", Input).value = ""
        self._hide_suggestions()

        if not line:
            return

        self.write_log(f"> {line}")

        if line.startswith("/"):
            try:
                response = await self.processor.execute(line)
            except Exception as exc:
                response = f"Command error: {exc}"
            if response:
                self.write_log(response)
            return

        if self.selected_ticker:
            response = await self.explain_ticker(self.selected_ticker, line)
            self.write_log(response)
            return

        self.write_log("No ticker selected. Type /help")

    def on_key(self, event: Key) -> None:
        prompt = self.query_one("#prompt", Input)
        if self.focused is not prompt:
            return
        if not self._suggestions:
            return

        if event.key == "down":
            self._suggestion_index = min(self._suggestion_index + 1, len(self._suggestions) - 1)
            self._sync_suggestion_cursor()
            event.stop()
            return

        if event.key == "up":
            self._suggestion_index = max(self._suggestion_index - 1, 0)
            self._sync_suggestion_cursor()
            event.stop()
            return

        if event.key == "tab":
            self._apply_suggestion()
            event.stop()
            return

    def _render_suggestions(self) -> None:
        suggestion_view = self.query_one("#suggestions", Static)

        if not self._suggestions:
            self._hide_suggestions()
            return

        suggestion_view.add_class("visible")
        self._sync_suggestion_cursor()

    def _hide_suggestions(self) -> None:
        suggestion_view = self.query_one("#suggestions", Static)
        suggestion_view.remove_class("visible")
        suggestion_view.update("")

    def _sync_suggestion_cursor(self) -> None:
        suggestion_view = self.query_one("#suggestions", Static)
        lines = []
        for index, suggestion in enumerate(self._suggestions):
            prefix = ">" if index == self._suggestion_index else " "
            lines.append(f"{prefix} {suggestion}")
        suggestion_view.update("\n".join(lines))

    def _apply_suggestion(self) -> None:
        if not self._suggestions:
            return

        selected = self._suggestions[self._suggestion_index]
        prompt = self.query_one("#prompt", Input)
        current = prompt.value
        trimmed = current.rstrip()

        if " " in trimmed:
            head, _, _ = trimmed.rpartition(" ")
            prompt.value = f"{head} {selected}" if head else selected
        else:
            prompt.value = selected

        prompt.cursor_position = len(prompt.value)
        self._hide_suggestions()
        self._suggestions = []

    def refresh_table(self) -> None:
        table = self.query_one("#ranking", DataTable)
        table.clear(columns=False)

        for rank, item in enumerate(self._current_results, start=1):
            table.add_row(
                str(rank),
                item.ticker,
                f"{item.score:.2f}",
                format_metric(item.price),
                format_metric(item.intrinsic_value),
                format_metric(item.mos, percentage=True),
                format_metric(item.pe),
                format_metric(item.pb),
                format_metric(item.dividend_rate),
                key=item.ticker,
            )

        if self._current_results:
            first = self._current_results[0]
            self._show_details(first)

    def _show_details(self, analysis: StockAnalysis) -> None:
        self.selected_ticker = analysis.ticker
        details = self.query_one("#details", Static)

        lines = [
            f"Ticker: {analysis.ticker}",
            f"Score: {analysis.score:.2f}",
            f"Price: {format_metric(analysis.price)}",
            f"V: {format_metric(analysis.intrinsic_value)}",
            f"MoS: {format_metric(analysis.mos, percentage=True)}",
            "",
            "Criteria:",
        ]
        for criterion in analysis.criteria:
            lines.append(f"{criterion.index}. {criterion.label}: {criterion.status}")
            lines.append(f"   note: {criterion.note}")

        if analysis.notes:
            lines.append("")
            lines.append("Notes:")
            lines.extend(f"- {note}" for note in analysis.notes)

        details.update("\n".join(lines))

    def _schedule_price_refresh(self) -> None:
        asyncio.create_task(self._refresh_prices())

    async def _refresh_prices(self) -> None:
        if self._refreshing or not self.engine.analyses:
            return
        self._refreshing = True
        try:
            ranked = await asyncio.to_thread(self.engine.refresh_prices)
            self._current_results = filter_ranked(ranked, top=self.scan_top, min_score=self.scan_min_score)
            self.refresh_table()
        except Exception as exc:
            self.write_log(f"Price refresh error: {exc}")
        finally:
            self._refreshing = False

    def _reset_timer(self) -> None:
        if self._timer is not None:
            try:
                self._timer.stop()
            except Exception:
                pass
        self._timer = self.set_interval(self.refresh_seconds, self._schedule_price_refresh)


def run_tui() -> None:
    app = GrahamApp()
    app.run()
