import unittest

import numpy as np
import pandas as pd

from auction_lab.data import FEATURES, make_features, synthetic_data, validate_data
from auction_lab.engine import Config, Game, clear_order, liquidate
from auction_lab.signals import fit_whitener, predict_day


class AuctionTests(unittest.TestCase):
    def order(self, side="sell", quantity=100, reserve=99.0):
        return {"customer_side": side, "quantity": quantity, "reserve_price": reserve,
                "date": "2024-01-02", "symbol": "X"}

    def test_highest_bid_and_partial_fill(self):
        quotes = {"A": {"price": 100, "quantity": 60}, "B": {"price": 101, "quantity": 70}}
        fills, external = clear_order(self.order(), quotes)
        self.assertEqual([(f["player"], f["quantity"]) for f in fills], [("B", 70), ("A", 30)])
        self.assertEqual(external, 0)
        self.assertEqual(fills[0]["price"], 101)  # pay own quote
        self.assertTrue(all(f["signed_quantity"] > 0 for f in fills))

    def test_lowest_ask_wins(self):
        quotes = {"A": {"price": 100, "quantity": 100}, "B": {"price": 99.5, "quantity": 100}}
        fills, _ = clear_order(self.order("buy", reserve=101), quotes)
        self.assertEqual(fills[0]["player"], "B")
        self.assertEqual(fills[0]["signed_quantity"], -100)

    def test_reserve_and_outside_option(self):
        fills, external = clear_order(self.order(), {"A": {"price": 98, "quantity": 100}})
        self.assertEqual(fills, [])
        self.assertEqual(external, 100)
        fills, external = clear_order(self.order(), {"A": {"price": 100, "quantity": 25}})
        self.assertEqual(sum(f["quantity"] for f in fills) + external, 100)

    def test_ties_do_not_depend_on_dictionary_order(self):
        q = {name: {"price": 100, "quantity": 75} for name in ["A", "B", "C"]}
        self.assertEqual(clear_order(self.order(), q, 12), clear_order(self.order(), dict(reversed(list(q.items()))), 12))

    def test_liquidation_signs_and_cash_accounting(self):
        c = Config(fee_bps=0.5, closing_half_spread_bps=3.0,
                   closing_slippage_bps=1.0, short_borrow_bps=0.5)
        for q in [100, -100]:
            result = liquidate(q, 100, 102, c)
            cash = -q * 100 - result["entry_fee"] + q * result["exit_price"] - result["exit_fee"] - result["borrow_cost"]
            self.assertAlmostEqual(cash, result["net_pnl"])
            self.assertAlmostEqual(result["gross_pnl"] - result["costs"], result["net_pnl"])
            self.assertGreater(result["costs"], 0)
        self.assertGreater(liquidate(100, 100, 102, c)["net_pnl"], 0)
        self.assertLess(liquidate(-100, 100, 102, c)["net_pnl"], 0)

    def test_default_liquidation_has_zero_cost_for_longs_and_shorts(self):
        for q in [100, -100]:
            for close in [98, 100, 102]:
                result = liquidate(q, 100, close, Config())
                self.assertEqual(result["exit_price"], close)
                self.assertEqual(result["net_pnl"], q * (close - 100))
                self.assertEqual(result["gross_pnl"], result["net_pnl"])
                for name in ["entry_fee", "exit_fee", "borrow_cost", "liquidation_cost", "costs"]:
                    self.assertEqual(result[name], 0)


class InformationAndRiskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = synthetic_data(82, seed=3)
        cls.c = Config(days=2, warmup=60, seed=3)

    def test_current_and_future_outcomes_cannot_change_quotes(self):
        changed = self.data.copy()
        cutoff = sorted(changed["date"].unique())[60]
        mask = changed["date"] >= cutoff
        changed.loc[mask, "close"] *= 1.4
        changed.loc[mask, "volume"] *= 3
        a, b = Game(self.data, self.c), Game(changed, self.c)
        self.assertEqual(a.observation(), b.observation())
        self.assertEqual(predict_day(a._features, cutoff), predict_day(b._features, cutoff))
        a.step()
        b.step()
        self.assertEqual(a.quote_log, b.quote_log)

    def test_history_has_only_completed_bars(self):
        game = Game(self.data, self.c)
        observation = game.observation()
        today = observation["orders"][0]["date"]
        self.assertTrue(all(row["date"] < today for row in game.history()))
        for row in observation["features"]:
            self.assertFalse({"close", "volume", "target", "high", "low"} & row.keys())

    def test_budget_conservation_zero_inventory_and_pnl_identity(self):
        game = Game(self.data, self.c).run()
        quotes = pd.DataFrame(game.quote_log)
        quotes["reserved"] = quotes["quantity"] * quotes["price"] * (1 + self.c.fee_bps / 10000)
        self.assertLessEqual(quotes.groupby(["date", "player"])["reserved"].sum().max(), self.c.capital + 1e-6)
        trades = pd.DataFrame(game.trades)
        self.assertTrue((trades["costs"] == 0).all())
        for order in game.order_log:
            filled = trades[(trades["date"] == order["date"]) & (trades["symbol"] == order["symbol"])]["quantity"].sum()
            self.assertEqual(filled + order["external_quantity"], order["quantity"])
        for row in game.daily:
            self.assertEqual(row["inventory_end"], 0)
            self.assertEqual(row["costs"], 0)
            self.assertAlmostEqual(row["net_pnl"], row["spread_pnl"] + row["price_pnl"] - row["costs"], places=7)

    def test_invalid_action_is_atomic(self):
        game = Game(self.data, self.c, human=True)
        state = game.observation()
        symbol = state["orders"][0]["symbol"]
        with self.assertRaises(ValueError):
            game.step({symbol: {"price": float("nan"), "quantity": 100}})
        self.assertEqual(game.index, 0)
        self.assertEqual(game.daily, [])
        self.assertEqual(game.observation(), state)

    def test_long_only_never_opens_a_short(self):
        game = Game(self.data, Config(days=2, warmup=60, seed=3, allow_short=False)).run()
        self.assertTrue(all(trade["signed_quantity"] > 0 for trade in game.trades))

    def test_whitening_and_rank_deficiency(self):
        rng = np.random.default_rng(9)
        raw = rng.normal(size=(100, 3))
        raw[:, 1] += 0.7 * raw[:, 0]
        for x in [raw, np.column_stack([raw[:, 0], raw[:, 0], np.ones(100)])]:
            mean, scale, matrix = fit_whitener(x)
            z = (x - mean) / scale @ matrix
            np.testing.assert_allclose(np.atleast_2d(np.cov(z, rowvar=False)), np.eye(matrix.shape[1]), atol=1e-10)

    def test_missing_bars_are_not_silently_filled(self):
        with self.assertRaises(ValueError):
            validate_data(self.data.iloc[1:])

    def test_deterministic_replay(self):
        a, b = Game(self.data, self.c).run(), Game(self.data, self.c).run()
        self.assertEqual(a.daily, b.daily)
        self.assertEqual(a.trades, b.trades)


if __name__ == "__main__":
    unittest.main()

