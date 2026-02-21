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
from textual.widgets import DataTable, Header, Input, RichLog, Static

from graham_agent.commands import CommandProcessor, discover_universe_names
from graham_agent.graham import GrahamEngine, StockAnalysis, filter_ranked, format_metric
from graham_agent.i18n import DisplayTranslator
from graham_agent.llm import LLMError, ask_model, fallback_explanation
from graham_agent.settings import UserSettings, load_user_settings, save_user_settings


class GrahamApp(App[None]):
    TITLE = "graham"
    CSS = """
    Screen {
        layout: vertical;
    }

    #center {
        height: auto;
        min-height: 8;
        max-height: 14;
    }

    #ranking {
        width: 1fr;
        min-height: 8;
        height: auto;
        border: round #4c956c;
        overflow: auto;
    }

    #details {
        width: 36;
        min-width: 26;
        max-width: 42;
        height: auto;
        max-height: 14;
        border: round #bc4749;
        padding: 1 1;
        overflow-y: auto;
    }

    #log {
        height: 1fr;
        min-height: 3;
        max-height: 10;
        border: round #386641;
    }

    #input-wrap {
        height: auto;
        padding: 0;
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

    @media (max-width: 120) {
        #center {
            layout: vertical;
            max-height: 16;
        }

        #ranking {
            width: 1fr;
            height: auto;
        }

        #details {
            width: 1fr;
            min-width: 0;
            max-height: 8;
        }

        #log {
            min-height: 3;
            max-height: 8;
        }
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.settings: UserSettings = load_user_settings()
        self.engine = GrahamEngine(y=4.4, require_dividend=True)
        startup_language = self.settings.default_language.strip().lower() if self.settings.default_language else "en"
        if not startup_language:
            startup_language = "en"
        self.i18n = DisplayTranslator(language=startup_language)
        self.language = startup_language
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
        self.score_green_min = self.settings.score_green_min
        self.score_orange_min = self.settings.score_orange_min
        self.processor = CommandProcessor(self)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="center"):
            yield DataTable(id="ranking")
            yield Static(self.tr("No row selected."), id="details")
        yield RichLog(id="log", markup=False, wrap=True)
        with Vertical(id="input-wrap"):
            yield Input(placeholder=self.tr("Type /help"), id="prompt")
            yield Static("", id="suggestions")

    async def on_mount(self) -> None:
        self._setup_table_columns()

        default_spec = self.settings.default_universe or "sample"
        tickers, note = self.processor.resolve_universe(default_spec)
        if not tickers:
            default_spec = "sample"
            tickers, note = self.processor.resolve_universe(default_spec)
            self.settings.default_universe = default_spec
            try:
                save_user_settings(self.settings)
            except Exception:
                pass
        self.set_universe(tickers, note)
        self._timer = self.set_interval(self.refresh_seconds, self._schedule_price_refresh)
        self.write_log("Welcome to graham. Type /help")
        self.write_log(f"Default universe: {default_spec}")
        self.write_log("Initial scan started in background...")
        asyncio.create_task(self.run_scan(top=None, min_score=0.0, refresh=self.refresh_seconds))

    def tr(self, text: str) -> str:
        return self.i18n.tr(text)

    def set_language(self, language: str) -> tuple[bool, str]:
        success, message = self.i18n.set_language(language)
        if not success:
            return False, message

        self.language = self.i18n.language
        self.settings.default_language = self.language
        try:
            save_user_settings(self.settings)
        except Exception as exc:
            return False, f"Language updated but could not persist settings: {exc}"
        prompt = self.query_one("#prompt", Input)
        prompt.placeholder = self.tr("Type /help")
        self._setup_table_columns()
        self.refresh_table()
        return True, self.tr(message)

    def get_rating_thresholds(self) -> tuple[float, float]:
        return self.score_green_min, self.score_orange_min

    def set_rating_thresholds(self, green: float, orange: float) -> tuple[bool, str]:
        if green > 1:
            green = green / 100.0
        if orange > 1:
            orange = orange / 100.0
        if green < 0 or orange < 0 or green > 1 or orange > 1:
            return False, "Thresholds must be in [0..1] or percentages [0..100]."
        if orange > green:
            return False, "Orange threshold must be <= green threshold."

        self.score_green_min = green
        self.score_orange_min = orange
        self.settings.score_green_min = green
        self.settings.score_orange_min = orange
        try:
            save_user_settings(self.settings)
        except Exception as exc:
            return False, f"Thresholds updated but could not persist settings: {exc}"

        self.refresh_table()
        return True, (
            f"Rating thresholds updated: green>={green:.2f}, orange>={orange:.2f}, red<{orange:.2f}"
        )

    def write_log(self, message: str, translate: bool = True) -> None:
        logger = self.query_one("#log", RichLog)
        logger.write(self.tr(message) if translate else message)

    def get_default_universe(self) -> str:
        return self.settings.default_universe

    def set_default_universe(self, spec: str) -> tuple[bool, str]:
        tickers, note = self.processor.resolve_universe(spec)
        if not tickers:
            return False, f"Cannot set default universe. {note}"

        self.settings.default_universe = spec
        try:
            save_user_settings(self.settings)
        except Exception as exc:
            return False, f"Default universe updated in memory but persistence failed: {exc}"

        self.set_universe(tickers, note)
        return True, f"Default universe set to: {spec} ({len(tickers)} tickers)"

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
                self.write_log(f"[LLM {self.model}]\n{response}", translate=False)
                return self.tr("LLM explanation written to log.")
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
                return self.tr("LLM error, deterministic fallback written to log.")

        fallback = fallback_explanation(
            ticker=analysis.ticker,
            question=question,
            score=analysis.score,
            mos=analysis.mos,
            criteria_lines=criteria_lines,
        )
        self.write_log(fallback)
        return self.tr("Explanation written to log.")

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
                self.write_log(response, translate=False)
            return

        if self.selected_ticker:
            response = await self.explain_ticker(self.selected_ticker, line)
            self.write_log(response, translate=False)
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
                self._score_badge(item.score),
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
            f"{self.tr('Ticker')}: {analysis.ticker}",
            f"{self.tr('Score')}: {analysis.score:.2f}",
            f"{self.tr('Price')}: {format_metric(analysis.price)}",
            f"V: {format_metric(analysis.intrinsic_value)}",
            f"MoS: {format_metric(analysis.mos, percentage=True)}",
            "",
            self.tr("Criteria:"),
        ]
        for criterion in analysis.criteria:
            lines.append(f"{criterion.index}. {self.tr(criterion.label)}: {criterion.status}")
            lines.append(f"   {self.tr('Note')}: {self.tr(criterion.note)}")

        if analysis.notes:
            lines.append("")
            lines.append(self.tr("Notes:"))
            lines.extend(f"- {self.tr(note)}" for note in analysis.notes)

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

    def _setup_table_columns(self) -> None:
        table = self.query_one("#ranking", DataTable)
        table.cursor_type = "row"
        table.clear(columns=True)
        table.add_columns(
            self.tr("rank"),
            self.tr("ticker"),
            self.tr("score"),
            self.tr("rating"),
            self.tr("price"),
            "V",
            "MoS",
            "P/E",
            "P/B",
            self.tr("dividend"),
        )

    def _score_badge(self, score: float) -> str:
        if score >= self.score_green_min:
            return "🟢"
        if score >= self.score_orange_min:
            return "🟠"
        return "🔴"


def run_tui() -> None:
    app = GrahamApp()
    app.run()
