"""Past-only joint empirical opponent model and expected-net-profit quoting.

Historical quote books are disclosed after settlement. Whole books are replayed
as joint scenarios: opponents are never assumed independent. Their paired
return residuals retain estimated dependence between winning and terminal value.
"""
import math

import numpy as np

from .data import FEATURES
from .pricing import stable_seed, tick_price

CONTEXT = FEATURES + ["lag_volatility"]


def scenario_scores(order, prices, quantity, weights, closes, books, config, player="opponent_aware"):
    """Exact price-priority partial fills and net P&L for each scenario/candidate.

    books is a list of dict[player, {price, quantity}], in today's price units.
    Return arrays have one entry per candidate. Ties use the engine's lottery.
    """
    prices = np.asarray(prices, dtype=float)
    weights, closes = np.asarray(weights), np.asarray(closes)
    n, k = len(books), len(prices)
    ahead = np.zeros((n, k))
    bid = order["customer_side"] == "sell"
    our_priority = stable_seed(config.seed, order["date"], order["symbol"], player)
    rival_names = sorted({name for book in books for name in book if name != player})
    for rival in rival_names:
        rp = np.array([book.get(rival, {}).get("price", 0) for book in books])[:, None]
        rq = np.array([book.get(rival, {}).get("quantity", 0) for book in books])[:, None]
        better = rp > prices if bid else rp < prices
        wins_tie = stable_seed(config.seed, order["date"], order["symbol"], rival) < our_priority
        ahead += rq * (better | ((rp == prices) & wins_tie))
    filled = np.minimum(quantity, np.maximum(order["quantity"] - ahead, 0))
    eligible = prices >= order["reserve_price"] if bid else prices <= order["reserve_price"]
    filled *= eligible
    sign = 1 if bid else -1
    exit_fraction = (config.closing_half_spread_bps + config.closing_slippage_bps) / 10000
    exits = closes[:, None] * (1 - sign * exit_fraction)
    fee = config.fee_bps / 10000
    borrow = 0 if bid else config.short_borrow_bps / 10000
    per_share = sign * (exits - prices) - fee * (prices + exits) - borrow * prices
    profit = filled * per_share
    return {
        "expected_profit": weights @ profit,
        "expected_quantity": weights @ filled,
        "fill_probability": weights @ (filled > 0),
    }


class OpponentQuoteModel:
    def __init__(self, config):
        self.config = config
        self.episodes = []

    def observe_completed(self, episode):
        """Engine calls this only after all same-day quotes and fills are fixed."""
        self.episodes.append(episode)

    def _past(self, order):
        eligible = [e for e in self.episodes if e["date"] < order["date"]
                    and e["sector"] == order["sector"] and e["customer_side"] == order["customer_side"]]
        dates = sorted({e["date"] for e in eligible})[-self.config.lookback:]
        return [e for e in eligible if e["date"] in dates]

    def _distribution(self, episodes, row, order, alpha):
        """Conditional probability masses; no density normality assumption."""
        x = np.array([e["context"] for e in episodes])
        current = np.array([row[name] for name in CONTEXT])
        scale = x.std(axis=0, ddof=1)
        scale = np.where(scale > 1e-10, scale, 1.0)
        distance = np.mean(((x - current) / scale) ** 2, axis=1)
        log_weights = -distance / (2 * self.config.opponent_bandwidth ** 2)
        log_weights -= log_weights.max()
        weights = np.exp(log_weights)
        weights /= weights.sum()
        # A small uniform component prevents a near-single-observation distribution.
        weights = 0.95 * weights + 0.05 / len(weights)
        residuals = np.array([e["return"] - e["alpha"] for e in episodes])
        # Preserve the current sector-router mean forecast, but retain dependence
        # of residual terminal value on the sampled opponent book.
        scenario_returns = alpha + residuals - weights @ residuals
        closes = order["reference_price"] * np.maximum(1e-6, 1 + scenario_returns)
        books = []
        for e in episodes:
            book = {}
            for name, quote in e["book"].items():
                if name == "opponent_aware":
                    continue
                price = tick_price(order["reference_price"] * quote["relative_price"], self.config.tick,
                                   bid=order["customer_side"] == "sell")
                quantity = max(0, int(round(order["quantity"] * quote["quantity_fraction"])))
                book[name] = {"price": price, "quantity": quantity}
            books.append(book)
        return weights, closes, books

    def quote(self, order, row, alpha, available_capital, n_orders):
        """Uses only today's observable context and prior completed episodes.

        Fixed per-order quantity is reserved at the search band's highest price;
        this makes the expected-profit calculation consistent with the budget.
        Abstention is an explicit action with payoff zero.
        """
        c = self.config
        bid = order["customer_side"] == "sell"
        ref = order["reference_price"]
        band = c.opponent_quote_band_bps / 10000
        low_tick = max(1, math.ceil(ref * (1 - band) / c.tick - 1e-10))
        high_tick = math.floor(ref * (1 + band) / c.tick + 1e-10)
        highest_price = high_tick * c.tick
        volatility_scale = min(1, 0.015 / max(float(row["lag_volatility"]), 1e-8))
        budget = min(available_capital / max(1, n_orders),
                     available_capital * c.max_stock_fraction * volatility_scale)
        quantity = max(0, int(min(order["quantity"], row["lag_volume"] * c.max_lag_volume_fraction,
                                  budget / max(c.tick, highest_price * (1 + c.fee_bps / 10000)))))
        past = self._past(order)
        diagnostic = {"date": order["date"], "symbol": order["symbol"], "customer_side": order["customer_side"],
                      "history_count": len(past), "latest_training_date": max((e["date"] for e in past), default=None),
                      "fair_close": ref * (1 + alpha), "forecast_return": alpha,
                      "requested_quantity": quantity, "mode": "warmup_sector_quote",
                      "estimated_net_profit": None, "estimated_filled_quantity": None,
                      "estimated_fill_probability": None, "effective_sample_size": None,
                      "fixed_offset_estimated_profit": None}
        baseline_price = tick_price(ref * (1 + alpha + (-1 if bid else 1) * c.half_spread_bps / 10000), c.tick, bid)
        if quantity == 0 or low_tick > high_tick:
            diagnostic.update(mode="no_capacity", quote_price=None, requested_quantity=0)
            return None, diagnostic
        if len(past) < c.opponent_min_history or len({e["date"] for e in past}) < c.opponent_min_dates:
            diagnostic["quote_price"] = baseline_price
            return {"price": baseline_price, "quantity": quantity}, diagnostic
        weights, closes, books = self._distribution(past, row, order, alpha)
        diagnostic["effective_sample_size"] = float(1 / np.sum(weights ** 2))
        if bid:
            low_tick = max(low_tick, math.ceil(order["reserve_price"] / c.tick - 1e-10))
        else:
            high_tick = min(high_tick, math.floor(order["reserve_price"] / c.tick + 1e-10))
        if low_tick > high_tick:
            diagnostic.update(mode="no_eligible_price", quote_price=None, requested_quantity=0)
            return None, diagnostic
        # Exact tick search for ordinary stocks; bounded candidate search for very
        # high prices, augmented with opponent price breakpoints and their neighbors.
        if high_tick - low_tick <= 2000:
            ticks = np.arange(low_tick, high_tick + 1)
        else:
            strategic = [round(q["price"] / c.tick) + shift for book in books for q in book.values()
                         for shift in (-1, 0, 1)]
            ticks = np.unique(np.r_[np.linspace(low_tick, high_tick, 2001).astype(int), strategic])
            ticks = ticks[(ticks >= low_tick) & (ticks <= high_tick)]
        prices = np.round(ticks * c.tick, 8)
        scores = scenario_scores(order, prices, quantity, weights, closes, books, c)
        best = int(np.argmax(scores["expected_profit"]))
        baseline_score = scenario_scores(order, [baseline_price], quantity, weights, closes, books, c)
        diagnostic["fixed_offset_estimated_profit"] = float(baseline_score["expected_profit"][0])
        diagnostic["best_quoted_estimated_profit"] = float(scores["expected_profit"][best])
        if scores["expected_profit"][best] <= 1e-10:
            diagnostic.update(mode="abstain", quote_price=None, requested_quantity=0,
                              estimated_net_profit=0.0, estimated_filled_quantity=0.0,
                              estimated_fill_probability=0.0)
            return None, diagnostic
        price = float(prices[best])
        diagnostic.update(mode="optimized", quote_price=price,
                          estimated_net_profit=float(scores["expected_profit"][best]),
                          estimated_filled_quantity=float(scores["expected_quantity"][best]),
                          estimated_fill_probability=float(scores["fill_probability"][best]))
        return {"price": price, "quantity": quantity}, diagnostic
