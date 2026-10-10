> Technical notes from the earlier prototype. For version-0.4 defaults, six/nine-player selection, and current documentation, start with [README.md](README.md) and [docs/](docs/01_market_and_api.md). Earlier result paths are retained under `archive/`; current results are separated into `results/six_players/` and `results/nine_players/`.

# Opponent-aware quoting by expected-profit optimization

Version 0.2 added `opponent_aware` as a ninth contestant. Version 0.3 sets all trading costs to zero for every player, including this optimizer. It is a numerical best response to an estimated distribution of other players' actions. It is not a Nash-equilibrium solver or a guarantee of positive realized profit.

## 1. What should be predicted?

In this game's pay-as-bid auction, a winning dealer trades at **its own submitted price**. Competitors' quotes determine whether it receives a fill and how much it receives. Therefore the quantities to predict are competitors' submitted prices and capacities, not a common execution price that everyone will pay.

If competitors' algorithms, parameters and inputs were fully known and deterministic, their quotes could in principle be calculated directly. A probability model describes incomplete knowledge: hidden parameters, inventories, private signals, changing behaviour, and estimation uncertainty. The new player treats its rivals as black boxes and learns only from past disclosed auctions, even though their source code is available to the researcher.

Modelling competitor quote distributions and resulting probabilities of trade has a close analogue in the RFQ research of Fermanian, Gueant and Pu [1]. Their empirical setting is corporate bonds; the implementation here is a simplified stock game, not a reproduction or calibration of that paper.

## 2. A simple single-lot bid problem

Suppose a customer sells Q shares as one indivisible lot. Each opponent can buy the entire lot. Let:

- b be our bid;
- B be the highest competing bid;
- C be the evening liquidation value before costs;
- v = E[C | I] be our fair-value forecast given current information I;
- c be a simplified constant round-trip cost per share, set to zero in the default game;
- L be the customer's minimum acceptable bid.

Assume ties have probability zero and, for this simple calculation, C and B are conditionally independent given I. For an eligible bid b >= L,

$$
\mathbb E[\Pi(b)\mid\mathcal I]
=Q(v-b-c)F_B(b\mid\mathcal I),
$$

where F_B(b | I) = P(B <= b | I). Raising b increases the probability of winning but reduces the profit per share if we win.

The action is the maximizer over eligible bids **and abstention**, whose trading profit is zero. With a differentiable CDF, a positive density and an interior optimum,

$$
\frac{d}{db}\big[(v-b-c)F_B(b)\big]
=-F_B(b)+(v-b-c)f_B(b)=0,
$$

so

$$
\boxed{b^*=v-c-\frac{F_B(b^*)}{f_B(b^*)}.}
$$

This is an implicit first-order condition, not a universal closed-form solution. Boundaries, the reserve price, abstention and multiple local optima still need checking. Real quote ticks and ties require a discrete search.

If there are n opponents whose bids are conditionally independent with CDFs F_1,...,F_n, then F_B(b) = product_i F_i(b). Shared information and related strategies often invalidate this independence assumption. A joint model or direct model of B avoids that product assumption. The implemented player replays joint books instead.

## 3. The ask problem

When the customer buys, we submit an ask a. Let A be the lowest rival ask, with CDF G_A. Under the corresponding single-lot and conditional-independence assumptions,

$$
\mathbb E[\Pi(a)\mid\mathcal I]
=Q(a-v-c)\bigl[1-G_A(a\mid\mathcal I)\bigr].
$$

Lowering a increases the chance of selling, while reducing the margin. An interior optimum satisfies

$$
\boxed{a^*=v+c+\frac{1-G_A(a^*)}{g_A(a^*)}.}
$$

The customer also has a maximum acceptable ask. The code enforces that reservation price. Optional proportional fees and close-out costs use the same accounting as all other players; they are zero by default.

With c = 0, the objectives are `Q(v - b) F_B(b)` for a bid and `Q(a - v) [1 - G_A(a)]` for an ask. The corresponding interior conditions become `b* = v - F_B(b*)/f_B(b*)` and `a* = v + [1 - G_A(a*)]/g_A(a*)`. Zero transaction costs do not imply zero quote margins: competition still trades off the margin against the chance of filling.

## 4. Numerical example

Let v = 101, c = 0, and let the **best rival bid** B be uniform on [99, 101]. Assume the customer's reserve does not exclude the bids below. Within this interval,

$$
F_B(b)=\frac{b-99}{2},\qquad
\frac{\mathbb E[\Pi(b)]}{Q}=(101-b)\frac{b-99}{2}.
$$

Differentiation gives b* = (101 + 99)/2 = 100.00, with expected profit 0.50 per offered share.

| Bid | Win probability | Margin if filled | Expected profit per offered share |
|---|---:|---:|---:|
| 99.50 | 25.0% | 1.50 | 0.37500 |
| **100.00** | **50.0%** | **1.00** | **0.50000** |
| 100.50 | 75.0% | 0.50 | 0.37500 |

The most aggressive bid in this table wins more often but earns less in expectation. These are illustrative numbers, not results fitted to market data. `expected_profit_example.png` plots this exact objective.

## 5. Why a quote density alone is sometimes insufficient

The independence between closing value and competitors' bids was only a simplifying assumption. More generally, even for one lot,

$$
\mathbb E[\Pi(b)\mid\mathcal I]
=Q\int_{-\infty}^{b}
\left(\mathbb E[C\mid B=u,\mathcal I]-b-c\right)
f_B(u\mid\mathcal I)\,du.
$$

For instance, a low competitor bid may itself indicate a low asset value. The value conditional on winning can differ from the unconditional forecast. Ignoring this selection can produce an apparently profitable quote that loses in practice.

The actual game also has divisible orders and capacity limits. A dealer can receive shares even without offering the best price, because better-priced rivals may run out of capacity. Let q_fill(p, book) be the fill computed from the complete rival price/quantity book. The relevant objective becomes

$$
J(p)=\mathbb E\left[
\operatorname{netPnL}\big(p,q_{\rm fill}(p,\mathrm{book}),C\big)
\mid\mathcal I\right].
$$

That is the objective implemented since version 0.2. It uses the same price priority, tie lottery, reserve constraints and liquidation accounting as the simulator. In version 0.3, net P&L defaults to signed filled quantity times `(C - p)`, with no cost deduction.

## 6. The distribution implemented in the code

The first version uses a **conditional empirical probability distribution**, not a fitted Gaussian density. A density is not necessary to compute an expectation: a weighted sum over scenarios is sufficient and naturally supports discrete quote ticks.

After a day is finished, the learner records each stock's approved opponent quote book, the opening-time features, the sector-router forecast, and the eventual open-to-close return. Today's quotes are never used to choose today's action, including quotes on stocks processed earlier in the same day.

For the next decision:

1. Keep completed episodes from the same sector and customer side, with dates strictly before today, over at most the last 126 relevant dates.
2. Require at least 30 observations spanning 10 distinct dates. Until then use the sector-router quote with the new player's quantity budget.
3. Weight episodes by similarity in lagged MACD, reversal, volume momentum and volatility. Context distances are scaled by historical standard deviations. Gaussian kernel bandwidth is 1.5; weights mix 95% kernel probability with 5% uniform probability.
4. Replay entire opponent books. Historical price/open ratios become quotes relative to today's open; historical offered-quantity/customer-quantity ratios become capacities relative to today's request. Quotes are rounded to ticks. Opponents within one historical episode stay together, preserving their empirical dependence.
5. Pair every book with its historical closing-return residual relative to the sector-router forecast. Shift those residuals so the weighted mean return equals today's sector-router forecast. This keeps the mean valuation comparable while retaining empirical dependence between the book and the residual. A defensive positivity floor applies only to impossible nonpositive scenario prices.
6. Compute partial fills and net P&L under each candidate quote and scenario. Average with the scenario probabilities. Choose the best quote if its estimated expectation is positive; otherwise abstain.

In notation, for scenarios e with weights w_e,

$$
\widehat J(p)=\sum_e w_e\,
\operatorname{netPnL}\big(p,q_{\rm fill}(p,\mathrm{book}_e),C_e\big),
\qquad \sum_e w_e=1.
$$

The value forecast is still a model assumption. In particular, centering on the existing sector forecast can leave bias when customer order direction itself carries price information. Learning a customer-side-dependent value forecast is a separate extension.

## 7. Prices, quantities and information rules

The search band defaults to +/-200 basis points of the open, intersected with customer-acceptable prices. The player searches every tick if the range contains at most 2,001 ticks. For larger ranges, it uses a bounded regular grid augmented by rival-price breakpoints and adjacent ticks. It is optimal only within this candidate set and under the fitted distribution.

Each current request receives an equal slice of the player's available gross capital. Its share quantity is bounded by the common volume, volatility and single-stock constraints and reserved at the highest price in the search band. That quantity stays fixed while prices are compared. Unused slices are not dynamically redistributed, and the code does not claim to solve a joint portfolio-allocation problem.

All approved quotes, including losing ones, become observable to every player **after settlement**. The local API returns them in each completed step and at GET /games/{id}/quotes. This is a new, explicit simulation disclosure rule.

If only winning execution prices are observable, they are not an unbiased sample of all submitted quotes. That is a censored-feedback learning problem. Han, Zhou and Weissman [2] study learning in repeated first-price auctions with this kind of restricted feedback. The present full-book model would need to change for such a market.

## 8. Interpreting the experiments

The nine-player tournament reuses the original synthetic price seed, uninformed customer-generation rule and 100-day evaluation length. Adding a competitor changes other players' fills and subsequent capital; the result is therefore a new tournament, not an extra row that can simply be appended to the old leaderboard. The original eight-player results remain in `results_v1/`; the version 0.2 nine-player results with costs are in `results_v2_costs/`. Version 0.3 reruns every player with zero trading costs in `results/`, including recomputing the optimizer's quotes and subsequent fills.

`results/opponent_decisions.csv` records learning cutoffs, modes, chosen quotes, expected and actual fills/profits and a same-quantity fixed-offset quote comparison under the fitted distribution. Its estimated gains are not out-of-sample proof of calibration: selecting the maximum of noisy estimates can be optimistic. The realized 100-day and repeated-seed results must be read separately.

The system passes 22 tests, including zero-cost long/short accounting, exact agreement between scenario scoring and the auction engine, a known analytic optimum with zero and nonzero costs, preservation of joint dependence, nonprofitable abstention, and a trained-model test that changes future outcomes without changing current quotes.

Useful next studies are chronological calibration of fill probabilities, sensitivity to the opponent population, adaptive opponents, uncertainty penalties on estimated profit, and learning from censored observations. Multiple optimizing players do not automatically establish a Nash equilibrium.

## References

[1] Jean-David Fermanian, Olivier Gueant and Jiang Pu, [The behavior of dealers and clients on the European corporate bond market: the case of Multi-Dealer-to-Client platforms](https://arxiv.org/abs/1511.07773).

[2] Yanjun Han, Zhengyuan Zhou and Tsachy Weissman, [Optimal No-regret Learning in Repeated First-price Auctions](https://arxiv.org/abs/2003.09795).

[3] Jonathan Levin, [Auction Theory lecture notes](https://web.stanford.edu/~jdlevin/Econ%20286/Auctions.pdf), for first-price auction foundations.

## Current version 0.3 results with zero costs

With synthetic prices, seed 7 and 100 evaluation days, opponent_aware earned 23,699.55 on 1,000,000 initial nominal capital. Price reversal led that run with 25,561.45. Across twenty additional synthetic tournaments, opponent_aware's mean P&L was 10,488.77 and it won 2 of 20; tight_quote had the highest mean P&L, 17,215.38, and won 10 of 20.

The optimizer made 667 optimized quotes, 185 warm-up decisions and 48 abstentions. Its 715 model-based decisions predicted total profit of 47,946.13 and realized 11,598.47. The difference remains substantial despite removing costs. The separate stress scenario with 35% perfectly informed orders produced a loss of 50,330.58 for this player; no_trade won at zero. Zero costs remove transaction deductions, not price risk or adverse selection.

The new main experiment uses exactly the same 900 customer requests and price path as the archived nine-player run. Every strategy and the optimizer use zero fees, zero closing spread/slippage and zero short-borrow charges. The change can alter optimal quotes, fills and future capital, so the new P&Ls are not obtained by adding old costs back. The actual trades have net P&L equal to gross P&L, and every day ends with zero inventory. Current diagnostics are in `results/opponent_decisions.csv` and the complete comparison is in `results/RESULTS.md`.

## Archived version 0.2 results with costs

With synthetic prices, seed 7 and 100 evaluation days, opponent_aware earned 1,124.20 on 1,000,000 initial nominal capital. Across twenty additional synthetic tournaments its mean P&L was -2,896.34, and it won 4 of 20 tournaments. These results do not establish an improvement in expected real-world profit.

Its learned-mode decisions predicted an aggregate profit of 33,495.35 but realized a loss of 10,051.42; the positive full-run result also includes the initial fixed-quote warm-up decisions. This illustrates the importance of calibration and selection bias when optimizing noisy profit estimates. Archived diagnostics are in `results_v2_costs/opponent_decisions.csv`; these numbers use nonzero costs.
