# Experiment results

Data: **SYNTHETIC demonstration**.

Predeclared demonstration seed: 7. Evaluation: 100 days after 180 warm-up dates.
Each player starts with 1,000,000 units of nominal capital. P&L units match the input prices; synthetic prices have arbitrary currency units.

| Player | Net P&L | Max drawdown | Customer volume share |
|---|---:|---:|---:|
| sector_router | 32,489.71 | 5,515.35 | 6.3% |
| flat_quote | 20,706.95 | 8,722.01 | 6.5% |
| price_reversal | 20,019.57 | 18,704.61 | 8.9% |
| no_trade | 0.00 | 0.00 | 0.0% |
| orthogonal_ensemble | -13,147.05 | 35,643.10 | 14.0% |
| volume_momentum | -14,492.05 | 31,611.08 | 7.6% |
| tight_quote | -22,726.38 | 47,922.32 | 47.8% |
| macd | -31,917.09 | 38,205.30 | 8.8% |

The winner in this one run is **sector_router**. The no_trade contestant earns exactly zero.
This is a realized outcome, not proof that the winning indicator predicts prices. The synthetic price model has no deliberately installed technical-indicator alpha.

The daily identity is: net P&L = entry price improvement versus open + signed open-to-close movement - all modelled costs.

## Orthogonality

Whitening is fitted on past observations separately in each sector. Its training covariance is the identity on retained components. Future signal covariance and strategy profit covariance need not be diagonal.
See whitening_diagnostics.json (first training transform frozen for its diagnostic), forecast_correlation.csv, and pnl_correlation.csv. Correlations with zero-variance no_trade/flat forecasts are undefined and left blank.

## Informed-customer stress test

With 35% perfectly informed customer orders, the winner is **no_trade**, with net P&L 0.00.
Informed customers buy before positive open-to-close moves and sell before negative moves. This is a deliberately severe simulator assumption, not a measured fraction in any real market. Agents never receive the future close.
Prices, volume requests, and latent customer random draws are shared with the main run; only informed-side decisions change. See results/informed_stress/.

## Repeated synthetic tournaments

Independent synthetic price/order seeds give the following sensitivity check. These are new simulated worlds, not independent real historical backtests.

| Player | Mean total P&L | Median total P&L | Share of tournament wins |
|---|---:|---:|---:|
| flat_quote | 2,911.48 | -2,120.19 | 25.0% |
| price_reversal | 594.50 | 156.79 | 20.0% |
| no_trade | 0.00 | 0.00 | 10.0% |
| macd | -1,740.37 | -3,522.01 | 15.0% |
| sector_router | -2,184.96 | 1,708.84 | 15.0% |
| volume_momentum | -3,307.42 | -3,899.39 | 5.0% |
| orthogonal_ensemble | -15,054.66 | -12,608.27 | 5.0% |
| tight_quote | -26,708.07 | -21,246.47 | 5.0% |

## Statistical limits

The paired_bootstrap.csv file uses a five-day circular block bootstrap of daily P&L differences against flat_quote. Intervals condition on the fitted policies, do not refit them, and do not correct for selecting the best strategy after the test. They are descriptive, not a reliable final significance claim from 100 days.
For real conclusions, predeclare policies and metrics; use chronological training, validation and untouched test periods; include delisted constituents and corporate actions; test realistic execution/borrow costs and different competitor populations.
The model has no endogenous price impact, queue position, exchange opening-price formation, intraday re-quoting, funding interest, or guaranteed availability of borrowed shares. All are material extensions.
