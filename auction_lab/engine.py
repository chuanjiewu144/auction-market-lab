"""Sealed, discriminatory-price RFQs with external liquidity and daily close-out."""
from dataclasses import asdict, dataclass
import math

import numpy as np
import pandas as pd

from .data import FEATURES, make_features, validate_data
from .signals import CORE_STRATEGIES, STRATEGIES, predict_day
from .pricing import stable_seed, tick_price
from .opponent import CONTEXT, OpponentQuoteModel


@dataclass(frozen=True)
class Config:
    days: int = 100
    warmup: int = 180
    competitors: int = 6
    seed: int = 7
    capital: float = 1_000_000.0
    half_spread_bps: float = 8.0
    outside_spread_bps: float = 15.0
    fee_bps: float = 0.0                 # optional fee charged on each leg
    closing_half_spread_bps: float = 0.0
    closing_slippage_bps: float = 0.0
    short_borrow_bps: float = 0.0        # optional per-day charge on entry short notional
    max_stock_fraction: float = 0.20
    max_lag_volume_fraction: float = 0.001
    allow_short: bool = True
    informed_fraction: float = 0.0
    tick: float = 0.01
    lookback: int = 126
    opponent_min_history: int = 30
    opponent_min_dates: int = 10
    opponent_bandwidth: float = 1.5
    opponent_quote_band_bps: float = 200.0

    def __post_init__(self):
        if type(self.competitors) is not int or self.competitors not in (6, 9):
            raise ValueError("competitors must be 6 or 9 built-in players")
        for name in ["days", "warmup", "lookback", "opponent_min_history", "opponent_min_dates"]:
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        if self.warmup < 60:
            raise ValueError("warmup must be at least 60 dates")
        for name in ["capital", "tick"]:
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive and finite")
        for name in ["half_spread_bps", "outside_spread_bps", "fee_bps",
                     "closing_half_spread_bps", "closing_slippage_bps", "short_borrow_bps"]:
            value = getattr(self, name)
            if not math.isfinite(value) or not 0 <= value < 1000:
                raise ValueError(f"{name} must lie in [0, 1000)")
        if not 0 <= self.informed_fraction <= 1:
            raise ValueError("informed_fraction must lie in [0, 1]")
        if not 0 < self.max_stock_fraction <= 1 or not 0 < self.max_lag_volume_fraction <= 1:
            raise ValueError("Position and participation fractions must lie in (0, 1]")
        if type(self.allow_short) is not bool:
            raise ValueError("allow_short must be a boolean")
        if not math.isfinite(self.opponent_bandwidth) or self.opponent_bandwidth <= 0:
            raise ValueError("opponent_bandwidth must be positive and finite")
        if self.opponent_min_history < 2:
            raise ValueError("opponent_min_history must be at least 2")
        if not math.isfinite(self.opponent_quote_band_bps) or not 150 <= self.opponent_quote_band_bps <= 900:
            raise ValueError("opponent_quote_band_bps must lie in [150, 900]")


def clear_order(order, quotes, seed=7):
    """Highest eligible bids take customer sells; lowest asks take customer buys.

    quotes: dict[player, {price, quantity}]. Each winner pays its own quote.
    Exact-price ties use a deterministic, seeded lottery, then partial fills.
    Unfilled customer volume goes to an external dealer at the reserve price.
    """
    customer_sells = order["customer_side"] == "sell"
    eligible = []
    for name, quote in quotes.items():
        price, quantity = quote["price"], quote["quantity"]
        acceptable = price >= order["reserve_price"] if customer_sells else price <= order["reserve_price"]
        if quantity > 0 and acceptable:
            eligible.append((name, price, quantity))
    eligible.sort(key=lambda x: (
        -x[1] if customer_sells else x[1],
        stable_seed(seed, order["date"], order["symbol"], x[0]),
    ))
    remaining = order["quantity"]
    fills = []
    for name, price, quantity in eligible:
        n = min(remaining, quantity)
        if n:
            fills.append({"player": name, "price": price, "quantity": n,
                          "signed_quantity": n if customer_sells else -n})
            remaining -= n
        if remaining == 0:
            break
    return fills, remaining


def liquidate(signed_quantity, entry, close, config):
    """Positive q is a long; negative q is a short which is bought back at close."""
    q = signed_quantity
    sign = 1 if q > 0 else -1
    exit_bps = config.closing_half_spread_bps + config.closing_slippage_bps
    exit_price = close * (1 - sign * exit_bps / 10_000)
    entry_fee = abs(q) * entry * config.fee_bps / 10_000
    exit_fee = abs(q) * exit_price * config.fee_bps / 10_000
    borrow = abs(q) * entry * config.short_borrow_bps / 10_000 if q < 0 else 0.0
    gross = q * (close - entry)
    exit_cost = abs(q) * close * exit_bps / 10_000
    net = q * (exit_price - entry) - entry_fee - exit_fee - borrow
    return {"gross_pnl": float(gross), "exit_price": float(exit_price),
            "entry_fee": float(entry_fee), "exit_fee": float(exit_fee),
            "borrow_cost": float(borrow), "liquidation_cost": float(exit_cost),
            "costs": float(entry_fee + exit_fee + borrow + exit_cost), "net_pnl": float(net)}


class Game:
    """Daily local research environment. Observations expose no future bar fields."""
    def __init__(self, data, config=None, human=False, data_label="user-supplied historical data"):
        self.config = config or Config()
        self._features = make_features(validate_data(data))
        dates = sorted(self._features["date"].unique())
        c = self.config
        if len(dates) < c.warmup + c.days:
            raise ValueError(f"Need {c.warmup + c.days} dates; received {len(dates)}")
        self._dates = dates[c.warmup:c.warmup + c.days]
        self.human = human
        self.strategies = CORE_STRATEGIES if c.competitors == 6 else STRATEGIES
        self.players = list(self.strategies) + (["you"] if human else [])
        self.equity = {name: c.capital for name in self.players}
        self.data_label = data_label
        self.index = 0
        self.daily, self.trades, self.quote_log, self.order_log, self.prediction_log = [], [], [], [], []
        self.opponent_model = OpponentQuoteModel(c)
        self.opponent_decisions = []
        self._round_cache = None

    @property
    def done(self):
        return self.index >= len(self._dates)

    def _round(self):
        if self.done:
            raise ValueError("Game is finished")
        if self._round_cache is not None:
            return self._round_cache
        date = self._dates[self.index]
        rows = self._features[self._features["date"] == date].sort_values("symbol")
        orders = []
        c = self.config
        for row in rows.to_dict("records"):
            rng = np.random.default_rng(stable_seed(c.seed, str(date), row["symbol"], "flow"))
            informed = rng.random() < c.informed_fraction
            random_side = "buy" if rng.random() < 0.5 else "sell"
            side = ("buy" if row["target"] > 0 else "sell") if informed else random_side
            quantity = max(1, int(row["lag_volume"] * rng.uniform(0.0005, 0.0015)))
            outside = row["open"] * (1 + (1 if side == "buy" else -1) * c.outside_spread_bps / 10_000)
            orders.append({"date": str(pd.Timestamp(date).date()), "symbol": row["symbol"],
                           "sector": row["sector"], "customer_side": side,
                           "quantity": quantity, "reference_price": float(row["open"]),
                           "reserve_price": tick_price(outside, c.tick, bid=side == "sell")})
        estimates = predict_day(self._features, date, c.lookback)
        predictions = {symbol: {name: values[name] for name in self.strategies}
                       for symbol, values in estimates.items()}
        self._round_cache = rows, orders, predictions
        return self._round_cache

    def observation(self):
        if self.done:
            return {"done": True, "days_completed": self.index, "equity": dict(self.equity),
                    "leaderboard": self.leaderboard().to_dict("records")}
        rows, orders, _ = self._round()
        visible = ["symbol", "sector"] + FEATURES + ["lag_volume", "lag_volatility"]
        return {"done": False, "day": self.index + 1, "total_days": self.config.days,
                "data_label": self.data_label, "timing": "just after opening price is observed",
                "orders": orders, "features": rows[visible].to_dict("records"),
                "equity": dict(self.equity), "config": asdict(self.config),
                "quote_disclosure": "All approved quotes become public after settlement, never before submission.",
                "action": "Submit {quotes: {SYMBOL: {price: NUMBER, quantity: INTEGER}}}; omitted symbols abstain."}

    def history(self, symbol=None, limit=126):
        """Only completed dates, including pre-game training history."""
        cutoff = self._dates[-1] + np.timedelta64(1, "D") if self.done else self._dates[self.index]
        f = self._features[self._features["date"] < cutoff]
        if symbol is not None:
            f = f[f["symbol"] == symbol]
        dates = sorted(f["date"].unique())[-int(limit):]
        out = f[f["date"].isin(dates)][["date", "symbol", "sector", "open", "close", "volume"]].copy()
        out["date"] = out["date"].dt.strftime("%Y-%m-%d")
        return out.to_dict("records")

    def _validate_human(self, quotes, orders):
        if not isinstance(quotes, dict):
            raise ValueError("quotes must be an object keyed by symbol")
        known = {o["symbol"]: o for o in orders}
        result = {}
        for symbol, q in quotes.items():
            if symbol not in known or not isinstance(q, dict) or set(q) != {"price", "quantity"}:
                raise ValueError("Each quote needs a known symbol, price, and quantity only")
            price, quantity = q["price"], q["quantity"]
            if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price):
                raise ValueError("price must be finite")
            if not 0.9 * known[symbol]["reference_price"] <= price <= 1.1 * known[symbol]["reference_price"]:
                raise ValueError("price must be within 10% of the reference price")
            if not math.isclose(price / self.config.tick, round(price / self.config.tick), abs_tol=1e-6):
                raise ValueError("price must be on the configured tick grid")
            if type(quantity) is not int or not 0 <= quantity <= 1_000_000_000:
                raise ValueError("quantity must be a nonnegative integer <= 1 billion")
            result[symbol] = {"price": float(price), "quantity": quantity}
        return result

    def completed_quotes(self, limit=126, symbol=None):
        """Quote log is populated only on completed days; available to every player."""
        rows = [q for q in self.quote_log if symbol is None or q["symbol"] == symbol]
        dates = sorted({q["date"] for q in rows})[-int(limit):]
        return [dict(q) for q in rows if q["date"] in dates]

    def _risk_limit(self, requested, rows, player):
        c = self.config
        capital = max(0.0, min(c.capital, self.equity[player]))
        lookup = rows.set_index("symbol")
        bounded = {}
        for symbol, quote in requested.items():
            row = lookup.loc[symbol]
            volatility_scale = min(1.0, 0.015 / max(float(row["lag_volatility"]), 1e-8))
            unit_cost = quote["price"] * (1 + c.fee_bps / 10_000)
            limit = min(capital * c.max_stock_fraction * volatility_scale / unit_cost,
                        row["lag_volume"] * c.max_lag_volume_fraction)
            bounded[symbol] = {"price": quote["price"], "quantity": min(quote["quantity"], int(limit))}
        # All orders are submitted simultaneously. Reserve gross capital even for quotes that may not fill.
        total = sum(q["quantity"] * q["price"] * (1 + c.fee_bps / 10_000) for q in bounded.values())
        scale = min(1.0, capital / total) if total else 1.0
        for quote in bounded.values():
            quote["quantity"] = int(quote["quantity"] * scale)
        return bounded

    def step(self, quotes=None):
        rows, orders, predictions = self._round()
        # Validate before any mutation so an invalid action cannot consume a day.
        human_quotes = self._validate_human({} if quotes is None else quotes, orders) if self.human else {}
        c = self.config
        proposed = {name: {} for name in self.players}
        for order in orders:
            symbol, ref = order["symbol"], order["reference_price"]
            if order["customer_side"] == "buy" and not c.allow_short:
                continue
            for name in self.strategies:
                if name in {"no_trade", "opponent_aware"}:
                    continue
                width = 1.0 if name == "tight_quote" else c.half_spread_bps
                alpha = predictions[symbol][name]
                bid = order["customer_side"] == "sell"
                price = ref * (1 + alpha + (-1 if bid else 1) * width / 10_000)
                proposed[name][symbol] = {"price": tick_price(price, c.tick, bid), "quantity": order["quantity"]}
        if self.human:
            allowed = {o["symbol"] for o in orders if c.allow_short or o["customer_side"] == "sell"}
            if set(human_quotes) - allowed:
                raise ValueError("Cannot sell to a customer while flat when allow_short=false")
            proposed["you"] = human_quotes
        # Only sanitized opening-time data enters the new model. No current
        # opponent quotes, capacities, future bars or same-day outcomes are passed.
        visible_rows = rows.set_index("symbol")
        tradable = [o for o in orders if c.allow_short or o["customer_side"] == "sell"]
        capital = max(0.0, min(c.capital, self.equity["opponent_aware"]))
        new_decisions = []
        for order in tradable:
            symbol = order["symbol"]
            visible = {name: float(visible_rows.loc[symbol, name]) for name in CONTEXT + ["lag_volume"]}
            quote, diagnostic = self.opponent_model.quote(order, visible, predictions[symbol]["sector_router"], capital, len(tradable))
            if quote is not None:
                proposed["opponent_aware"][symbol] = quote
            new_decisions.append(diagnostic)
        approved = {name: self._risk_limit(q, rows, name) for name, q in proposed.items()}
        date = orders[0]["date"]
        self.prediction_log.extend({"date": date, "symbol": symbol, **p} for symbol, p in predictions.items())
        pnl = {name: 0.0 for name in self.players}
        totals = {name: {"filled_shares": 0, "entry_notional": 0.0, "costs": 0.0,
                         "spread_pnl": 0.0, "price_pnl": 0.0} for name in self.players}
        closes = rows.set_index("symbol")["close"].to_dict()
        day_fills = []
        pending_episodes = []
        quote_log_start = len(self.quote_log)
        for order in orders:
            symbol = order["symbol"]
            auction_quotes = {name: q[symbol] for name, q in approved.items() if symbol in q}
            fills, external = clear_order(order, auction_quotes, c.seed)
            by_player = {f["player"]: f["quantity"] for f in fills}
            for name, quote in auction_quotes.items():
                self.quote_log.append({"date": date, "symbol": symbol, "player": name, **quote,
                                       "requested_quantity": proposed[name][symbol]["quantity"],
                                       "filled_quantity": by_player.get(name, 0)})
            self.order_log.append({**order, "external_quantity": external})
            pending_episodes.append({
                "date": date, "symbol": symbol, "sector": order["sector"], "customer_side": order["customer_side"],
                "context": [float(visible_rows.loc[symbol, name]) for name in CONTEXT],
                "alpha": predictions[symbol]["sector_router"],
                "return": float(closes[symbol] / order["reference_price"] - 1),
                "book": {name: {"relative_price": quote["price"] / order["reference_price"],
                                 "quantity_fraction": quote["quantity"] / order["quantity"]}
                         for name, quote in auction_quotes.items() if name != "opponent_aware"},
            })
            for fill in fills:
                name, q, price = fill["player"], fill["signed_quantity"], fill["price"]
                accounting = liquidate(q, price, closes[symbol], c)
                spread = q * (order["reference_price"] - price)
                movement = q * (closes[symbol] - order["reference_price"])
                trade = {"date": date, "symbol": symbol, "sector": order["sector"],
                         "customer_side": order["customer_side"], **fill,
                         "close": float(closes[symbol]), "spread_pnl": float(spread),
                         "price_pnl": float(movement), **accounting, "inventory_end": 0}
                self.trades.append(trade)
                day_fills.append(trade)
                pnl[name] += accounting["net_pnl"]
                totals[name]["filled_shares"] += abs(q)
                totals[name]["entry_notional"] += abs(q) * price
                totals[name]["costs"] += accounting["costs"]
                totals[name]["spread_pnl"] += spread
                totals[name]["price_pnl"] += movement
        requested_shares = sum(o["quantity"] for o in orders)
        for name in self.players:
            self.equity[name] += pnl[name]
            self.daily.append({"date": date, "player": name, "net_pnl": pnl[name],
                               "equity": self.equity[name], "daily_return": pnl[name] / c.capital,
                               "customer_shares": requested_shares, "inventory_end": 0, **totals[name]})
        # All current actions have already been chosen before any new observation
        # enters the learner. Even other stocks from this day cannot train it early.
        for episode in pending_episodes:
            self.opponent_model.observe_completed(episode)
        for diagnostic in new_decisions:
            own = [f for f in day_fills if f["player"] == "opponent_aware" and f["symbol"] == diagnostic["symbol"]]
            diagnostic["actual_filled_quantity"] = sum(f["quantity"] for f in own)
            diagnostic["actual_net_profit"] = sum(f["net_pnl"] for f in own)
            diagnostic["approved_quantity"] = approved["opponent_aware"].get(diagnostic["symbol"], {}).get("quantity", 0)
        self.opponent_decisions.extend(new_decisions)
        self.index += 1
        self._round_cache = None
        return {"date": date, "daily_pnl": pnl, "fills": day_fills,
                "completed_quotes": self.quote_log[quote_log_start:],
                "equity": dict(self.equity), "inventory_end": {name: 0 for name in self.players},
                "done": self.done}

    def run(self):
        while not self.done:
            self.step()
        return self

    def leaderboard(self):
        if not self.daily:
            return pd.DataFrame([{"player": name, "net_pnl": 0.0} for name in self.players])
        frame = pd.DataFrame(self.daily)
        output = []
        for name, group in frame.groupby("player", sort=True):
            p = group["net_pnl"].to_numpy()
            path = np.r_[self.config.capital, group["equity"].to_numpy()]
            high = np.maximum.accumulate(path)
            sd = p.std(ddof=1) if len(p) > 1 else 0
            output.append({"player": name, "net_pnl": float(p.sum()),
                           "return_pct": float(100 * p.sum() / self.config.capital),
                           "daily_sharpe_annualized": float(np.sqrt(252) * p.mean() / sd) if sd > 1e-12 else None,
                           "max_drawdown_cash": float(np.max(high - path)),
                           "max_drawdown_pct": float(100 * np.max((high - path) / high)),
                           "filled_shares": int(group["filled_shares"].sum()),
                           "share_of_customer_volume_pct": float(100 * group["filled_shares"].sum() / group["customer_shares"].sum()),
                           "costs": float(group["costs"].sum()),
                           "spread_pnl": float(group["spread_pnl"].sum()),
                           "price_pnl": float(group["price_pnl"].sum()),
                           "profitable_days": int((p > 0).sum())})
        return pd.DataFrame(output).sort_values(["net_pnl", "player"], ascending=[False, True]).reset_index(drop=True)
