# Changelog

## 0.4.0 — GitHub project edition

- Organize the presentation into market/API, code, strategies and results chapters.
- Make six research competitors the default throughout Python, CLI, API and Colab. Select nine with `Config(competitors=9)` or `--players 9`; API games add one external player.
- Store each game's roster separately, without notebook mutation of module constants.
- Make CLI informed-customer stress runs opt-in with `--stress`.
- Use the sector router as the descriptive bootstrap baseline when the fixed-quote benchmark is absent.
- Bundle the Colab notebook and reproducible six-player results alongside nine-player reference experiments.
- Retain the previous strategy equations, costs, customer flow, auction rules and nine-player outcomes. Version-0.4 seed-7 checks reproduce both previously reported 100-day leaderboards.
- Expand validation from 22 to 25 tests, including actual roster exclusion and report generation.

## 0.3.0

- Set default entry/exit fees, closing spread/slippage and short borrowing charges to zero for every player.

## 0.2.0

- Add the opponent-aware expected-profit strategy and completed-book disclosure.

## 0.1.0

- Initial RFQ simulator, indicator strategies and benchmark dealers.
