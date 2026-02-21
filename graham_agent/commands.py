from __future__ import annotations

import shlex
from pathlib import Path

DEFAULT_SAMPLE = ["AAPL", "MSFT", "JNJ", "PG", "KO", "XOM", "PEP", "MMM"]


class CommandProcessor:
    COMMANDS = ["/help", "/model", "/universe", "/scan", "/screen", "/explain", "/export"]
    MODELS = ["none", "gpt-4.1-mini", "claude-3-5-sonnet", "gemini-2.0-flash"]
    SCAN_OPTIONS = ["--top", "--min-score", "--refresh"]
    EXPORT_FORMATS = ["csv", "json"]

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

        if cmd == "/universe":
            base = ["sample", "sp500", "cac40", "custom:./universes/sample.txt"]
            base.extend(self.app.available_universes())
            merged = sorted(set(base))
            return [name for name in merged if name.startswith(current)]

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
            return f"Invalid command: {exc}"

        if not parts:
            return ""

        command = parts[0]
        args = parts[1:]

        if command == "/help":
            return self.help_text()

        if command == "/model":
            if not args:
                return f"Current model: {self.app.model}. Usage: /model [none|model-name]"
            self.app.model = args[0]
            return f"Active model: {self.app.model}"

        if command == "/universe":
            if not args:
                return "Usage: /universe [sample|sp500|cac40|custom:path]"
            tickers, note = self.resolve_universe(args[0])
            if not tickers:
                return f"Empty universe. {note}"
            self.app.set_universe(tickers, note)
            return f"Universe loaded: {len(tickers)} tickers ({note})"

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
                "Scan completed. "
                f"top={options['top'] or 'all'}, min_score={options['min_score']:.2f}, "
                f"refresh={self.app.refresh_seconds}s"
            )

        if command == "/screen":
            if not args:
                return "Usage: /screen TICKERS_CSV"
            tickers = [item.strip().upper() for item in args[0].split(",") if item.strip()]
            if not tickers:
                return "No valid ticker provided."
            self.app.set_universe(tickers, "custom csv")
            await self.app.run_scan(top=None, min_score=0.0, refresh=self.app.refresh_seconds)
            return f"Screen completed on {len(tickers)} tickers."

        if command == "/explain":
            ticker, question = self._extract_explain_args(args)
            if not ticker:
                return "Select a ticker or use /explain TICKER [question]."
            return await self.app.explain_ticker(ticker, question)

        if command == "/export":
            if not args:
                return "Usage: /export [csv|json]"
            export_format = args[0].lower()
            if export_format not in self.EXPORT_FORMATS:
                return "Unsupported format. Use /export [csv|json]."
            output = self.app.export_results(export_format)
            return f"Export created: {output}"

        return f"Unknown command: {command}. Type /help"

    def help_text(self) -> str:
        return (
            "Available commands:\n"
            "/help\n"
            "/model [none|model-name]\n"
            "/universe [sample|sp500|cac40|custom:path]\n"
            "/scan [--top N] [--min-score N] [--refresh SECONDS]\n"
            "/screen TICKERS_CSV\n"
            "/explain [TICKER] [question]\n"
            "/export [csv|json]"
        )

    def parse_scan_options(self, args: list[str]) -> dict[str, float | int | None] | str:
        top: int | None = None
        min_score = 0.0
        refresh: int | None = None

        index = 0
        while index < len(args):
            token = args[index]

            if token == "--top":
                if index + 1 >= len(args):
                    return "Option --top expects a numeric value."
                try:
                    top = int(args[index + 1])
                except ValueError:
                    return "Invalid --top value."
                index += 2
                continue

            if token == "--min-score":
                if index + 1 >= len(args):
                    return "Option --min-score expects a numeric value."
                try:
                    min_score = float(args[index + 1])
                except ValueError:
                    return "Invalid --min-score value."
                min_score = max(0.0, min(1.0, min_score))
                index += 2
                continue

            if token == "--refresh":
                if index + 1 >= len(args):
                    return "Option --refresh expects a numeric value."
                try:
                    refresh = int(args[index + 1])
                except ValueError:
                    return "Invalid --refresh value."
                refresh = max(3, refresh)
                index += 2
                continue

            return f"Unknown option: {token}"

        return {"top": top, "min_score": min_score, "refresh": refresh}

    def resolve_universe(self, spec: str) -> tuple[list[str], str]:
        if spec.startswith("custom:"):
            custom_path = spec.split(":", 1)[1]
            return self._read_universe_file(Path(custom_path)), f"custom:{custom_path}"

        root = Path(__file__).resolve().parent.parent
        universe_file = root / "universes" / f"{spec}.txt"
        if universe_file.exists():
            return self._read_universe_file(universe_file), spec

        if spec == "sample":
            return DEFAULT_SAMPLE, "sample (builtin)"

        return [], f"File universes/{spec}.txt not found"

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


def discover_universe_names() -> list[str]:
    root = Path(__file__).resolve().parent.parent
    base = root / "universes"
    if not base.exists():
        return []
    return sorted(path.stem for path in base.glob("*.txt"))
