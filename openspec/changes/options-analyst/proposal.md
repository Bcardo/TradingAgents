## Why

No analyst in the current pipeline looks at options market data. Options flow — specifically
call/put volume skew, Vol/OI ratios, and OTM buying — is one of the strongest short-term
directional signals available, widely used by professional traders to detect informed positioning
before price moves. Short interest (squeeze potential) is a related signal that pairs naturally
with options flow. Both are freely available via yfinance with no API key.

## What Changes

- **New analyst node**: `Options Analyst` — selector key `"options"`, slots between Market and
  Social in the default analyst sequence
- **New dataflow**: `tradingagents/dataflows/options_flow.py` — fetches and formats the options
  chain for a ticker via yfinance (capped at 4 expirations, 7–60 DTE filter); returns
  call/put volume totals, Vol/OI leaders, call/put skew, and OTM call activity
- **New dataflow**: `tradingagents/dataflows/short_interest.py` — fetches short interest %
  float via `yf.Ticker(ticker).info["shortPercentOfFloat"]`; returns a formatted one-liner
- **New tools**: `tradingagents/agents/utils/options_tools.py` — two `@tool`-decorated wrappers:
  `get_options_flow(ticker)` and `get_short_interest(ticker)`
- **New analyst**: `tradingagents/agents/analysts/options_analyst.py` — LLM node that calls
  both tools, then writes an `options_report`
- **Update** `agent_states.py` — add `options_report` field to `AgentState`
- **Update** `conditional_logic.py` — add `should_continue_options` method
- **Update** `setup.py` — add `"options"` if-block (follows same pattern as existing analysts)
- **Update** `trading_graph.py` — add `"options"` ToolNode; include `options_report` in
  `_log_state`; add `"options"` to default `selected_analysts`
- **Update** `interface.py` — add `get_options_flow` and `get_short_interest` to
  `VENDOR_METHODS` and `TOOLS_CATEGORIES`
- **Update** `default_config.py` — add `"options_data": "default"` to `data_vendors`;
  add `"options"` to default `selected_analysts` list
- **Update** `agents/__init__.py` — export `create_options_analyst`
- **New tests**: mock-based tests for `options_flow.py` and `short_interest.py`

## Capabilities

### New Capabilities

- `options-flow`: Fetch the live options chain for a ticker — call/put volume totals,
  highest Vol/OI contracts per expiration, call/put skew, and OTM call concentration.
  Covers up to 4 expirations in the 7–60 DTE window. Free via yfinance.
- `short-interest`: Fetch short interest % of float for a ticker via yfinance.info.
  One value, no scraping. Used to identify squeeze setups when combined with bullish
  options flow.

### Modified Capabilities

- Default analyst sequence changes from `["market", "social", "news", "fundamentals"]`
  to `["market", "options", "social", "news", "fundamentals"]`

## Impact

- **Files added**: `tradingagents/dataflows/options_flow.py`,
  `tradingagents/dataflows/short_interest.py`,
  `tradingagents/agents/analysts/options_analyst.py`,
  `tradingagents/agents/utils/options_tools.py`,
  `tests/test_options_tools.py`
- **Files modified**: `agent_states.py`, `conditional_logic.py`, `setup.py`,
  `trading_graph.py`, `interface.py`, `default_config.py`, `agents/__init__.py`
- **Dependencies added**: none — yfinance already in pyproject.toml
- **New env vars**: none
- **Speed impact**: Options chain fetch adds ~4 yfinance HTTP calls per run (one per
  expiration). Acceptable given LLM invocation latency already dominates.
- **Breaking changes**: `options_report` is a new required field in `AgentState` —
  existing log files will not have this field (backward-compatible for reading, but
  new runs will always populate it)
