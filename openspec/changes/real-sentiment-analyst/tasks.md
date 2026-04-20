## 1. Reddit Sentiment Dataflow

- [x] 1.1 Create `tradingagents/dataflows/reddit_sentiment.py` — implement `get_reddit_sentiment_yfinance(ticker, days)` that calls Reddit public JSON API across r/wallstreetbets, r/stocks, r/options and returns formatted post list (title, score, comments, upvote_ratio, flair)
- [x] 1.2 Add graceful error handling — return empty string on 429/5xx, log WARNING with status code
- [x] 1.3 Add `get_reddit_sentiment` to `VENDOR_METHODS` in `tradingagents/dataflows/interface.py` with `"yfinance"` (default) key mapping to the new implementation

## 2. Fear & Greed Index Dataflow

- [x] 2.1 Create `tradingagents/dataflows/fear_greed.py` — implement `get_fear_greed(days)` calling `https://api.alternative.me/fng/?limit={days}`, return formatted daily entries (date, score, classification)
- [x] 2.2 Add graceful error handling — return empty string on non-200 or timeout, log WARNING
- [x] 2.3 Add `get_market_fear_greed` to `VENDOR_METHODS` in `interface.py`

## 3. Discord UW Dataflow [LOCAL ONLY — not on feat/real-sentiment]

> These tasks are implemented directly on `local/my-trading` after merging feat/real-sentiment.
> Never commit discord_sentiment.py or any reference to get_unusual_whales_discord upstream.

- [x] 3.1 Create `tradingagents/dataflows/discord_sentiment.py` — implement `get_discord_uw_alerts(ticker)` reading `DISCORD_TOKEN` + `DISCORD_UW_CHANNEL_ID` env vars, fetching last 50 messages from Discord HTTP API v10, parsing UW embed format regex `([A-Z]{1,5})\s+\d+(?:\.\d+)?\s+[CP]\s+\d{2}/\d{2}/\d{4}`, filtering to last 24h
- [x] 3.2 Return empty string (no HTTP call) when either env var is absent
- [x] 3.3 Handle 401/403 from Discord API — log WARNING with status, return empty string

## 4. Sentiment Tools (@tool wrappers)

- [x] 4.1 Create `tradingagents/agents/utils/sentiment_tools.py` with three `@tool`-decorated functions following the pattern in `core_stock_tools.py`:
  - `get_reddit_sentiment(ticker, days)` → calls `route_to_vendor("get_reddit_sentiment", ...)`
  - `get_market_fear_greed(days)` → calls `route_to_vendor("get_market_fear_greed", ...)`
  - `get_unusual_whales_discord(ticker)` → calls `route_to_vendor("get_unusual_whales_discord", ...)`
- [x] 4.2 Add `Annotated` type hints to all parameters with clear descriptions
- [x] 4.3 Write docstrings: Reddit and Discord are ticker-specific; Fear & Greed is market-wide macro signal

## 5. Update Sentiment Analyst

- [x] 5.1 Update `tradingagents/agents/analysts/social_media_analyst.py` — import the three new tools, replace `tools = [get_news]` with `tools = [get_reddit_sentiment, get_market_fear_greed, get_unusual_whales_discord]`
- [x] 5.2 Rewrite the system message to accurately describe the analyst's capabilities: Reddit retail sentiment, Fear/Greed macro context, optional UW options flow — remove the false "social media posts" framing
- [x] 5.3 Add instruction for handling empty results (e.g., no Reddit posts for obscure tickers)

## 6. Wire Into Graph

- [x] 6.1 Update `tradingagents/graph/trading_graph.py` — in `_create_tool_nodes()`, replace the `"social"` ToolNode contents with `[get_reddit_sentiment, get_market_fear_greed, get_unusual_whales_discord]`; update imports
- [x] 6.2 Update `tradingagents/graph/setup.py` — rename node label from `"Social Analyst"` to `"Sentiment Analyst"` in `add_node()` call; keep selector key `"social"` and `should_continue_social` unchanged

## 7. Environment Variables

- [ ] 7.1 ~~Add to `.env.example`: `DISCORD_TOKEN=` and `DISCORD_UW_CHANNEL_ID=`~~ — skipped (Discord is local-only, not going upstream)

## 8. Tests

- [x] 8.1 Create `tests/test_sentiment_tools.py` — mock-based tests for `reddit_sentiment.py`:
  - Happy path: mock `requests.get` returning sample posts → assert formatted output contains title, score, comments
  - No posts: mock returning empty `children` list → assert "no posts found" in output
  - 429 response: assert returns `""` and no exception raised
- [x] 8.2 Tests for `fear_greed.py`:
  - Happy path: mock returning 7 days of data → assert 7 entries in output with score and label
  - API failure: mock 500 → assert returns `""` and no exception
- [x] 8.3 Tests for `discord_sentiment.py`:
  - Env vars absent: assert returns `""` and no HTTP call made (mock `requests.get` not called)
  - Happy path with env vars: mock returning UW bot embed messages → assert ticker extracted correctly
  - 401 from Discord: assert returns `""` and no exception
  - No matching ticker in messages: assert "no alerts found" in output
