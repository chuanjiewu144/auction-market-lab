"""Run the API first: python -m auction_lab serve. This bot has no price forecast."""
import json
import math
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8000"


def request(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=120) as response:
        return json.load(response)


game = request("/games", {"days": 100, "seed": 7, "competitors": 6})
identifier, state = game["game_id"], game["state"]
while not state["done"]:
    quotes = {}
    tick = state["config"]["tick"]
    for order in state["orders"]:
        buy = order["customer_side"] == "sell"
        value = order["reference_price"] * (1 + (-1 if buy else 1) * 5 / 10000)
        price = (math.floor(value / tick) if buy else math.ceil(value / tick)) * tick
        quotes[order["symbol"]] = {"price": round(price, 8), "quantity": 500}
    response = request(f"/games/{identifier}/step", {"quotes": quotes})
    state = response["next_state"]
print(json.dumps(request(f"/games/{identifier}/results")["leaderboard"], indent=2))
