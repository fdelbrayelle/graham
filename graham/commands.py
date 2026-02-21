from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import io
import json
import os
import re
import shlex
import time
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from graham.i18n import COMMON_LANGUAGE_CODES
from graham.market_data import create_ticker, resolve_market_data_provider

UNIVERSE_PRESETS: dict[str, list[str]] = {
    "sample": ["AAPL", "MSFT", "JNJ", "PG", "KO", "XOM", "PEP", "MMM"],
    "world": ["AAPL", "MSFT", "NVDA", "ASML", "NVO", "SHEL", "TTE", "TM", "SONY", "TSM", "SAP", "BABA"],
    "usa": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "JPM", "JNJ", "PG", "XOM", "PEP", "KO", "HD", "UNH"],
    "emerging_markets": ["TSM", "BABA", "PDD", "MELI", "INFY", "VALE", "NU", "ITUB", "HDB", "NIO", "JD", "BIDU"],
    "china": ["BABA", "JD", "PDD", "BIDU", "TCOM", "NTES", "LI", "XPEV", "NIO", "TME", "BEKE", "BILI"],
    "india": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "ITC.NS", "HINDUNILVR.NS", "LT.NS", "SUNPHARMA.NS", "BHARTIARTL.NS", "MARUTI.NS", "BAJFINANCE.NS"],
    "germany": ["SAP.DE", "SIE.DE", "ALV.DE", "BAS.DE", "BMW.DE", "MBG.DE", "DTE.DE", "MUV2.DE", "IFX.DE", "RWE.DE", "DB1.DE", "VOW3.DE", "DHL.DE", "ADS.DE"],
    "europe": ["ASML", "NVO", "SAP", "SHEL", "TTE", "SNY", "AZN", "UL", "BP", "RHHBY", "NESN.SW", "MC.PA"],
    "france": ["RMS.PA", "MC.PA", "AI.PA", "SU.PA", "TTE.PA", "SAN.PA", "OR.PA", "BNP.PA", "ENGI.PA", "DG.PA", "CAP.PA", "CS.PA", "KER.PA", "VIE.PA"],
    "japan": ["7203.T", "6758.T", "9984.T", "8035.T", "6501.T", "6861.T", "9432.T", "8306.T", "6098.T", "7974.T", "6367.T", "9433.T"],
}
UNIVERSE_PRESET_DESCRIPTIONS: dict[str, str] = {
    "sample": "Sample universe",
    "world": "World large caps and global leaders",
    "usa": "USA large caps",
    "emerging_markets": "Emerging markets mix",
    "china": "China large caps and leading ADRs",
    "india": "India leaders (NSE symbols)",
    "germany": "Germany leaders (DAX style selection)",
    "europe": "Europe large caps",
    "france": "France CAC40 style selection",
    "japan": "Japan large caps",
}
UNIVERSE_ALIASES = {
    "monde": "world",
    "world": "world",
    "usa": "usa",
    "us": "usa",
    "etats-unis": "usa",
    "emerging": "emerging_markets",
    "emerging_markets": "emerging_markets",
    "emerging-markets": "emerging_markets",
    "china": "china",
    "chine": "china",
    "india": "india",
    "inde": "india",
    "germany": "germany",
    "allemagne": "germany",
    "europe": "europe",
    "france": "france",
    "japan": "japan",
    "japon": "japan",
}
INDEX_SPECS: dict[str, dict[str, Any]] = {
    "msci_world": {
        "description": "MSCI World (ETF proxy URTH)",
        "symbols": ["URTH"],
        "aliases": ["world", "msciworld", "msci-world"],
    },
    "msci_acwi": {
        "description": "MSCI ACWI (ETF proxy ACWI)",
        "symbols": ["ACWI"],
        "aliases": ["acwi", "msciacwi", "msci-acwi"],
    },
    "msci_emerging": {
        "description": "MSCI Emerging Markets (ETF proxy EEM/IEMG)",
        "symbols": ["EEM", "IEMG"],
        "aliases": ["emerging", "msciemerging", "msci-emerging"],
    },
    "msci_eafe": {
        "description": "MSCI EAFE (ETF proxy EFA/IEFA)",
        "symbols": ["EFA", "IEFA"],
        "aliases": ["eafe", "msci-eafe", "mscieafe"],
    },
    "msci_europe": {
        "description": "MSCI Europe (ETF proxy VGK/IEUR)",
        "symbols": ["VGK", "IEUR"],
        "aliases": ["msci-europe", "mscieurope"],
    },
    "msci_china": {
        "description": "MSCI China (ETF proxy MCHI)",
        "symbols": ["MCHI"],
        "aliases": ["china", "msci-china", "mscichina"],
    },
    "sp500": {
        "description": "S&P 500",
        "symbols": ["^GSPC", "SPY", "IVV", "VOO"],
        "aliases": ["s&p500", "s&p-500", "spx"],
    },
    "dowjones": {
        "description": "Dow Jones Industrial Average",
        "symbols": ["^DJI", "DIA"],
        "aliases": ["dow", "djia", "dow-jones"],
    },
    "nasdaq100": {
        "description": "NASDAQ-100",
        "symbols": ["^NDX", "QQQ", "QQQM"],
        "aliases": ["nasdaq", "ndx", "nasdaq-100"],
    },
    "russell2000": {
        "description": "Russell 2000",
        "symbols": ["^RUT", "IWM"],
        "aliases": ["russell", "rut", "russell-2000"],
    },
    "russell1000": {
        "description": "Russell 1000",
        "symbols": ["IWB"],
        "aliases": ["russell-1000", "rut1000"],
    },
    "cac40": {
        "description": "CAC 40",
        "symbols": ["^FCHI", "CAC.PA", "EWQ"],
        "aliases": ["cac", "cac-40"],
    },
    "eurostoxx": {
        "description": "Euro Stoxx 50",
        "symbols": ["^STOXX50E", "FEZ"],
        "aliases": ["eurostoxx50", "stoxx50", "stoxx-50"],
    },
    "ftse100": {
        "description": "FTSE 100",
        "symbols": ["^FTSE", "ISF.L", "EWU"],
        "aliases": ["ftse", "ftse-100"],
    },
    "dax40": {
        "description": "DAX 40",
        "symbols": ["^GDAXI", "EXS1.DE", "EWG"],
        "aliases": ["dax", "dax-40"],
    },
    "stoxx600": {
        "description": "STOXX Europe 600 (ETF proxy EXSA.DE/MEUD)",
        "symbols": ["EXSA.DE", "MEUD.DE"],
        "aliases": ["stoxx-600", "europe600", "stoxx_europe_600"],
    },
    "aex25": {
        "description": "AEX 25 (Netherlands)",
        "symbols": ["^AEX", "EWN"],
        "aliases": ["aex", "aex-25"],
    },
    "mib40": {
        "description": "FTSE MIB (Italy)",
        "symbols": ["FTSEMIB.MI", "EWI"],
        "aliases": ["ftsemib", "mib", "mib-40"],
    },
    "nikkei225": {
        "description": "Nikkei 225",
        "symbols": ["^N225", "EWJ"],
        "aliases": ["nikkei", "nikkei-225"],
    },
    "topix": {
        "description": "TOPIX",
        "symbols": ["^TOPX", "TOPIX.JP"],
        "aliases": ["topix-index"],
    },
    "hangseng": {
        "description": "Hang Seng Index",
        "symbols": ["^HSI", "2800.HK"],
        "aliases": ["hsi", "hang-seng"],
    },
    "csi300": {
        "description": "CSI 300 (ETF proxy ASHR)",
        "symbols": ["000300.SS", "ASHR"],
        "aliases": ["csi", "csi-300"],
    },
    "shanghai_comp": {
        "description": "Shanghai Composite",
        "symbols": ["000001.SS", "MCHI"],
        "aliases": ["shanghai", "sse", "shcomp"],
    },
    "sensex": {
        "description": "BSE SENSEX",
        "symbols": ["^BSESN", "INDA"],
        "aliases": ["bse", "bse-sensex"],
    },
    "nifty50": {
        "description": "NIFTY 50",
        "symbols": ["^NSEI", "INDY"],
        "aliases": ["nifty", "nifty-50"],
    },
    "asx200": {
        "description": "S&P/ASX 200",
        "symbols": ["^AXJO", "EWA"],
        "aliases": ["asx", "asx-200"],
    },
    "tsx60": {
        "description": "S&P/TSX 60",
        "symbols": ["^GSPTSE", "XIU.TO"],
        "aliases": ["tsx", "tsx-60"],
    },
    "ibovespa": {
        "description": "Ibovespa",
        "symbols": ["^BVSP", "EWZ"],
        "aliases": ["bovespa", "ibov"],
    },
    "ibex35": {
        "description": "IBEX 35",
        "symbols": ["^IBEX", "EWP"],
        "aliases": ["ibex", "ibex-35"],
    },
    "omx_stockholm30": {
        "description": "OMX Stockholm 30",
        "symbols": ["^OMX", "EWD"],
        "aliases": ["omxs30", "stockholm30", "omx-30"],
    },
    "smi20": {
        "description": "Swiss Market Index",
        "symbols": ["^SSMI", "EWL"],
        "aliases": ["smi", "swiss-market-index"],
    },
    "kospi": {
        "description": "KOSPI",
        "symbols": ["^KS11", "EWY"],
        "aliases": ["kospi-200"],
    },
    "taiex": {
        "description": "TAIEX",
        "symbols": ["^TWII", "EWT"],
        "aliases": ["taiwan", "twii"],
    },
    "mexico_ipc": {
        "description": "S&P/BMV IPC Mexico",
        "symbols": ["^MXX", "EWW"],
        "aliases": ["ipc", "mexico", "mexico-ipc"],
    },
    "south_africa_top40": {
        "description": "South Africa Top 40 (ETF proxy EZA)",
        "symbols": ["EZA"],
        "aliases": ["jse", "jse-top40", "south-africa"],
    },
    "merval": {
        "description": "MERVAL (Argentina)",
        "symbols": ["^MERV"],
        "aliases": ["argentina", "merv"],
    },
}
PROBABLE_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-=/]{0,14}$")
NASDAQ_SYMBOL_RE = re.compile(r"^[A-Z0-9\-]{1,10}$")
NASDAQ_QUOTE_API = "https://api.nasdaq.com/api/quote"
ISHARES_PRODUCT_SCREENER_API = (
    "https://www.ishares.com/us/product-screener/product-screener-v3.1.jsn"
    "?dcrPath=/templatedata/config/product-screener-v3/data/en/us-ishares/"
    "ishares-product-screener-backend-config&siteEntryPassthrough=true"
)
NIKKEI_COMPONENTS_URL = "https://indexes.nikkei.co.jp/en/nkave/index/component?idx=nk225"
TOPIX_CONSTITUENTS_CSV_URL = (
    "https://www.jpx.co.jp/english/markets/indices/topix/tvdivq0000001vg2-att/topixweight_j.csv"
)
MEDIAWIKI_PARSE_API = "https://en.wikipedia.org/w/api.php"
PUBLIC_CONSTITUENT_TARGETS: dict[str, int] = {
    "sp500": 400,
    "nasdaq100": 80,
}
INDEX_WIKIPEDIA_PAGES: dict[str, dict[str, Any]] = {
    "sp500": {
        "page": "List_of_S&P_500_companies",
        "header_keywords": ("symbol", "ticker"),
    },
    "nasdaq100": {
        "page": "Nasdaq-100",
        "header_keywords": ("ticker", "symbol"),
    },
    "dowjones": {
        "page": "Dow_Jones_Industrial_Average",
        "header_keywords": ("symbol", "ticker", "stock symbol"),
    },
    "cac40": {
        "page": "CAC_40",
        "header_keywords": ("ticker", "symbol", "epic"),
        "default_suffix": ".PA",
    },
    "dax40": {
        "page": "DAX",
        "header_keywords": ("ticker", "symbol", "epic"),
        "default_suffix": ".DE",
    },
    "eurostoxx": {
        "page": "EURO_STOXX_50",
        "header_keywords": ("ticker", "symbol", "epic"),
    },
    "nikkei225": {
        "page": "Nikkei_225",
        "header_keywords": ("ticker", "code", "symbol"),
        "default_suffix": ".T",
    },
}


def normalize_universe_spec(spec: str) -> str:
    value = spec.strip()
    if value.startswith("custom:"):
        return value
    return UNIVERSE_ALIASES.get(value.lower(), value.lower())


def universe_search_dirs() -> list[Path]:
    candidates = [
        Path.cwd() / "universes",
        Path.home() / ".graham" / "universes",
        Path(__file__).resolve().parent.parent / "universes",
    ]
    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate.absolute())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def find_universe_file(name: str) -> Path | None:
    filename = f"{name}.txt"
    for base in universe_search_dirs():
        path = base / filename
        if path.exists():
            return path
    return None


class CommandProcessor:
    COMMANDS = [
        "/help",
        "/keys",
        "/universes",
        "/indices",
        "/languages",
        "/lang",
        "/model",
        "/universe",
        "/default-universe",
        "/scan",
        "/sort",
        "/screen",
        "/explain",
        "/moat",
        "/rating",
        "/export",
    ]
    MODELS = [
        "none",
        # OpenAI (official IDs)
        "gpt-5.2",
        "gpt-5.2-codex",
        "gpt-5.1",
        "gpt-5.1-codex",
        "gpt-5.1-codex-max",
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-5-pro",
        "gpt-4.1",
        "gpt-4.1-mini",
        # Anthropic (official IDs/aliases)
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
        "claude-opus-4-5-20251101",
        "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5-20251001",
        # Gemini (official IDs)
        "gemini-3-pro-preview",
        "gemini-3-flash-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash-preview-09-2025",
        "gemini-2.5-flash-lite-preview-09-2025",
    ]
    SCAN_OPTIONS = ["--top", "--min-score", "--refresh"]
    EXPORT_FORMATS = ["csv", "json"]
    SORT_DIRECTIONS = ["asc", "desc"]
    LANGUAGE_CODES = COMMON_LANGUAGE_CODES

    def __init__(self, app: object) -> None:
        self.app = app
        self._ishares_product_url_cache: dict[str, str | None] = {}
        self._ishares_screener_payload: dict[str, Any] | None = None
        self._api_cache_ttl_seconds = 3600
        self._api_cache: dict[str, tuple[float, Any]] = {}
        self._index_cache_ttl_seconds = 900
        self._index_constituents_cache: dict[str, tuple[float, tuple[list[str], str, dict[str, str]]]] = {}

    def suggestions(self, text: str) -> list[str]:
        value = text.strip()
        if not value.startswith("/"):
            return []

        if value == "/":
            return self.COMMANDS

        ends_with_space = text.endswith(" ")
        parts = value.split()
        if not parts:
            return self.COMMANDS

        if len(parts) == 1 and not ends_with_space:
            prefix = parts[0]
            return [command for command in self.COMMANDS if command.startswith(prefix)]

        cmd = parts[0]
        current = "" if ends_with_space else parts[-1]

        if cmd == "/model":
            return [name for name in self.MODELS if name.startswith(current)]

        if cmd == "/lang":
            return [code for code in self.LANGUAGE_CODES if code.startswith(current.lower())]

        if cmd == "/universe":
            base = [
                "sample",
                "world",
                "usa",
                "emerging_markets",
                "china",
                "india",
                "germany",
                "europe",
                "france",
                "japan",
                "custom:./universes/sample.txt",
            ]
            base.extend(self.app.available_universes())
            merged = self._unique_preserve_order(base)
            return [name for name in merged if name.startswith(current)]

        if cmd == "/default-universe":
            base = [
                "sample",
                "world",
                "usa",
                "emerging_markets",
                "china",
                "india",
                "germany",
                "europe",
                "france",
                "japan",
            ]
            base.extend(self.app.available_universes())
            merged = self._unique_preserve_order(base)
            return [name for name in merged if name.startswith(current)]

        if cmd == "/indices":
            base = list(INDEX_SPECS.keys())
            return [name for name in base if name.startswith(current.lower())]

        if cmd == "/export":
            return [fmt for fmt in self.EXPORT_FORMATS if fmt.startswith(current)]

        if cmd == "/scan":
            if current.startswith("--") or ends_with_space:
                return [option for option in self.SCAN_OPTIONS if option.startswith(current)]
            return []

        if cmd == "/sort":
            columns = self._sort_columns()
            if len(parts) == 1 and ends_with_space:
                return columns
            if len(parts) == 2:
                if ends_with_space:
                    return self.SORT_DIRECTIONS
                prefix = parts[1].lower()
                return [name for name in columns if name.startswith(prefix)]
            if len(parts) == 3:
                prefix = "" if ends_with_space else parts[2].lower()
                return [name for name in self.SORT_DIRECTIONS if name.startswith(prefix)]
            return []

        if cmd == "/explain":
            tickers = self.app.current_tickers()
            return [ticker for ticker in tickers if ticker.startswith(current.upper())]

        if cmd == "/moat":
            tickers = self.app.current_tickers()
            return [ticker for ticker in tickers if ticker.startswith(current.upper())]

        return []

    async def execute(self, raw_line: str) -> str:
        line = raw_line.strip()
        if not line:
            return ""

        try:
            parts = shlex.split(line)
        except ValueError as exc:
            return self._t(f"Invalid command: {exc}")

        if not parts:
            return ""

        command = parts[0]
        args = parts[1:]

        if command == "/help":
            return self.help_text()

        if command == "/keys":
            return self.shortcuts_text()

        if command == "/universes":
            return self.list_universes_text()

        if command == "/indices":
            if not args:
                return self.list_indices_text()
            canonical = self._canonical_index_name(args[0])
            if canonical is None:
                return self._t(
                    "Unknown index. Use /indices to list supported options."
                )
            tickers, note, company_overrides = await asyncio.to_thread(self._fetch_index_tickers, canonical)
            if not tickers:
                return self._t(f"Unable to fetch index constituents for {canonical}.")
            remember_spec = self._persist_index_universe(canonical, tickers)
            try:
                self.app.set_universe(
                    tickers,
                    note,
                    remember_spec=remember_spec,
                    company_overrides=company_overrides,
                )
            except TypeError:
                set_overrides = getattr(self.app, "set_company_name_overrides", None)
                if callable(set_overrides):
                    set_overrides(company_overrides)
                self.app.set_universe(tickers, note, remember_spec=remember_spec)
            await self.app.run_scan(
                top=self.app.scan_top,
                min_score=self.app.scan_min_score,
                refresh=self.app.refresh_seconds,
            )
            return self._t(f"Index loaded: {canonical} ({len(tickers)} tickers).")

        if command == "/languages":
            return self.list_languages_text()

        if command == "/lang":
            if not args:
                return self._t(
                    f"Current display language: {self.app.language}. Usage: /lang [language-code]"
                )
            success, message = self.app.set_language(args[0])
            return self._t(message) if not success else message

        if command == "/model":
            if not args:
                return self._t(f"Current model: {self.app.model}. Usage: /model [none|model-name]")
            selected_model = args[0]
            set_model = getattr(self.app, "set_model", None)
            if callable(set_model):
                success, message = set_model(selected_model)
                if not success:
                    return self._t(message)
            else:
                self.app.model = selected_model
            key_hint = self._model_key_hint(self.app.model)
            if key_hint is None:
                return self._t(f"Active model: {self.app.model}")
            return self._t(f"Active model: {self.app.model}. {key_hint}")

        if command == "/universe":
            if not args:
                return self._t(
                    "Usage: /universe [sample|world|usa|emerging_markets|china|india|europe|france|japan|custom:path]"
                )
            tickers, note = self.resolve_universe(args[0])
            if not tickers:
                return self._t(f"Empty universe. {note}")
            set_overrides = getattr(self.app, "set_company_name_overrides", None)
            if callable(set_overrides):
                set_overrides(None)
            self.app.set_universe(tickers, note, remember_spec=normalize_universe_spec(args[0]))
            await self.app.run_scan(
                top=self.app.scan_top,
                min_score=self.app.scan_min_score,
                refresh=self.app.refresh_seconds,
            )
            return self._t(f"Universe loaded: {len(tickers)} tickers ({note})")

        if command == "/scan":
            options = self.parse_scan_options(args)
            if isinstance(options, str):
                return options
            await self.app.run_scan(
                top=options["top"],
                min_score=options["min_score"],
                refresh=options["refresh"],
            )
            return (
                self._t("Scan completed. ")
                + " "
                f"top={options['top'] or 'all'}, min_score={options['min_score']:.2f}, "
                f"refresh={self.app.refresh_seconds}s"
            )

        if command == "/sort":
            if not args:
                get_state = getattr(self.app, "get_sort_state", None)
                if callable(get_state):
                    column, direction = get_state()
                    return self._t(
                        f"Current sort: {column} ({direction}). "
                        "Usage: /sort COLUMN [asc|desc]"
                    )
                return self._t("Usage: /sort COLUMN [asc|desc]")
            if len(args) > 2:
                return self._t("Usage: /sort COLUMN [asc|desc]")
            direction = args[1].lower() if len(args) == 2 else None
            set_sort = getattr(self.app, "set_sort", None)
            if not callable(set_sort):
                return self._t("Sort command not supported by this UI build.")
            success, message = set_sort(args[0], direction)
            return self._t(message) if not success else message

        if command == "/default-universe":
            if not args:
                return self._t(
                    f"Current default universe: {self.app.get_default_universe()}. "
                    "Usage: /default-universe [name|custom:path]"
                )
            success, message = self.app.set_default_universe(args[0])
            if not success:
                return self._t(message)
            await self.app.run_scan(
                top=self.app.scan_top,
                min_score=self.app.scan_min_score,
                refresh=self.app.refresh_seconds,
            )
            return self._t(message)

        if command == "/screen":
            if not args:
                return self._t("Usage: /screen TICKERS_CSV")
            tickers = [item.strip().upper() for item in args[0].split(",") if item.strip()]
            if not tickers:
                return self._t("No valid ticker provided.")
            set_overrides = getattr(self.app, "set_company_name_overrides", None)
            if callable(set_overrides):
                set_overrides(None)
            self.app.set_universe(tickers, "custom csv")
            await self.app.run_scan(top=None, min_score=0.0, refresh=self.app.refresh_seconds)
            return self._t(f"Screen completed on {len(tickers)} tickers.")

        if command == "/explain":
            ticker, question = self._extract_explain_args(args)
            if not ticker:
                return self._t("Select a ticker or use /explain TICKER [question].")
            return await self.app.explain_ticker(ticker, question)

        if command == "/moat":
            if len(args) != 1:
                return self._t("Usage: /moat TICKER")
            return await self.app.moat_ticker(args[0])

        if command == "/export":
            if not args:
                return self._t("Usage: /export [csv|json]")
            export_format = args[0].lower()
            if export_format not in self.EXPORT_FORMATS:
                return self._t("Unsupported format. Use /export [csv|json].")
            output = self.app.export_results(export_format)
            return self._t(f"Export created: {output}")

        if command == "/rating":
            if not args:
                green, orange = self.app.get_rating_thresholds()
                return self._t(
                    f"Rating thresholds: green>={green:.2f}, orange>={orange:.2f}, red<{orange:.2f}. "
                    "Usage: /rating GREEN ORANGE (0..1 or 0..100)"
                )
            if len(args) != 2:
                return self._t("Usage: /rating GREEN ORANGE (0..1 or 0..100)")
            try:
                green = float(args[0])
                orange = float(args[1])
            except ValueError:
                return self._t("Invalid /rating values. Use numbers.")
            success, message = self.app.set_rating_thresholds(green, orange)
            return self._t(message) if not success else message

        return self._t(f"Unknown command: {command}. Type /help")

    def help_text(self) -> str:
        if self.app.model == "none":
            model_note = (
                "Model mode: none (deterministic). Explanations are generated locally from market data.\n"
                "No LLM call is made while model is set to none."
            )
        else:
            model_note = (
                f"Model mode: {self.app.model} (LLM enabled).\n"
                "The app uses market data providers for screening and uses the configured LLM for /explain and /moat.\n"
                "If the LLM call fails, the app falls back to a deterministic local explanation."
            )

        return self._t(
            "Available commands:\n"
            "/help\n"
            "/keys\n"
            "/universes\n"
            "/indices [name]\n"
            "/languages\n"
            "/lang [language-code]\n"
            "/model [none|model-name]\n"
            "/universe [sample|world|usa|emerging_markets|china|india|germany|europe|france|japan|custom:path]\n"
            "/default-universe [name|custom:path]\n"
            "/scan [--top N] [--min-score N] [--refresh SECONDS]\n"
            "/sort COLUMN [asc|desc]\n"
            "/screen TICKERS_CSV\n"
            "/explain [TICKER] [question]\n"
            "/moat TICKER\n"
            "/rating GREEN ORANGE\n"
            "/export [csv|json]\n"
            "Examples: /indices sp500, /indices msci_world, /indices dax40, /indices nikkei225\n\n"
            + model_note
        )

    def shortcuts_text(self) -> str:
        return self._t(
            "Keyboard shortcuts:\n"
            "F1: show this shortcuts list\n"
            "Ctrl+L: clear output log panel\n"
            "Ctrl+R: search ticker/company in the top table\n"
            "Ctrl+D: focus details panel\n"
            "Ctrl+P: focus prompt\n"
            "Up/Down: navigate suggestions or prompt history\n"
            "Tab: autocomplete suggestion\n"
            "Enter: submit prompt or command"
        )

    def list_universes_text(self) -> str:
        default_universe_raw = str(getattr(self.app, "get_default_universe", lambda: "sample")())
        default_universe = UNIVERSE_ALIASES.get(
            default_universe_raw.strip().lower(), default_universe_raw.strip().lower()
        )

        names = discover_universe_names()
        if not names:
            return self._t("No universes found.")

        lines = [self._t("Available universes:")]
        for name in names:
            path = find_universe_file(name)
            if path is not None:
                description, count = self._read_universe_metadata(path)
            else:
                description = UNIVERSE_PRESET_DESCRIPTIONS.get(name, "No description")
                count = len(UNIVERSE_PRESETS.get(name, []))
            marker = "★" if name == default_universe else " "
            lines.append(f"{marker} {name:<18} ({count:>3} tickers) - {self._t(description)}")

        lines.append("")
        lines.append(self._t("Use /universe <name> to load now."))
        lines.append(self._t("Use /default-universe <name> to persist your default."))
        return "\n".join(lines)

    def list_indices_text(self) -> str:
        lines = [self._t("Supported indices (fetched dynamically via market data providers):")]
        for name, payload in INDEX_SPECS.items():
            description = str(payload.get("description", name))
            lines.append(f"- {name}: {self._t(description)}")
        lines.append("")
        lines.append(self._t("Use /indices <name> to load all detected constituents."))
        return "\n".join(lines)

    def list_languages_text(self) -> str:
        current = str(getattr(self.app, "language", "en")).strip().lower() or "en"
        lines = [self._t("Available display languages:")]
        for code in self.LANGUAGE_CODES:
            marker = "★" if code == current else " "
            lines.append(f"{marker} {code}")
        lines.append("")
        lines.append(self._t("Use /lang <code> to change and persist your display language."))
        return "\n".join(lines)

    def parse_scan_options(self, args: list[str]) -> dict[str, float | int | None] | str:
        top: int | None = None
        min_score = 0.0
        refresh: int | None = None

        index = 0
        while index < len(args):
            token = args[index]

            if token == "--top":
                if index + 1 >= len(args):
                    return self._t("Option --top expects a numeric value.")
                try:
                    top = int(args[index + 1])
                except ValueError:
                    return self._t("Invalid --top value.")
                index += 2
                continue

            if token == "--min-score":
                if index + 1 >= len(args):
                    return self._t("Option --min-score expects a numeric value.")
                try:
                    min_score = float(args[index + 1])
                except ValueError:
                    return self._t("Invalid --min-score value.")
                min_score = max(0.0, min(1.0, min_score))
                index += 2
                continue

            if token == "--refresh":
                if index + 1 >= len(args):
                    return self._t("Option --refresh expects a numeric value.")
                try:
                    refresh = int(args[index + 1])
                except ValueError:
                    return self._t("Invalid --refresh value.")
                refresh = max(3, refresh)
                index += 2
                continue

            return self._t(f"Unknown option: {token}")

        return {"top": top, "min_score": min_score, "refresh": refresh}

    def resolve_universe(self, spec: str) -> tuple[list[str], str]:
        normalized = normalize_universe_spec(spec)

        if normalized.startswith("custom:"):
            custom_path = normalized.split(":", 1)[1]
            return self._read_universe_file(Path(custom_path)), f"custom:{custom_path}"

        universe_file = find_universe_file(normalized)
        if universe_file is not None:
            return self._read_universe_file(universe_file), normalized

        preset = UNIVERSE_PRESETS.get(normalized)
        if preset is not None:
            return preset, f"{normalized} (builtin preset)"

        return [], self._t(f"File universes/{normalized}.txt not found")

    def _read_universe_file(self, path: Path) -> list[str]:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []

        values: list[str] = []
        for line in lines:
            item = line.strip()
            if not item or item.startswith("#"):
                continue
            values.append(item.upper())
        return values

    def _extract_explain_args(self, args: list[str]) -> tuple[str | None, str]:
        if not args:
            return self.app.selected_ticker, ""

        maybe_ticker = args[0].upper()
        known = set(self.app.current_tickers())

        if maybe_ticker in known:
            return maybe_ticker, " ".join(args[1:])

        if self.app.selected_ticker:
            return self.app.selected_ticker, " ".join(args)

        return maybe_ticker, " ".join(args[1:])

    def _t(self, text: str) -> str:
        translator = getattr(self.app, "tr", None)
        if callable(translator):
            return str(translator(text))
        return text

    def _read_universe_metadata(self, path: Path) -> tuple[str, int]:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return "No description", 0

        description = "No description"
        count = 0
        for line in lines:
            item = line.strip()
            if not item:
                continue
            if item.startswith("#"):
                if description == "No description":
                    description = item.lstrip("#").strip() or description
                continue
            count += 1
        return description, count

    def _model_key_hint(self, model: str) -> str | None:
        value = model.strip().lower()
        if not value or value == "none":
            return None

        if value.startswith("gpt-") or value.startswith("o"):
            return self._env_hint("OPENAI_API_KEY")
        if value.startswith("claude-"):
            return self._env_hint("ANTHROPIC_API_KEY")
        if value.startswith("gemini-"):
            return self._gemini_env_hint()
        return self._t(
            "Custom model ID: if auto-detection fails, use explicit provider/model (for example openai/gpt-5)."
        )

    def _env_hint(self, env_key: str) -> str:
        if os.getenv(env_key):
            return self._t(f"{env_key} detected.")
        return self._t(f"{env_key} is missing. Export it before using this model.")

    def _gemini_env_hint(self) -> str:
        if os.getenv("GOOGLE_API_KEY"):
            return self._t("GOOGLE_API_KEY detected.")
        if os.getenv("GEMINI_API_KEY"):
            return self._t("GEMINI_API_KEY detected.")
        return self._t("GEMINI_API_KEY or GOOGLE_API_KEY is missing. Export one before using this model.")

    def _unique_preserve_order(self, items: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    def _sort_columns(self) -> list[str]:
        getter = getattr(self.app, "available_sort_columns", None)
        if callable(getter):
            try:
                values = [str(item) for item in getter()]
            except Exception:
                values = []
            if values:
                return values
        return [
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
        ]

    def _canonical_index_name(self, raw_name: str) -> str | None:
        value = raw_name.strip().lower()
        if value in INDEX_SPECS:
            return value
        for name, payload in INDEX_SPECS.items():
            aliases = payload.get("aliases", [])
            if value in aliases:
                return name
        return None

    def _fetch_index_tickers(self, index_name: str) -> tuple[list[str], str, dict[str, str]]:
        cached = self._index_cache_get(index_name)
        if cached is not None:
            return cached

        spec = INDEX_SPECS[index_name]
        symbols = [str(item).strip() for item in spec.get("symbols", []) if str(item).strip()]
        provider = resolve_market_data_provider()
        found: list[str] = []
        found_set: set[str] = set()
        company_overrides: dict[str, str] = {}
        source_notes: list[str] = []

        public_values, public_note, public_names = self._fetch_public_index_constituents(index_name)
        if public_values:
            source_notes.append(public_note)
        for ticker, company in public_names.items():
            if ticker and company:
                company_overrides[ticker] = company
        for item in public_values:
            normalized = self._normalize_ticker(item)
            if normalized and normalized not in found_set:
                found_set.add(normalized)
                found.append(normalized)
        target = PUBLIC_CONSTITUENT_TARGETS.get(index_name)
        if target is not None and public_note and len(found) >= target:
            note = f"index:{index_name} ({public_note})"
            self._index_cache_set(index_name, found, note, company_overrides)
            return found, note, company_overrides

        def _fetch_symbol_sources(symbol: str) -> tuple[str, list[str], list[str]]:
            values: list[str] = []
            notes: list[str] = []

            if index_name.startswith("msci_"):
                ishares_values = self._fetch_ishares_holdings(symbol)
                if ishares_values:
                    notes.append(f"ishares:{symbol}")
                    values.extend(ishares_values)

            nasdaq_values = self._fetch_nasdaq_constituents(symbol)
            if nasdaq_values:
                notes.append(f"nasdaq:{symbol}")
                values.extend(nasdaq_values)

            try:
                ticker_obj, source = create_ticker(symbol, provider=provider, yfinance_fallback=True)
            except Exception:
                return symbol, values, notes
            notes.append(f"{source}:{symbol}")

            extracted = self._extract_tickers_from_any(getattr(ticker_obj, "constituents", None))
            if not extracted:
                extracted = self._extract_tickers_from_funds_data(ticker_obj)
            if extracted:
                notes.append(f"yfinance:{symbol}")
                values.extend(extracted)
            return symbol, values, notes

        per_symbol: dict[str, tuple[list[str], list[str]]] = {}
        if symbols:
            max_workers = min(6, max(1, len(symbols)))
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                future_map = {pool.submit(_fetch_symbol_sources, symbol): symbol for symbol in symbols}
                for future in as_completed(future_map):
                    symbol = future_map[future]
                    try:
                        _, values, notes = future.result()
                    except Exception:
                        values, notes = [], []
                    per_symbol[symbol] = (values, notes)

        for symbol in symbols:
            values, notes = per_symbol.get(symbol, ([], []))
            source_notes.extend(notes)
            for item in values:
                normalized = self._normalize_ticker(item)
                if normalized and normalized not in found_set:
                    found_set.add(normalized)
                    found.append(normalized)

        note = f"index:{index_name}"
        if source_notes:
            note = f"{note} ({', '.join(source_notes)})"
        self._index_cache_set(index_name, found, note, company_overrides)
        return found, note, company_overrides

    def _fetch_public_index_constituents(self, index_name: str) -> tuple[list[str], str, dict[str, str]]:
        if index_name == "nikkei225":
            values, names = self._fetch_nikkei_components_with_names()
            if values:
                return values, "nikkei:nk225", names
            values, names = self._fetch_wikipedia_components_with_names(index_name)
            if values:
                return values, "wikipedia:nikkei225", names
            return [], "", {}

        if index_name == "topix":
            values, names = self._fetch_topix_components_with_names()
            if values:
                return values, "jpx:topix", names
            return [], "", {}

        if index_name in {"sp500", "nasdaq100", "cac40", "dax40", "dowjones", "eurostoxx"}:
            values, names = self._fetch_wikipedia_components_with_names(index_name)
            if values:
                return values, f"wikipedia:{index_name}", names
        return [], "", {}

    def _fetch_nikkei_components_with_names(self) -> tuple[list[str], dict[str, str]]:
        text = self._load_text(
            NIKKEI_COMPONENTS_URL,
            headers=self._http_headers(referer="https://indexes.nikkei.co.jp/en"),
        )
        if not text:
            return [], {}

        row_matches = re.findall(
            r"<td[^>]*>\s*([1-9]\d{3})\s*</td>.*?<a[^>]*>(.*?)</a>",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if len(row_matches) < 180:
            codes = re.findall(r"<td[^>]*>\s*([1-9]\d{3})\s*</td>", text, flags=re.IGNORECASE)
            rows = [(code, "") for code in codes]
        else:
            rows = row_matches

        found: list[str] = []
        names: dict[str, str] = {}
        seen: set[str] = set()
        for code, company_raw in rows:
            ticker = f"{code}.T"
            normalized = self._normalize_ticker(ticker)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            found.append(normalized)
            company_name = self._clean_company_name(company_raw)
            if company_name:
                names[normalized] = company_name
        return found, names

    def _fetch_nikkei_components(self) -> list[str]:
        values, _ = self._fetch_nikkei_components_with_names()
        return values

    def _fetch_topix_components_with_names(self) -> tuple[list[str], dict[str, str]]:
        text = self._load_text(
            TOPIX_CONSTITUENTS_CSV_URL,
            headers=self._http_headers(referer="https://www.jpx.co.jp/english/"),
        )
        return self._extract_tokyo_constituents_from_csv_text(text)

    def _fetch_topix_components(self) -> list[str]:
        values, _ = self._fetch_topix_components_with_names()
        return values

    def _fetch_wikipedia_components_with_names(self, index_name: str) -> tuple[list[str], dict[str, str]]:
        payload = INDEX_WIKIPEDIA_PAGES.get(index_name)
        if payload is None:
            return [], {}
        page = str(payload.get("page", "")).strip()
        if not page:
            return [], {}
        params = urlencode(
            {
                "action": "parse",
                "format": "json",
                "formatversion": 2,
                "prop": "text",
                "page": page,
            }
        )
        url = f"{MEDIAWIKI_PARSE_API}?{params}"
        data = self._load_json(url, headers=self._http_headers(referer="https://en.wikipedia.org/"))
        parse_node = data.get("parse")
        if not isinstance(parse_node, dict):
            return [], {}
        html = parse_node.get("text")
        if not isinstance(html, str):
            return [], {}
        return self._extract_wikipedia_constituents_from_html(index_name, html)

    def _fetch_wikipedia_components(self, index_name: str) -> list[str]:
        values, _ = self._fetch_wikipedia_components_with_names(index_name)
        return values

    def _extract_tokyo_tickers_from_csv_text(self, text: str) -> list[str]:
        values, _ = self._extract_tokyo_constituents_from_csv_text(text)
        return values

    def _extract_tokyo_constituents_from_csv_text(self, text: str) -> tuple[list[str], dict[str, str]]:
        if not text.strip():
            return [], {}
        try:
            rows = list(csv.reader(io.StringIO(text)))
        except Exception:
            return [], {}
        if len(rows) < 2:
            return [], {}

        code_col = self._find_probable_stock_code_column(rows)
        if code_col is None:
            return [], {}
        name_col = self._find_probable_name_column(rows, exclude=code_col)

        found: list[str] = []
        names: dict[str, str] = {}
        seen: set[str] = set()
        for row in rows[1:]:
            if code_col >= len(row):
                continue
            raw = row[code_col].strip().strip('"')
            match = re.search(r"\b([1-9]\d{3})\b", raw)
            if match is None:
                continue
            ticker = f"{match.group(1)}.T"
            normalized = self._normalize_ticker(ticker)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            found.append(normalized)
            if name_col is not None and name_col < len(row):
                company_name = self._clean_company_name(row[name_col])
                if company_name:
                    names[normalized] = company_name
        return found, names

    def _find_probable_stock_code_column(self, rows: list[list[str]]) -> int | None:
        header = rows[0]
        cleaned_headers = [self._normalized_header_value(item) for item in header]
        for idx, value in enumerate(cleaned_headers):
            if any(token in value for token in ("code", "ticker", "symbol")):
                return idx

        width = max((len(row) for row in rows), default=0)
        if width <= 0:
            return None

        best_index: int | None = None
        best_count = 0
        for col in range(width):
            count = 0
            sample_size = 0
            for row in rows[1:301]:
                if col >= len(row):
                    continue
                sample_size += 1
                raw = row[col].strip().strip('"')
                if re.fullmatch(r"[1-9]\d{3}", raw):
                    count += 1
            if sample_size == 0:
                continue
            if count > best_count:
                best_count = count
                best_index = col

        if best_count < 20:
            return None
        return best_index

    def _normalized_header_value(self, value: str) -> str:
        cleaned = value.strip().strip('"').lower()
        return cleaned.replace("_", " ").replace("-", " ")

    def _find_probable_name_column(self, rows: list[list[str]], exclude: int | None = None) -> int | None:
        if not rows:
            return None
        header = rows[0]
        cleaned_headers = [self._normalized_header_value(item) for item in header]
        for idx, value in enumerate(cleaned_headers):
            if idx == exclude:
                continue
            if any(token in value for token in ("company", "name", "constituent", "security", "issue")):
                return idx
        return None

    def _clean_company_name(self, value: str) -> str:
        cleaned = self._clean_html_cell(value)
        if not cleaned:
            return ""
        if cleaned.upper() in {"N/A", "NA", "-"}:
            return ""
        return cleaned

    def _extract_wikipedia_tickers_from_html(self, index_name: str, html: str) -> list[str]:
        values, _ = self._extract_wikipedia_constituents_from_html(index_name, html)
        return values

    def _extract_wikipedia_constituents_from_html(
        self,
        index_name: str,
        html: str,
    ) -> tuple[list[str], dict[str, str]]:
        spec = INDEX_WIKIPEDIA_PAGES.get(index_name)
        if spec is None:
            return [], {}
        keywords = tuple(str(item).lower() for item in spec.get("header_keywords", ()))
        suffix = str(spec.get("default_suffix", "")).strip().upper()

        tables = self._extract_wikitable_rows(html)
        found: list[str] = []
        names: dict[str, str] = {}
        seen: set[str] = set()

        for table_rows in tables:
            if len(table_rows) < 2:
                continue
            header = [self._normalized_header_value(cell) for cell in table_rows[0]]
            target_columns = [
                idx
                for idx, item in enumerate(header)
                if keywords and any(keyword in item for keyword in keywords)
            ]
            if not target_columns:
                continue
            company_columns = [
                idx
                for idx, item in enumerate(header)
                if any(token in item for token in ("company", "name", "constituent", "security"))
            ]

            for row in table_rows[1:]:
                company_name = ""
                for col in company_columns:
                    if col < len(row):
                        company_name = self._clean_company_name(row[col])
                        if company_name:
                            break
                for col in target_columns:
                    if col >= len(row):
                        continue
                    for token in self._extract_candidate_tickers(row[col]):
                        normalized = self._normalize_index_specific_ticker(index_name, token, suffix)
                        if not normalized or normalized in seen:
                            continue
                        seen.add(normalized)
                        found.append(normalized)
                        if company_name:
                            names[normalized] = company_name
        return found, names

    def _extract_wikitable_rows(self, html: str) -> list[list[list[str]]]:
        tables: list[list[list[str]]] = []
        table_matches = re.findall(
            r"<table(?=[^>]*wikitable)[^>]*>(.*?)</table>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        for table_html in table_matches:
            rows: list[list[str]] = []
            row_matches = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.IGNORECASE | re.DOTALL)
            for row_html in row_matches:
                cells = re.findall(
                    r"<t[hd][^>]*>(.*?)</t[hd]>",
                    row_html,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                if not cells:
                    continue
                rows.append([self._clean_html_cell(cell) for cell in cells])
            if rows:
                tables.append(rows)
        return tables

    def _clean_html_cell(self, value: str) -> str:
        text = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
        text = re.sub(r"</p>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        text = re.sub(r"\[[^\]]+\]", " ", text)
        return " ".join(text.split())

    def _extract_candidate_tickers(self, value: str) -> list[str]:
        if not value:
            return []
        tokens = re.findall(r"\b[A-Z0-9][A-Z0-9.\-]{0,14}\b", value.upper())
        cleaned: list[str] = []
        for token in tokens:
            if token in {"USD", "EUR", "ISIN", "CUSIP", "SEDOL"}:
                continue
            cleaned.append(token)
        return cleaned

    def _normalize_index_specific_ticker(self, index_name: str, token: str, suffix: str) -> str:
        value = token.strip().upper()
        if not value:
            return ""
        if index_name in {"nikkei225", "topix"} and re.fullmatch(r"[1-9]\d{3}", value):
            value = f"{value}.T"
        elif suffix and "." not in value and re.fullmatch(r"[A-Z0-9\-]{1,8}", value):
            value = f"{value}{suffix}"

        normalized = self._normalize_ticker(value)
        if not normalized:
            return ""

        if index_name == "dowjones":
            if "." in normalized:
                return ""
        if index_name == "eurostoxx":
            if "." not in normalized:
                return ""
        return normalized

    def _fetch_nasdaq_constituents(self, symbol: str) -> list[str]:
        clean_symbol = symbol.strip().upper()
        if not clean_symbol:
            return []
        if not self._is_nasdaq_symbol_candidate(clean_symbol):
            return []

        if clean_symbol.startswith("^"):
            asset_classes = ("index", "stocks", "etf")
        else:
            asset_classes = ("etf", "stocks", "index")

        for asset_class in asset_classes:
            values = self._fetch_nasdaq_rows(clean_symbol, "holdings", asset_class)
            if values:
                return values

        for asset_class in asset_classes:
            values = self._fetch_nasdaq_rows(clean_symbol, "components", asset_class)
            if values:
                return values
        return []

    def _fetch_ishares_holdings(self, symbol: str) -> list[str]:
        clean_symbol = symbol.strip().upper()
        if not clean_symbol:
            return []
        if not self._is_ishares_symbol_candidate(clean_symbol):
            return []

        product_url = self._resolve_ishares_product_url(clean_symbol)
        if not product_url:
            return []

        holdings_url = (
            f"{product_url.rstrip('/')}/1467271812596.ajax"
            f"?fileType=csv&fileName={clean_symbol}_holdings&dataType=fund"
        )
        text = self._load_text(holdings_url, headers=self._http_headers(referer=product_url))
        if not text:
            return []
        return self._extract_tickers_from_csv_text(text)

    def _resolve_ishares_product_url(self, symbol: str) -> str | None:
        if symbol in self._ishares_product_url_cache:
            return self._ishares_product_url_cache[symbol]

        payload = self._load_ishares_screener_payload()
        if not payload:
            self._ishares_product_url_cache[symbol] = None
            return None

        url = self._find_ishares_product_url(payload, symbol)
        self._ishares_product_url_cache[symbol] = url
        return url

    def _load_ishares_screener_payload(self) -> dict[str, Any]:
        if self._ishares_screener_payload is not None:
            return self._ishares_screener_payload

        headers = self._http_headers(referer="https://www.ishares.com/us")
        payload = self._load_json(ISHARES_PRODUCT_SCREENER_API, headers=headers)
        if payload:
            self._ishares_screener_payload = payload
            return payload
        self._ishares_screener_payload = {}
        return {}

    def _find_ishares_product_url(self, payload: dict[str, Any], symbol: str) -> str | None:
        ticker_keys = (
            "ticker",
            "localExchangeTicker",
            "fundTicker",
            "symbol",
            "exchangeTicker",
            "displayTicker",
        )
        url_keys = (
            "productPageUrl",
            "productUrl",
            "fundUrl",
            "url",
            "path",
            "detailsPath",
        )

        stack: list[Any] = [payload]
        seen: set[int] = set()

        while stack:
            node = stack.pop()
            node_id = id(node)
            if node_id in seen:
                continue
            seen.add(node_id)

            if isinstance(node, dict):
                if self._matches_symbol(node, ticker_keys, symbol):
                    for key in url_keys:
                        value = node.get(key)
                        normalized_url = self._normalize_ishares_url(value)
                        if normalized_url:
                            return normalized_url
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
                continue

            if isinstance(node, list):
                stack.extend(node)
        return None

    def _matches_symbol(self, payload: dict[str, Any], keys: tuple[str, ...], target: str) -> bool:
        target_upper = target.strip().upper()
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip().upper() == target_upper:
                return True
        return False

    def _normalize_ishares_url(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        if "/products/" not in text:
            return None
        if text.startswith("/"):
            text = f"https://www.ishares.com{text}"
        if not text.startswith("http"):
            return None
        return text.split("?", 1)[0].split("#", 1)[0]

    def _extract_tickers_from_csv_text(self, text: str) -> list[str]:
        if not text.strip():
            return []
        try:
            rows = list(csv.reader(io.StringIO(text)))
        except Exception:
            return []
        if not rows:
            return []

        header_index = -1
        symbol_column = -1
        expected = {
            "ticker",
            "symbol",
            "holding ticker",
            "holding symbol",
            "issuer ticker",
        }
        for index, row in enumerate(rows):
            normalized_headers = [item.strip().strip('"').lower() for item in row]
            for col_index, header in enumerate(normalized_headers):
                if header in expected:
                    header_index = index
                    symbol_column = col_index
                    break
            if header_index >= 0:
                break
        if header_index < 0 or symbol_column < 0:
            return []

        found: list[str] = []
        seen: set[str] = set()
        for row in rows[header_index + 1 :]:
            if symbol_column >= len(row):
                continue
            raw = row[symbol_column].strip().strip('"')
            normalized = self._normalize_ticker(raw)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            found.append(normalized)
        return found

    def _fetch_nasdaq_rows(self, symbol: str, endpoint: str, asset_class: str) -> list[str]:
        encoded_symbol = quote(symbol, safe="")
        headers = self._http_headers(referer="https://www.nasdaq.com/")

        out: list[str] = []
        seen: set[str] = set()
        limit = 250
        offset = 0

        for _ in range(20):
            params = urlencode(
                {
                    "assetclass": asset_class,
                    "limit": limit,
                    "offset": offset,
                }
            )
            url = f"{NASDAQ_QUOTE_API}/{encoded_symbol}/{endpoint}?{params}"
            payload = self._load_json(url, headers=headers)
            if not payload:
                break
            rows, total = self._nasdaq_rows_and_total(payload)
            if not rows:
                break

            before = len(seen)
            for row in rows:
                ticker = self._extract_symbol_from_nasdaq_row(row)
                normalized = self._normalize_ticker(ticker)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                out.append(normalized)

            if len(seen) == before:
                break
            if total is not None and len(seen) >= total:
                break
            if len(rows) < limit:
                break
            offset += limit
        return out

    def _api_cache_key(self, kind: str, url: str, headers: dict[str, str]) -> str:
        items = tuple(sorted((str(key).lower(), str(value)) for key, value in headers.items()))
        return f"{kind}|{url}|{items!r}"

    def _index_cache_get(self, index_name: str) -> tuple[list[str], str, dict[str, str]] | None:
        entry = self._index_constituents_cache.get(index_name)
        if entry is None:
            return None
        expires_at, payload = entry
        if time.time() >= expires_at:
            self._index_constituents_cache.pop(index_name, None)
            return None
        tickers, note, overrides = payload
        return list(tickers), note, dict(overrides)

    def _index_cache_set(self, index_name: str, tickers: list[str], note: str, overrides: dict[str, str]) -> None:
        payload = (list(tickers), note, dict(overrides))
        self._index_constituents_cache[index_name] = (
            time.time() + float(self._index_cache_ttl_seconds),
            payload,
        )

    def _api_cache_get(self, key: str) -> Any:
        entry = self._api_cache.get(key)
        if entry is None:
            return None
        expires_at, payload = entry
        if time.time() >= expires_at:
            self._api_cache.pop(key, None)
            return None
        return payload

    def _api_cache_set(self, key: str, payload: Any) -> None:
        self._api_cache[key] = (time.time() + float(self._api_cache_ttl_seconds), payload)

    def _http_get_bytes(self, url: str, headers: dict[str, str], timeout: int) -> bytes:
        request = Request(url, headers=headers)
        with urlopen(request, timeout=timeout) as response:
            return response.read()

    def _load_json(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        cache_key = self._api_cache_key("json", url, headers)
        cached = self._api_cache_get(cache_key)
        if isinstance(cached, dict):
            return cached
        try:
            raw = self._http_get_bytes(url, headers=headers, timeout=4)
        except (URLError, TimeoutError, OSError):
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return {}
        if isinstance(payload, dict):
            if payload:
                self._api_cache_set(cache_key, payload)
            return payload
        return {}

    def _load_text(self, url: str, headers: dict[str, str]) -> str:
        cache_key = self._api_cache_key("text", url, headers)
        cached = self._api_cache_get(cache_key)
        if isinstance(cached, str):
            return cached
        try:
            raw = self._http_get_bytes(url, headers=headers, timeout=5)
        except (URLError, TimeoutError, OSError):
            return ""
        try:
            text = raw.decode("utf-8", errors="ignore")
        except Exception:
            return ""
        if text:
            self._api_cache_set(cache_key, text)
        return text

    def _http_headers(self, referer: str) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": referer,
        }

    def _nasdaq_rows_and_total(self, payload: dict[str, Any]) -> tuple[list[Any], int | None]:
        data = payload.get("data")
        if not isinstance(data, dict):
            return [], None

        candidate_nodes: list[Any] = [data]
        for key in ("holdings", "components", "constituents", "participants"):
            value = data.get(key)
            if value is not None:
                candidate_nodes.append(value)

        for node in candidate_nodes:
            rows, total = self._rows_and_total_from_node(node)
            if rows:
                return rows, total
        return [], None

    def _rows_and_total_from_node(self, node: Any) -> tuple[list[Any], int | None]:
        if isinstance(node, list):
            return node, None
        if not isinstance(node, dict):
            return [], None

        rows = node.get("rows")
        if not isinstance(rows, list):
            return [], None

        total = self._parse_optional_int(
            node.get("totalRecords")
            or node.get("totalrecords")
            or node.get("total")
            or node.get("count")
        )
        return rows, total

    def _parse_optional_int(self, value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            cleaned = value.replace(",", "").strip()
            if cleaned.isdigit():
                return int(cleaned)
        return None

    def _extract_symbol_from_nasdaq_row(self, row: Any) -> str:
        if isinstance(row, str):
            return row
        if not isinstance(row, dict):
            return ""

        keys = (
            "symbol",
            "ticker",
            "holdingSymbol",
            "securitySymbol",
            "holdingTicker",
            "code",
        )
        for key in keys:
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""

    def _is_nasdaq_symbol_candidate(self, symbol: str) -> bool:
        if symbol.startswith("^"):
            return True
        if NASDAQ_SYMBOL_RE.match(symbol):
            return True
        if "." not in symbol:
            return False
        root, suffix = symbol.rsplit(".", 1)
        if not root or not suffix:
            return False
        # Allow US share-class notation (BRK.B, BF.B).
        return bool(root.isalpha() and len(suffix) == 1 and suffix.isalpha())

    def _is_ishares_symbol_candidate(self, symbol: str) -> bool:
        if not symbol:
            return False
        if symbol.startswith("^"):
            return False
        return bool(re.fullmatch(r"[A-Z0-9.\-]{1,12}", symbol))

    def _normalize_ticker(self, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            return ""
        if "." in normalized:
            root, suffix = normalized.rsplit(".", 1)
            if root and len(suffix) == 1 and root.isalpha():
                normalized = f"{root}-{suffix}"
        if not self._is_probable_ticker(normalized):
            return ""
        return normalized

    def _extract_tickers_from_funds_data(self, ticker_obj: Any) -> list[str]:
        values: list[str] = []
        try:
            funds_data = getattr(ticker_obj, "funds_data", None)
            if funds_data is None:
                getter = getattr(ticker_obj, "get_funds_data", None)
                if callable(getter):
                    funds_data = getter()
            if funds_data is None:
                return values
            for attr in ("equity_holdings", "top_holdings", "bond_holdings", "holdings"):
                data = getattr(funds_data, attr, None)
                values.extend(self._extract_tickers_from_any(data))
        except Exception:
            return values
        return values

    def _extract_tickers_from_any(self, data: Any, depth: int = 0) -> list[str]:
        if data is None or depth > 3:
            return []

        values: list[str] = []
        if isinstance(data, str):
            maybe = data.strip().upper()
            if self._is_probable_ticker(maybe):
                return [maybe]
            return []

        if isinstance(data, dict):
            for value in data.values():
                values.extend(self._extract_tickers_from_any(value, depth + 1))
            if values:
                return values

            # Fallback for maps like {"AAPL": 0.07, ...} where keys are tickers.
            keys: list[str] = []
            for key in data.keys():
                key_text = str(key).strip().upper()
                if self._is_probable_ticker(key_text):
                    keys.append(key_text)
            if len(keys) >= 3:
                return keys
            return values

        if isinstance(data, (list, tuple, set)):
            for item in data:
                values.extend(self._extract_tickers_from_any(item, depth + 1))
            return values

        columns = getattr(data, "columns", None)
        index = getattr(data, "index", None)
        if columns is not None and index is not None:
            try:
                frame = data
                candidate_cols = [
                    column
                    for column in frame.columns
                    if str(column).strip().lower() in {"symbol", "ticker", "holding", "code"}
                ]
                if candidate_cols:
                    for column in candidate_cols:
                        for item in frame[column].tolist():
                            values.extend(self._extract_tickers_from_any(item, depth + 1))
                if not values:
                    for item in frame.index.tolist():
                        values.extend(self._extract_tickers_from_any(item, depth + 1))
                return values
            except Exception:
                return values

        to_dict = getattr(data, "to_dict", None)
        if callable(to_dict):
            try:
                payload = to_dict()
                values.extend(self._extract_tickers_from_any(payload, depth + 1))
            except Exception:
                return values
        return values

    def _is_probable_ticker(self, value: str) -> bool:
        if not value:
            return False
        if not PROBABLE_TICKER_RE.match(value):
            return False
        blocked = {"NAME", "SYMBOL", "COMPANY", "WEIGHT", "VALUE", "SECTOR", "COUNTRY"}
        return value not in blocked

    def _persist_index_universe(self, index_name: str, tickers: list[str]) -> str:
        base_dir = Path.home() / ".graham" / "universes"
        base_dir.mkdir(parents=True, exist_ok=True)
        path = base_dir / f"index_{index_name}.txt"
        lines = [f"# Auto-generated from dynamic market data providers for {index_name}", *tickers]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return f"custom:{path}"


def discover_universe_names() -> list[str]:
    names: set[str] = set(UNIVERSE_PRESETS.keys())
    for base in universe_search_dirs():
        if not base.exists():
            continue
        names.update(path.stem for path in base.glob("*.txt"))
    preferred = [
        "sample",
        "world",
        "usa",
        "emerging_markets",
        "china",
        "india",
        "germany",
        "europe",
        "france",
        "japan",
    ]
    ordered: list[str] = []
    for item in preferred:
        if item in names:
            ordered.append(item)
            names.remove(item)
    ordered.extend(sorted(names))
    return ordered
