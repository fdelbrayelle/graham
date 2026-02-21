from __future__ import annotations


def matches_ticker_or_company_query(ticker: str, company_name: str | None, query: str) -> bool:
    text = query.strip().upper()
    if not text:
        return True
    return text in ticker.upper() or text in (company_name or "").upper()
