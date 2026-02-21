# 🚀 Installation

## 🧰 Prerequis
- Python 3.11+
- Connexion internet (yfinance / LLM optionnel)

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

## 🔁 Alternative pip
```bash
python -m pip install .
graham
```

# 💻 Utilisation

- `graham` lance directement la TUI fullscreen.
- `graham --help` affiche l'aide CLI minimale.

Dans la TUI, utilisez un input unique en bas:
- slash commands (`/help`, `/scan`, etc.)
- prompt libre (si un ticker est selectionne, cela equivaut a `/explain <ticker> "..."`)

# 📊 Fonctionnement

Pipeline KISS:
1. Charger un univers depuis `universes/*.txt`
2. Calculer les fondamentaux une fois
3. Rafraichir le prix toutes les `X` secondes
4. Recalculer la marge de securite (MoS)
5. Trier par:
   - `score` desc
   - `MoS` desc
   - `P/E` asc

Colonnes ranking:
- `rank | ticker | score | price | V | MoS | P/E | P/B | dividend`

Score:
- `PASS / criteres scores`
- Les `N/A` sont exclus du denominateur

# 🧠 Logique Graham

Reference:
- https://fr.wikipedia.org/wiki/Formule_de_Benjamin_Graham

7 criteres implementes:
1. Note S&P earnings/dividend rating >= B
   - Non disponible via yfinance -> `N/A`
   - N'entre pas dans le score si `N/A`
2. Dette totale / actif courant < 1.10
3. Current ratio > 1.50
4. EPS croissance positive ~5 ans sans deficit (best effort)
5. P/E <= 9.0
6. P/B < 1.20
7. Dividendes (`dividendRate > 0`, requis par defaut)

Formule valeur intrinseque:
- `V = EPS * (8.5 + 2g) * 4.4 / Y`
- `Y` configurable (defaut `4.4`)
- `g = CAGR EPS` si disponible sinon `0`
- `MoS = (V - price) / price`

Regle de robustesse:
- Si une donnee manque: afficher `N/A` + note explicative.
- Jamais crash: erreurs capturees et logguees.

# 🧭 Slash Commands

- `/help`
- `/model [none|model-name]`
- `/universe [sample|sp500|cac40|custom:path]`
- `/scan [--top N] [--min-score N] [--refresh SECONDS]`
- `/screen TICKERS_CSV`
- `/explain [TICKER] [question optionnelle]`
- `/export [csv|json]`

# ✨ Autocompletion

Autocompletion contextuelle (ListView Textual):
- `/` -> commandes disponibles
- `/model` -> `none` + exemples de modeles
- `/universe` -> univers disponibles + `custom:path`
- `/export` -> `csv/json`
- `/scan` -> options `--top`, `--min-score`, `--refresh`

Clavier:
- `↑` `↓` pour naviguer
- `TAB` pour completer
- `ENTER` pour valider la suggestion

# 🤖 LLM Optionnel

Modele par defaut: `none`

- `none` = aucun appel LLM
- si modele actif, `/explain` peut appeler `litellm`
- en cas d'echec LLM: erreur + fallback deterministe

Variables d'environnement possibles:
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`

Exemple:
```text
/model gpt-4.1-mini
```

# 🗂️ Structure

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
