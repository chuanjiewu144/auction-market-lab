# 3. Forecasts and quoting strategies

Every strategy can quote on every stock. Sector labels change model estimation or signal selection; they do not allocate exclusive stocks to different players.

## Common training procedure

For stock $j$ and date $d$, the target is the realized open-to-close return:

$$y_{j,d}=C_{j,d}/O_{j,d}-1.$$

To quote on date $t$, the regression uses only dates $d<t$, over the latest 126 completed dates. Observations are pooled within a sector. Three stocks and 126 usable dates give $n_s=378$ stock-date rows per sector; shared market shocks mean these rows are not independent samples.

Input columns are standardized using that sector's training mean and sample standard deviation. The target remains a raw decimal return. For a standardized design matrix $Z$, the coefficient is

$$\widehat\beta=(Z^\top Z+0.25n_s I)^{-1}Z^\top y.$$

No intercept is fitted. Today's predicted return is clipped to $[-0.01,0.01]$. The coefficients, standardization and whitening are refitted from past data each morning. Fewer than 40 usable training rows gives a zero prediction. The 126-day window, penalty and sector routing are fixed experiment choices, not settings optimized on the displayed test results.

## The six research strategies

### MACD (`macd`)

Let $L=\operatorname{EMA}_{12}(C)-\operatorname{EMA}_{26}(C)$, and let the histogram be $H=L-\operatorname{EMA}_{9}(L)$. The morning input is

$$x^M_{j,t}=H_{j,t-1}/C_{j,t-1}.$$

Fit one single-feature regression in each sector. Its coefficient is learned and can have either sign: the name identifies the input, not a forced buy/sell rule.

### Price reversal (`price_reversal`)

The input measures the previous close relative to its 20-day moving average:

$$x^R_{j,t}=\overline C^{20}_{j,t-1}/C_{j,t-1}-1.$$

A positive raw value means price is below its moving average. Sector-specific regression decides whether that feature was associated with positive or negative subsequent open-to-close returns.

### Volume momentum (`volume_momentum`)

The input combines the previous close-to-close return with relative volume:

$$x^V_{j,t}=\left(\frac{C_{j,t-1}}{C_{j,t-2}}-1\right)
\left(\frac{V_{j,t-1}}{\overline V^{20}_{j,t-1}}-1\right).$$

The mean-volume window includes $t-1$. The signed product can also reverse sign when volume is below average. It feeds one single-feature regression per sector.

### Sector strategy (`sector_router`)

Use the MACD model on technology stocks, volume momentum on commodity-related stocks, and reversal on financial stocks. This is a predeclared routing hypothesis. It does not learn the sector-to-signal mapping from the evaluation period.

Each sector's selected training matrix is $n_s\times1$, and its coefficient is scalar. A stock uses its own current signal with the coefficient shared by its sector. At a given date, its forecast equals the corresponding single-indicator strategy's forecast; overall portfolios can still differ because the router mixes policies across sectors and capital is shared across its submitted quotes.

### Orthogonal ensemble (`orthogonal_ensemble`)

Within each sector, use all three input columns, $X_s\in\mathbb R^{n_s\times3}$. Standardize to $Z_s$, then compute

$$\frac{Z_s^\top Z_s}{n_s-1}=U\Lambda U^\top,\qquad
W_s=Z_s U_r\Lambda_r^{-1/2}.$$

Retain eigenvalues greater than $10^{-8}$. This gives $W_s^\top W_s/(n_s-1)=I_r$, up to numerical precision. Fit the same ridge regression with $W_s$ as its design. Transform today's three signals using the same fitted means, scales and whitening matrix:

$$\omega_{j,t}\in\mathbb R^{1\times r},\qquad
\widehat\beta_{s,t}\in\mathbb R^{r\times1},\qquad
\widehat\alpha_{j,t}=\operatorname{clip}(\omega_{j,t}\widehat\beta_{s,t},-0.01,0.01).$$

When all components are retained, $r=3$. The three components mix indicator columns; they do not represent the three sectors. There is a separate coefficient vector for each sector.

Whitening removes training-sample linear covariance among retained features. It does not guarantee uncorrelated future signals, independent strategy profits, improved prediction or higher profit. Keeping every component introduces no new information; with ridge it changes the geometry of the coefficient penalty.

### Expected-profit strategy (`opponent_aware`)

This player uses the sector router's mean closing-price forecast, then models execution competition. It learns from completed matching-sector, matching-side RFQs. Current rival quotes are never visible.

Historical episodes contain entire approved quote/quantity books and paired realized-return residuals. Gaussian context weights use the three lagged signals and lagged volatility; a 5% uniform mixture limits extreme concentration. Books are rescaled to today's price and order size. Return scenarios are recentered around today's sector forecast while retaining their pairing with rival books.

This is a conditional empirical probability distribution, not a fitted normal density or an independence assumption across rivals. For a candidate own quote $p$, score

$$\widehat{\mathbb E}[\Pi(p)]
=\sum_{\ell}w_\ell F_\ell(p)\,d\,(C_\ell-p),$$

under zero costs. Here $d=+1$ when the dealer buys, $d=-1$ when it sells, and $F_\ell(p)$ is the nonnegative filled quantity under scenario $\ell$, including price priority, ties, reserve eligibility and partial fills. Choose the highest positive estimated profit over candidate prices; otherwise abstain. With optional costs, the same configured deductions enter the scenario score and realized accounting.

Quantity is fixed before optimization using equal capital slices and conservative risk limits. The default search is within 200 basis points of the open and within the customer reserve. Ordinary ranges examine every tick; very large ranges use a bounded grid with rival-price breakpoints. Cold start requires at least 30 matching completed episodes on at least 10 dates; before this, use a sector-based quote. The 180-day price warm-up does not fabricate auction histories.

The player executes at its own quote if it fills. It predicts rival books to estimate fills, rather than predicting a single common auction execution price. This is a fitted best response over a candidate set, not a Nash-equilibrium solver. Its allocation differs from the sector router, so their profit difference does not isolate the causal effect of opponent modelling.

## From return prediction to quote

All ordinary forecasting strategies use opening reference $O$, predicted return $\widehat\alpha$, and half-width $h=8/10000$:

$$b=O(1+\widehat\alpha-h),\qquad a=O(1+\widehat\alpha+h).$$

Submit the bid for a customer sell and the ask for a customer buy. Round bids down and asks up to a tick. Apply quantity/risk limits, then compete. A higher forecast raises both prices; whether the quote fills depends on customer limits and rivals. `opponent_aware` replaces this fixed-offset price rule after cold start.

## Three optional benchmarks

| Player | Forecast | Quote rule |
|---|---|---|
| `no_trade` | None | Always abstain; profit zero, without interest. |
| `flat_quote` | Zero | Bid $O(1-0.0008)$, ask $O(1+0.0008)$. |
| `tight_quote` | Zero | Bid $O(1-0.0001)$, ask $O(1+0.0001)$. |

At an opening price of 100 before tick effects, fixed quotes are 99.92/100.08 and tight quotes are 99.99/100.01. These widths are not transaction fees. Adding these players changes the auction and must trigger a fresh run; filtering a nine-player chart cannot reproduce a six-player tournament.
