from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import yfinance as yf

PASS = "PASS"
FAIL = "FAIL"
NA = "N/A"


@dataclass
class CriterionResult:
    index: int
    label: str
    status: str
    note: str


@dataclass
class StockAnalysis:
    ticker: str
    score: float = 0.0
    price: float | None = None
    intrinsic_value: float | None = None
    mos: float | None = None
    pe: float | None = None
    pb: float | None = None
    dividend_rate: float | None = None
    criteria: list[CriterionResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def compute_intrinsic_value(eps: float | None, growth_percent: float, y: float = 4.4) -> float | None:
    if eps is None or y <= 0:
        return None
    return eps * (8.5 + 2.0 * growth_percent) * 4.4 / y


def compute_margin_of_safety(intrinsic_value: float | None, price: float | None) -> float | None:
    if intrinsic_value is None or price is None or price <= 0:
        return None
    return (intrinsic_value - price) / price


def compute_score(criteria: list[CriterionResult]) -> float:
    scored = [criterion for criterion in criteria if criterion.status != NA]
    if not scored:
        return 0.0
    passed = sum(1 for criterion in scored if criterion.status == PASS)
    return passed / len(scored)


def _sort_key(value: Any) -> float:
    try:
        return float(getattr(value, "timestamp")())
    except Exception:
        return 0.0


def extract_eps_series(ticker: Any) -> list[float]:
    frames = [
        getattr(ticker, "income_stmt", None),
        getattr(ticker, "quarterly_income_stmt", None),
    ]
    for frame in frames:
        if frame is None:
            continue
        try:
            if getattr(frame, "empty", True):
                continue
            for label in ("Diluted EPS", "Basic EPS", "Normalized EPS", "EPS"):
                if label not in frame.index:
                    continue
                series = frame.loc[label]
                values: list[tuple[float, float]] = []
                for column, item in series.items():
                    number = safe_float(item)
                    if number is None:
                        continue
                    values.append((_sort_key(column), number))
                if len(values) < 2:
                    continue
                values.sort(key=lambda pair: pair[0])
                return [number for _, number in values][-6:]
        except Exception:
            continue
    return []


def compute_eps_cagr_percent(eps_series: list[float]) -> float:
    if len(eps_series) < 2:
        return 0.0
    start = eps_series[0]
    end = eps_series[-1]
    if start <= 0 or end <= 0:
        return 0.0
    periods = max(1, len(eps_series) - 1)
    return ((end / start) ** (1 / periods) - 1) * 100


def _extract_price(info: dict[str, Any], ticker: Any) -> float | None:
    for key in ("currentPrice", "regularMarketPrice", "previousClose"):
        number = safe_float(info.get(key))
        if number is not None and number > 0:
            return number
    try:
        fast_info = getattr(ticker, "fast_info", None)
        if fast_info is not None:
            for key in ("last_price", "regular_market_price", "previous_close"):
                number = safe_float(fast_info.get(key))
                if number is not None and number > 0:
                    return number
    except Exception:
        return None
    return None


def _build_criteria(
    info: dict[str, Any],
    eps_series: list[float],
    price: float | None,
    require_dividend: bool,
) -> list[CriterionResult]:
    criteria: list[CriterionResult] = []

    criteria.append(
        CriterionResult(
            index=1,
            label="Note S&P earnings/dividend >= B",
            status=NA,
            note="Not available via yfinance.",
        )
    )

    total_debt = safe_float(info.get("totalDebt"))
    current_assets = safe_float(info.get("totalCurrentAssets"))
    if total_debt is None or current_assets is None or current_assets <= 0:
        criteria.append(
            CriterionResult(
                index=2,
                label="Total debt / current assets < 1.10",
                status=NA,
                note="Unable to compute total debt/current assets ratio.",
            )
        )
    else:
        ratio = total_debt / current_assets
        status = PASS if ratio < 1.10 else FAIL
        criteria.append(
            CriterionResult(
                index=2,
                label="Total debt / current assets < 1.10",
                status=status,
                note=f"Ratio={ratio:.2f}.",
            )
        )

    current_ratio = safe_float(info.get("currentRatio"))
    if current_ratio is None:
        current_liabilities = safe_float(info.get("totalCurrentLiabilities"))
        if current_assets is not None and current_liabilities is not None and current_liabilities > 0:
            current_ratio = current_assets / current_liabilities
    if current_ratio is None:
        criteria.append(
            CriterionResult(
                index=3,
                label="Current ratio > 1.50",
                status=NA,
                note="Current ratio unavailable.",
            )
        )
    else:
        status = PASS if current_ratio > 1.50 else FAIL
        criteria.append(
            CriterionResult(
                index=3,
                label="Current ratio > 1.50",
                status=status,
                note=f"Current ratio={current_ratio:.2f}.",
            )
        )

    earnings_growth = safe_float(info.get("earningsGrowth"))
    if len(eps_series) >= 2:
        positive = all(value > 0 for value in eps_series)
        growth = eps_series[-1] > eps_series[0]
        status = PASS if positive and growth else FAIL
        criteria.append(
            CriterionResult(
                index=4,
                label="Positive EPS growth over ~5 years with no deficit",
                status=status,
                note=f"EPS start={eps_series[0]:.2f}, end={eps_series[-1]:.2f}.",
            )
        )
    elif earnings_growth is not None:
        status = PASS if earnings_growth > 0 else FAIL
        criteria.append(
            CriterionResult(
                index=4,
                label="Positive EPS growth over ~5 years with no deficit",
                status=status,
                note="Using earningsGrowth proxy (incomplete EPS history).",
            )
        )
    else:
        criteria.append(
            CriterionResult(
                index=4,
                label="Positive EPS growth over ~5 years with no deficit",
                status=NA,
                note="Incomplete EPS history.",
            )
        )

    trailing_eps = safe_float(info.get("trailingEps")) or safe_float(info.get("epsTrailingTwelveMonths"))
    pe = safe_float(info.get("trailingPE"))
    if pe is None and trailing_eps is not None and trailing_eps > 0 and price is not None:
        pe = price / trailing_eps
    if pe is None:
        criteria.append(
            CriterionResult(
                index=5,
                label="P/E <= 9.0",
                status=NA,
                note="P/E unavailable.",
            )
        )
    else:
        status = PASS if pe <= 9.0 else FAIL
        criteria.append(
            CriterionResult(
                index=5,
                label="P/E <= 9.0",
                status=status,
                note=f"P/E={pe:.2f}.",
            )
        )

    pb = safe_float(info.get("priceToBook"))
    if pb is None:
        criteria.append(
            CriterionResult(
                index=6,
                label="P/B < 1.20",
                status=NA,
                note="P/B unavailable.",
            )
        )
    else:
        status = PASS if pb < 1.20 else FAIL
        criteria.append(
            CriterionResult(
                index=6,
                label="P/B < 1.20",
                status=status,
                note=f"P/B={pb:.2f}.",
            )
        )

    dividend_rate = safe_float(info.get("dividendRate"))
    if dividend_rate is None:
        criteria.append(
            CriterionResult(
                index=7,
                label="Dividends > 0",
                status=NA,
                note="dividendRate unavailable.",
            )
        )
    else:
        has_dividend = dividend_rate > 0
        if require_dividend:
            status = PASS if has_dividend else FAIL
        else:
            status = PASS if has_dividend else NA
        criteria.append(
            CriterionResult(
                index=7,
                label="Dividends > 0",
                status=status,
                note=f"dividendRate={dividend_rate:.2f}.",
            )
        )

    return criteria


def analyze_symbol(
    symbol: str,
    ticker: Any,
    y: float = 4.4,
    require_dividend: bool = True,
) -> StockAnalysis:
    try:
        info = ticker.info or {}
    except Exception as exc:
        return StockAnalysis(
            ticker=symbol,
            notes=[f"yfinance loading error: {exc}"],
            criteria=[],
        )

    price = _extract_price(info, ticker)
    eps_series = extract_eps_series(ticker)

    trailing_eps = safe_float(info.get("trailingEps")) or safe_float(info.get("epsTrailingTwelveMonths"))
    if trailing_eps is None and eps_series:
        trailing_eps = eps_series[-1]

    growth_percent = compute_eps_cagr_percent(eps_series)
    if growth_percent == 0.0:
        proxy_growth = safe_float(info.get("earningsGrowth"))
        if proxy_growth is not None:
            growth_percent = proxy_growth * 100

    intrinsic_value = compute_intrinsic_value(trailing_eps, growth_percent, y=y)
    mos = compute_margin_of_safety(intrinsic_value, price)

    criteria = _build_criteria(
        info=info,
        eps_series=eps_series,
        price=price,
        require_dividend=require_dividend,
    )

    score = compute_score(criteria)

    pe = safe_float(info.get("trailingPE"))
    if pe is None and trailing_eps is not None and trailing_eps > 0 and price is not None:
        pe = price / trailing_eps

    pb = safe_float(info.get("priceToBook"))
    dividend_rate = safe_float(info.get("dividendRate"))

    notes: list[str] = []
    if trailing_eps is None:
        notes.append("EPS unavailable: V is shown as N/A.")
    if price is None:
        notes.append("Price unavailable: MoS is shown as N/A.")

    return StockAnalysis(
        ticker=symbol,
        score=score,
        price=price,
        intrinsic_value=intrinsic_value,
        mos=mos,
        pe=pe,
        pb=pb,
        dividend_rate=dividend_rate,
        criteria=criteria,
        notes=notes,
    )


def rank_analyses(analyses: list[StockAnalysis]) -> list[StockAnalysis]:
    return sorted(
        analyses,
        key=lambda item: (
            -item.score,
            -(item.mos if item.mos is not None else -10**9),
            item.pe if item.pe is not None else 10**9,
            item.ticker,
        ),
    )


def filter_ranked(
    analyses: list[StockAnalysis],
    top: int | None = None,
    min_score: float = 0.0,
) -> list[StockAnalysis]:
    filtered = [analysis for analysis in analyses if analysis.score >= min_score]
    if top is not None and top > 0:
        return filtered[:top]
    return filtered


class GrahamEngine:
    def __init__(self, y: float = 4.4, require_dividend: bool = True) -> None:
        self.y = y
        self.require_dividend = require_dividend
        self.universe: list[str] = []
        self._tickers: dict[str, Any] = {}
        self._analyses: dict[str, StockAnalysis] = {}

    @property
    def analyses(self) -> list[StockAnalysis]:
        return list(self._analyses.values())

    def set_universe(self, symbols: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for symbol in symbols:
            item = symbol.strip().upper()
            if not item or item in seen:
                continue
            seen.add(item)
            cleaned.append(item)
        self.universe = cleaned
        return self.universe

    def scan_fundamentals(self) -> list[StockAnalysis]:
        import yfinance as yf

        for symbol in self.universe:
            ticker = self._tickers.get(symbol)
            if ticker is None:
                ticker = yf.Ticker(symbol)
                self._tickers[symbol] = ticker
            analysis = analyze_symbol(symbol, ticker, y=self.y, require_dividend=self.require_dividend)
            self._analyses[symbol] = analysis
        return rank_analyses(self.analyses)

    def refresh_prices(self) -> list[StockAnalysis]:
        for symbol, analysis in self._analyses.items():
            ticker = self._tickers.get(symbol)
            if ticker is None:
                continue
            previous_price = analysis.price
            price = self._read_live_price(ticker)
            if price is None:
                continue
            analysis.price = price
            if analysis.intrinsic_value is not None:
                analysis.mos = compute_margin_of_safety(analysis.intrinsic_value, analysis.price)
            if previous_price and previous_price > 0 and analysis.pe is not None:
                analysis.pe = analysis.pe * (price / previous_price)
        return rank_analyses(self.analyses)

    def _read_live_price(self, ticker: Any) -> float | None:
        try:
            fast_info = getattr(ticker, "fast_info", None)
            if fast_info is not None:
                for key in ("last_price", "regular_market_price", "previous_close"):
                    number = safe_float(fast_info.get(key))
                    if number is not None and number > 0:
                        return number
        except Exception:
            return None
        return None


def format_metric(value: float | None, percentage: bool = False) -> str:
    if value is None:
        return "N/A"
    if percentage:
        return f"{value * 100:.2f}%"
    return f"{value:.2f}"
