# 1. Market background and game API

Auction Market Lab studies how forecasts and competitive quotes interact in a daily request-for-quote (RFQ) market. Customers request trades; competing dealers supply prices and quantities. The goal is to compare realized profit, risk and execution across policies under the same simulated conditions.

## Universe, participants and timing

The default synthetic universe contains nine equities:

| Sector label | Symbols | Meaning |
|---|---|---|
| `technology` | `TECH_1`, `TECH_2`, `TECH_3` | Technology companies |
| `commodities` | `COMM_1`, `COMM_2`, `COMM_3` | Commodity-related companies, not futures |
| `financials` | `FIN_1`, `FIN_2`, `FIN_3` | Financial companies |

There is one customer request per stock per evaluation day: nine requests a day and 900 over 100 days. Every selected strategy can respond to every request. Sectors do not divide stocks among competitors.

The supported built-in rosters have six or nine players. Six is the default and contains the research strategies. Nine adds `no_trade`, `flat_quote` and `tight_quote`. The external API player `you` is additional, giving seven or ten participants in an API game. Residual customer demand goes to an external liquidity provider that is not ranked.

The default input spans 280 trading dates. The first 180 are a warm-up history; the next 100 are evaluated. A forecaster is refitted each morning using the latest 126 completed dates. The opponent model starts without any pre-game quote history and learns as auctions settle.

The morning opening price is already known when quotes are submitted. Indicators use information through the previous close. Current closing prices and volumes are hidden from the quoting policies. At settlement, trades close, profit is recorded, and all approved quotes are disclosed. The next day starts with zero stock inventory but retains the accumulated cash profit or loss.

## Clearing an RFQ

| Customer side | Dealer action | Priority | Customer price limit |
|---|---|---|---|
| Sell | Buy at a bid | Highest eligible bid first | Bid at least the reserve |
| Buy | Sell at an ask | Lowest eligible ask first | Ask at most the reserve |

Orders can fill across multiple dealers. Each dealer trades at its own submitted price. Equal-price priority uses a reproducible seeded lottery; requested shares remaining after dealer fills go to the outside provider at the reserve. This is a sealed, discriminatory-price RFQ game. It is neither a single-price exchange opening auction nor a fill-or-kill order mechanism: partial fills are allowed.

The outside price is the opening price plus 15 basis points for a customer purchase, or minus 15 basis points for a customer sale, rounded to the configured tick. The default tick is 0.01 price units.

## Random customer requests

For each stock and date, an independent reproducible random stream is keyed by the experiment seed, date and symbol. With the ordinary configuration, buy and sell are equally likely. Requested quantity is

$$
Q_{j,t}=\max\left(1,\left\lfloor\overline V_{j,t-1}^{20} U_{j,t}\right\rfloor\right),
\qquad U_{j,t}\sim\operatorname{Uniform}(0.0005,0.0015).
$$

Thus size is random and scaled to that stock's recent volume. The random flow does not depend on which roster is selected. Executions do depend on the roster.

In the optional stress scenario, each request has a 35% chance of being informed. Informed customers buy before positive open-to-close returns and sell before negative ones. Other requests keep a fair random side. This is a Bernoulli probability per request, not an exact 35% count or volume share. It is a deliberately adverse assumption, not an estimate from market data. The simulator uses the hidden outcome to construct the informed customer side; dealers are not given the future close. Prices, requested sizes and underlying random draws are shared with the ordinary run.

## Prices and historical CSVs

Synthetic prices have shared daily market and sector shocks plus a stock-specific shock. The opening price is the previous close times a random overnight multiplier; the close is the open times an exponential intraday return. The stock-specific log-return standard deviations are 0.011, 0.013 and 0.008 for the three sectors. Innovations are independent across dates. Sector labels change covariance and volatility, without installing a technical-indicator forecasting advantage. Zero-mean log shocks do not imply zero expected arithmetic returns.

Historical mode accepts `date,symbol,sector,open,close,volume`. A CSV can contain a different number of stocks, but must use the supported sector labels and a balanced panel: one positive, finite row per stock per selected date, stable sectors and no duplicates. Default evaluation needs at least 280 complete dates. Select the date interval before running. Use consistent price/volume adjustment conventions; corporate actions are not implemented by the engine.

```bash
python -m auction_lab backtest --data prices.csv --players 6 --warmup 180 --days 100 --out runs/historical
```

Historical prices replace the price generator. Customer orders, quotes, fills and end-of-day execution are still simulated; daily OHLCV does not reveal actual RFQ or queue outcomes.

## Capital and settlement

Each dealer starts with 1,000,000 cash units. Daily available risk capital is bounded by both initial capital and current positive equity. Defaults cap each stock at 20% of available capital, reduce that cap for higher volatility, and cap quantities at 0.1% of lagged average volume. Gross capital is reserved across submitted quotes, including quotes that may not fill.

Short selling is enabled. Long positions are sold at the close; shorts are bought back. Every player has zero transaction costs by default, including fees, closing spread, slippage and borrowing charges. For signed filled quantity $q$, execution price $p$ and close $C$, profit is

$$\Pi=q(C-p).$$

Quote margins remain part of the strategy. A quote half-width of eight basis points is not an eight-basis-point fee. Optional cost parameters can be supplied in `Config` or directly in the JSON body of `POST /games`.

## Local HTTP API

Start the server and the example bot in separate terminals:

```bash
python -m auction_lab serve --port 8000
python examples/play_api.py
```

The server is an in-memory local simulation bound to `127.0.0.1`. There is no broker connection or production authentication. Roster and game settings belong in `POST /games`; `--players` selects offline CLI tournaments.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Server status |
| `POST` | `/games` | Create a game from `Config` fields |
| `GET` | `/games/{id}` | Opening-time observation and current customer requests |
| `GET` | `/games/{id}/history?symbol=TECH_1&limit=126` | Completed price history |
| `POST` | `/games/{id}/step` | Submit quotes, clear and settle one day |
| `GET` | `/games/{id}/quotes?limit=126` | Completed approved quote books |
| `GET` | `/games/{id}/results` | Daily P&L and leaderboard |
| `DELETE` | `/games/{id}` | Remove a game |

Create a game with this JSON body:

```json
{"days": 100, "warmup": 180, "seed": 7, "competitors": 6}
```

An action has this shape, using a symbol and valid price from the current observation:

```json
{"quotes": {"TECH_1": {"price": 99.95, "quantity": 500}}}
```

The price here is illustrative. It must be on the tick grid and within 10% of the observed opening price. Omitted symbols abstain. Quantities are subject to the common risk limits. Invalid actions return HTTP 400 without advancing the day. The response contains realized fills, P&L, completed quotes and the next observation. Current rival quotes remain sealed until settlement.

[Code map](02_code_map.md) · [Strategies](03_strategies.md) · [Results](04_results.md)
