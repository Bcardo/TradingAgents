## ADDED Requirements

### Requirement: History panel displays past analyses on page load
The system SHALL render a dataframe above the analysis form showing all past analyses from `TradingMemoryLog`, populated on every page load.

#### Scenario: History shown after server restart
- **WHEN** the server restarts and a user loads the page
- **THEN** the history panel SHALL display all past analyses previously stored in the memory log (retrieved from S3 on startup)

#### Scenario: Empty history on first use
- **WHEN** no analyses have been run yet (memory log is empty)
- **THEN** the history panel SHALL render an empty dataframe with column headers visible

### Requirement: History panel columns
The history panel SHALL display the following columns: Date, Ticker, Signal (emoji + rating), and Decision (first 120 characters of portfolio manager decision text).

#### Scenario: Row content
- **WHEN** the history panel is populated
- **THEN** each row SHALL show date, ticker, signal emoji with rating text, and a truncated decision snippet

### Requirement: Row click pre-fills form inputs
The system SHALL pre-fill the ticker and date inputs when the user clicks a row in the history panel.

#### Scenario: Clicking a history row
- **WHEN** a user clicks any row in the history dataframe
- **THEN** `ticker_box` SHALL be set to that row's ticker and `date_box` SHALL be set to that row's date

### Requirement: Most recent analyses shown first
The history panel SHALL display entries in reverse chronological order (most recent at top).

#### Scenario: Order of entries
- **WHEN** the history panel is populated with multiple entries
- **THEN** the entry with the most recent date SHALL appear in the first row
