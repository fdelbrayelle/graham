from __future__ import annotations

import importlib
import os
import re
from typing import Any


def resolve_market_data_provider() -> str:
    value = os.getenv("GRAHAM_MARKET_DATA_PROVIDER", "yfinance").strip().lower()
    if value in {"defeatbeta", "defeatbeta-api", "defeatbeta_api"}:
        return "defeatbeta"
    return "yfinance"


def create_ticker(symbol: str, provider: str | None = None, yfinance_fallback: bool = True) -> tuple[Any, str]:
    selected = provider or resolve_market_data_provider()
    if selected == "defeatbeta":
        ticker = _create_defeatbeta_ticker(symbol)
        if ticker is not None:
            return ticker, "defeatbeta"
        if not yfinance_fallback:
            raise RuntimeError("defeatbeta-api unavailable and yfinance fallback disabled.")

    yfinance = importlib.import_module("yfinance")
    return yfinance.Ticker(symbol), "yfinance"


def _create_defeatbeta_ticker(symbol: str) -> Any | None:
    candidates = [
        ("defeatbeta_api.data.ticker", "Ticker"),
        ("defeatbeta_api.ticker", "Ticker"),
        ("defeatbeta_api", "Ticker"),
    ]
    for module_name, class_name in candidates:
        try:
            module = importlib.import_module(module_name)
            ticker_cls = getattr(module, class_name, None)
            if not callable(ticker_cls):
                continue
            raw = ticker_cls(symbol)
            return DefeatBetaTickerAdapter(symbol, raw)
        except Exception:
            continue
    return None


class _SimpleSeries:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def items(self):
        return self._values.items()


class _SimpleLoc:
    def __init__(self, rows: dict[str, dict[str, Any]]) -> None:
        self._rows = rows

    def __getitem__(self, key: str) -> _SimpleSeries:
        return _SimpleSeries(self._rows[key])


class _SimpleFrame:
    def __init__(self, rows: dict[str, dict[str, Any]]) -> None:
        self._rows = rows
        self.index = list(rows.keys())
        self.loc = _SimpleLoc(rows)
        self.empty = not rows


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.strip().lower())


def _coerce_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "to_dict"):
        try:
            mapped = payload.to_dict()
            if isinstance(mapped, dict):
                return mapped
        except Exception:
            pass
    if hasattr(payload, "__dict__"):
        try:
            data = vars(payload)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _maybe_call(value: Any) -> Any:
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value


def _read_any(obj: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        if not hasattr(obj, name):
            continue
        value = _maybe_call(getattr(obj, name))
        if value is not None:
            return value
    return None


def _flatten_dict_values(payload: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            nested = _coerce_dict(value)
            if nested:
                for n_key, n_val in nested.items():
                    text = str(n_key).strip()
                    if text and text not in flattened:
                        flattened[text] = n_val
        text = str(key).strip()
        if text:
            flattened[text] = value
    return flattened


def _payload_to_rows(payload: Any) -> dict[str, dict[str, Any]]:
    if payload is None:
        return {}

    if hasattr(payload, "empty") and hasattr(payload, "index") and hasattr(payload, "loc"):
        return {}

    mapped = _coerce_dict(payload)
    if mapped:
        if all(isinstance(value, dict) for value in mapped.values()):
            rows = {
                str(label): {str(period): amount for period, amount in _coerce_dict(values).items()}
                for label, values in mapped.items()
                if str(label).strip()
            }
            if rows:
                return rows

        if all(not isinstance(value, dict) for value in mapped.values()):
            return {"Value": {str(key): value for key, value in mapped.items()}}

        transposed: dict[str, dict[str, Any]] = {}
        for period, values in mapped.items():
            nested = _coerce_dict(values)
            if not nested:
                continue
            for label, amount in nested.items():
                row = transposed.setdefault(str(label), {})
                row[str(period)] = amount
        if transposed:
            return transposed

    if isinstance(payload, list):
        rows: dict[str, dict[str, Any]] = {}
        for item in payload:
            data = _coerce_dict(item)
            if not data:
                continue
            metric_key = None
            for key in ("metric", "label", "name", "item", "line_item"):
                if key in data and data.get(key):
                    metric_key = str(data[key])
                    break
            if metric_key is not None:
                row = rows.setdefault(metric_key, {})
                for key, value in data.items():
                    if key in {"metric", "label", "name", "item", "line_item"}:
                        continue
                    row[str(key)] = value
                continue

            period = None
            for key in ("period", "date", "fiscalDate", "asOfDate"):
                if key in data and data.get(key):
                    period = str(data[key])
                    break
            if period is None:
                continue
            for key, value in data.items():
                if key in {"period", "date", "fiscalDate", "asOfDate"}:
                    continue
                row = rows.setdefault(str(key), {})
                row[period] = value
        return rows
    return {}


def _to_frame(payload: Any) -> Any:
    if payload is None:
        return None
    if hasattr(payload, "empty") and hasattr(payload, "index") and hasattr(payload, "loc"):
        return payload
    rows = _payload_to_rows(payload)
    if not rows:
        return None
    return _SimpleFrame(rows)


def _first_numeric(payload: Any) -> float | None:
    try:
        if isinstance(payload, (int, float)):
            return float(payload)
        if isinstance(payload, str):
            return float(payload.replace(",", "").strip())
        if isinstance(payload, dict):
            for value in payload.values():
                number = _first_numeric(value)
                if number is not None:
                    return number
        if isinstance(payload, list):
            for value in payload:
                number = _first_numeric(value)
                if number is not None:
                    return number
    except Exception:
        return None
    return None


def _alias_lookup() -> dict[str, str]:
    aliases = {
        "totalDebt": (
            "totaldebt",
            "debt",
        ),
        "totalCurrentAssets": (
            "totalcurrentassets",
            "currentassets",
        ),
        "totalCurrentLiabilities": (
            "totalcurrentliabilities",
            "currentliabilities",
        ),
        "currentRatio": (
            "currentratio",
        ),
        "earningsGrowth": (
            "earningsgrowth",
            "epsgrowth",
            "revenuegrowth",
        ),
        "trailingEps": (
            "trailingeps",
            "eps",
            "epsttm",
        ),
        "epsTrailingTwelveMonths": (
            "epstrailingtwelvemonths",
            "ttmeps",
        ),
        "trailingPE": (
            "trailingpe",
            "pe",
            "peratio",
        ),
        "priceToBook": (
            "pricetobook",
            "pb",
            "pbratio",
        ),
        "dividendRate": (
            "dividendrate",
            "annualdividendrate",
        ),
        "longName": (
            "longname",
            "companyname",
            "name",
        ),
        "shortName": (
            "shortname",
            "symbolname",
        ),
        "displayName": (
            "displayname",
        ),
        "currentPrice": (
            "currentprice",
            "price",
            "lastprice",
            "close",
        ),
        "regularMarketPrice": (
            "regularmarketprice",
            "marketprice",
        ),
        "previousClose": (
            "previousclose",
            "prevclose",
        ),
        "regularMarketTime": (
            "regularmarkettime",
            "markettime",
            "timestamp",
        ),
    }
    out: dict[str, str] = {}
    for target, names in aliases.items():
        for name in names:
            out[name] = target
    return out


_ALIASES = _alias_lookup()


def _normalize_info(payload: Any) -> dict[str, Any]:
    mapped = _flatten_dict_values(_coerce_dict(payload))
    if not mapped:
        return {}
    out: dict[str, Any] = {}
    for key, value in mapped.items():
        alias = _ALIASES.get(_normalize_key(key))
        if alias is None or alias in out:
            continue
        out[alias] = value
    return out


class DefeatBetaTickerAdapter:
    def __init__(self, symbol: str, raw: Any) -> None:
        self.symbol = symbol
        self._raw = raw
        self._info_cache: dict[str, Any] | None = None
        self._fast_info_cache: dict[str, Any] | None = None
        self._income_cache: Any = None
        self._quarterly_income_cache: Any = None
        self._balance_cache: Any = None

    @property
    def info(self) -> dict[str, Any]:
        if self._info_cache is not None:
            return self._info_cache

        info_payload = _read_any(
            self._raw,
            (
                "info",
                "overview",
                "statistics",
                "summary",
                "quote",
                "profile",
            ),
        )
        info = _normalize_info(info_payload)

        price_payload = _read_any(
            self._raw,
            (
                "price",
                "last_price",
                "quote_price",
                "current_price",
            ),
        )
        number = _first_numeric(price_payload)
        if number is not None:
            info.setdefault("currentPrice", number)
            info.setdefault("regularMarketPrice", number)

        info.setdefault("displayName", self.symbol)
        self._info_cache = info
        return info

    @property
    def fast_info(self) -> dict[str, Any]:
        if self._fast_info_cache is not None:
            return self._fast_info_cache
        info = self.info
        out: dict[str, Any] = {}
        if "currentPrice" in info:
            out["last_price"] = info["currentPrice"]
            out["regular_market_price"] = info["currentPrice"]
        if "previousClose" in info:
            out["previous_close"] = info["previousClose"]
        if "regularMarketTime" in info:
            out["regular_market_time"] = info["regularMarketTime"]
        self._fast_info_cache = out
        return out

    @property
    def income_stmt(self) -> Any:
        if self._income_cache is not None:
            return self._income_cache
        payload = _read_any(
            self._raw,
            (
                "income_stmt",
                "income_statement",
                "income_statements",
                "financials",
                "income",
            ),
        )
        self._income_cache = _to_frame(payload)
        return self._income_cache

    @property
    def quarterly_income_stmt(self) -> Any:
        if self._quarterly_income_cache is not None:
            return self._quarterly_income_cache
        payload = _read_any(
            self._raw,
            (
                "quarterly_income_stmt",
                "quarterly_income_statement",
                "income_statement_quarterly",
                "quarterly_financials",
            ),
        )
        self._quarterly_income_cache = _to_frame(payload)
        return self._quarterly_income_cache

    @property
    def balance_sheet(self) -> Any:
        if self._balance_cache is not None:
            return self._balance_cache
        payload = _read_any(
            self._raw,
            (
                "balance_sheet",
                "balancesheet",
                "balance",
            ),
        )
        self._balance_cache = _to_frame(payload)
        return self._balance_cache

    @property
    def constituents(self) -> Any:
        return _read_any(
            self._raw,
            (
                "constituents",
                "holdings",
                "components",
            ),
        )

