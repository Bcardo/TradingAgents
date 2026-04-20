"""
Short interest dataflow — fetches short interest % of float and days-to-cover
for a ticker via yfinance.info. No API key required.
"""

import logging

import yfinance as yf

logger = logging.getLogger(__name__)

_UNAVAILABLE = "Short interest data unavailable for {ticker}."


def get_short_interest_data(ticker: str) -> str:
    """
    Fetch short interest % of float and days-to-cover (short ratio) for a ticker.

    Returns a formatted string with context interpretation. Returns an
    informative fallback message when the data key is missing from yfinance
    (common for ETFs and some foreign listings) or on any exception.
    """
    ticker = ticker.upper()

    try:
        info = yf.Ticker(ticker).info
    except Exception as e:
        logger.warning("short_interest %s: yfinance exception: %s", ticker, e)
        return _UNAVAILABLE.format(ticker=ticker)

    si_pct = info.get("shortPercentOfFloat")
    short_ratio = info.get("shortRatio")

    if si_pct is None:
        return _UNAVAILABLE.format(ticker=ticker)

    try:
        si_pct = float(si_pct)
    except (TypeError, ValueError):
        return _UNAVAILABLE.format(ticker=ticker)

    lines = [f"Short Interest — {ticker}:"]
    lines.append(f"  Short % of Float: {si_pct:.1%}")

    if short_ratio is not None:
        try:
            lines.append(f"  Days to Cover (Short Ratio): {float(short_ratio):.1f}")
        except (TypeError, ValueError):
            pass

    if si_pct >= 0.25:
        context = "Very high — significant squeeze potential if a bullish catalyst emerges"
    elif si_pct >= 0.15:
        context = "High — notable squeeze risk; watch for covering pressure on upward moves"
    elif si_pct >= 0.08:
        context = "Moderate — shorts are a secondary factor"
    else:
        context = "Low — short sellers are not a major market factor"

    lines.append(f"  Context: {context}")
    return "\n".join(lines)
