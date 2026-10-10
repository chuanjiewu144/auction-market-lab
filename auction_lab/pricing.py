"""Shared price ticks and reproducible auction priorities."""
import hashlib
import math


def stable_seed(*items):
    return int.from_bytes(hashlib.sha256("|".join(map(str, items)).encode()).digest()[:8], "big")


def tick_price(value, tick, bid):
    count = math.floor(value / tick + 1e-10) if bid else math.ceil(value / tick - 1e-10)
    return float(round(max(1, count) * tick, 8))

