"""Integration check starts and stops its own local API process."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class APIIntegrationTest(unittest.TestCase):
    def test_full_game_and_information_boundary(self):
        process = subprocess.Popen([sys.executable, "-m", "auction_lab", "serve", "--port", "0"],
                                   cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True)
        try:
            line = process.stdout.readline()
            self.assertIn("Auction API:", line)
            base = line.split()[2]

            def api(path, body=None, method=None):
                request = Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                  headers={"Content-Type": "application/json"}, method=method)
                with urlopen(request, timeout=20) as response:
                    return json.load(response)

            self.assertEqual(api("/health")["status"], "ok")
            game = api("/games", {"days": 2, "warmup": 60, "seed": 7})
            path, state = "/games/" + game["game_id"], game["state"]
            self.assertEqual(api(path + "/quotes")["completed_quotes"], [])
            today = state["orders"][0]["date"]
            self.assertTrue(all(row["date"] < today for row in api(path + "/history")["history"]))
            with self.assertRaises(HTTPError) as error:
                api(path + "/step", {"quotes": {"BAD": {"price": 100, "quantity": 1}}})
            self.assertEqual(error.exception.code, 400)
            self.assertEqual(api(path)["day"], 1)
            for _ in range(2):
                quotes = {o["symbol"]: {"price": o["reserve_price"], "quantity": 50} for o in state["orders"]}
                result = api(path + "/step", {"quotes": quotes})
                state = result["next_state"]
                self.assertTrue(all(value == 0 for value in result["result"]["inventory_end"].values()))
                completed = api(path + "/quotes")["completed_quotes"]
                self.assertTrue(completed)
                if not state["done"]:
                    self.assertTrue(all(q["date"] < state["orders"][0]["date"] for q in completed))
            self.assertTrue(state["done"])
            result = api(path + "/results")
            self.assertEqual(result["days_completed"], 2)
            self.assertEqual(len(result["leaderboard"]), 7)  # six bots plus external player
            self.assertTrue(api(path, method="DELETE")["deleted"])
            nine = api("/games", {"days": 1, "warmup": 60, "competitors": 9})
            nine_path = "/games/" + nine["game_id"]
            api(nine_path + "/step", {"quotes": {}})
            self.assertEqual(len(api(nine_path + "/results")["leaderboard"]), 10)
            self.assertTrue(api(nine_path, method="DELETE")["deleted"])
        finally:
            process.terminate()
            process.wait(timeout=10)
            process.stdout.close()


if __name__ == "__main__":
    unittest.main()
