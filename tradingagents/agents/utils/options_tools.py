from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_options_flow(
    ticker: Annotated[str, "Stock ticker symbol, e.g. NVDA or AAPL"],
) -> str:
    """
    Fetch the live options chain for a stock and return a formatted flow summary.

    Analyzes up to 4 expirations in the 7-60 DTE window. Reports call/put volume
    totals per expiration, the top contracts by Vol/OI ratio (a measure of fresh
    unusual activity vs existing open interest), overall call/put skew across all
    expirations, and OTM call concentration (high OTM call % = speculative
    directional bets, not hedging).

    Use this to assess how options market participants are positioned: bullish call
    dominance, bearish put dominance, or neutral balanced flow. High Vol/OI ratios
    on specific strikes indicate informed or institutional positioning.
    """
    return route_to_vendor("get_options_flow", ticker)


@tool
def get_short_interest(
    ticker: Annotated[str, "Stock ticker symbol, e.g. NVDA or AAPL"],
) -> str:
    """
    Fetch short interest % of float and days-to-cover for a stock via yfinance.

    Short interest % of float measures the proportion of tradeable shares that are
    currently sold short. High short interest (>15%) combined with bullish options
    flow can signal a short squeeze setup — shorts may be forced to cover on any
    upward move, amplifying price gains.

    Days to cover (short ratio) indicates how many average trading days it would
    take for all shorts to cover their positions — higher values mean shorts are
    more trapped.

    Use this alongside get_options_flow: bullish call skew + high short interest
    is a classic squeeze precondition.
    """
    return route_to_vendor("get_short_interest", ticker)
