## 1. BrowserState Persistence

- [x] 1.1 Add `gr.BrowserState` component with default shape `{"ticker": "SPY", "date": today, "analysts": [...], "result": ""}` inside the `gr.Blocks` context
- [x] 1.2 Add `demo.load()` handler that reads `saved` and restores `ticker_box`, `date_box`, `analysts_box`, and `result_box` when `result` is non-empty
- [x] 1.3 Add `saved` to `analyze_btn.click` outputs list
- [x] 1.4 Modify `run_analysis` final success yield to include updated `saved` dict (ticker, date, analysts, result); all other yields pass `gr.update()` for the `saved` output

## 3. S3 Full-Report Cache

- [x] 3.1 Add `_s3_upload_report(markdown: str) -> None` — writes full formatted markdown to fixed S3 key `reports/last_report.md` in the existing S3 bucket; no-op if S3 not configured
- [x] 3.2 Add `_s3_download_report() -> str` — reads `reports/last_report.md`; returns `""` if S3 not configured or key missing (404 → silent, no warning)
- [x] 3.3 In `run_analysis` worker thread, after `_s3_upload_memory(_MEMORY_PATH)`, call `_s3_upload_report(formatted_markdown)` so the full report lands in S3 even when the browser was backgrounded during the run
- [x] 3.4 In `demo.load` handler (extends task 1.2): after BrowserState restore, if `saved["result"]` is empty AND `_S3_BUCKET` is set, call `_s3_download_report()`; if non-empty, populate `result_box` AND write the fetched markdown back into `saved` so BrowserState is warm for subsequent reloads (avoids hitting S3 on every cold start)

## 2. Analysis History Panel

- [x] 2.1 Add `load_history()` function that calls `memory_log.load_entries()`, reverses order, and returns a list of `[date, ticker, signal_emoji + rating, decision[:120]]` rows
- [x] 2.2 Instantiate `TradingMemoryLog` at module level (reuse config) so history is available without running an analysis
- [x] 2.3 Add `gr.Dataframe` component above the ticker/date row with headers `["Date", "Ticker", "Signal", "Decision"]`, `interactive=False`, `wrap=True`
- [x] 2.4 Add `demo.load()` call to populate the dataframe from `load_history()` on every page load
- [x] 2.5 Wire `history_df.select()` event to a handler that reads the selected row index and pre-fills `ticker_box` and `date_box`
