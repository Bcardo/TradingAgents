"""Finnhub data vendor for TradingAgents.

Most public functions raise FinnhubUnavailableError on any failure so that
route_to_vendor silently falls back to the next vendor in the chain.
Exception: get_analyst_consensus and get_earnings_surprise return a graceful
message string instead of raising, because they have no vendor fallback.
"""

import os
import calendar
import requests
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Annotated

FINNHUB_BASE = "https://finnhub.io/api/v1"


class FinnhubUnavailableError(Exception):
    """Sentinel: Finnhub API is unavailable (no key, network error, rate limit, etc.)."""
    pass


# Mirror of y_finance.py best_ind_params — same indicators, same descriptions.
_INDICATOR_DESCRIPTIONS = {
    "close_50_sma": (
        "50 SMA: A medium-term trend indicator. "
        "Usage: Identify trend direction and serve as dynamic support/resistance. "
        "Tips: It lags price; combine with faster indicators for timely signals."
    ),
    "close_200_sma": (
        "200 SMA: A long-term trend benchmark. "
        "Usage: Confirm overall market trend and identify golden/death cross setups. "
        "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
    ),
    "close_10_ema": (
        "10 EMA: A responsive short-term average. "
        "Usage: Capture quick shifts in momentum and potential entry points. "
        "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
    ),
    "macd": (
        "MACD: Computes momentum via differences of EMAs. "
        "Usage: Look for crossovers and divergence as signals of trend changes. "
        "Tips: Confirm with other indicators in low-volatility or sideways markets."
    ),
    "macds": (
        "MACD Signal: An EMA smoothing of the MACD line. "
        "Usage: Use crossovers with the MACD line to trigger trades. "
        "Tips: Should be part of a broader strategy to avoid false positives."
    ),
    "macdh": (
        "MACD Histogram: Shows the gap between the MACD line and its signal. "
        "Usage: Visualize momentum strength and spot divergence early. "
        "Tips: Can be volatile; complement with additional filters in fast-moving markets."
    ),
    "rsi": (
        "RSI: Measures momentum to flag overbought/oversold conditions. "
        "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
        "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
    ),
    "boll": (
        "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
        "Usage: Acts as a dynamic benchmark for price movement. "
        "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
    ),
    "boll_ub": (
        "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
        "Usage: Signals potential overbought conditions and breakout zones. "
        "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
    ),
    "boll_lb": (
        "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
        "Usage: Indicates potential oversold conditions. "
        "Tips: Use additional analysis to avoid false reversal signals."
    ),
    "atr": (
        "ATR: Averages true range to measure volatility. "
        "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
        "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
    ),
    "vwma": (
        "VWMA: A moving average weighted by volume. "
        "Usage: Confirm trends by integrating price action with volume data. "
        "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
    ),
    "mfi": (
        "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure buying and selling pressure. "
        "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength of trends or reversals. "
        "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI can indicate potential reversals."
    ),
}


# ---------------------------------------------------------------------------
# Internal helpers
# Two-tier candle cache:
#   L1 (in-memory dict): avoids repeated disk reads within the same process
#   L2 (disk CSV in data_cache_dir): persists across runs — refreshed once per calendar day
_candle_cache: dict = {}


# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    key = os.getenv("FINNHUB_API_KEY")
    if not key:
        raise FinnhubUnavailableError("FINNHUB_API_KEY environment variable is not set.")
    return key


def _finnhub_get(endpoint: str, params: dict) -> dict | list:
    """GET from Finnhub REST API. Raises FinnhubUnavailableError on any failure."""
    try:
        key = _get_api_key()
        full_params = {**params, "token": key}
        resp = requests.get(f"{FINNHUB_BASE}{endpoint}", params=full_params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except FinnhubUnavailableError:
        raise
    except Exception as e:
        raise FinnhubUnavailableError(f"Finnhub request failed for {endpoint}: {e}") from e


def _to_unix(date_str: str) -> int:
    """Convert YYYY-MM-DD to Unix timestamp (UTC midnight)."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(calendar.timegm(dt.timetuple()))


def _load_candles_for_indicator(symbol: str) -> pd.DataFrame:
    """Return full 2-year OHLCV DataFrame for a ticker, using two-tier cache.

    L1: in-memory dict (per process).
    L2: CSV in data_cache_dir (refreshed once per calendar day).
    Callers must filter by curr_date before using the data.
    """
    from .config import get_config

    key = symbol.upper()
    if key in _candle_cache:
        return _candle_cache[key]

    cache_dir = get_config().get("data_cache_dir", "")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"finnhub_candles_{key}.csv")

    today = datetime.utcnow().date()
    if os.path.exists(cache_path):
        mtime = datetime.utcfromtimestamp(os.path.getmtime(cache_path)).date()
        if mtime >= today:
            df = pd.read_csv(cache_path, dtype={"Date": str})
            _candle_cache[key] = df
            return df

    # Cache miss or stale — fetch from Finnhub
    hist_start = (datetime.utcnow() - relativedelta(years=2)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    df = _fetch_candles(symbol, hist_start, today_str)
    df.to_csv(cache_path, index=False)
    _candle_cache[key] = df
    return df


def _fetch_candles(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch daily OHLCV candles from Finnhub. Returns DataFrame with columns
    Date (str), Open, High, Low, Close, Volume."""
    data = _finnhub_get("/stock/candle", {
        "symbol": symbol.upper(),
        "resolution": "D",
        "from": _to_unix(start_date),
        "to": _to_unix(end_date),
    })
    if data.get("s") != "ok":
        raise FinnhubUnavailableError(
            f"Finnhub candles returned status '{data.get('s')}' for {symbol}"
        )
    df = pd.DataFrame({
        "Date": [datetime.utcfromtimestamp(t).strftime("%Y-%m-%d") for t in data["t"]],
        "Open": data["o"],
        "High": data["h"],
        "Low": data["l"],
        "Close": data["c"],
        "Volume": data["v"],
    })
    return df


def _fetch_financials(ticker: str, freq: str, curr_date: str | None, stmt_key: str) -> str:
    """Fetch reported financials from Finnhub and return CSV-formatted string.

    stmt_key: 'bs' (balance sheet), 'ic' (income statement), 'cf' (cash flow)
    """
    fh_freq = "quarterly" if freq.lower() == "quarterly" else "annual"
    data = _finnhub_get("/financials/reported", {"symbol": ticker.upper(), "freq": fh_freq})

    reports = data.get("data", [])
    if not reports:
        raise FinnhubUnavailableError(f"No financial data returned by Finnhub for {ticker}")

    # Filter to reports before curr_date (look-ahead guard)
    if curr_date:
        reports = [r for r in reports if r.get("endDate", "9999-99-99") <= curr_date]

    if not reports:
        raise FinnhubUnavailableError(
            f"No Finnhub financial data before {curr_date} for {ticker}"
        )

    # Most recent 4 periods
    reports = sorted(reports, key=lambda r: r.get("endDate", ""), reverse=True)[:4]
    dates = [r["endDate"] for r in reports]

    # Build label → {date: value} mapping
    label_map: dict[str, dict[str, float]] = {}
    for r in reports:
        for item in r.get("report", {}).get(stmt_key, []):
            label = item.get("label") or item.get("concept", "Unknown")
            label_map.setdefault(label, {})[r["endDate"]] = item.get("value")

    rows = []
    for label, date_vals in label_map.items():
        row = {"Label": label}
        for d in dates:
            row[d] = date_vals.get(d)
        rows.append(row)

    df = pd.DataFrame(rows).set_index("Label")[dates]

    stmt_names = {"bs": "Balance Sheet", "ic": "Income Statement", "cf": "Cash Flow"}
    header = f"# {stmt_names[stmt_key]} data for {ticker.upper()} ({freq})\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + df.to_csv()


# ---------------------------------------------------------------------------
# Existing tool implementations
# ---------------------------------------------------------------------------

def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "end date in yyyy-mm-dd format"],
) -> str:
    """Fetch daily OHLCV data from Finnhub and return as CSV string."""
    df = _fetch_candles(symbol, start_date, end_date)
    if df.empty:
        return f"No data found for '{symbol}' between {start_date} and {end_date}"

    df[["Open", "High", "Low", "Close"]] = df[["Open", "High", "Low", "Close"]].round(2)

    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(df)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + df.to_csv(index=False)


def get_current_price(symbol: str) -> str:
    """Fetch real-time quote from Finnhub."""
    data = _finnhub_get("/quote", {"symbol": symbol.upper()})
    price = data.get("c")
    if price is None:
        raise FinnhubUnavailableError(f"No price data returned for {symbol}")
    # d/dp are null outside market hours — default to 0 when absent or null
    change = data.get("d") or 0
    change_pct = data.get("dp") or 0
    return (
        f"Current price for {symbol.upper()}: ${price:.2f} "
        f"({change:+.2f}, {change_pct:+.2f}%)"
    )


def get_indicators(
    symbol: Annotated[str, "ticker symbol"],
    indicator: Annotated[str, "technical indicator name"],
    curr_date: Annotated[str, "current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "number of days to look back"],
) -> str:
    """Compute a technical indicator from Finnhub candles via stockstats."""
    if indicator not in _INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"Indicator '{indicator}' is not supported. "
            f"Choose from: {list(_INDICATOR_DESCRIPTIONS.keys())}"
        )

    from stockstats import wrap
    from .stockstats_utils import _clean_dataframe

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before_dt = curr_dt - relativedelta(days=look_back_days)

    # Load from two-tier cache (in-memory → disk → Finnhub).
    # Filter to curr_date to prevent look-ahead bias.
    df_raw = _load_candles_for_indicator(symbol)
    df_raw = df_raw[df_raw["Date"] <= curr_date].copy()

    df_clean = _clean_dataframe(df_raw.copy())
    df_ss = wrap(df_clean)

    # Format date column as strings after stockstats processes it
    if hasattr(df_ss["Date"], "dt"):
        df_ss["Date"] = df_ss["Date"].dt.strftime("%Y-%m-%d")

    # Trigger indicator calculation
    df_ss[indicator]

    date_to_value = dict(zip(df_ss["Date"].astype(str), df_ss[indicator]))

    ind_string = ""
    current_dt = curr_dt
    while current_dt >= before_dt:
        date_str = current_dt.strftime("%Y-%m-%d")
        raw_val = date_to_value.get(date_str)
        if raw_val is None:
            indicator_value = "N/A: Not a trading day (weekend or holiday)"
        elif pd.isna(raw_val):
            indicator_value = "N/A"
        else:
            indicator_value = str(raw_val)
        ind_string += f"{date_str}: {indicator_value}\n"
        current_dt -= relativedelta(days=1)

    return (
        f"## {indicator} values from {before_dt.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + ind_string
        + "\n\n"
        + _INDICATOR_DESCRIPTIONS[indicator]
    )


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date (unused, for API compatibility)"] = None,
) -> str:
    """Fetch company fundamentals from Finnhub /stock/metric and /stock/profile2."""
    profile = _finnhub_get("/stock/profile2", {"symbol": ticker.upper()})
    metrics_resp = _finnhub_get("/stock/metric", {"symbol": ticker.upper(), "metric": "all"})
    m = metrics_resp.get("metric", {})

    fields = [
        ("Name", profile.get("name")),
        ("Industry", profile.get("finnhubIndustry")),
        ("Exchange", profile.get("exchange")),
        ("IPO Date", profile.get("ipo")),
        ("Market Cap (M)", profile.get("marketCapitalization")),
        ("Shares Outstanding (M)", profile.get("shareOutstanding")),
        ("52 Week High", m.get("52WeekHigh")),
        ("52 Week Low", m.get("52WeekLow")),
        ("10-Day Avg Volume (M)", m.get("10DayAverageTradingVolume")),
        ("Beta", m.get("beta")),
        ("PE (TTM)", m.get("peTTM")),
        ("PE Normalized (Annual)", m.get("peNormalizedAnnual")),
        ("PEG (Annual)", m.get("pegAnnual")),
        ("EPS (TTM)", m.get("epsTTM")),
        ("Book Value/Share (Quarterly)", m.get("bookValuePerShareQuarterly")),
        ("Price/Book (Quarterly)", m.get("pbQuarterly")),
        ("Debt/Equity (Annual)", m.get("totalDebt/totalEquityAnnual")),
        ("Current Ratio (Annual)", m.get("currentRatioAnnual")),
        ("Gross Margin (TTM)", m.get("grossMarginTTM")),
        ("Operating Margin (TTM)", m.get("operatingMarginTTM")),
        ("Net Margin (TTM)", m.get("netMarginTTM")),
        ("ROE (Annual)", m.get("roeRfy")),
        ("ROA (TTM)", m.get("roaTTM")),
        ("Revenue (TTM, M)", m.get("revenueTTM")),
        ("Revenue Growth (3Y)", m.get("revenueGrowth3Y")),
        ("EPS Growth (3Y)", m.get("epsGrowth3Y")),
        ("Dividend Yield (TTM)", m.get("dividendYieldIndicatedAnnual")),
    ]

    lines = [f"{label}: {value}" for label, value in fields if value is not None]

    header = f"# Company Fundamentals for {ticker.upper()}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + "\n".join(lines)


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Fetch balance sheet from Finnhub /financials/reported."""
    return _fetch_financials(ticker, freq, curr_date, "bs")


def get_income_statement(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Fetch income statement from Finnhub /financials/reported."""
    return _fetch_financials(ticker, freq, curr_date, "ic")


def get_cashflow(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Fetch cash flow statement from Finnhub /financials/reported."""
    return _fetch_financials(ticker, freq, curr_date, "cf")


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """Fetch insider transactions from Finnhub /stock/insider-transactions."""
    data = _finnhub_get("/stock/insider-transactions", {"symbol": ticker.upper()})
    records = data.get("data", [])

    if not records:
        return f"No insider transactions data found for symbol '{ticker}'"

    df = pd.DataFrame(records)
    # Normalize column names to match yfinance style
    rename = {
        "name": "Name",
        "share": "Shares",
        "change": "Change",
        "filingDate": "Filing Date",
        "transactionDate": "Transaction Date",
        "transactionCode": "Transaction Code",
        "transactionPrice": "Price",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    header = f"# Insider Transactions data for {ticker.upper()}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + df.to_csv(index=False)


def get_news(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Fetch company news from Finnhub /company-news."""
    articles = _finnhub_get("/company-news", {
        "symbol": ticker.upper(),
        "from": start_date,
        "to": end_date,
    })

    if not articles:
        return f"No news found for {ticker} between {start_date} and {end_date}"

    news_str = ""
    for article in articles[:30]:
        headline = article.get("headline", "No headline")
        summary = article.get("summary", "")
        source = article.get("source", "Unknown")
        url = article.get("url", "")

        news_str += f"### {headline} (source: {source})\n"
        if summary:
            news_str += f"{summary}\n"
        if url:
            news_str += f"Link: {url}\n"
        news_str += "\n"

    return f"## {ticker} News, from {start_date} to {end_date}:\n\n{news_str}"


# ---------------------------------------------------------------------------
# New tools: analyst consensus and earnings surprise (Tasks 2.1, 2.2)
# ---------------------------------------------------------------------------

def get_analyst_consensus(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current trading date, YYYY-mm-dd"],
) -> str:
    """Fetch analyst buy/hold/sell consensus and price targets from Finnhub.

    Calls /stock/recommendation and /stock/price-target.
    Filters recommendations to periods on or before curr_date to prevent
    look-ahead bias in backtesting. Returns a graceful message if unavailable.
    """
    try:
        recommendations = _finnhub_get("/stock/recommendation", {"symbol": ticker.upper()})
    except FinnhubUnavailableError as e:
        return f"Analyst consensus unavailable: {e}"

    # /stock/price-target requires a paid plan; degrade gracefully if unavailable
    try:
        price_target = _finnhub_get("/stock/price-target", {"symbol": ticker.upper()})
    except FinnhubUnavailableError:
        price_target = {}

    lines = [f"# Analyst Consensus for {ticker.upper()} (as of {curr_date})"]

    if recommendations:
        # Filter to periods on or before curr_date — prevents look-ahead in backtesting
        valid_recs = [r for r in recommendations if r.get("period", "9999-99-99") <= curr_date]
        if not valid_recs:
            lines.append("\nNo recommendation data available for this date.")
            return "\n".join(lines)
        rec = valid_recs[0]
        period = rec.get("period", "unknown")
        strong_buy = rec.get("strongBuy", 0)
        buy = rec.get("buy", 0)
        hold = rec.get("hold", 0)
        sell = rec.get("sell", 0)
        strong_sell = rec.get("strongSell", 0)
        total = strong_buy + buy + hold + sell + strong_sell

        lines.append(f"\n## Analyst Ratings (period: {period}, n={total})")
        lines.append(f"Strong Buy: {strong_buy}")
        lines.append(f"Buy:        {buy}")
        lines.append(f"Hold:       {hold}")
        lines.append(f"Sell:       {sell}")
        lines.append(f"Strong Sell:{strong_sell}")
    else:
        lines.append("\nNo recommendation data available.")

    pt = price_target
    if pt and pt.get("targetMean"):
        updated = pt.get("lastUpdated", "unknown")
        lines.append(f"\n## Price Targets (last updated: {updated})")
        lines.append(f"Mean Target:   ${pt.get('targetMean', 'N/A')}")
        lines.append(f"Median Target: ${pt.get('targetMedian', 'N/A')}")
        lines.append(f"High Target:   ${pt.get('targetHigh', 'N/A')}")
        lines.append(f"Low Target:    ${pt.get('targetLow', 'N/A')}")
    else:
        lines.append("\nNo price target data available.")

    return "\n".join(lines)


def get_earnings_surprise(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current trading date, YYYY-mm-dd"],
) -> str:
    """Fetch last 4 quarters of EPS actual vs estimate from Finnhub /stock/earnings.

    Returns formatted table. Returns a graceful message if Finnhub is unavailable.
    """
    try:
        earnings = _finnhub_get("/stock/earnings", {"symbol": ticker.upper()})
    except FinnhubUnavailableError as e:
        return f"Earnings surprise unavailable: {e}"

    if not earnings:
        return f"No earnings data available for {ticker}"

    # Filter to quarters on or before curr_date, take last 4
    filtered = [e for e in earnings if e.get("period", "9999-99-99") <= curr_date]
    filtered = sorted(filtered, key=lambda e: e.get("period", ""), reverse=True)[:4]

    if not filtered:
        return f"No earnings data before {curr_date} for {ticker}"

    lines = [f"# Earnings Surprise for {ticker.upper()} (last 4 quarters before {curr_date})"]
    lines.append(f"{'Period':<12} {'Actual EPS':>12} {'Est. EPS':>12} {'Surprise':>10} {'Surprise %':>12}")
    lines.append("-" * 60)

    for e in filtered:
        period = e.get("period", "N/A")
        actual = e.get("actual")
        estimate = e.get("estimate")
        surprise = e.get("surprise")
        surprise_pct = e.get("surprisePercent")

        actual_str = f"${actual:.2f}" if actual is not None else "N/A"
        estimate_str = f"${estimate:.2f}" if estimate is not None else "N/A"
        surprise_str = f"{surprise:+.2f}" if surprise is not None else "N/A"
        surprise_pct_str = f"{surprise_pct:+.1f}%" if surprise_pct is not None else "N/A"

        lines.append(
            f"{period:<12} {actual_str:>12} {estimate_str:>12} {surprise_str:>10} {surprise_pct_str:>12}"
        )

    return "\n".join(lines)
