## Why

On mobile, users frequently switch apps or let the screen go off during the 5–15 minute analysis run. When they return — especially after a server restart hours later — the page is blank and they must re-run from scratch. The result should survive both the browser session and the server lifecycle.

## What Changes

- Add `gr.BrowserState` to persist the last analysis result (full formatted markdown) and input values (ticker, date, analysts) in the browser's `localStorage` — restored automatically on every page load
- Add a history panel above the form that reads from `TradingMemoryLog` on page load, displaying all past analyses (ticker, date, rating, decision snippet) with click-to-fill behaviour

## Capabilities

### New Capabilities
- `browser-result-persistence`: Saves completed analysis result and form inputs to `localStorage` via `gr.BrowserState`; restores them on page load so the result survives refresh and server restarts
- `analysis-history-panel`: Displays a scrollable list of all past analyses from `TradingMemoryLog` on page load; clicking a row pre-fills the ticker and date inputs for easy re-run

### Modified Capabilities

## Impact

- `web/app.py` — only file changed
- Requires Gradio ≥ 5.x (`gr.BrowserState` API); project runs Gradio 6.13.0 ✓
- No new dependencies
- No breaking changes to existing analysis flow
