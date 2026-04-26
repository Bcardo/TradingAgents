## ADDED Requirements

### Requirement: Result persists across page refresh
The system SHALL save the completed analysis result and form inputs (ticker, date, analysts) to browser `localStorage` via `gr.BrowserState` when an analysis completes.

#### Scenario: Result restored after page refresh
- **WHEN** a user has previously completed an analysis
- **THEN** the result markdown, ticker, date, and analyst selection SHALL be restored automatically on the next page load without any user action

#### Scenario: Empty state on first visit
- **WHEN** a user visits the app for the first time with no `localStorage` entry
- **THEN** the form SHALL display default values (ticker="SPY", today's date, default analysts) and result area SHALL be empty

### Requirement: Result persists across server restart
The system SHALL store result data client-side (in `localStorage`) so that a server restart does not erase a previously completed result visible to the user.

#### Scenario: Viewing result after server restarts
- **WHEN** a user completed an analysis, the server restarted, and the user refreshes the page
- **THEN** the last result SHALL still be visible without re-running the analysis

### Requirement: Full report written to S3 on completion
When analysis completes and S3 is configured (`S3_MEMORY_BUCKET` env var set), the system SHALL upload the full formatted result markdown to the fixed S3 key `reports/last_report.md` immediately after uploading the memory log.

#### Scenario: S3 report upload on success
- **WHEN** `run_analysis` yields its final result and S3 is configured
- **THEN** the full formatted markdown SHALL be uploaded to `reports/last_report.md` in the configured S3 bucket

#### Scenario: No-op when S3 not configured
- **WHEN** `S3_MEMORY_BUCKET` is not set
- **THEN** no S3 upload SHALL be attempted and no error SHALL be raised

### Requirement: S3 report restored when BrowserState is empty
On page load, if `BrowserState.result` is empty and S3 is configured, the system SHALL attempt to download `reports/last_report.md` from S3 and populate the result area. This covers the case where the user switched away mid-run and the browser discarded the tab before the result was delivered.

#### Scenario: Full report restored from S3 after mobile app-switch
- **WHEN** a user switched away during an analysis, the analysis completed server-side, and the user returns to a freshly loaded page with empty BrowserState
- **THEN** the full report markdown SHALL be fetched from S3 and displayed in `result_box`
- **AND** BrowserState SHALL be updated with the fetched result so subsequent reloads do not hit S3 again

#### Scenario: S3 key missing — graceful fallback
- **WHEN** `BrowserState.result` is empty, S3 is configured, but `reports/last_report.md` does not exist (e.g. first ever run)
- **THEN** the result area SHALL remain empty and no error SHALL be shown

### Requirement: BrowserState updated on analysis completion
The system SHALL update the `gr.BrowserState` component at the final yield of `run_analysis`, storing the full formatted result markdown along with the ticker, date, and analyst values used.

#### Scenario: BrowserState written when analysis succeeds
- **WHEN** `run_analysis` yields its final result
- **THEN** the `gr.BrowserState` SHALL be updated with ticker, date, analysts, and result fields

#### Scenario: BrowserState not written on error
- **WHEN** `run_analysis` yields an error result
- **THEN** the `gr.BrowserState` result field SHALL NOT be updated with error text
