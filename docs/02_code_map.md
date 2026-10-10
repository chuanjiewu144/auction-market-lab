# 2. Code structure and class responsibilities

The project separates data preparation, forecasting, quote optimization, execution and reporting. Indicator strategies are functions and named policies; the current implementation does not define one class per strategy.

## Repository map

| Path | Contents |
|---|---|
| `auction_lab/` | Importable Python package and command-line entry point |
| `docs/` | The four project chapters |
| `notebooks/auction_market_lab_colab.ipynb` | Self-contained Colab experiment with graphs |
| `examples/play_api.py` | External bot calling the local HTTP API |
| `tests/` | Automated auction, information, accounting, optimizer and API checks |
| `results/six_players/` | Seed-7 six-player ordinary and stress experiments |
| `results/nine_players/` | Nine-player ordinary, stress and repeated-seed reference results |
| `archive/` | Earlier documentation and earlier experiment versions |
| `GITHUB_SETUP.md` | Upload instructions for this folder |
| `requirements.txt`, `pyproject.toml` | Dependencies and installable package metadata |

Generated experiments should go in `runs/`, which is excluded by `.gitignore`. The curated reference results above remain included in the repository.

## Classes

| Class | File | Responsibilities |
|---|---|---|
| `Config` | `auction_lab/engine.py` | Frozen dataclass containing dates, roster, seed, capital, costs, risk limits, lookback and opponent-model settings. Validates settings at construction. |
| `Game` | `auction_lab/engine.py` | Owns one tournament: data, current date, competitors, equity, logs and opponent learner. Produces observations, validates actions, generates quotes, limits risk, clears RFQs and settles positions. |
| `OpponentQuoteModel` | `auction_lab/opponent.py` | Stores completed auction episodes, estimates a conditional joint scenario distribution and selects a quote by expected profit. |
| `Handler` | Nested inside `serve()` in `auction_lab/api.py` | Subclasses `BaseHTTPRequestHandler`; translates local HTTP requests into `Game` operations and serializes responses/errors. |

There are no `Stock`, `OrderBook` or `Portfolio` classes. Prices/features use pandas DataFrames, and orders/quotes/fills use dictionaries. Equity and transaction logs live inside `Game`. The engine produces daily RFQs rather than maintaining an intraday continuous limit order book.

## Important methods

| Object/method | What happens |
|---|---|
| `Game.__init__()` | Validates the panel, prepares lagged features, selects evaluation dates and the per-game roster, initializes equity and histories. |
| `Game.observation()` | Returns current orders, available lagged features, equity and settings. Hides current outcomes and rival quotes. |
| `Game._round()` | Creates and caches that day's random requests and forecasts. Re-reading the observation does not redraw requests. |
| `Game.history()` | Returns completed bars only. |
| `Game._validate_human()` | Checks an external player's quote schema, tick, symbol and quantity before mutation. |
| `Game._risk_limit()` | Applies stock, volume, volatility and simultaneous gross-capital constraints. |
| `Game.step()` | Fixes all current actions, clears every stock's RFQ, closes all resulting positions, records profit, then updates opponent history. |
| `Game.completed_quotes()` | Returns approved quotes from settled days. |
| `Game.run()` | Repeats `step()` until the configured horizon is complete. |
| `Game.leaderboard()` | Aggregates profit, return, drawdown, filled shares, volume share and other metrics. |
| `OpponentQuoteModel.observe_completed()` | Appends a settled episode; never called before the day's actions are fixed. |
| `OpponentQuoteModel._past()` | Filters history by earlier dates, matching sector and matching customer side. |
| `OpponentQuoteModel._distribution()` | Builds context weights and replays whole joint rival books with paired return residuals. |
| `OpponentQuoteModel.quote()` | Sets a conservative fixed quantity, searches eligible prices and can abstain when fitted expected profit is nonpositive. |

## Functions and modules

| File | Main functions | Role |
|---|---|---|
| `data.py` | `synthetic_data`, `validate_data`, `load_data`, `make_features` | Generate/load prices and construct strictly lagged indicators. |
| `signals.py` | `fit_whitener`, `ridge_predict`, `predict_day`, `whitening_diagnostics` | Fit sector models and produce one return prediction per stock and strategy. |
| `pricing.py` | `stable_seed`, `tick_price` | Reproducible random priorities and directional tick rounding. |
| `engine.py` | `clear_order`, `liquidate` | Price-priority partial fills and long/short cash accounting. |
| `opponent.py` | `scenario_scores` | Exact scenario fills and expected profit for candidate quotes. |
| `report.py` | `save_game`, `plot_game`, `paired_bootstrap`, `write_results_note` | Export audit tables, charts and descriptive comparisons. |
| `api.py` | `serve` | Start the local HTTP server. |
| `__main__.py` | `main` | Parse `demo`, `backtest` and `serve` commands. |

## Python usage

```python
from auction_lab.data import synthetic_data
from auction_lab.engine import Config, Game
from auction_lab.report import save_game

config = Config(days=100, warmup=180, competitors=6, seed=7)
data = synthetic_data(config.warmup + config.days, config.seed)
game = Game(data, config, data_label="SYNTHETIC demonstration").run()
print(game.leaderboard())
save_game(game, "runs/python_example")
```

Set `competitors=9` for the three extra benchmarks. Roster selection belongs to each game, so six-player and nine-player instances can coexist without changing module globals. `Game(..., human=True)` adds the external player named `you`.

## Validation

```bash
python -m unittest discover -s tests -v
```

Version 0.4 has 25 automated tests: the previous 22, with API coverage updated for both roster sizes, plus three roster/report checks. The tests cover price priority and partial fills; reserve prices and outside liquidity; stable ties; long/short cash accounting with zero and optional costs; risk budgets and share conservation; zero closing inventory; atomic invalid actions; past-only training; future-outcome isolation; singular whitening; replay; analytic opponent examples; and a real local API subprocess.

The new checks verify actual roster exclusion in quotes and learning histories, isolation of simultaneous games, unchanged customer inputs across rosters, a valid reporting baseline for six players, and rejection of unsupported roster sizes. The CLI and notebook paths are also exercised when preparing this release. These tests check the simulator's rules, not predictive trading skill.

The archive includes earlier research notes in `PROJECT.md` and `OPPONENT_STRATEGY.md`. Use the four `docs/` chapters for current entry points and defaults.
