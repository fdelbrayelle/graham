# 👤 Who Is Benjamin Graham?

Benjamin Graham (1894-1976) is widely considered the father of value investing. He promoted disciplined stock selection based on financial strength, earnings quality, and buying at a discount to intrinsic value.

This project applies a practical, KISS version of Graham-style screening in a fullscreen terminal UI.

Reference:
- https://fr.wikipedia.org/wiki/Formule_de_Benjamin_Graham

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

Intrinsic value formula:
- `V = EPS * (8.5 + 2g) * 4.4 / Y`
- `Y` configurable (default `4.4`)
- `g = EPS CAGR` if available, otherwise `0`
- `MoS = (V - price) / price`

Robustness policy:
- Missing data => show `N/A` with an explanatory note.
- Never crash by design (errors are captured and logged when possible).

# 🧭 Slash Commands

- `/help`
- `/model [none|model-name]`
- `/universe [sample|sp500|cac40|custom:path]`
- `/scan [--top N] [--min-score N] [--refresh SECONDS]`
- `/screen TICKERS_CSV`
- `/explain [TICKER] [optional question]`
- `/export [csv|json]`

# ✨ Autocompletion

Context-aware autocompletion in the input overlay:
- `/` -> command list
- `/model` -> `none` + model examples
- `/universe` -> available universes + `custom:path`
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

Environment variables (depending on provider):
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`

Example:
```text
/model gpt-4.1-mini
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
