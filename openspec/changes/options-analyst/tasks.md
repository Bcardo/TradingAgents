## 1. Options Flow Dataflow

- [x] 1.1 Create `tradingagents/dataflows/options_flow.py` — implement `get_options_flow_data(ticker)`
  that calls `yf.Ticker(ticker).options` to get expiration dates, filters to 7–60 DTE,
  fetches up to 4 expirations via `tk.option_chain(exp)`, and returns a formatted string with:
  call/put volume totals per expiration, top 3 contracts by Vol/OI ratio (calls and puts
  separately), overall call/put skew %, and OTM call volume as % of total call volume
- [x] 1.2 Add graceful handling — return informative message if no expirations exist or all
  are outside the DTE window; return empty string on yfinance exception, log WARNING
- [x] 1.3 Add `get_options_flow` to `VENDOR_METHODS` in `interface.py` with `"default"` key;
  add to `TOOLS_CATEGORIES` under a new `"options_data"` category
- [x] 1.4 Add `"options_data": "default"` to `data_vendors` in `default_config.py`

## 2. Short Interest Dataflow

- [x] 2.1 Create `tradingagents/dataflows/short_interest.py` — implement `get_short_interest_data(ticker)`
  that reads `yf.Ticker(ticker).info["shortPercentOfFloat"]` and returns a formatted one-liner
  e.g. `"Short interest: 18.3% of float"`. Include `shortRatio` (days-to-cover) if available.
- [x] 2.2 Add graceful handling — return `"Short interest data unavailable"` if key missing or
  yfinance raises; log WARNING on exception
- [x] 2.3 Add `get_short_interest` to `VENDOR_METHODS` in `interface.py` with `"default"` key;
  add to `TOOLS_CATEGORIES` under `"options_data"`

## 3. Options Tools (@tool wrappers)

- [x] 3.1 Create `tradingagents/agents/utils/options_tools.py` with two `@tool`-decorated functions:
  - `get_options_flow(ticker)` → calls `route_to_vendor("get_options_flow", ticker)`
  - `get_short_interest(ticker)` → calls `route_to_vendor("get_short_interest", ticker)`
- [x] 3.2 Add `Annotated` type hints with clear descriptions; write docstrings explaining
  what each signal means and when to use it (options flow = directional positioning,
  short interest = squeeze setup context)

## 4. Options Analyst Node

- [x] 4.1 Create `tradingagents/agents/analysts/options_analyst.py` — implement
  `create_options_analyst(llm)` following the exact same pattern as `market_analyst.py`:
  - Binds `[get_options_flow, get_short_interest]` as tools
  - System prompt instructs the LLM to: call `get_options_flow` first to assess directional
    positioning (call/put skew, Vol/OI leaders, OTM speculation level, institutional premium);
    call `get_short_interest` to check squeeze potential; combine both into an `options_report`
    covering: market positioning bias, urgency signals (short DTE + high Vol/OI),
    squeeze risk if short interest is elevated, and key contracts to watch
  - Appends Markdown table summarising key metrics
  - Returns `{"messages": [result], "options_report": report}`

## 5. State and Graph Wiring

- [x] 5.1 Add `options_report: Annotated[str, "Report from the Options Analyst"]` to
  `AgentState` in `agent_states.py`
- [x] 5.2 Add `should_continue_options(state)` to `ConditionalLogic` in `conditional_logic.py` —
  same pattern as existing methods: return `"tools_options"` if last message has tool calls,
  else `"Msg Clear Options"`
- [x] 5.3 Add `"options"` if-block to `setup_graph()` in `setup.py` — same pattern as
  `"market"`, `"social"`, etc. No `_labels` entry needed (`"options".capitalize()` == `"Options"`)
- [x] 5.4 In `trading_graph.py`:
  - Import `get_options_flow` and `get_short_interest` from `options_tools`
  - Add `"options"` ToolNode containing both tools in `_create_tool_nodes()`
  - Add `"options_report"` to the state dict logged in `_log_state()`
  - Add `"options"` to the default `selected_analysts` list in `__init__` signature
- [x] 5.5 Export `create_options_analyst` from `tradingagents/agents/__init__.py`
- [x] 5.6 Update `default_config.py` — add `"options"` to the default `selected_analysts` list;
  add `OPTIONS = "options"` to `AnalystType` in `cli/models.py`; add "Options Analyst" to
  `ANALYST_ORDER` in `cli/utils.py`

## 6. Tests

- [x] 6.1 Create `tests/test_options_tools.py` — mock-based tests for `options_flow.py`:
  - Happy path: mock `yf.Ticker` returning sample calls/puts dataframe → assert output
    contains call/put volumes, Vol/OI ratio, skew percentage
  - No expirations: mock `tk.options` returning `[]` → assert informative message returned
  - All expirations outside DTE window: mock expirations all > 60 DTE → assert informative message
  - yfinance exception: assert returns `""` and no exception raised
- [x] 6.2 Tests for `short_interest.py`:
  - Happy path: mock `tk.info` returning `shortPercentOfFloat=0.15` → assert "15%" in output
  - Key missing from info dict: assert fallback message returned, no exception
  - yfinance exception: assert fallback message returned, no exception
