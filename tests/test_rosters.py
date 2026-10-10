"""Check that roster selection changes the auction and remains per-game state."""
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from auction_lab.data import synthetic_data
from auction_lab.engine import Config, Game
from auction_lab.report import save_game
from auction_lab.signals import CORE_STRATEGIES, STRATEGIES


class RosterTests(unittest.TestCase):
    def test_rosters_are_isolated_and_share_customer_inputs(self):
        data = synthetic_data(80, 7)
        six = Game(data, Config(days=2, warmup=60))
        nine = Game(data, Config(days=2, warmup=60, competitors=9))
        self.assertEqual(six.observation()["orders"], nine.observation()["orders"])
        six.step()
        nine.step()
        six.step()
        nine.step()
        self.assertEqual(tuple(six.players), CORE_STRATEGIES)
        self.assertEqual(tuple(nine.players), STRATEGIES)
        self.assertEqual({r["player"] for r in six.daily}, set(CORE_STRATEGIES))
        self.assertFalse({"no_trade", "flat_quote", "tight_quote"} &
                         {r["player"] for r in six.quote_log})
        self.assertTrue(all(set(e["book"]) <= set(CORE_STRATEGIES)
                            for e in six.opponent_model.episodes))
        self.assertEqual(six.observation()["equity"].keys(), six.equity.keys())

    def test_six_player_report_has_an_existing_explicit_baseline(self):
        game = Game(synthetic_data(80, 7), Config(days=2, warmup=60)).run()
        with tempfile.TemporaryDirectory() as directory:
            summary = save_game(game, directory)
            self.assertEqual(summary["number_of_players"], 6)
            self.assertEqual(summary["bootstrap_baseline"], "sector_router")
            comparisons = pd.read_csv(Path(directory) / "paired_bootstrap.csv")
            self.assertEqual(set(comparisons["baseline"]), {"sector_router"})
            self.assertTrue((Path(directory) / "overview.png").is_file())

    def test_unsupported_rosters_are_rejected(self):
        for count in (0, 5, 7, 8, 10, True, 6.0):
            with self.subTest(count=count), self.assertRaises(ValueError):
                Config(competitors=count)


if __name__ == "__main__":
    unittest.main()
