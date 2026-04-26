"""SEC EDGAR data provider for TradingAgents.

Fetches 8-K filing metadata for US-listed tickers via the EDGAR submissions API.
No API key required — only a User-Agent header per SEC fair-use policy.
Non-US or unknown tickers return a graceful no-op string.
"""

import os
import json
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta

EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# SEC requires a real contact email in the User-Agent header.
# Set EDGAR_USER_AGENT in your environment, e.g.:
#   "MyApp/1.0 (contact@myemail.com)"
_EDGAR_USER_AGENT = os.getenv(
    "EDGAR_USER_AGENT",
    "TradingAgents/1.0 (contact@tradingagents.local)",
)

# In-memory cache for the ticker→CIK mapping (populated once per process from disk)
_cik_map: dict | None = None


def _get_cik_map() -> dict:
    """Return ticker→CIK mapping, loading from disk cache or downloading if needed.

    Cache file: {data_cache_dir}/edgar_tickers.json
    No TTL — file persists until manually deleted (changes infrequently).
    """
    global _cik_map
    if _cik_map is not None:
        return _cik_map

    from .config import get_config
    cache_dir = get_config().get("data_cache_dir", "")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, "edgar_tickers.json")

    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            raw = json.load(f)
    else:
        resp = requests.get(EDGAR_TICKERS_URL, headers={"User-Agent": _EDGAR_USER_AGENT}, timeout=30)
        resp.raise_for_status()
        raw = resp.json()
        with open(cache_path, "w") as f:
            json.dump(raw, f)

    # raw format: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    _cik_map = {v["ticker"].upper(): v["cik_str"] for v in raw.values()}
    return _cik_map


def _get_cik(ticker: str) -> str | None:
    """Return zero-padded 10-digit CIK for a ticker, or None if not found."""
    cik_int = _get_cik_map().get(ticker.upper())
    if cik_int is None:
        return None
    return str(cik_int).zfill(10)


def get_sec_filings(ticker: str, curr_date: str) -> str:
    """Return recent 8-K filing metadata for a US-listed ticker.

    Fetches EDGAR submissions JSON, filters to 8-K and 8-K/A filings within
    30 days before curr_date. Non-US or unknown tickers return a graceful message.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL")
        curr_date: Analysis date in YYYY-MM-DD format

    Returns:
        Formatted string listing recent 8-K filings, or a no-data message.
    """
    try:
        cik = _get_cik(ticker)
    except Exception as e:
        return f"SEC EDGAR lookup failed for {ticker}: {e}"

    if cik is None:
        return (
            f"No SEC EDGAR data available for {ticker} "
            f"(non-US or unknown ticker — CIK not found)."
        )

    try:
        url = EDGAR_SUBMISSIONS_URL.format(cik=cik)
        resp = requests.get(url, headers={"User-Agent": _EDGAR_USER_AGENT}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"SEC EDGAR request failed for {ticker} (CIK {cik}): {e}"

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])

    if not forms:
        return f"No filing history found in SEC EDGAR for {ticker}."

    # Date window: [curr_date - 30 days, curr_date]
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    window_start = (curr_dt - relativedelta(days=30)).strftime("%Y-%m-%d")

    target_forms = {"8-K", "8-K/A"}
    matches = []
    for form, date, accession in zip(forms, dates, accessions):
        if form in target_forms and window_start <= date <= curr_date:
            matches.append((date, form, accession))

    if not matches:
        return (
            f"No 8-K filings found for {ticker} in the 30 days before {curr_date}."
        )

    matches.sort(key=lambda x: x[0], reverse=True)
    lines = [
        f"# SEC EDGAR 8-K Filings for {ticker.upper()} "
        f"(last 30 days before {curr_date})",
        f"# {len(matches)} filing(s) found\n",
    ]
    for date, form, accession in matches:
        lines.append(f"- {date}  {form:<8}  Accession: {accession}")

    return "\n".join(lines)
