# Auction Market Lab

A runnable financial-mathematics project and local game API for competing stock dealers. Each morning a customer requests purchases or sales. Players submit sealed quotes; winners hold their positions until compulsory end-of-day liquidation.

**The included data and results are synthetic. No real-stock performance is claimed.** Historical CSV input is supported, but customer orders, executions and costs remain simulated.

Read `PROJECT.md` for the mathematical model and research questions. Read `OPPONENT_STRATEGY.md` for the new expected-profit strategy, its equations and information limits. Read `results/RESULTS.md` for the completed experiments.

**Version 0.3 uses zero trading costs for every player by default.** Entry/exit fees, closing half-spread, closing slippage and short-borrow charges are all zero. Positions close at the supplied closing price, so realized profit is `signed_quantity * (close - execution_price)`. The opponent-aware strategy optimizes this same cost-free profit.

The players' bid/ask margins (for example, `half_spread_bps=8`) and the customer's outside quote (`outside_spread_bps=15`) still determine submitted and acceptable prices. They are not fees deducted from profit. Optional costs remain configurable through Python `Config` or the API's `config` object; the previous cost settings were `fee_bps=0.5`, `closing_half_spread_bps=3`, `closing_slippage_bps=1`, and `short_borrow_bps=0.5`.

## Quick start

Python 3.10 or later. From this directory:

```bash
python -m pip install -r requirements.txt
python -m auction_lab demo --days 100 --seed 7 --repetitions 20 --out results
python -m unittest discover -s tests -v
```

The saved run uses Python 3.12, NumPy 2.3.5, pandas 2.2.3 and Matplotlib 3.10.8. A new environment may produce tiny numerical differences. `--repetitions 20` runs twenty additional synthetic tournaments after the main run and the informed-customer stress test.

## Auction rules

| Customer request | Player's action | Competitive price |
|---|---|---|
| Sell shares | Buy using a bid | Higher bids fill first |
| Buy shares | Sell using an ask | Lower asks fill first |

The order-generating party is called the **customer**. The competing players act as dealers. This avoids using “market maker” for both sides.

- One auction per stock per day, just after the opening price is observable. All player quotes are submitted simultaneously.
- A winner trades at its own submitted price: a discriminatory-price, or pay-as-bid, RFQ auction. Partial fills are allowed.
- Equal prices are ranked by a reproducible seeded lottery. Reordering Python dictionaries does not change tie results.
- An external dealer provides the customer's reservation price. Quotes worse for the customer do not fill; residual shares go to that external dealer. Thus players cannot force an arbitrary profitable transaction price.
- Each player has the same initial capital and risk limits. Gross capital is reserved across all submitted quotes, even quotes that might not execute.
- Default short selling is allowed without a borrow charge. Longs are sold and shorts bought back at the supplied close, with zero fees and zero closing spread/slippage by default. Inventory ends at zero; cash profits/losses persist.
- Daily risk capital is the smaller of initial capital and current positive equity. Profits are not reinvested above the initial limit. A player with nonpositive equity cannot open new trades.

This is not an exchange opening auction: the opening price is an external input, and the auction does not discover a single market-clearing price.

## Contestants

| Name | Forecast or quoting rule |
|---|---|
| `no_trade` | Cash-only benchmark, zero trading P&L and no interest |
| `flat_quote` | No directional forecast; quote 8 basis points around the open |
| `tight_quote` | No directional forecast; quote 1 basis point around the open |
| `macd` | MACD histogram input; rolling ridge regression fitted separately by sector |
| `price_reversal` | Distance from a 20-day moving average; same estimation method |
| `volume_momentum` | Previous daily return multiplied by relative-volume deviation |
| `sector_router` | MACD for technology; volume momentum for commodities; reversal for financials |
| `orthogonal_ensemble` | All three features, standardized and whitened on past data within each sector |
| `opponent_aware` | Sector-router mean forecast plus a past-only joint opponent model; maximize expected net profit over candidate quotes |

Sector routing is a predeclared experimental hypothesis, not a claim about which indicator really suits each sector. Names describe the model inputs: fitted coefficients can change sign. All learned contestants use a 126-date rolling training window and a fixed ridge penalty; no hyperparameter is selected on the reported 100-day result. Forecasts are clipped to +/-1%.

Whitening makes the retained training features uncorrelated. It does not make their future forecasts or their auction P&Ls independent. Competing strategies also affect one another's fills.

## Historical-price input

Provide a CSV with these required columns:

```csv
date,symbol,sector,open,close,volume
2023-01-03,TECH_A,technology,100.0,101.2,1200000
2023-01-03,COMM_A,commodities,60.0,59.7,1800000
2023-01-03,FIN_A,financials,80.0,80.5,1500000
```

The three lines above illustrate the schema only, not a runnable dataset. Optional high/low columns are preserved in generated data but are not used by the strategies.

```bash
python -m auction_lab backtest --data prices.csv --warmup 180 --days 100 --out historical_results
```

Requirements:

- At least 280 complete trading dates for the default 180-day warm-up plus 100-day test.
- One row for every selected symbol on every selected date; one common currency; positive finite prices and volumes; no duplicate symbol/date rows.
- Sector labels must be `technology`, `commodities`, or `financials`. Here “commodities” means commodity-related equities, not futures contracts.
- Data must be sorted chronologically in meaning; the loader sorts rows. The first 180 dates are warm-up and the next 100 are evaluated. Slice your input deliberately to choose a test interval.
- No forward filling or silent dropping of missing bars. An unbalanced panel raises an error. The prototype does not handle IPOs, delistings, halts, changes in universe or differing trading calendars automatically.
- Start with an event-free interval or carefully prepared data. Corporate actions are not implemented. A serious cash backtest needs raw execution prices and separately action-aware historical features; treating split-adjusted prices and unadjusted volumes as real dollar executions is incorrect. Document any adjustment convention and remember survivor selection bias.

At the decision for day t, the current open is known. Close, volume, moving averages, MACD and volatility are available only through t-1. The current close is revealed for settlement after the submitted quotes have been fixed. Regression labels come strictly from completed dates.

**Daily OHLCV cannot identify actual queues, quotes, spreads, RFQ requests or fills.** Even when historical prices are loaded, this project tests policies in an assumed execution game. Use timestamped bid/ask, trade and depth data plus an execution model for a more realistic market-making study.

## Local API and an external player

```bash
python -m auction_lab serve --port 8000
# In another terminal:
python examples/play_api.py
```

Or start with historical data fixed by the server operator:

```bash
python -m auction_lab serve --port 8000 --data prices.csv
```

The server listens on `127.0.0.1` only. It is a local research API, with in-memory games, no authentication, no broker connection, and no anti-cheating system. Synthetic prices can be regenerated from their seed. Do not treat this as a secure hosted competition.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Check the server |
| POST | `/games` | Create a game; accepts `Config` fields such as days and seed |
| GET | `/games/{id}` | Current orders and information available before quoting |
| GET | `/games/{id}/history?symbol=TECH_1&limit=126` | Completed historical bars only |
| POST | `/games/{id}/step` | Submit your quotes, clear the day, settle, reveal next state |
| GET | `/games/{id}/results` | Completed daily results and leaderboard |
| GET | `/games/{id}/quotes?limit=126` | Approved quotes from completed days only |
| DELETE | `/games/{id}` | Remove an in-memory game |

Create a game:

```json
{"days": 100, "seed": 7, "allow_short": true}
```

Submit a daily action using actual symbols and prices from the state:

```json
{"quotes": {"TECH_1": {"price": 99.95, "quantity": 500}}}
```

The numeric example is illustrative; quotes must be on the configured price tick and within 10% of the observed reference price. Prices are interpreted as bids when the customer sells and asks when the customer buys. Omit a symbol to abstain. Oversized quantities are reduced by the same position and total-capital rules used for built-in bots. Invalid requests return HTTP 400 without consuming a day. With `allow_short=false`, an external player's attempt to sell while flat is rejected.

The Python example runs 100 rounds against all nine built-in players. Replace its quote calculation with your own policy; the history endpoint supplies past bars. Competitors' current quotes are not revealed before submission. Completed fills and all approved quotes are revealed afterward to every player. This after-settlement quote disclosure is an explicit rule added in version 0.2; it is not an assumption about real venues.

## Outputs

`results_v1/` preserves the original eight-player experiment. `results_v2_costs/` preserves the nine-player version 0.2 experiment with nonzero costs. The current nine-player, zero-cost experiment is in `results/`, which includes:

- `RESULTS.md`, `summary.json`, `leaderboard.csv`, and `overview.png`.
- Every customer order, quote, fill, liquidation cost, daily P&L and forecast.
- `opponent_decisions.csv`: selected prices, model modes, strictly past training cutoffs, expected versus actual fills/profits, and a fixed-offset quote comparison under the learned distribution.
- Forecast and P&L correlation matrices and train/test whitening diagnostics.
- Paired five-day block-bootstrap comparisons against the neutral dealer; these are descriptive and do not correct strategy selection or refit policies.
- `informed_stress/`: the same prices with 35% perfectly informed customers. This is an intentionally severe adverse-selection scenario, not an estimate of real informed trading.
- `repeated_runs.csv` and `repeated_summary.csv` if repetitions were requested.

The primary leaderboard ranks net P&L. It also reports drawdown, volume share, costs and annualized daily Sharpe. Different exposures can make raw profit comparisons misleading; examine them together. Undefined zero-variance Sharpe/correlations are blank/null. Sharpe annualization assumes 252 sessions and is not a reliable performance estimate from 100 observations.

## Validation

Twenty-two automated checks cover both auction directions, partial fills, customer price limits, reproducible ties, zero-cost and optional-cost long/short cash accounting, portfolio budgets, share conservation, compulsory liquidation, missing data, whitening rank, future-data isolation, reproducible replay, and the complete local API flow.

The test that changes today's and all future closes/volumes while keeping the observed opening price fixed verifies that current quotes do not change. In the explicit informed-customer scenario, the customer side intentionally depends on its private future-value information; this information is never passed directly to the quoting agent.

## Research references

1. [SEC Investor.gov: Bid Price/Ask Price](https://www.investor.gov/introduction-investing/investing-basics/glossary/ask-price).
2. [Nasdaq Equity 4 trading rules](https://listingcenter.nasdaq.com/rulebook/nasdaq/rules/Nasdaq%20Equity%204), especially the Opening Cross, for a real single-price auction to contrast with this RFQ model.
3. [Avellaneda and Stoikov, High-frequency trading in a limit order book](https://math.nyu.edu/inmemoriam/avellaneda/HighFrequencyTrading.pdf), for inventory-aware continuous-time market making. This implementation is not a calibration or reproduction of that paper.


## Opponent-aware player (version 0.2)

The new player uses completed auction histories, including all approved losing quotes. Today's opponent quotes remain sealed. Its conditional empirical distribution replays whole past opponent books and paired return residuals; it does not multiply independent dealer distributions. It conditions on sector, customer side and lagged signals/volatility.

For each current request it evaluates expected **net** profit, including partial fills, equal-price priorities, customer reservation prices and any configured transaction costs. All transaction costs default to zero in version 0.3. A zero-profit abstention action is available. Its mean closing-price forecast is exactly the sector_router forecast (apart from a numerical positivity floor), so the distributional addition principally changes quoting and fill selection. Residual dependence between opponent quotes and closing value is retained.

Cold start requires 30 completed observations from the same sector and customer side, spread over at least 10 dates. Before then it uses the sector quote. There is no fabricated pre-game quote history. Kernel bandwidth 1.5, a 5% uniform probability mixture and a default search band of +/-200 basis points are fixed settings, not tuned on the reported test.

The player reserves an equal slice of its available capital for each tradable request, with the same volume, volatility and per-stock maximum constraints. Quantity is fixed conservatively at the search band's highest price, so the final budget check does not alter its optimized request. It searches every eligible tick when there are at most 2,001; larger ranges use a bounded grid plus opponent-price breakpoints. These are separate per-request decisions with a fixed allocation, not a global portfolio optimum.

The configured opponent_min_history, opponent_min_dates, opponent_bandwidth and opponent_quote_band_bps fields are available through the Python Config and POST /games. The opponent player is enabled by default. The original stock forecasters are unchanged.

The tests include a known analytic optimal-bid example with both zero and nonzero costs, joint dependence, nonprofitable abstention, exact agreement with auction clearing and long/short settlement, and a trained optimizer test that alters today's/future outcomes without altering today's quotes. The local API test also checks delayed quote disclosure.

Estimated optimality is relative to the fitted distribution and candidate set. It is not a guarantee of realized profit, an equilibrium claim, or a market-calibrated fill model. If only winning executions are observed, their prices are a censored sample; this full-book implementation must then be replaced with censored-feedback estimation.
