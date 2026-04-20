from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_market_fear_greed(
    days: Annotated[int, "Number of past days to fetch (default 7)"] = 7,
) -> str:
    """
    Fetch the CNN Fear & Greed Index time series from alternative.me.
    Returns one entry per day with a numeric score (0–100) and classification
    label (Extreme Fear / Fear / Neutral / Greed / Extreme Greed).
    This is a market-wide macro signal — not ticker-specific. Use it to
    contextualise retail sentiment against the broader market mood.
    """
    return route_to_vendor("get_market_fear_greed", days)


@tool
def get_unusual_whales_discord(
    ticker: Annotated[str, "Stock ticker symbol to filter alerts for, e.g. NVDA"],
) -> str:
    """
    Fetch recent Unusual Whales options flow alerts for a ticker from a
    configured Discord channel. Returns matching alerts from the last 24 hours
    in the format: timestamp | TICKER $STRIKE Call/Put EXPIRY.
    Requires DISCORD_TOKEN and DISCORD_UW_CHANNEL_ID environment variables.
    Returns empty string silently when env vars are not configured.
    """
    return route_to_vendor("get_unusual_whales_discord", ticker)


@tool
def get_reddit_sentiment(
    ticker: Annotated[str, "Stock ticker symbol, e.g. NVDA or AAPL"],
    days: Annotated[int, "Number of past days to search for posts (default 3)"] = 3,
) -> str:
    """
    Fetch recent Reddit posts mentioning a stock ticker from investing subreddits
    (r/wallstreetbets, r/stocks, r/options). Returns post titles, upvote scores,
    comment counts, and upvote ratios as a formatted string. This is a
    ticker-specific retail sentiment signal, not a news source.
    Automatically searches by both ticker symbol and company name (e.g. NVDA OR
    Nvidia) so posts using the company name are not missed.
    Returns an empty string on API failure; returns a 'no posts found' message
    for obscure tickers with no Reddit coverage.
    """
    return route_to_vendor("get_reddit_sentiment", ticker, days)
