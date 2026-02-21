# 👤 Who Is Benjamin Graham?

Benjamin Graham (1894-1976) is widely considered the father of value investing. He promoted disciplined stock selection based on financial strength, earnings quality, and buying at a discount to intrinsic value.

This project applies a practical, KISS version of Graham-style screening in a fullscreen terminal UI.

> Past performance does not guarantee future results.  
> Investing involves risk.  
> This application does not provide investment advice.  
> Over 20 years, among professional equity investors, more than 90% of funds underperform the market. Stock picking must therefore be approached with great caution.

Classical Graham-style rules:
1. Adequate company size
   - Avoid very small companies with fragile access to financing and limited reporting quality.
   - In practice, this is often implemented with minimum revenue or market-cap thresholds.
2. Strong financial condition
   - Balance-sheet resilience is central: healthy liquidity and controlled leverage.
   - Typical checks include current ratio, debt versus current assets, and debt service capacity.
3. Earnings stability
   - Prefer businesses with positive earnings over a long period, avoiding repeated deficits.
   - Stability reduces downside risk and improves confidence in valuation inputs.
4. Long dividend record
   - Graham historically favored companies paying regular dividends for many years (often ~20 years).
   - A long dividend history acts as a discipline signal for management and cash generation.
5. Earnings growth
   - Look for sustained, not one-off, profit growth over multi-year windows.
   - CAGR-like approaches are commonly used to smooth noisy year-to-year moves.
6. Moderate price/earnings ratio
   - Classical references often mention a cap around 15x earnings.
   - The spirit is paying a reasonable multiple, not maximum growth premiums.
7. Moderate price/book ratio
   - Classical references often mention a cap near 1.5x book value.
   - Combined with P/E, this aims to avoid overpaying for low-quality balance sheets.

Reference:
- [Benjamin Graham formula](https://en.wikipedia.org/wiki/Benjamin_Graham_formula)
- [The Intelligent Investor](https://en.wikipedia.org/wiki/The_Intelligent_Investor)

# 🚀 Installation

## 🧰 Prerequisites
- Python 3.11+
- Internet access (for yfinance and optional LLM calls)

## 🐧 Ubuntu
```bash
sudo apt install pipx
pipx ensurepath
pipx install .
graham
```

## 🍎 macOS
```bash
brew install pipx
pipx ensurepath
pipx install .
graham
```

## 🪟 Windows
```bash
py -m pip install --user pipx
py -m pipx ensurepath
pipx install .
graham
```

## 🔁 Alternative (pip)
```bash
python -m pip install .
graham
```

# 💻 Usage

- `graham` launches the fullscreen TUI.
- `graham --help` shows a minimal CLI help.

The app uses one input box at the bottom:
- slash commands (`/help`, `/scan`, ...)
- free prompt mode (if a ticker is selected, it behaves like `/explain <ticker> "..."`)

# 📊 Product Flow

KISS pipeline:
1. Load a universe from `universes/*.txt`
2. Compute fundamentals once
3. Refresh prices every `X` seconds
4. Recompute Margin of Safety (MoS)
5. Rank by:
   - `score` descending
   - `MoS` descending
   - `P/E` ascending

Ranking columns:
- `rank | ticker | score | price | V | MoS | P/E | P/B | dividend`

Score formula:
- `PASS / scored_criteria`
- `N/A` criteria are excluded from the denominator

# 🧠 Graham Logic

7 implemented criteria:
1. S&P earnings/dividend rating >= B
   - Not available in yfinance -> `N/A`
   - Ignored in score if `N/A`
2. Total debt / current assets < 1.10
3. Current ratio > 1.50
4. Positive EPS growth over ~5 years with no deficit (best effort if data is partial)
5. P/E <= 9.0
6. P/B < 1.20
7. Dividends required by default (`dividendRate > 0`)

This app intentionally uses stricter default thresholds for criteria 5 and 6 (`P/E <= 9.0`, `P/B < 1.20`) to stay conservative.

Intrinsic value formula:
- `V = EPS * (8.5 + 2g) * 4.4 / Y`
- `Y` configurable (default `4.4`)
- `g = EPS CAGR` if available, otherwise `0`
- `MoS = (V - price) / price`

Important: the Graham formula should be used with caution in modern markets. Accounting standards, sector composition, intangible assets, and interest-rate regimes have changed significantly since the original framework.

Robustness policy:
- Missing data => show `N/A` with an explanatory note.
- Never crash by design (errors are captured and logged when possible).

# 🧭 Slash Commands

- `/help`
- `/universes`
- `/languages`
- `/lang [language-code]`
- `/model [none|model-name]`
- `/universe [sample|world|usa|emerging_markets|europe|france|japan|custom:path]`
- `/default-universe [name|custom:path]`
- `/scan [--top N] [--min-score N] [--refresh SECONDS]`
- `/screen TICKERS_CSV`
- `/explain [TICKER] [optional question]`
- `/rating GREEN ORANGE`
- `/export [csv|json]`

# ✨ Autocompletion

Context-aware autocompletion in the input overlay:
- `/` -> command list
- `/lang` -> common language codes (`en`, `fr`, `es`, `de`, ...)
- `/model` -> `none` + model examples
- `/universe` -> available universes + `custom:path`
- `/default-universe` -> available presets
- `/export` -> `csv/json`
- `/scan` -> `--top`, `--min-score`, `--refresh`

Keyboard:
- `↑` `↓` move in suggestions
- `TAB` complete
- `ENTER` accept

# 🤖 Optional LLM

Default model: `none`

- `none` means no LLM API call
- if a model is set, `/explain` can call `litellm`
- if LLM call fails, the app logs the error and falls back to a deterministic template
- `/model` accepts any valid provider model ID; the built-in suggestion list contains verified official IDs.
- Your selected model is persisted in `~/.graham/config.json`.

Environment variables (depending on provider):
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`

Examples:
```text
/model gpt-5.2
/model claude-opus-4-5
/model gemini-3-pro-preview
```

Configure API keys in your shell before launching `graham`:
```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="..."
export GEMINI_API_KEY="..."
graham
```

# 🌍 Display Language

- Default display language is English (`en`).
- List supported language codes:

```text
/languages
```

- Change language at runtime with:

```text
/lang fr
```

- Translation uses `deep-translator` (Google Translate backend), not LLMs.
- If translation fails for any reason, the app keeps English text (safe fallback).
- Your chosen language is persisted in `~/.graham/config.json`.

# 🎯 Score Rating

- The ranking now includes a visual rating badge:
  - `🟢` if score is above the green threshold
  - `🟠` if score is between orange and green thresholds
  - `🔴` otherwise
- Configure thresholds at runtime:

```text
/rating 0.80 0.60
```

You can also pass percentages:

```text
/rating 80 60
```

# 🌐 Universe Presets

Available universe files now include:
- `sample`
- `world`
- `usa`
- `emerging_markets`
- `europe`
- `france`
- `japan`

Set and persist your default universe:

```text
/default-universe world
```

Your latest selected universe is saved in `~/.graham/config.json` and automatically reused on next launch.

List all universes with metadata:

```text
/universes
```

# 🗂️ Project Structure

```text
graham_agent/
  main.py
  tui.py
  graham.py
  commands.py
  llm.py
universes/
  sample.txt
tests/
  test_graham.py
```

# 🧪 Tests

```bash
pytest
```
