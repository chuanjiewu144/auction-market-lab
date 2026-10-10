> Technical notes from the earlier prototype. For version-0.4 defaults, six/nine-player selection, and current documentation, start with [README.md](README.md) and [docs/](docs/01_market_and_api.md). Earlier result paths are retained under `archive/`; current results are separated into `results/six_players/` and `results/nine_players/`.

# Competitive RFQ Market Making with Sector Signals and Daily Liquidation

## Research question

Can sector-specific price forecasts improve a dealer's net profit when it must compete for customer orders, bear intraday price risk, and close all positions each evening? Does reducing correlation between input signals improve the resulting profit distribution?

This is a coherent project in financial mathematics, statistical learning and game theory. A daily prototype gives an accessible first experiment; intraday re-quoting leads naturally to a stochastic-control problem.

## 1. Economic roles and auction

A customer announces a stock, a side and a quantity. The competing players are dealers who supply liquidity. One submitted quote may receive a full fill, a partial fill, or no fill.

| Customer side | Dealer position after winning | Price competition |
|---|---|---|
| Sell | Buy shares, positive inventory | Highest eligible bid first |
| Buy | Sell shares, negative inventory if initially flat | Lowest eligible ask first |

The default is a sealed, pay-as-bid auction. Winners transact at their submitted prices. An external dealer provides a publicly known reservation price, so a customer can reject collectively unattractive player quotes. Equal prices use a seeded lottery. Remaining volume goes to external liquidity.

The opening price is observed first and treated as exogenous. Thus this is a daily request-for-quote tournament, not an exchange opening auction that jointly determines a common clearing price. Nasdaq's Opening Cross is an example of the latter [2].

## 2. Information and forecasting

Let O_(j,t) and C_(j,t) be opening and closing prices of stock j on date t. A player observes O_(j,t), the customer request, and price/volume history through t-1. It cannot observe C_(j,t), today's high/low, or today's total volume before quoting.

Write the information set as F_t^open. The price forecast is

$$
\widehat\alpha_{j,t}
\approx \mathbb E\!\left[\frac{C_{j,t}}{O_{j,t}}-1\mid\mathcal F_t^{\rm open}\right],
\qquad
\widehat m_{j,t}=O_{j,t}(1+\widehat\alpha_{j,t}).
$$

The implemented estimators use only lagged features, fitted separately by sector with rolling ridge regression. The quote template is

$$
b_{j,t}=\widehat m_{j,t}-\delta_{j,t},
\qquad
a_{j,t}=\widehat m_{j,t}+\delta_{j,t},
$$

followed by conservative tick rounding. Only the side requested by the customer is submitted. In the baseline implementation, delta is a fixed fraction of the opening price; quantities are bounded by capital, per-stock exposure, past volume and past volatility. It does not yet solve an optimal spread-control problem.

Volume alone is not a directional forecast. The volume feature multiplies a lagged return by lagged relative-volume deviation. All model coefficients are estimated from completed observations; named features do not fix coefficient signs.

The initial sector hypothesis is MACD for technology, volume momentum for commodity-related equities and reversal for financials. It is deliberately predeclared and must be tested, not assumed true. The synthetic market does not encode this hypothesis as a profitable relationship.

## 3. Profit, risk and the objective

Let q be the signed executed number of shares: positive for a dealer purchase and negative for a dealer sale. Let P be the execution price. Before costs, the evening profit is

$$
\Pi^{\rm gross}=q(C-P).
$$

For example, buying 100 shares at 100 and closing at 101 earns 100 before costs; short-selling 100 at 100 and covering at 101 loses 100. Shorts must be bought back, not “sold out.”

Version 0.3 sets all trading costs to zero by default, uniformly across players. Thus net and gross profit coincide: `Pi = q(C - P)`. The quote margin is a choice of execution price, not a separate charge. Intraday price risk and uncertain fills remain.

For optional nonzero costs, with closing half-spread/slippage fraction h, the model uses

$$
P^{\rm exit}=C\bigl(1-\operatorname{sgn}(q)h\bigr),
\qquad
\Pi=q(P^{\rm exit}-P)-\text{entry fee}-\text{exit fee}-\text{borrow charge}.
$$

Every position is closed each day. This eliminates overnight inventory but leaves risk between the morning trade and the close. Cash P&L carries forward.

The accounting decomposition is

$$
\boxed{\Pi=q(O-P)+q(C-O)-\text{total costs}.}
$$

The first term measures entry price improvement relative to the opening reference; it is not automatically the actual exchange spread captured. The second term measures signed subsequent price movement. Recording both distinguishes quote economics from directional exposure.

A research objective might maximize

$$
\mathbb E\!\left[\sum_t\Pi_t\right]
-\frac{\gamma}{2}\operatorname{Var}\!\left(\sum_t\Pi_t\right)
$$

subject to gross-exposure and participation constraints. The implemented leaderboard instead reports realized net P&L, drawdown, turnover/volume share and a descriptive Sharpe ratio separately. It does not claim to optimize the objective above.

Winning more auctions need not increase profit. For a simplified single-unit customer sell order, a quote b has value

$$
J(b)=\mathbb E\!\left[(C-b-c)\,\mathbf 1\{b\geq\max(B_{-i},L)\}\mid\mathcal F_t^{\rm open}\right],
$$

where B_(-i) is the best competing bid, L the customer reservation price and c a simplified per-share cost. If winning and future value were conditionally independent, this would factor into a profit margin times a fill probability. Generally they need not be independent: competition and informed customer flow create selection effects. This is one reason a price predictor alone is not a complete quoting strategy.

## 4. What “orthogonal strategies” should mean

There are three distinct objects:

| Object | A possible criterion | What it establishes |
|---|---|---|
| Training feature columns | Sample inner products or covariances are zero | Removes linear redundancy in that training sample |
| Future strategy forecasts | Low correlation on later observations | Different predictions in the evaluated period |
| Realized strategy P&Ls | Low covariance after fills and costs | Potential diversification of realized strategy returns |

None implies the others automatically. Zero correlation also does not imply statistical independence.

For a past-data feature matrix X, first standardize its columns to obtain Z. If the training covariance is

$$
\widehat\Sigma=V\Lambda V^\top,
$$

then retained positive-eigenvalue components are transformed as

$$
\widetilde Z=ZV_r\Lambda_r^{-1/2},
\qquad
\widehat{\operatorname{Cov}}(\widetilde Z)=I_r.
$$

The mean, scale, eigenvectors and eigenvalues must be fitted on past data only. Near-zero directions are dropped. The actual ensemble refits on each rolling training window. A separate diagnostic freezes the first training transform and measures covariance on later test observations.

Whitening may amplify estimation noise, and maximizing mathematical orthogonality is not itself a trading objective. A useful next experiment is to choose forecast or portfolio weights on a validation period to balance net return, exposure and P&L covariance. Keep the final test period untouched.

## 5. Completed experiment and interpretation

The original v0.1 experiment contains 180 warm-up dates plus a 100-day tournament, nine synthetic stocks in three sectors, eight contestants, and twenty additional synthetic tournaments. It is preserved in `results_v1/`. Version 0.2 added the opponent-aware ninth contestant; that experiment with nonzero costs is preserved in `results_v2_costs/`. Version 0.3 reruns the same nine-player evaluation schedule with zero trading costs in `results/`. The optimizer is rerun under zero costs; its prices and fills may change, so this is not merely adding old costs back to old profits. Daily synthetic innovations are correlated across stocks but have no deliberately built-in technical-indicator predictability. Sector labels mainly change volatility.

The fixed demonstration seed is 7; the additional seeds are 1007 through 1026. The main run assumes uninformed customer flow. A stress scenario uses the same prices and latent customer random draws, but 35% of customer orders choose their side with perfect knowledge of the close. This is a deliberately severe adverse-selection assumption, not a measured market statistic.

In the archived v0.1 experiment, the sector router wins the main run, while the neutral fixed-spread dealer has the highest average P&L across the twenty additional simulations. With informed customers, the cash-only player wins the stress scenario. These findings illustrate sensitivity to the price path, opponents and customer information; they do not establish a real trading edge. Original values are in `results_v1/RESULTS.md`; updated nine-player results are in `results/RESULTS.md`.

The engine is verified for price priority, fills and outside allocation, long/short cash accounting, budget limits, future-data isolation, reproducibility and the local API. Every evaluation day closes with zero inventory.

## 6. A credible empirical study

1. Fix an economic universe using information available at the time. Avoid selecting only surviving or successful companies.
2. Split chronologically into training, validation and final test dates. Fit models on training data; choose sectors, windows, quote widths and penalties on validation data only. During the test, refit past-only estimates using the fixed predeclared procedure.
3. Compare a focal strategy against a fixed opponent population on identical price paths and customer requests. The packaged tournament ranks simultaneous players; this does not by itself isolate the causal contribution of a single indicator.
4. Include no-trade and no-signal baselines. Report exposure, fill rates, fees, liquidation losses and drawdown alongside profit. A bigger notional bet should not be mistaken for a better forecast.
5. Vary informed flow, external liquidity, costs, short availability and competition. The synthetic customer-flow assumption may dominate results.
6. Use more than one 100-day window and several market regimes. Treat the included paired block bootstrap as descriptive: it conditions on fitted policies, does not refit them and does not adjust for choosing a winner after seeing the data.
7. Use timestamped quotes/trades and order-book or RFQ data when investigating actual execution. Historical daily OHLCV supplies paths and lagged features, but cannot recover queues, customer orders or trading prices.

## 7. Stochastic-control and PDE extension

For a more mathematical second stage, allow repeated quotes within each day. State variables become time t, mid-price S, cash X, inventory Q, sector signals and possibly competitors' states. Suppose the mid-price follows

$$
dS_t=\mu_t\,dt+\sigma_t\,dW_t,
$$

while bid and ask executions arrive with intensities depending on the dealer's quotes and its competitors. A dealer controls price offsets and quantities, and maximizes terminal marked-to-market wealth minus holding-risk and close-out costs. Forced liquidation gives a terminal value of the form

$$
V(T,x,s,q)=x+qs-\operatorname{closeoutCost}(q,s).
$$

Dynamic programming gives a nonlinear Hamilton-Jacobi-Bellman equation with a diffusion term in price and jump terms in cash/inventory. If every player's quote responds strategically to the others, this becomes a stochastic game rather than a single-agent control problem. Avellaneda–Stoikov [3] is a useful starting reference for inventory-aware market making; the daily code here is not an implementation of its continuous-time model.

Practical extensions should come in this order: intraday data and event clock; repeated quote/cancel actions; explicit inventory skew and terminal liquidation; calibrated fills and price impact; then adaptive opponents or equilibrium questions. An equilibrium claim is not justified by merely running several fixed strategies against one another.

## References

[1] [SEC Investor.gov: Bid Price/Ask Price](https://www.investor.gov/introduction-investing/investing-basics/glossary/ask-price).

[2] [Nasdaq Equity 4 trading rules](https://listingcenter.nasdaq.com/rulebook/nasdaq/rules/Nasdaq%20Equity%204), Opening Cross provisions.

[3] [M. Avellaneda and S. Stoikov, High-frequency trading in a limit order book](https://math.nyu.edu/inmemoriam/avellaneda/HighFrequencyTrading.pdf), Quantitative Finance, 2008.

## 8. Opponent-aware expected-profit quoting (implemented in v0.2)

A ninth player estimates a conditional joint distribution of competing quote/quantity books and terminal-price residuals, then chooses its quote to maximize estimated net profit. Completed books are disclosed after settlement; no current competitor quotes or same-day outcomes are supplied to the learner. The mean price forecast remains sector_router's forecast.

For a single lot and conditionally independent closing value and competing bids, the bid objective reduces to `(expected closing value - bid - costs) * probability of beating the best rival bid`. The actual code evaluates partial fills under whole-book scenarios and therefore does not need that factorization or independent-rival assumptions. It explicitly allows abstention. Quantity budgets are assigned before optimizing prices.

See `OPPONENT_STRATEGY.md` for the derivation, implementation choices, censored-data caveat, and the distinction between an estimated best response and a Nash equilibrium. Results include past-only learning diagnostics and predicted-versus-realized outcomes, which should be assessed separately from profit rankings.
