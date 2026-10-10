import argparse
from dataclasses import replace
from pathlib import Path

import pandas as pd

from .data import load_data, synthetic_data
from .engine import Config, Game
from .report import save_game, write_results_note


def main():
    p = argparse.ArgumentParser(description="Daily competitive RFQ market-making research lab")
    p.add_argument("command", choices=["demo", "backtest", "serve"])
    p.add_argument("--data", help="CSV for backtest or the local API")
    p.add_argument("--out", default="results")
    p.add_argument("--days", type=int, default=100)
    p.add_argument("--players", type=int, choices=[6, 9], default=6,
                   help="Built-in competitors: six strategies, or nine including benchmarks")
    p.add_argument("--stress", action="store_true",
                   help="Also run the same prices with 35%% informed-request probability")
    p.add_argument("--warmup", type=int, default=180)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--repetitions", type=int, default=0, help="Additional synthetic tournaments, each with a new price/order seed")
    p.add_argument("--informed-fraction", type=float, default=0)
    p.add_argument("--long-only", action="store_true")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    if args.command == "serve":
        from .api import serve
        serve(args.port, args.data)
        return
    if args.command == "backtest" and not args.data:
        p.error("backtest requires --data PATH")
    if args.command == "backtest" and args.repetitions:
        p.error("--repetitions generates synthetic markets and is only supported for demo")
    if args.repetitions < 0:
        p.error("--repetitions must be nonnegative")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    c = Config(days=args.days, warmup=args.warmup, seed=args.seed, competitors=args.players,
               allow_short=not args.long_only, informed_fraction=args.informed_fraction)
    label = "SYNTHETIC demonstration" if args.command == "demo" else "user-supplied historical data"
    data = synthetic_data(max(80, c.warmup + c.days), c.seed) if args.command == "demo" else load_data(args.data)
    if args.command == "demo":
        data.to_csv(out / "synthetic_prices.csv", index=False)
    base = Game(data, c, data_label=label).run()
    save_game(base, out)
    print(base.leaderboard()[["player", "net_pnl", "return_pct", "max_drawdown_cash"]].to_string(index=False), flush=True)
    # Scenario uses the same price path and the same latent flow draws.
    stress = None
    if args.stress:
        stress = Game(data, replace(c, informed_fraction=0.35), data_label=label).run()
        save_game(stress, out / "informed_stress")
    repeated = None
    if args.repetitions:
        records = []
        for j in range(args.repetitions):
            seed = c.seed + 1000 + j
            simulated = synthetic_data(max(80, c.warmup + c.days), seed)
            game = Game(simulated, replace(c, seed=seed), data_label=label).run()
            board = game.leaderboard()
            winners = board[board["net_pnl"] == board["net_pnl"].max()]["player"].tolist()
            for row in board.to_dict("records"):
                records.append({"seed": seed, "player": row["player"], "net_pnl": row["net_pnl"],
                                "win_share": (1 / len(winners)) if row["player"] in winners else 0})
            print(f"Additional synthetic tournament {j + 1}/{args.repetitions}: winner {winners}", flush=True)
        per_seed = pd.DataFrame(records)
        per_seed.to_csv(out / "repeated_runs.csv", index=False)
        repeated = per_seed.groupby("player").agg(mean_pnl=("net_pnl", "mean"),
                    median_pnl=("net_pnl", "median"), win_share=("win_share", "mean")).reset_index()
        repeated = repeated.sort_values("mean_pnl", ascending=False)
        repeated.to_csv(out / "repeated_summary.csv", index=False)
    write_results_note(base, stress, repeated, out / "RESULTS.md")
    print(f"Saved results to {out.resolve()}", flush=True)


if __name__ == "__main__":
    main()
