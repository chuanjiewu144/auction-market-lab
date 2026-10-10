# Auction Market Lab

A reproducible financial-mathematics project and local Python API for competitive stock RFQ auctions. Six forecasting/quoting strategies compete on the same customer requests; three optional benchmarks expand the tournament to nine players.

**The bundled experiments use synthetic prices and simulated execution.** Historical CSV input is supported. The research question is how predictive signals, execution competition and customer information affect realized market-making profit.

[1. Market and API](#1-market-background-and-api) · [2. Code](#2-code-structure) · [3. Strategies](#3-strategies) · [4. Results](#4-results-and-interpretation)

## 1. Market background and API

| Setting | Default |
|---|---|
| Stock universe | Nine stocks: three technology, three commodity-related, three financial |
| Customer flow | One random buy/sell request per stock per day; nine daily RFQs |
| Competitors | Six research strategies; optionally nine including three benchmarks |
| Timeline | 180 warm-up dates followed by 100 evaluation dates |
| Forecast training | Refit daily using the latest 126 completed dates within each sector |
| Starting capital | 1,000,000 cash units per player |
| Costs and inventory | Zero trading costs; all positions closed each evening |
| Optional stress | 35% probability per request of an informed customer |

Every player can act on all nine requests. A customer sell goes to the highest eligible dealer bids; a customer buy goes to the lowest eligible asks. Winners trade at their own quotes, partial fills are allowed, and equal-price ties use a seeded lottery. An outside dealer fills residual demand at the customer's reserve price. The opening price is supplied externally; this is an RFQ game, not an exchange opening-price auction.

### Run an experiment

Use Python 3.10 or newer, from this repository's root:

```bash
python -m pip install -r requirements.txt
python -m auction_lab demo --players 6 --days 100 --seed 7 --out runs/six
```

The output includes `overview.png`, daily P&L, a leaderboard, orders, quotes, trades and diagnostics. Select all nine players and optional stress/repeated-seed experiments with:

```bash
python -m auction_lab demo --players 9 --days 100 --seed 7 --stress --repetitions 20 --out runs/nine
```

The stress run uses the same prices and requested quantities, but sometimes chooses the customer side using knowledge of the eventual price direction. Stress is off unless `--stress` is supplied. The twenty repetitions use new synthetic price/order seeds, separately from the main run and stress scenario.

For historical prices:

```bash
python -m auction_lab backtest --data prices.csv --players 6 --warmup 180 --days 100 --out runs/historical
```

Required columns are `date,symbol,sector,open,close,volume`, with at least 280 complete dates per stock for the defaults. The first 180 dates provide pre-test history; each daily regression still uses a rolling 126-date window. Customer flow and execution remain simulated in historical mode.

### Use the API or Colab

```bash
python -m auction_lab serve --port 8000
# In another terminal:
python examples/play_api.py
```

`POST /games` creates a game, `GET /games/{id}` supplies the observation, `POST /games/{id}/step` accepts quotes and settles one day, and `GET /games/{id}/results` returns performance. Completed price/quote histories have their own endpoints. A creation body such as `{"days":100,"warmup":180,"seed":7,"competitors":6}` selects six built-in bots **plus your external player**. API games therefore have seven or ten participants. Current rival quotes are sealed; approved quotes are disclosed after settlement.

For Colab, upload [the self-contained notebook](notebooks/auction_market_lab_colab.ipynb), select six/nine players and optional stress, and run the cells. CPU is sufficient.

See [market rules, data generation and the full API](docs/01_market_and_api.md). To publish this folder, follow [GitHub setup](GITHUB_SETUP.md).

## 2. Code structure

| Location | Responsibility |
|---|---|
| `auction_lab/data.py` | Synthetic/historical prices, validation, lagged indicators |
| `auction_lab/signals.py` | Sector regressions, feature whitening, return forecasts |
| `auction_lab/engine.py` | `Config`, `Game`, auction clearing, risk limits and settlement |
| `auction_lab/opponent.py` | `OpponentQuoteModel` and scenario expected-profit calculations |
| `auction_lab/report.py` | CSV/JSON outputs, charts and descriptive uncertainty comparisons |
| `auction_lab/api.py` | Local HTTP server and its request `Handler` |
| `auction_lab/pricing.py` | Tick rounding and deterministic seeds |
| `auction_lab/__main__.py` | CLI commands |
| `docs/`, `notebooks/`, `examples/` | Explanation, Colab workflow and example API bot |
| `tests/`, `results/`, `archive/` | Checks, current reference experiments and earlier versions |

`Config` validates settings. `Game` owns the tournament and its accounting. `OpponentQuoteModel` learns from completed auctions. `Handler` exposes game operations over HTTP. Individual indicator policies are functions, not separate classes.

Run `python -m unittest discover -s tests -v` for the 25 automated checks. See the [class and method guide](docs/02_code_map.md).

## 3. Strategies

| Player | Forecast / quote rule |
|---|---|
| `macd` | Lagged MACD histogram; single-feature regression within each sector |
| `price_reversal` | Previous close relative to its 20-day mean; sector regression |
| `volume_momentum` | Previous return times relative-volume deviation; sector regression |
| `sector_router` | Technology → MACD; commodities → volume momentum; financials → reversal |
| `orthogonal_ensemble` | All three signals, standardized and whitened within each sector, then ridge regression |
| `opponent_aware` | Sector-router mean forecast plus a joint model of past rival books; maximize estimated execution profit |
| `flat_quote` (optional) | No forecast; bid/ask eight basis points below/above the open |
| `tight_quote` (optional) | No forecast; bid/ask one basis point below/above the open |
| `no_trade` (optional) | Always abstain; zero trading profit |

Signals and regression labels use completed dates only. Single-indicator and sector-router models have one input column per sector; the ensemble has three before whitening. Each stock receives its own return prediction, clipped to ±1%. With three stocks and 126 complete dates, each sector contributes 378 training rows.

Ordinary strategies quote around their predicted close with an eight-basis-point half-width. The opponent-aware player instead searches eligible quote prices for the best fitted expected profit after its cold-start period. All players have zero transaction costs by default; quote widths are not fees.

The sector mapping is a fixed experimental hypothesis. Whitening makes retained training features uncorrelated; it does not guarantee independent profits or profitable forecasts. See the [strategy equations and dimensions](docs/03_strategies.md).

## 4. Results and interpretation

These two seed-7 tournaments use the same 100 evaluation dates, 180 warm-up dates, synthetic prices, customer input draws and initial capital. Only the roster differs. Values are cash P&L in the arbitrary currency units of the synthetic prices.

| Strategy | Six-player P&L | Nine-player P&L |
|---|---:|---:|
| `sector_router` | 51,060.52 | 20,731.60 |
| `opponent_aware` | 44,693.89 | 23,699.55 |
| `price_reversal` | 41,234.53 | 25,561.45 |
| `volume_momentum` | 4,965.63 | -14,076.04 |
| `orthogonal_ensemble` | -357.03 | 401.37 |
| `macd` | -10,106.59 | -10,745.16 |
| `flat_quote` | Not entered | 11,436.45 |
| `tight_quote` | Not entered | 25,507.36 |
| `no_trade` | Not entered | 0.00 |

![Six-player cumulative profit and final ranking](results/six_players/overview.png)

The sector router wins the six-player run. Its 51,060.52 profit comprises 16,084.29 of entry price improvement relative to the open and 34,976.23 of subsequent signed price movement. MACD earns 16,849.43 from entry price improvement, but loses 26,956.01 from price movement. These are realized accounting explanations, not evidence of a reliable forecasting advantage.

Adding benchmark quotes changes fills: tight quoting captures 45.61% of requested customer volume in the nine-player run. Reversal wins that run, narrowly ahead of tight quoting. The opponent-aware player does not necessarily win because its fitted expectations can be wrong and its conservative quantity allocation differs from other players.

Across twenty additional **nine-player** synthetic seeds, tight quoting has the highest mean profit, 17,215.38, and wins 50% of tournaments. The opponent-aware player's mean is 10,488.77, with a 10% win share. These are separate synthetic worlds, not twenty historical market validations.

Under the 35% informed-request stress, all active trading policies lose in both roster sizes. In the nine-player game, `no_trade` wins with zero. The stress illustrates adverse selection: winning a customer trade can coincide with unfavorable subsequent price movement.

See [the full comparison, stress tables and limitations](docs/04_results.md). The results directories contain the underlying trades, fills, forecasts, daily profits and model diagnostics. Earlier eight-player and nonzero-cost experiments are retained under `archive/`.

Version 0.4 makes player selection explicit and stress optional. The forecasting and auction rules are unchanged, and both previously reported 100-day leaderboards were reproduced. See [the changelog](CHANGELOG.md).
