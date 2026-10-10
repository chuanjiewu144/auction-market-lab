# Experiment results

Data: **SYNTHETIC demonstration**.

Predeclared demonstration seed: 7. Evaluation: 100 days after 180 warm-up dates.
Each player starts with 1,000,000 units of nominal capital. P&L units match the input prices; synthetic prices have arbitrary currency units.

Common trading costs (basis points): fee per leg = 0; closing half-spread = 0; closing slippage = 0; daily short-borrow charge = 0. The same settings apply to every player and to the opponent-aware profit calculation.
Bid/ask quote margins and customer reservation prices are separate strategy and auction settings; they are not transaction-cost deductions.

| Player | Net P&L | Max drawdown | Customer volume share |
|---|---:|---:|---:|
| sector_router | 51,060.52 | 12,302.81 | 13.9% |
| opponent_aware | 44,693.89 | 18,160.89 | 18.4% |
| price_reversal | 41,234.53 | 15,952.50 | 15.8% |
| volume_momentum | 4,965.63 | 30,628.26 | 15.6% |
| orthogonal_ensemble | -357.03 | 33,279.23 | 19.8% |
| macd | -10,106.59 | 25,349.57 | 15.8% |

The winner in this one run is **sector_router**.
This is a realized outcome, not proof that the winning indicator predicts prices. The synthetic price model has no deliberately installed technical-indicator alpha.

The daily identity is: net P&L = entry price improvement versus open + signed open-to-close movement - all modelled costs.

## Orthogonality

Whitening is fitted on past observations separately in each sector. Its training covariance is the identity on retained components. Future signal covariance and strategy profit covariance need not be diagonal.
See whitening_diagnostics.json (first training transform frozen for its diagnostic), forecast_correlation.csv, and pnl_correlation.csv. Correlations with zero-variance no_trade/flat forecasts are undefined and left blank.

## Opponent-aware expected-profit player

The new player earned **44,693.89**, versus **51,060.52** for sector_router in the same tournament.
Decision counts: {'optimized': 662, 'warmup_sector_quote': 185, 'abstain': 53}.
It uses the same mean closing-price forecast as sector_router, estimates a joint distribution of competing quote/quantity books from completed days, and searches candidate ticks for the highest estimated profit after costs. It can abstain. Cold-start days use the sector quote with the new player's conservative per-order quantity allocation.
Across its 715 model-based decisions, estimated net profit summed to 56,587.23, while realized net profit was 27,947.86. These are different quantities: maximizing a fitted expectation does not guarantee realized profit or an unbiased model.
All current opponent quotes stay sealed; approved quote books become available to every player after settlement. This is an explicit simulation disclosure rule. A market showing only winning execution prices would require censored-data estimation instead.
The player reserves equal capital slices for current requests before optimizing each price; its quantity allocation is more conservative than sector_router. Therefore the realized comparison is not a pure causal estimate of the value of opponent modelling.
See opponent_decisions.csv for predicted and actual fills/profits, training cutoffs, selected quotes and a same-quantity fixed-offset counterfactual evaluated under its fitted distribution. No current-day outcome enters a quote decision.

## Informed-customer stress test

With 35% informed-request probability, the winner is **sector_router**, with net P&L -29,144.81.
Informed customers buy before positive open-to-close moves and sell before negative moves. This is a deliberately severe simulator assumption, not a measured fraction in any real market. Agents never receive the future close.
Prices, volume requests, and latent customer random draws are shared with the main run; only informed-side decisions change. See informed_stress/ alongside this report.

## Statistical limits

The paired_bootstrap.csv file uses a five-day circular block bootstrap of daily P&L differences against flat_quote when present, otherwise sector_router. The baseline is recorded in the CSV and summary. Intervals condition on the fitted policies, do not refit them, and do not correct for selecting the best strategy after the test. They are descriptive, not a reliable final significance claim from 100 days.
For real conclusions, predeclare policies and metrics; use chronological training, validation and untouched test periods; include delisted constituents and corporate actions; test realistic execution/borrow costs and different competitor populations.
The model has no endogenous price impact, queue position, exchange opening-price formation, intraday re-quoting, funding interest, or guaranteed availability of borrowed shares. All are material extensions.
