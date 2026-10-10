"""Inspectable results, paired uncertainty estimates, and static research figures."""
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .signals import whitening_diagnostics


def clean_json(value):
    if isinstance(value, dict):
        return {k: clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def write_json(path, value):
    Path(path).write_text(json.dumps(clean_json(value), indent=2, allow_nan=False) + "\n")


def paired_bootstrap(daily, baseline="flat_quote", seed=7, samples=1000, block=5):
    """Circular moving-block bootstrap of paired daily differences; descriptive.

    This conditions on fitted policies and the realized tournament. It neither
    retrains policies nor corrects selection of a winner after observing results.
    """
    pivot = daily.pivot(index="date", columns="player", values="net_pnl")
    rng = np.random.default_rng(seed)
    n = len(pivot)
    starts = rng.integers(0, n, size=(samples, math_ceil(n / block)))
    indices = ((starts[:, :, None] + np.arange(block)) % n).reshape(samples, -1)[:, :n]
    differences = pivot.subtract(pivot[baseline], axis=0).to_numpy()
    boot = differences[indices].sum(axis=1)
    return [{"player": name, "baseline": baseline,
             "realized_total_difference": float(differences[:, j].sum()),
             "bootstrap_low_95": float(np.quantile(boot[:, j], 0.025)),
             "bootstrap_high_95": float(np.quantile(boot[:, j], 0.975))}
            for j, name in enumerate(pivot.columns)]


def math_ceil(value):
    return int(np.ceil(value))


def save_game(game, directory):
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    leaderboard = game.leaderboard()
    leaderboard.to_csv(out / "leaderboard.csv", index=False)
    for name, rows in [("daily_pnl", game.daily), ("trades", game.trades),
                       ("quotes", game.quote_log), ("customer_orders", game.order_log),
                       ("predictions", game.prediction_log)]:
        pd.DataFrame(rows).to_csv(out / f"{name}.csv", index=False)
    pd.DataFrame(game.opponent_decisions).to_csv(out / "opponent_decisions.csv", index=False)
    daily = pd.DataFrame(game.daily)
    pnl = daily.pivot(index="date", columns="player", values="net_pnl")
    pnl.corr().to_csv(out / "pnl_correlation.csv")
    pd.DataFrame(game.prediction_log).drop(columns=["date", "symbol"]).corr().to_csv(out / "forecast_correlation.csv")
    baseline = "flat_quote" if "flat_quote" in game.players else "sector_router"
    intervals = paired_bootstrap(daily, baseline=baseline, seed=game.config.seed)
    pd.DataFrame(intervals).to_csv(out / "paired_bootstrap.csv", index=False)
    factors = whitening_diagnostics(game._features, game._dates[0], game._dates[-1], game.config.lookback)
    write_json(out / "whitening_diagnostics.json", factors)
    summary = {"data_label": game.data_label, "config": asdict(game.config),
               "active_players": game.players, "number_of_players": len(game.players),
               "bootstrap_baseline": baseline,
               "days": game.index, "winner_by_net_pnl": leaderboard.iloc[0]["player"],
               "leaderboard": leaderboard.to_dict("records"),
               "all_inventory_closed": all(x["inventory_end"] == 0 for x in game.daily),
               "opponent_decision_modes": pd.Series([x["mode"] for x in game.opponent_decisions], dtype="object").value_counts().to_dict(),
               "disclosure": "Completed approved quotes are public after settlement; current quotes stay sealed.",
               "caveat": "A sample ranking, not evidence of profitable live trading; synthetic prices when so labelled."}
    write_json(out / "summary.json", summary)
    plot_game(game, out / "overview.png")
    return summary


def plot_game(game, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    daily = pd.DataFrame(game.daily)
    pivot = daily.pivot(index="date", columns="player", values="net_pnl").cumsum()
    leaders = game.leaderboard()
    colors = dict(zip(sorted(game.players), plt.get_cmap("tab10").colors))
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, (left, right) = plt.subplots(1, 2, figsize=(14, 6), gridspec_kw={"width_ratios": [1.8, 1]})
    for name in pivot.columns:
        left.plot(np.arange(1, len(pivot) + 1), pivot[name] / 1000,
                  label=name.replace("_", " "), color=colors[name], linewidth=1.7)
    left.set(xlabel="Evaluation day", ylabel="Cumulative net P&L (thousands)", title="Same prices and customer orders for every player")
    left.axhline(0, color="#666666", linewidth=0.6)
    left.grid(axis="y", alpha=0.2)
    left.legend(loc="best", fontsize=8)
    ranked = leaders.iloc[::-1]
    right.barh(ranked["player"].str.replace("_", " "), ranked["net_pnl"] / 1000,
               color=[colors[n] for n in ranked["player"]])
    right.axvline(0, color="#666666", linewidth=0.7)
    cost_fields = ["fee_bps", "closing_half_spread_bps", "closing_slippage_bps", "short_borrow_bps"]
    zero_cost = all(getattr(game.config, name) == 0 for name in cost_fields)
    right.set(xlabel="Final net P&L (thousands)",
              title="Ranking | zero trading costs" if zero_cost else "Ranking after costs")
    fig.suptitle(f"Daily auction lab | {game.index} days | {game.data_label}", fontsize=15, fontweight="bold", x=0.04, ha="left")
    fig.text(0.04, 0.02, "One sealed RFQ per stock per day. Positions closed every evening. A simulation ranking does not establish predictive skill.", fontsize=9, color="#555555")
    fig.tight_layout(rect=[0.02, 0.06, 0.98, 0.90])
    fig.savefig(destination, dpi=160, facecolor="white")
    plt.close(fig)


def write_results_note(base, stress, repeated, output):
    path = Path(output)
    table = base.leaderboard()
    lines = ["# Experiment results", "", f"Data: **{base.data_label}**.", "",
             f"Predeclared demonstration seed: {base.config.seed}. Evaluation: {base.config.days} days after {base.config.warmup} warm-up dates.",
             f"Each player starts with {base.config.capital:,.0f} units of nominal capital. P&L units match the input prices; synthetic prices have arbitrary currency units.", "",
             f"Common trading costs (basis points): fee per leg = {base.config.fee_bps:g}; closing half-spread = {base.config.closing_half_spread_bps:g}; closing slippage = {base.config.closing_slippage_bps:g}; daily short-borrow charge = {base.config.short_borrow_bps:g}. The same settings apply to every player and to the opponent-aware profit calculation.",
             "Bid/ask quote margins and customer reservation prices are separate strategy and auction settings; they are not transaction-cost deductions.", "",
             "| Player | Net P&L | Max drawdown | Customer volume share |", "|---|---:|---:|---:|"]
    for row in table.to_dict("records"):
        lines.append(f"| {row['player']} | {row['net_pnl']:,.2f} | {row['max_drawdown_cash']:,.2f} | {row['share_of_customer_volume_pct']:.1f}% |")
    lines += ["", f"The winner in this one run is **{table.iloc[0]['player']}**.",
              "This is a realized outcome, not proof that the winning indicator predicts prices. The synthetic price model has no deliberately installed technical-indicator alpha.", "",
              "The daily identity is: net P&L = entry price improvement versus open + signed open-to-close movement - all modelled costs.", "",
              "## Orthogonality", "",
              "Whitening is fitted on past observations separately in each sector. Its training covariance is the identity on retained components. Future signal covariance and strategy profit covariance need not be diagonal.",
              "See whitening_diagnostics.json (first training transform frozen for its diagnostic), forecast_correlation.csv, and pnl_correlation.csv. Correlations with zero-variance no_trade/flat forecasts are undefined and left blank.", ""]
    if base.opponent_decisions:
        decisions = pd.DataFrame(base.opponent_decisions)
        learned = decisions[decisions["mode"].isin(["optimized", "abstain"])]
        own = table[table["player"] == "opponent_aware"].iloc[0]
        router = table[table["player"] == "sector_router"].iloc[0]
        counts = decisions["mode"].value_counts().to_dict()
        lines += ["## Opponent-aware expected-profit player", "",
                  f"The new player earned **{own['net_pnl']:,.2f}**, versus **{router['net_pnl']:,.2f}** for sector_router in the same tournament.",
                  f"Decision counts: {counts}.",
                  "It uses the same mean closing-price forecast as sector_router, estimates a joint distribution of competing quote/quantity books from completed days, and searches candidate ticks for the highest estimated profit after costs. It can abstain. Cold-start days use the sector quote with the new player's conservative per-order quantity allocation.",
                  f"Across its {len(learned)} model-based decisions, estimated net profit summed to {learned['estimated_net_profit'].sum():,.2f}, while realized net profit was {learned['actual_net_profit'].sum():,.2f}. These are different quantities: maximizing a fitted expectation does not guarantee realized profit or an unbiased model.",
                  "All current opponent quotes stay sealed; approved quote books become available to every player after settlement. This is an explicit simulation disclosure rule. A market showing only winning execution prices would require censored-data estimation instead.",
                  "The player reserves equal capital slices for current requests before optimizing each price; its quantity allocation is more conservative than sector_router. Therefore the realized comparison is not a pure causal estimate of the value of opponent modelling.",
                  "See opponent_decisions.csv for predicted and actual fills/profits, training cutoffs, selected quotes and a same-quantity fixed-offset counterfactual evaluated under its fitted distribution. No current-day outcome enters a quote decision.", ""]
    if stress is not None:
        st = stress.leaderboard()
        lines += ["## Informed-customer stress test", "",
                  f"With {stress.config.informed_fraction:.0%} informed-request probability, the winner is **{st.iloc[0]['player']}**, with net P&L {st.iloc[0]['net_pnl']:,.2f}.",
                  "Informed customers buy before positive open-to-close moves and sell before negative moves. This is a deliberately severe simulator assumption, not a measured fraction in any real market. Agents never receive the future close.",
                  "Prices, volume requests, and latent customer random draws are shared with the main run; only informed-side decisions change. See informed_stress/ alongside this report.", ""]
    if repeated is not None and len(repeated):
        lines += ["## Repeated synthetic tournaments", "",
                  "Independent synthetic price/order seeds give the following sensitivity check. These are new simulated worlds, not independent real historical backtests.", "",
                  "| Player | Mean total P&L | Median total P&L | Share of tournament wins |", "|---|---:|---:|---:|"]
        for row in repeated.to_dict("records"):
            lines.append(f"| {row['player']} | {row['mean_pnl']:,.2f} | {row['median_pnl']:,.2f} | {100 * row['win_share']:.1f}% |")
        lines.append("")
    lines += ["## Statistical limits", "",
              "The paired_bootstrap.csv file uses a five-day circular block bootstrap of daily P&L differences against flat_quote when present, otherwise sector_router. The baseline is recorded in the CSV and summary. Intervals condition on the fitted policies, do not refit them, and do not correct for selecting the best strategy after the test. They are descriptive, not a reliable final significance claim from 100 days.",
              "For real conclusions, predeclare policies and metrics; use chronological training, validation and untouched test periods; include delisted constituents and corporate actions; test realistic execution/borrow costs and different competitor populations.",
              "The model has no endogenous price impact, queue position, exchange opening-price formation, intraday re-quoting, funding interest, or guaranteed availability of borrowed shares. All are material extensions.", ""]
    path.write_text("\n".join(lines))

