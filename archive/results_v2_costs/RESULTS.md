# Experiment results

Data: **SYNTHETIC demonstration**.

Predeclared demonstration seed: 7. Evaluation: 100 days after 180 warm-up dates.
Each player starts with 1,000,000 units of nominal capital. P&L units match the input prices; synthetic prices have arbitrary currency units.

| Player | Net P&L | Max drawdown | Customer volume share |
|---|---:|---:|---:|
| price_reversal | 23,891.85 | 10,877.21 | 7.5% |
| sector_router | 23,135.81 | 6,397.01 | 4.9% |
| flat_quote | 12,207.34 | 6,034.88 | 3.8% |
| opponent_aware | 1,124.20 | 23,392.08 | 10.3% |
| no_trade | 0.00 | 0.00 | 0.0% |
| orthogonal_ensemble | -10,194.48 | 34,328.25 | 13.3% |
| volume_momentum | -16,560.88 | 26,257.18 | 5.7% |
| tight_quote | -22,135.09 | 47,717.83 | 47.3% |
| macd | -24,631.68 | 31,178.19 | 7.2% |

The winner in this one run is **price_reversal**. The no_trade contestant earns exactly zero.
This is a realized outcome, not proof that the winning indicator predicts prices. The synthetic price model has no deliberately installed technical-indicator alpha.

The daily identity is: net P&L = entry price improvement versus open + signed open-to-close movement - all modelled costs.

## Orthogonality

Whitening is fitted on past observations separately in each sector. Its training covariance is the identity on retained components. Future signal covariance and strategy profit covariance need not be diagonal.
See whitening_diagnostics.json (first training transform frozen for its diagnostic), forecast_correlation.csv, and pnl_correlation.csv. Correlations with zero-variance no_trade/flat forecasts are undefined and left blank.

## Opponent-aware expected-profit player

The new player earned **1,124.20**, versus **23,135.81** for sector_router in the same tournament.
Decision counts: {'optimized': 636, 'warmup_sector_quote': 185, 'abstain': 79}.
It uses the same mean closing-price forecast as sector_router, estimates a joint distribution of competing quote/quantity books from completed days, and searches candidate ticks for the highest estimated profit after costs. It can abstain. Cold-start days use the sector quote with the new player's conservative per-order quantity allocation.
Across its 715 model-based decisions, estimated net profit summed to 33,495.35, while realized net profit was -10,051.42. These are different quantities: maximizing a fitted expectation does not guarantee realized profit or an unbiased model.
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
| flat_quote | 2,477.55 | 2,741.13 | 30.0% |
| no_trade | 0.00 | 0.00 | 5.0% |
| price_reversal | -353.03 | -1,809.43 | 20.0% |
| macd | -1,245.20 | -3,859.12 | 5.0% |
| sector_router | -2,485.93 | -2,608.26 | 10.0% |
| opponent_aware | -2,896.34 | -6,088.42 | 20.0% |
| volume_momentum | -4,353.94 | -5,846.34 | 5.0% |
| orthogonal_ensemble | -14,507.16 | -11,955.34 | 5.0% |
| tight_quote | -26,438.32 | -20,615.63 | 0.0% |

## Statistical limits

The paired_bootstrap.csv file uses a five-day circular block bootstrap of daily P&L differences against flat_quote. Intervals condition on the fitted policies, do not refit them, and do not correct for selecting the best strategy after the test. They are descriptive, not a reliable final significance claim from 100 days.
For real conclusions, predeclare policies and metrics; use chronological training, validation and untouched test periods; include delisted constituents and corporate actions; test realistic execution/borrow costs and different competitor populations.
The model has no endogenous price impact, queue position, exchange opening-price formation, intraday re-quoting, funding interest, or guaranteed availability of borrowed shares. All are material extensions.
