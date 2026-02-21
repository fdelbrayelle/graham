# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

## [0.3.4] - 2026-02-21

### Added
- Alternative market-data provider support via `defeatbeta-api` with adapter coverage tests.
- Provider selection through `GRAHAM_MARKET_DATA_PROVIDER` while keeping transparent fallback behavior.
- Additional regression tests for provider fallback paths in fundamentals scans and index constituent loading.

### Changed
- Fundamentals scans now process symbols in batches of 30 for more stable large-universe execution.
- Fundamentals analysis results are cached in-memory for 15 minutes to reduce repeated provider calls.
- Index loading reliability improved for `sp500` and `nasdaq100` with dedicated public constituent source handling.

### Fixed
- Restored `yfinance` as the default provider to avoid sparse-data regressions when optional providers are incomplete.
- Added robust fallback from sparse `defeatbeta` payloads to `yfinance` for both screening metrics and index constituents.
- Corrected `defeatbeta-api` dependency constraint to a published version range for successful `pipx` installs.

## [0.3.3] - 2026-02-21

### Changed
- `/explain` LLM responses are now rendered as Markdown in the output panel, matching `/moat` readability.
- LLM output handling now auto-scrolls the output panel to the start of the newly generated Markdown block.

### Added
- Regression tests for `/explain` and `/moat` Markdown rendering and scroll targeting in the TUI.

## [0.3.2] - 2026-02-21

### Added
- Clear `Features` section in `README.md` to highlight core product capabilities.

### Changed
- `/moat` LLM responses are now rendered as Markdown in the output panel for improved readability.

## [0.3.1] - 2026-02-21

### Added
- API response cache (non-yfinance) with 1 hour TTL for index constituent loaders.
- Company name override reconciliation for index sources (Nikkei/TOPIX/Wikipedia-derived providers).

### Changed
- `/indices` pipeline now passes source company metadata into the scan engine before yfinance enrichment.
- `/moat` keeps the detailed startup log (`with model ...`) while avoiding duplicated start output.

### Fixed
- Resolved TUI shutdown crashes (`NoMatches '#log'`) by making background logging/loading indicators safe after unmount.
- Improved scan resilience when yfinance `info` fails: keep price/as_of from available snapshots and preserve last valid metrics.
- Reduced yfinance error noise in terminal output and lowered concurrent fundamentals workers to limit transient API failures.

## [0.3.0] - 2026-02-21

### Added
- New `/keys` command and `F1` shortcut to quickly display keyboard shortcuts in the output panel.
- Keyboard shortcuts `Ctrl+L` (clear outputs) and `Ctrl+R` (ticker/company search mode on the top table).
- Dynamic index constituent loaders for `nikkei225`, `topix`, `cac40`, `dax40`, `dowjones`, and `eurostoxx` using public sources.
- Immediate command start feedback plumbing (`command_feedback`) with tests for slash commands.

### Changed
- Slash commands now always write an immediate output message when validated, even while long-running work is in progress.
- `/indices` fetching now combines dynamic market/provider sources with existing fallbacks and persists generated universes with updated source note text.
- Top-table search filtering now matches both `ticker` and `company`.

### Fixed
- Autocompletion argument replacement for commands like `/moat` and `/lang` when validating suggestions.
- `/moat` prompt language now follows persisted language configuration from `~/.graham/config.json`.

## [0.2.0] - 2026-02-21

### Added
- New `/moat TICKER` command that requests an economic moat analysis through the configured LLM model.
- Loading feedback for `/moat` requests so users get immediate progress information.
- Prompt history navigation in the input panel with `↑/↓`.
- Click-to-copy interactions for output blocks and details/criteria panel.

### Changed
- `/moat` prompt now asks the model to answer in the display language configured via `/lang`.
- LLM model resolution now supports broader provider inference and clearer `provider/model` guidance.
- Suggestion list behavior improved: stable cyclic navigation, visible selected item, and 8 visible lines in the suggestions panel.

### Fixed
- Improved clipboard reliability with system clipboard fallbacks for terminal environments.

## [0.1.1] - 2026-02-21

### Added
- Automated release workflow for GitHub + PyPI publication on version tags (`v*`).
- Release documentation for GitHub + PyPI Trusted Publishing.

### Changed
- PyPI distribution name changed to `graham-agent`.
- CI test workflow updated to install the package before pytest and run on supported Python versions.

## [0.1.0] - 2026-02-21

### Added
- Initial release of `graham` with fullscreen TUI screening and command interface.
