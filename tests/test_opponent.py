from dataclasses import replace
import unittest

import numpy as np

from auction_lab.data import synthetic_data
from auction_lab.engine import Config, Game, clear_order, liquidate
from auction_lab.opponent import OpponentQuoteModel, scenario_scores


def free_config(**kwargs):
    return Config(fee_bps=0, closing_half_spread_bps=0, closing_slippage_bps=0,
                  short_borrow_bps=0, **kwargs)


class ExpectedProfitTests(unittest.TestCase):
    def test_scenario_partial_fills_match_real_engine_on_both_sides(self):
        c = Config()
        books = [
            {"A": {"price": 100.00, "quantity": 60}, "B": {"price": 100.05, "quantity": 80}},
            {"A": {"price": 99.95, "quantity": 30}, "B": {"price": 100.00, "quantity": 20}},
        ]
        prices, closes, weights = np.array([99.9, 99.95, 100, 100.05, 100.1]), [99.8, 100.2], [0.3, 0.7]
        for side in ["buy", "sell"]:
            order = {"date": "2024-01-01", "symbol": "X", "customer_side": side,
                     "quantity": 100, "reserve_price": 100.05 if side == "buy" else 99.95}
            score = scenario_scores(order, prices, 50, weights, closes, books, c)
            for j, price in enumerate(prices):
                expected_pnl = expected_q = probability = 0
                for book, close, weight in zip(books, closes, weights):
                    full = {**book, "opponent_aware": {"price": price, "quantity": 50}}
                    fills, _ = clear_order(order, full, c.seed)
                    own = [f for f in fills if f["player"] == "opponent_aware"]
                    if own:
                        f = own[0]
                        expected_pnl += weight * liquidate(f["signed_quantity"], price, close, c)["net_pnl"]
                        expected_q += weight * f["quantity"]
                        probability += weight
                self.assertAlmostEqual(score["expected_profit"][j], expected_pnl)
                self.assertAlmostEqual(score["expected_quantity"][j], expected_q)
                self.assertAlmostEqual(score["fill_probability"][j], probability)

    def test_uniform_competitor_distribution_has_interior_optimum(self):
        rivals = np.linspace(99, 101, 401)
        books = [{"rival": {"price": float(b), "quantity": 1}} for b in rivals]
        order = {"date": "2024-01-01", "symbol": "X", "customer_side": "sell",
                 "quantity": 1, "reserve_price": 99}
        prices = np.round(np.arange(99, 100.91, 0.01), 2)
        for cost in [0.0, 0.1]:
            with self.subTest(cost_per_share=cost):
                c = replace(Config(), closing_slippage_bps=cost / 101 * 10000)
                s = scenario_scores(order, prices, 1, np.ones(401) / 401, np.full(401, 101.0), books, c)
                best = int(np.argmax(s["expected_profit"]))
                # Continuous optimum is (101 - cost + 99)/2: 100.00 with zero costs.
                optimum = (101 - cost + 99) / 2
                expected = (101 - cost - optimum) * (optimum - 99) / 2
                self.assertLessEqual(abs(prices[best] - optimum), 0.02)
                self.assertLess(abs(s["expected_profit"][best] - expected), 0.004)

    def test_joint_dependence_is_not_replaced_by_product_of_means(self):
        order = {"date": "2024-01-01", "symbol": "X", "customer_side": "sell",
                 "quantity": 1, "reserve_price": 98}
        books = [{"A": {"price": 100, "quantity": 1}}, {"A": {"price": 98, "quantity": 1}}]
        s = scenario_scores(order, [99], 1, [0.5, 0.5], [99, 101], books, free_config())
        self.assertAlmostEqual(s["expected_profit"][0], 1)
        self.assertNotAlmostEqual(s["expected_profit"][0], (100 - 99) * 0.5)

    def test_abstains_when_all_eligible_quotes_have_nonpositive_expectation(self):
        c = free_config(opponent_min_history=2, opponent_min_dates=1)
        model = OpponentQuoteModel(c)
        for date in ["2024-01-01", "2024-01-02"]:
            model.observe_completed({"date": date, "sector": "technology", "customer_side": "buy",
                "context": [0, 0, 0, 0.01], "return": 0, "alpha": 0,
                "book": {"A": {"relative_price": 0.97, "quantity_fraction": 1}}})
        order = {"date": "2024-01-03", "symbol": "X", "sector": "technology", "customer_side": "buy",
                 "quantity": 100, "reserve_price": 100.15, "reference_price": 100}
        row = {"macd": 0, "reversal": 0, "volume_momentum": 0, "lag_volatility": 0.01, "lag_volume": 1e6}
        quote, diagnostic = model.quote(order, row, 0, 1e6, 1)
        self.assertIsNone(quote)
        self.assertEqual(diagnostic["mode"], "abstain")

    def test_scenario_mean_preserves_sector_forecast(self):
        c = free_config()
        model = OpponentQuoteModel(c)
        episodes = [{"context": [i * 0.001, 0, 0, 0.01], "return": r, "alpha": 0.002, "book": {}}
                    for i, r in enumerate([-0.02, 0.01, 0.005])]
        row = {"macd": 0.001, "reversal": 0, "volume_momentum": 0, "lag_volatility": 0.01}
        order = {"reference_price": 100, "quantity": 100, "customer_side": "sell"}
        weights, closes, _ = model._distribution(episodes, row, order, 0.003)
        self.assertAlmostEqual(weights @ closes, 100.3)


class OpponentInformationTests(unittest.TestCase):
    def test_trained_optimizer_cannot_see_current_or_future_outcomes(self):
        data = synthetic_data(90, 4)
        changed = data.copy()
        cutoff = sorted(data["date"].unique())[72]
        mask = changed["date"] >= cutoff
        changed.loc[mask, "close"] *= 1.2
        changed.loc[mask, "volume"] *= 2
        c = Config(days=14, warmup=60, seed=4, opponent_min_history=2, opponent_min_dates=2)
        a, b = Game(data, c), Game(changed, c)
        for _ in range(13):
            a.step()
            b.step()
        self.assertEqual(a.quote_log, b.quote_log)
        decisions = [x for x in a.opponent_decisions if x["date"] == str(cutoff.date())]
        self.assertTrue(decisions)
        self.assertTrue(all(x["mode"] in {"optimized", "abstain"} for x in decisions))
        self.assertTrue(all(x["latest_training_date"] < x["date"] for x in decisions))
        self.assertTrue(all(x["approved_quantity"] == x["requested_quantity"] for x in a.opponent_decisions))

    def test_same_day_and_future_episodes_are_excluded(self):
        model = OpponentQuoteModel(Config())
        for date in ["2024-01-01", "2024-01-02", "2024-01-03"]:
            model.observe_completed({"date": date, "sector": "technology", "customer_side": "sell"})
        past = model._past({"date": "2024-01-02", "sector": "technology", "customer_side": "sell"})
        self.assertEqual([e["date"] for e in past], ["2024-01-01"])


if __name__ == "__main__":
    unittest.main()
