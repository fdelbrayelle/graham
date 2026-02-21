from __future__ import annotations

import asyncio
import os
import re
import shlex
from pathlib import Path
from typing import Any

from graham.i18n import COMMON_LANGUAGE_CODES

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
        "/universes",
        "/indices",
        "/languages",
        "/lang",
        "/model",
        "/universe",
        "/default-universe",
        "/scan",
        "/screen",
        "/explain",
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
    LANGUAGE_CODES = COMMON_LANGUAGE_CODES

    def __init__(self, app: object) -> None:
        self.app = app

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

        if cmd == "/explain":
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
            tickers, note = await asyncio.to_thread(self._fetch_index_tickers, canonical)
            if not tickers:
                return self._t(f"Unable to fetch index constituents for {canonical}.")
            remember_spec = self._persist_index_universe(canonical, tickers)
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
            self.app.set_universe(tickers, "custom csv")
            await self.app.run_scan(top=None, min_score=0.0, refresh=self.app.refresh_seconds)
            return self._t(f"Screen completed on {len(tickers)} tickers.")

        if command == "/explain":
            ticker, question = self._extract_explain_args(args)
            if not ticker:
                return self._t("Select a ticker or use /explain TICKER [question].")
            return await self.app.explain_ticker(ticker, question)

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
                "Model mode: none (deterministic). Explanations are generated locally from yfinance data.\n"
                "No LLM call is made while model is set to none."
            )
        else:
            model_note = (
                f"Model mode: {self.app.model} (LLM enabled).\n"
                "The app uses yfinance for screening data and uses the configured LLM for /explain.\n"
                "If the LLM call fails, the app falls back to a deterministic local explanation."
            )

        return self._t(
            "Available commands:\n"
            "/help\n"
            "/universes\n"
            "/indices [name]\n"
            "/languages\n"
            "/lang [language-code]\n"
            "/model [none|model-name]\n"
            "/universe [sample|world|usa|emerging_markets|china|india|germany|europe|france|japan|custom:path]\n"
            "/default-universe [name|custom:path]\n"
            "/scan [--top N] [--min-score N] [--refresh SECONDS]\n"
            "/screen TICKERS_CSV\n"
            "/explain [TICKER] [question]\n"
            "/rating GREEN ORANGE\n"
            "/export [csv|json]\n"
            "Examples: /indices sp500, /indices msci_world, /indices dax40, /indices nikkei225\n\n"
            + model_note
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
        lines = [self._t("Supported indices (fetched via yfinance):")]
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
            return self._env_hint("GEMINI_API_KEY")
        return self._t(
            "Custom model ID: make sure the corresponding provider API key is set in your environment."
        )

    def _env_hint(self, env_key: str) -> str:
        if os.getenv(env_key):
            return self._t(f"{env_key} detected.")
        return self._t(f"{env_key} is missing. Export it before using this model.")

    def _unique_preserve_order(self, items: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    def _canonical_index_name(self, raw_name: str) -> str | None:
        value = raw_name.strip().lower()
        if value in INDEX_SPECS:
            return value
        for name, payload in INDEX_SPECS.items():
            aliases = payload.get("aliases", [])
            if value in aliases:
                return name
        return None

    def _fetch_index_tickers(self, index_name: str) -> tuple[list[str], str]:
        import yfinance as yf

        spec = INDEX_SPECS[index_name]
        symbols = spec.get("symbols", [])
        found: list[str] = []
        for symbol in symbols:
            try:
                ticker_obj = yf.Ticker(symbol)
            except Exception:
                continue

            extracted = self._extract_tickers_from_any(getattr(ticker_obj, "constituents", None))
            if not extracted:
                extracted = self._extract_tickers_from_funds_data(ticker_obj)
            if not extracted:
                extracted = self._extract_tickers_from_any(getattr(ticker_obj, "info", None))

            for item in extracted:
                normalized = item.strip().upper()
                if normalized and normalized not in found:
                    found.append(normalized)

        note = f"index:{index_name}"
        return found, note

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
            for key, value in data.items():
                key_text = str(key).strip().upper()
                if self._is_probable_ticker(key_text):
                    values.append(key_text)
                values.extend(self._extract_tickers_from_any(value, depth + 1))
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
        lines = [f"# Auto-generated from yfinance for {index_name}", *tickers]
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
