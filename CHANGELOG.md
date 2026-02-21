# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

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
