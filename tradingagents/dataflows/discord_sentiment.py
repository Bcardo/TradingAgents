# -*- coding: utf-8 -*-
"""
Unusual Whales Discord alert fetching via Discord HTTP API v10.

LOCAL ONLY — never commit this file or any reference to
get_unusual_whales_discord upstream.

Requires:
    DISCORD_TOKEN        — user token for the Discord account that has
                           joined the Unusual Whales server
    DISCORD_UW_CHANNEL_ID — channel ID of the UW alerts channel

Both env vars must be present; the tool silently returns "" when either
is absent, so the rest of the sentiment analyst continues unaffected.
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

_API_BASE = "https://discord.com/api/v10"
_TIMEOUT = 10
_MESSAGE_LIMIT = 50

# UW bot embed format: TICKER STRIKE C/P MM/DD/YYYY
# e.g. "NVDA 115.50 C 05/16/2025"  or  "AAPL 200 P 01/17/2025"
_UW_PATTERN = re.compile(
    r"\b([A-Z]{1,5})\s+(\d+(?:\.\d+)?)\s+([CP])\s+(\d{2}/\d{2}/\d{4})\b"
)


def get_discord_uw_alerts(ticker: str) -> str:
    """
    Fetch recent Unusual Whales options flow alerts for a ticker from Discord.

    Reads the last 50 messages from the configured Discord channel, parses
    UW bot embed format (TICKER STRIKE C/P EXPIRY), and returns all alerts
    matching the ticker from the last 24 hours.

    Returns empty string when env vars are absent (no HTTP call made),
    or on any API error. Returns a 'no alerts found' message when the
    channel was fetched successfully but no matching alerts exist.

    Args:
        ticker: Stock ticker symbol to filter alerts for (e.g., "NVDA")

    Returns:
        Formatted string of matching alerts, empty string on failure/unconfigured.
    """
    token = os.getenv("DISCORD_TOKEN", "")
    channel_id = os.getenv("DISCORD_UW_CHANNEL_ID", "")

    if not token or not channel_id:
        return ""

    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
    }

    try:
        r = requests.get(
            f"{_API_BASE}/channels/{channel_id}/messages",
            params={"limit": _MESSAGE_LIMIT},
            headers=headers,
            timeout=_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.warning("Discord API request failed: %s", e)
        return ""

    if r.status_code in (401, 403):
        logger.warning("Discord API returned HTTP %s — check DISCORD_TOKEN and channel access", r.status_code)
        return ""
    if not r.ok:
        logger.warning("Discord API returned HTTP %s", r.status_code)
        return ""

    r.encoding = "utf-8"
    try:
        messages = r.json()
    except ValueError:
        logger.warning("Discord API returned invalid JSON")
        return ""

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    ticker_upper = ticker.upper()
    alerts = []

    for msg in messages:
        # Parse timestamp
        try:
            msg_time = datetime.fromisoformat(msg.get("timestamp", "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if msg_time < cutoff:
            continue

        # Search both plain content and all embed descriptions/titles
        texts = [msg.get("content", "")]
        for embed in msg.get("embeds", []):
            texts.append(embed.get("description", ""))
            texts.append(embed.get("title", ""))

        for text in texts:
            for match in _UW_PATTERN.finditer(text or ""):
                match_ticker, strike, side, expiry = match.groups()
                if match_ticker != ticker_upper:
                    continue
                alerts.append({
                    "ticker": match_ticker,
                    "strike": strike,
                    "side": "Call" if side == "C" else "Put",
                    "expiry": expiry,
                    "timestamp": msg_time.strftime("%Y-%m-%d %H:%M UTC"),
                })

    if not alerts:
        return f"No Unusual Whales Discord alerts found for {ticker_upper} in the last 24 hours."

    lines = [f"Unusual Whales Discord alerts for {ticker_upper} (last 24h):\n"]
    for a in alerts:
        lines.append(
            f"{a['timestamp']} | {a['ticker']} ${a['strike']} {a['side']} {a['expiry']}"
        )

    return "\n".join(lines)
