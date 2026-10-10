# Experiment results

Data: **SYNTHETIC demonstration**.

Predeclared demonstration seed: 7. Evaluation: 100 days after 180 warm-up dates.
Each player starts with 1,000,000 units of nominal capital. P&L units match the input prices; synthetic prices have arbitrary currency units.

Common trading costs (basis points): fee per leg = 0; closing half-spread = 0; closing slippage = 0; daily short-borrow charge = 0. The same settings apply to every player and to the opponent-aware profit calculation.
Bid/ask quote margins and customer reservation prices are separate strategy and auction settings; they are not transaction-cost deductions.

| Player | Net P&L | Max drawdown | Customer volume share |
|---|---:|---:|---:|
| price_reversal | 25,561.45 | 10,943.35 | 6.7% |
| tight_quote | 25,507.36 | 37,489.52 | 45.6% |
| opponent_aware | 23,699.55 | 19,089.49 | 15.9% |
| sector_router | 20,731.60 | 6,201.59 | 4.3% |
| flat_quote | 11,436.45 | 3,847.04 | 3.1% |
| orthogonal_ensemble | 401.37 | 30,129.71 | 12.8% |
| no_trade | 0.00 | 0.00 | 0.0% |
| macd | -10,745.16 | 20,007.50 | 6.5% |
| volume_momentum | -14,076.04 | 23,496.19 | 5.0% |

The winner in this one run is **price_reversal**. The no_trade contestant earns exactly zero.
This is a realized outcome, not proof that the winning indicator predicts prices. The synthetic price model has no deliberately installed technical-indicator alpha.

The daily identity is: net P&L = entry price improvement versus open + signed open-to-close movement - all modelled costs.

## Orthogonality

Whitening is fitted on past observations separately in each sector. Its training covariance is the identity on retained components. Future signal covariance and strategy profit covariance need not be diagonal.
See whitening_diagnostics.json (first training transform frozen for its diagnostic), forecast_correlation.csv, and pnl_correlation.csv. Correlations with zero-variance no_trade/flat forecasts are undefined and left blank.

## Opponent-aware expected-profit player

The new player earned **23,699.55**, versus **20,731.60** for sector_router in the same tournament.
Decision counts: {'optimized': 667, 'warmup_sector_quote': 185, 'abstain': 48}.
It uses the same mean closing-price forecast as sector_router, estimates a joint distribution of competing quote/quantity books from completed days, and searches candidate ticks for the highest estimated profit after costs. It can abstain. Cold-start days use the sector quote with the new player's conservative per-order quantity allocation.
Across its 715 model-based decisions, estimated net profit summed to 47,946.13, while realized net profit was 11,598.47. These are different quantities: maximizing a fitted expectation does not guarantee realized profit or an unbiased model.
All current opponent quotes stay sealed; approved quote books become available to every player after settlement. This is an explicit simulation disclosure rule. A market showing only winning execution prices would require censored-data estimation instead.
The player reserves equal capital slices for current requests before optimizing each price; its quantity allocation is more conservative than sector_router. Therefore the realized comparison is not a pure causal estimate of the value of opponent modelling.
See opponent_decisions.csv for predicted and actual fills/profits, training cutoffs, selected quotes and a same-quantity fixed-offset counterfactual evaluated under its fitted distribution. No current-day outcome enters a quote decision.

## Informed-customer stress test

With 35% perfectly informed customer orders, the winner is **no_trade**, with net P&L 0.00.
Informed customers buy before positive open-to-close moves and sell before negative moves. This is a deliberately severe simulator assumption, not a measured fraction in any real market. Agents never receive the future close.
Prices, volume requests, and latent customer random draws are shared with the main run; only informed-side decisions change. See results/informed_stress/.

## Repeated synthetic tournaments

Independent synthetic price/order seeds give the following sensitivity check. These are new simulated worlds, not independent real historical backtests.

| Player | Mean total P&L | Median total P&L | Share of tournament wins |
|---|---:|---:|---:|
| tight_quote | 17,215.38 | 27,955.46 | 50.0% |
| opponent_aware | 10,488.77 | 14,331.78 | 10.0% |
| flat_quote | 7,382.70 | 6,648.44 | 10.0% |
| macd | 5,056.59 | 6,057.66 | 0.0% |
| price_reversal | 3,956.69 | 3,659.40 | 10.0% |
| sector_router | 2,063.59 | 2,068.98 | 5.0% |
| volume_momentum | 2,044.21 | -1,715.03 | 5.0% |
| no_trade | 0.00 | 0.00 | 0.0% |
| orthogonal_ensemble | -2,103.12 | 2,187.45 | 10.0% |

## Statistical limits

The paired_bootstrap.csv file uses a five-day circular block bootstrap of daily P&L differences against flat_quote. Intervals condition on the fitted policies, do not refit them, and do not correct for selecting the best strategy after the test. They are descriptive, not a reliable final significance claim from 100 days.
For real conclusions, predeclare policies and metrics; use chronological training, validation and untouched test periods; include delisted constituents and corporate actions; test realistic execution/borrow costs and different competitor populations.
The model has no endogenous price impact, queue position, exchange opening-price formation, intraday re-quoting, funding interest, or guaranteed availability of borrowed shares. All are material extensions.
