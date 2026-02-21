from __future__ import annotations

import asyncio
import csv
import json
from datetime import datetime
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Key, Resize
from textual.widgets import DataTable, Header, Input, RichLog, Static

from graham.commands import CommandProcessor, discover_universe_names
from graham.graham import GrahamEngine, StockAnalysis, filter_ranked, format_metric
from graham.i18n import DisplayTranslator
from graham.llm import LLMError, ask_model, build_moat_prompt, fallback_explanation
from graham.settings import UserSettings, load_user_settings, save_user_settings


class DetailsPanel(Static):
    can_focus = True


class GrahamApp(App[None]):
    TITLE = "graham"
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
        Binding("ctrl+q", "noop", "", show=False, priority=True),
        Binding("ctrl+d", "focus_details", "Details", show=False, priority=True),
        Binding("ctrl+p", "focus_prompt", "Prompt", show=False, priority=True),
    ]
    CSS = """
    Screen {
        layout: vertical;
    }

    #center {
        height: 1fr;
        min-height: 6;
    }

    #ranking {
        width: 2fr;
        min-height: 6;
        height: 1fr;
        border: round #4c956c;
        overflow: auto;
    }

    #details {
        width: 1fr;
        min-width: 24;
        height: 1fr;
        border: round #bc4749;
        padding: 1 1;
        overflow-y: auto;
    }

    #log {
        height: 1fr;
        min-height: 4;
        border: round #386641;
        overflow: auto;
    }

    #input-wrap {
        height: auto;
        min-height: 3;
        margin-top: 1;
        padding: 0 1;
        border: round #1d3557;
    }

    #prompt {
        width: 100%;
        margin: 0;
    }

    #suggestions {
        display: none;
        max-height: 8;
        overflow-y: auto;
        border: round #6a994e;
    }

    #suggestions.visible {
        display: block;
    }

    #center.narrow {
        layout: vertical;
    }

    #ranking.narrow {
        width: 1fr;
        height: 1fr;
    }

    #details.narrow {
        width: 1fr;
        min-width: 0;
        height: 1fr;
    }

    #log.narrow {
        height: 1fr;
        min-height: 4;
    }
    """
    SORTABLE_COLUMNS = (
        "rank",
        "ticker",
        "company",
        "score",
        "rating",
        "price",
        "as_of",
        "v",
        "mos",
        "pe",
        "pb",
        "dividend",
    )
    SORT_COLUMN_ALIASES = {
        "asof": "as_of",
        "as_of": "as_of",
        "as_of_time": "as_of",
        "price_time": "as_of",
        "company_name": "company",
        "symbol": "ticker",
        "intrinsic": "v",
        "intrinsic_value": "v",
        "value": "v",
        "margin_of_safety": "mos",
        "pe_ratio": "pe",
        "pb_ratio": "pb",
        "dividend_rate": "dividend",
    }

    def __init__(self) -> None:
        super().__init__()
        self.settings: UserSettings = load_user_settings()
        self.engine = GrahamEngine(y=4.4, require_dividend=True)
        startup_language = self.settings.default_language.strip().lower() if self.settings.default_language else "en"
        if not startup_language:
            startup_language = "en"
        self.i18n = DisplayTranslator(language=startup_language)
        self.language = startup_language
        self.model = self.settings.default_model or "none"
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
        self._scan_loading = False
        self._scan_spinner_step = 0
        self._scan_spinner_frames = ["-", "\\", "|", "/"]
        self._scan_spinner_timer = None
        self._details_nav_mode = False
        self._sort_column = "rank"
        self._sort_reverse = False
        self.score_green_min = self.settings.score_green_min
        self.score_orange_min = self.settings.score_orange_min
        self.processor = CommandProcessor(self)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="center"):
            yield DataTable(id="ranking")
            yield DetailsPanel(self.tr("No row selected."), id="details")
        yield RichLog(id="log", markup=False, wrap=True)
        with Vertical(id="input-wrap"):
            yield Input(placeholder=self.tr("Type /help"), id="prompt")
            yield Static("", id="suggestions")

    async def on_mount(self) -> None:
        self._setup_table_columns()
        self._apply_responsive_layout()
        self.query_one("#prompt", Input).focus()

        default_spec = self.settings.default_universe or "sample"
        tickers, note = self.processor.resolve_universe(default_spec)
        if not tickers:
            default_spec = "sample"
            tickers, note = self.processor.resolve_universe(default_spec)
            self.settings.default_universe = default_spec
            self._save_settings()
        self.set_universe(tickers, note)
        self._timer = self.set_interval(self.refresh_seconds, self._schedule_price_refresh)
        self.write_log("Welcome to graham. Type /help")
        self.write_log(f"Default universe: {default_spec}")
        self.write_log("Initial scan started in background...")
        self.call_later(self._start_initial_scan)

    def on_resize(self, event: Resize) -> None:
        self._apply_responsive_layout()

    def _start_initial_scan(self) -> None:
        asyncio.create_task(self._run_initial_scan())

    async def _run_initial_scan(self) -> None:
        try:
            await self.run_scan(top=None, min_score=0.0, refresh=self.refresh_seconds)
        except Exception as exc:
            self.write_log(f"Initial scan error: {exc}")

    def tr(self, text: str) -> str:
        return self.i18n.tr(text)

    def set_language(self, language: str) -> tuple[bool, str]:
        success, message = self.i18n.set_language(language)
        if not success:
            return False, message

        self.language = self.i18n.language
        self.settings.default_language = self.language
        saved, save_error = self._save_settings()
        if not saved:
            return False, f"Language updated but could not persist settings: {save_error}"
        prompt = self.query_one("#prompt", Input)
        prompt.placeholder = self.tr("Type /help")
        self._setup_table_columns()
        self.refresh_table()
        return True, self.tr(message)

    def set_model(self, model: str) -> tuple[bool, str]:
        value = model.strip() or "none"
        self.model = value
        self.settings.default_model = value
        saved, save_error = self._save_settings()
        if not saved:
            return False, f"Model updated but could not persist settings: {save_error}"
        return True, f"Model saved: {value}"

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
        saved, save_error = self._save_settings()
        if not saved:
            return False, f"Thresholds updated but could not persist settings: {save_error}"

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
        saved, save_error = self._save_settings()
        if not saved:
            return False, f"Default universe updated in memory but persistence failed: {save_error}"

        self.set_universe(tickers, note, remember_spec=spec)
        return True, f"Default universe set to: {spec} ({len(tickers)} tickers)"

    def available_universes(self) -> list[str]:
        return discover_universe_names()

    def current_tickers(self) -> list[str]:
        if self._current_results:
            return [item.ticker for item in self._current_results]
        return list(self.engine.universe)

    def set_universe(self, tickers: list[str], note: str, remember_spec: str | None = None) -> None:
        cleaned = self.engine.set_universe(tickers)
        self._universe_note = note
        if remember_spec is not None:
            self.settings.default_universe = remember_spec
            self._save_settings()
        self.write_log(f"Active universe: {len(cleaned)} tickers ({note})")

    async def run_scan(self, top: int | None, min_score: float, refresh: int | None) -> None:
        self.scan_top = top
        self.scan_min_score = min_score
        if refresh is not None:
            self.refresh_seconds = max(3, refresh)
            self._reset_timer()

        self.write_log("Running fundamentals scan...")
        self._set_scan_loading(True)
        try:
            ranked = await asyncio.to_thread(self.engine.scan_fundamentals)
            self._current_results = filter_ranked(ranked, top=self.scan_top, min_score=self.scan_min_score)
            self.refresh_table()

            if not self._current_results:
                self.write_log("No results. Try /scan --min-score 0")
            else:
                self.write_log(f"Scan completed: {len(self._current_results)} results")
        finally:
            self._set_scan_loading(False)

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

    async def moat_ticker(self, ticker: str) -> str:
        if self.model == "none":
            return self.tr("LLM disabled. Set a model first with /model [model-name].")

        symbol = ticker.strip().upper()
        if not symbol:
            return self.tr("Usage: /moat TICKER")

        prompt = build_moat_prompt(symbol)
        try:
            response = await asyncio.to_thread(ask_model, self.model, "", prompt, 60)
        except LLMError as exc:
            self.write_log(f"LLM error: {exc}")
            return self.tr("LLM error while generating moat analysis.")

        self.write_log(f"[LLM {self.model} /moat {symbol}]\n{response}", translate=False)
        return self.tr("LLM moat analysis written to log.")

    def export_results(self, export_format: str) -> str:
        export_dir = Path("exports")
        export_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = export_dir / f"graham_scan_{stamp}.{export_format}"

        payload = [
            {
                "ticker": item.ticker,
                "company_name": item.company_name,
                "score": item.score,
                "price": item.price,
                "price_time": item.price_time,
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
                fieldnames=[
                    "ticker",
                    "company_name",
                    "score",
                    "price",
                    "price_time",
                    "intrinsic_value",
                    "mos",
                    "pe",
                    "pb",
                    "dividend_rate",
                ],
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

    @on(DataTable.HeaderSelected, "#ranking")
    def on_header_selected(self, event: DataTable.HeaderSelected) -> None:
        column_index = self._extract_header_column_index(event)
        if column_index is None:
            return
        column = self._column_id_for_index(column_index)
        if column is None:
            return

        success, message = self.set_sort(column)
        if success:
            self.write_log(message, translate=False)

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
        if self._details_nav_mode:
            if event.key in {"up", "down", "pageup", "pagedown", "home", "end"}:
                self._scroll_details(event.key)
                event.stop()
                return
            if event.key == "escape":
                self.action_focus_prompt()
                event.stop()
                return

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
        self._scroll_suggestion_cursor_into_view()

    def _scroll_suggestion_cursor_into_view(self) -> None:
        if not self._suggestions:
            return

        suggestion_view = self.query_one("#suggestions", Static)
        viewport_height = 1
        try:
            viewport_height = max(1, int(suggestion_view.content_region.height))
        except Exception:
            viewport_height = 1

        try:
            top = int(getattr(suggestion_view, "scroll_y", 0))
        except Exception:
            top = 0

        bottom = top + viewport_height - 1
        target_top = top
        if self._suggestion_index < top:
            target_top = self._suggestion_index
        elif self._suggestion_index > bottom:
            target_top = self._suggestion_index - viewport_height + 1
        else:
            return

        self._scroll_widget_to(suggestion_view, max(0, target_top))

    def _scroll_widget_to(self, widget: Static, y: int) -> None:
        try:
            widget.scroll_to(y=y, animate=False)
            return
        except TypeError:
            try:
                widget.scroll_to(y=y)
                return
            except Exception:
                pass
        except Exception:
            pass

        try:
            current = int(getattr(widget, "scroll_y", 0))
        except Exception:
            current = 0
        delta = y - current
        if delta == 0:
            return
        try:
            widget.scroll_relative(y=delta)
        except Exception:
            return

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
        sorted_results = self._sorted_results()

        for rank, item in enumerate(sorted_results, start=1):
            table.add_row(
                str(rank),
                item.ticker,
                item.company_name or "N/A",
                f"{item.score:.2f}",
                self._score_badge(item.score),
                format_metric(item.price),
                item.price_time or "N/A",
                format_metric(item.intrinsic_value),
                format_metric(item.mos, percentage=True),
                format_metric(item.pe),
                format_metric(item.pb),
                format_metric(item.dividend_rate),
                key=item.ticker,
            )

        if sorted_results:
            first = sorted_results[0]
            self._show_details(first)
        table.refresh(repaint=True, layout=True)
        self.refresh(repaint=True, layout=True)

    def _extract_header_column_index(self, event: DataTable.HeaderSelected) -> int | None:
        index = getattr(event, "column_index", None)
        if isinstance(index, int):
            return index

        coordinate = getattr(event, "coordinate", None)
        if coordinate is not None:
            coord_index = getattr(coordinate, "column", None)
            if isinstance(coord_index, int):
                return coord_index
        return None

    def _column_id_for_index(self, index: int) -> str | None:
        if 0 <= index < len(self.SORTABLE_COLUMNS):
            return self.SORTABLE_COLUMNS[index]
        return None

    def available_sort_columns(self) -> list[str]:
        return list(self.SORTABLE_COLUMNS)

    def get_sort_state(self) -> tuple[str, str]:
        direction = "desc" if self._sort_reverse else "asc"
        return self._sort_column, direction

    def set_sort(self, column: str, direction: str | None = None) -> tuple[bool, str]:
        normalized = self._normalize_sort_column(column)
        if normalized is None:
            choices = ", ".join(self.SORTABLE_COLUMNS)
            return False, f"Unknown sort column: {column}. Use one of: {choices}"

        direction_value = (direction or "").strip().lower()
        if direction_value and direction_value not in {"asc", "desc"}:
            return False, "Sort direction must be 'asc' or 'desc'."

        if direction_value:
            reverse = direction_value == "desc"
        elif self._sort_column == normalized:
            reverse = not self._sort_reverse
        else:
            reverse = False

        self._sort_column = normalized
        self._sort_reverse = reverse
        self.refresh_table()
        final_direction = "desc" if reverse else "asc"
        return True, f"Sorted by {normalized} ({final_direction})."

    def _normalize_sort_column(self, column: str) -> str | None:
        value = column.strip().lower()
        if not value:
            return None
        cleaned = value.replace("-", "_").replace(" ", "_").replace("/", "")
        canonical = self.SORT_COLUMN_ALIASES.get(cleaned, cleaned)
        if canonical in self.SORTABLE_COLUMNS:
            return canonical
        return None

    def _sorted_results(self) -> list[StockAnalysis]:
        results = list(self._current_results)
        if not results:
            return results

        if self._sort_column == "rank":
            if self._sort_reverse:
                results.reverse()
            return results

        present: list[StockAnalysis] = []
        missing: list[StockAnalysis] = []
        for item in results:
            value = self._sort_value(item, self._sort_column)
            if value is None or value == "":
                missing.append(item)
            else:
                present.append(item)

        present.sort(key=lambda item: self._sort_value(item, self._sort_column), reverse=self._sort_reverse)
        return present + missing

    def _sort_value(self, item: StockAnalysis, column: str) -> str | float | None:
        if column == "ticker":
            return item.ticker
        if column == "company":
            return (item.company_name or "").lower()
        if column in {"score", "rating"}:
            return item.score
        if column == "price":
            return item.price
        if column == "as_of":
            return item.price_time or ""
        if column == "v":
            return item.intrinsic_value
        if column == "mos":
            return item.mos
        if column == "pe":
            return item.pe
        if column == "pb":
            return item.pb
        if column == "dividend":
            return item.dividend_rate
        return None

    def _show_details(self, analysis: StockAnalysis) -> None:
        self.selected_ticker = analysis.ticker
        details = self.query_one("#details", Static)

        lines = [
            f"{self.tr('Ticker')}: {analysis.ticker}",
            f"{self.tr('Company')}: {analysis.company_name or 'N/A'}",
            f"{self.tr('Score')}: {analysis.score:.2f}",
            f"{self.tr('Price')}: {format_metric(analysis.price)}",
            f"{self.tr('As of')}: {analysis.price_time or 'N/A'}",
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

    def _save_settings(self) -> tuple[bool, str | None]:
        try:
            save_user_settings(self.settings)
        except Exception as exc:
            return False, str(exc)
        return True, None

    def _set_scan_loading(self, loading: bool) -> None:
        self._scan_loading = loading
        logger = self.query_one("#log", RichLog)
        if not loading:
            if self._scan_spinner_timer is not None:
                try:
                    self._scan_spinner_timer.stop()
                except Exception:
                    pass
                self._scan_spinner_timer = None
            logger.border_title = ""
            return

        self._scan_spinner_step = 0
        if self._scan_spinner_timer is None:
            self._scan_spinner_timer = self.set_interval(0.12, self._tick_scan_spinner)
        self._tick_scan_spinner()

    def _tick_scan_spinner(self) -> None:
        if not self._scan_loading:
            return
        logger = self.query_one("#log", RichLog)
        spinner = self._scan_spinner_frames[self._scan_spinner_step % len(self._scan_spinner_frames)]
        self._scan_spinner_step += 1
        logger.border_title = f"{spinner} {self.tr('Loading tickers...')}"

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
            self.tr("company"),
            self.tr("score"),
            self.tr("rating"),
            self.tr("price"),
            self.tr("as_of"),
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

    def action_noop(self) -> None:
        return

    def action_focus_details(self) -> None:
        self._details_nav_mode = True
        self.query_one("#details", DetailsPanel).focus()
        self.write_log("Details navigation enabled (Esc or Ctrl+P to return to prompt).")

    def action_focus_prompt(self) -> None:
        self._details_nav_mode = False
        self.query_one("#prompt", Input).focus()

    def _scroll_details(self, key: str) -> None:
        details = self.query_one("#details", Static)
        if key == "up":
            self._try_scroll(details, ("scroll_up", "action_scroll_up"), y=-1)
            return
        if key == "down":
            self._try_scroll(details, ("scroll_down", "action_scroll_down"), y=1)
            return
        if key == "pageup":
            self._try_scroll(details, ("scroll_page_up", "action_page_up"), y=-6)
            return
        if key == "pagedown":
            self._try_scroll(details, ("scroll_page_down", "action_page_down"), y=6)
            return
        if key == "home":
            self._try_scroll(details, ("scroll_home", "action_scroll_home"), y=0, home=True)
            return
        if key == "end":
            self._try_scroll(details, ("scroll_end", "action_scroll_end"), y=10**9, end=True)
            return

    def _try_scroll(
        self,
        widget: Static,
        method_names: tuple[str, ...],
        *,
        y: int,
        home: bool = False,
        end: bool = False,
    ) -> None:
        for method_name in method_names:
            method = getattr(widget, method_name, None)
            if not callable(method):
                continue
            try:
                if method_name.startswith("scroll_") and method_name not in {"scroll_up", "scroll_down"}:
                    method(animate=False)
                else:
                    method()
                return
            except TypeError:
                try:
                    method()
                    return
                except Exception:
                    continue
            except Exception:
                continue

        # Fallback for older/newer Textual APIs.
        try:
            if home:
                widget.scroll_to(y=0, animate=False)
                return
            if end:
                widget.scroll_to(y=10**9, animate=False)
                return
            widget.scroll_relative(y=y)
        except Exception:
            return

    def _apply_responsive_layout(self) -> None:
        narrow = self.size.width < 120
        try:
            center = self.query_one("#center", Horizontal)
            ranking = self.query_one("#ranking", DataTable)
            details = self.query_one("#details", Static)
            log = self.query_one("#log", RichLog)
        except Exception:
            return

        for widget in (center, ranking, details, log):
            if narrow:
                widget.add_class("narrow")
            else:
                widget.remove_class("narrow")


def run_tui() -> None:
    app = GrahamApp()
    app.run()
