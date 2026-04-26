## Context

`web/app.py` is a Gradio 6.13.0 single-file app. Analysis runs in a background Python thread, yielding SSE updates to the client every 2s. When the mobile browser is backgrounded or the server restarts, the SSE stream dies and the result is lost.

Two data sources are already in place:
- `TradingMemoryLog.load_entries()` — returns all past decisions with ticker, date, rating, and full decision text
- S3 sync — memory is downloaded on startup, so history is available even after a server restart

## Goals / Non-Goals

**Goals:**
- Result survives mobile app switch (no refresh)
- Result survives page refresh
- Result survives server restart
- History panel shows all past analyses on login; clicking a row pre-fills inputs

**Non-Goals:**
- In-flight recovery (analysis still running when user returns) — acceptable loss if server restarted
- Per-user history isolation — single shared memory log is fine for personal use
- Full analyst report replay — history shows portfolio manager decision only, not the full breakdown

## Decisions

**`gr.BrowserState` over server-side cache**
Server cache is wiped on restart; the result must live client-side. `gr.BrowserState` writes to `localStorage` automatically, survives refresh, and requires zero JS. Considered: custom `localStorage` JS injection — works on any Gradio version, but adds ~20 lines of JS and has no advantage on Gradio 6.

**Memory log as history source (not a separate store)**
`TradingMemoryLog` is already populated after every run and S3-synced on startup. No new persistence layer needed. The decision text is sufficient for a history panel — full analyst reports are in local JSON log files that don't survive server restarts and are not S3-synced.

**`gr.Dataframe` with `.select()` for history panel**
Gradio's dataframe component fires a `select` event when a row is clicked, returning row index. We use that to pre-fill ticker + date. Considered: `gr.HTML` table — more flexible styling, but no built-in click-to-row event.

**BrowserState shape**
```python
{
  "ticker":   str,   # last used ticker
  "date":     str,   # last used date
  "analysts": list,  # last used analyst selection
  "result":   str,   # full formatted result markdown (empty string if none)
}
```
Storing analysts avoids the user having to re-select their preferred configuration.

**Single fixed S3 key for full-report cache**
`reports/last_report.md` is always overwritten on each completed run. No TTL, no key management, no cleanup needed — each new run is the natural replacement. The S3 fetch only happens when `BrowserState.result` is empty (cold load after mobile app-switch), so it is at most one GET per cold start. On success the result is written back into BrowserState so subsequent reloads skip S3 entirely. Considered keyed by `{ticker}_{date}` — rejected because we only ever need "the last one" and per-key management adds unnecessary complexity.

## Risks / Trade-offs

`localStorage` size limit (~5 MB) → The result markdown is typically 5–20 KB per analysis. No concern in practice.

History panel on every page load calls `load_entries()` which reads the memory file → File is small (append-only markdown), read is fast. No concern.

`gr.BrowserState` restores on load which triggers `demo.load` — if `result` is non-empty, result_box will be populated before the user does anything → Desired behaviour; user sees their last result immediately.

Row select in `gr.Dataframe` only fires when user clicks, not on programmatic update → Pre-fill only happens on user interaction, which is correct.

## Migration Plan

No migration needed. `gr.BrowserState` defaults to empty dict on first load (no prior `localStorage` entry). History panel shows empty dataframe if memory log has no entries. Both degrade gracefully.
