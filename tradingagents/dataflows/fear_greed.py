# -*- coding: utf-8 -*-
"""CNN Fear & Greed Index fetching via CNN's production dataviz API (no auth required)."""

import logging
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_TIMEOUT = 10

# CNN's API requires a browser-like User-Agent; without it the server
# returns HTTP 418.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def get_fear_greed(days: int = 7) -> str:
    """
    Fetch the CNN Fear & Greed Index from CNN's production dataviz API.

    Returns the current score plus recent daily history with a numeric score
    (0–100) and classification label (Extreme Fear / Fear / Neutral / Greed /
    Extreme Greed). This is a **stock market** sentiment indicator composed of
    7 sub-indicators: market momentum, stock price strength, stock price
    breadth, put/call options, market volatility (VIX), junk bond demand,
    and safe haven demand.

    Args:
        days: Number of past days to include in the history (default 7).

    Returns:
        Formatted string of daily entries, or empty string on API failure.
    """
    try:
        r = requests.get(_URL, headers=_HEADERS, timeout=_TIMEOUT)
    except requests.RequestException as e:
        logger.warning("CNN Fear & Greed API request failed: %s", e)
        return ""

    if not r.ok:
        logger.warning("CNN Fear & Greed API returned HTTP %s", r.status_code)
        return ""

    r.encoding = "utf-8"
    try:
        payload = r.json()
    except ValueError:
        logger.warning("CNN Fear & Greed API returned invalid JSON")
        return ""

    # ── Current reading ──────────────────────────────────────────────
    fng = payload.get("fear_and_greed", {})
    current_score = fng.get("score")
    current_rating = fng.get("rating", "?")
    current_ts = fng.get("timestamp", "")

    if current_score is None:
        logger.warning("CNN Fear & Greed response missing 'score'")
        return ""

    lines = ["CNN Fear & Greed Index (stock market sentiment):\n"]

    # Format the current reading
    current_date = current_ts[:10] if current_ts else "today"
    lines.append(
        f"Current ({current_date}): Score {round(current_score)}/100 | "
        f"{_format_rating(current_rating)}"
    )

    # ── Benchmarks ───────────────────────────────────────────────────
    prev_close = fng.get("previous_close")
    prev_week = fng.get("previous_1_week")
    prev_month = fng.get("previous_1_month")
    prev_year = fng.get("previous_1_year")

    if prev_close is not None:
        lines.append(f"Previous close: {round(prev_close)}/100")
    if prev_week is not None:
        lines.append(f"1 week ago: {round(prev_week)}/100")
    if prev_month is not None:
        lines.append(f"1 month ago: {round(prev_month)}/100")
    if prev_year is not None:
        lines.append(f"1 year ago: {round(prev_year)}/100")

    # ── Historical daily data ────────────────────────────────────────
    historical = payload.get("fear_and_greed_historical", {})
    data_points = historical.get("data", [])

    if data_points and days > 0:
        # data_points are ordered oldest→newest; take the last `days` entries
        recent = data_points[-days:]
        recent.reverse()  # most recent first

        lines.append(f"\nDaily history (last {min(days, len(recent))} days, most recent first):")
        for point in recent:
            ts_ms = point.get("x", 0)
            score = point.get("y")
            rating = point.get("rating", "?")
            if score is not None:
                date = datetime.fromtimestamp(
                    ts_ms / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d")
                lines.append(
                    f"{date} | Score: {round(score)}/100 | {_format_rating(rating)}"
                )

    # ── Sub-indicator snapshot ───────────────────────────────────────
    _SUB_INDICATORS = [
        ("market_momentum_sp500", "Market Momentum (S&P 500)"),
        ("stock_price_strength", "Stock Price Strength"),
        ("stock_price_breadth", "Stock Price Breadth"),
        ("put_call_options", "Put/Call Options"),
        ("market_volatility_vix", "Market Volatility (VIX)"),
        ("junk_bond_demand", "Junk Bond Demand"),
        ("safe_haven_demand", "Safe Haven Demand"),
    ]

    sub_lines = []
    for key, label in _SUB_INDICATORS:
        sub = payload.get(key, {})
        sub_score = sub.get("score")
        sub_rating = sub.get("rating", "?")
        if sub_score is not None:
            sub_lines.append(
                f"  {label}: {round(sub_score)}/100 ({_format_rating(sub_rating)})"
            )

    if sub_lines:
        lines.append("\nSub-indicators:")
        lines.extend(sub_lines)

    return "\n".join(lines)


def _format_rating(rating: str) -> str:
    """Capitalise a CNN rating string like 'extreme fear' → 'Extreme Fear'."""
    if not rating or rating == "?":
        return "?"
    return rating.replace("_", " ").title()
