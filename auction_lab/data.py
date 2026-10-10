"""Daily data with an explicit boundary between observations and outcomes."""
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = ["macd", "reversal", "volume_momentum"]
SECTORS = ("technology", "commodities", "financials")


def validate_data(frame):
    """Require a balanced daily panel; fail rather than silently fill missing bars."""
    required = {"date", "symbol", "sector", "open", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    f = frame.copy()
    f["date"] = pd.to_datetime(f["date"], errors="raise").dt.normalize()
    if f[list(required)].isna().any().any():
        raise ValueError("Missing values are not allowed in required columns")
    if f.duplicated(["date", "symbol"]).any():
        raise ValueError("Duplicate date/symbol rows")
    for col in ["open", "close", "volume"]:
        f[col] = pd.to_numeric(f[col], errors="raise")
        if not np.isfinite(f[col]).all() or (f[col] <= 0).any():
            raise ValueError(f"{col} must be finite and strictly positive")
    f["symbol"] = f["symbol"].astype(str)
    f["sector"] = f["sector"].astype(str).str.lower()
    if (f["symbol"].str.len() == 0).any():
        raise ValueError("Empty symbols are not allowed")
    unknown = set(f["sector"]) - set(SECTORS)
    if unknown:
        raise ValueError(f"sector must be one of {SECTORS}; found {unknown}")
    if (f.groupby("symbol")["sector"].nunique() != 1).any():
        raise ValueError("Each symbol must have a stable sector label")
    n_symbols = f["symbol"].nunique()
    if (f.groupby("date").size() != n_symbols).any():
        raise ValueError("Unbalanced panel: every symbol needs every selected date")
    if len(f["date"].unique()) < 80:
        raise ValueError("Supply at least 80 complete dates for feature warm-up")
    return f.sort_values(["date", "symbol"]).reset_index(drop=True)


def load_data(path):
    return validate_data(pd.read_csv(Path(path)))


def synthetic_data(days=280, seed=7):
    """Artificial correlated OHLCV. Sector labels imply no predictive advantage.

    Returns have independent daily innovations; the demo deliberately makes
    no claim that its indicators predict these innovations.
    """
    if days < 80:
        raise ValueError("Generate at least 80 dates")
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=days)  # synthetic weekdays, not a venue calendar
    last = np.linspace(45.0, 160.0, 9)
    base_volume = np.linspace(900_000, 2_500_000, 9)
    rows = []
    for date in dates:
        market = rng.normal(0, 0.005)
        sector_move = rng.normal(0, 0.004, 3)
        for j in range(9):
            group = j // 3
            sector = SECTORS[group]
            opening = last[j] * np.exp(rng.normal(0, 0.003))
            r = market + sector_move[group] + rng.normal(0, (0.011, 0.013, 0.008)[group])
            closing = opening * np.exp(r)
            excursion = abs(rng.normal(0, 0.004))
            rows.append({
                "date": date, "symbol": f"{('TECH', 'COMM', 'FIN')[group]}_{j % 3 + 1}",
                "sector": sector, "open": opening,
                "high": max(opening, closing) * (1 + excursion),
                "low": min(opening, closing) / (1 + excursion),
                "close": closing,
                "volume": int(base_volume[j] * np.exp(rng.normal(0, 0.25) + 8 * abs(r))),
            })
            last[j] = closing
    return validate_data(pd.DataFrame(rows))


def make_features(data):
    """Every feature on row t uses bars through t-1, never today's close/volume."""
    frames = []
    for _, raw in data.groupby("symbol", sort=True):
        f = raw.sort_values("date").copy()
        close = f["close"]
        change = close.pct_change()
        line = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        histogram = line - line.ewm(span=9, adjust=False).mean()
        f["macd"] = (histogram / close).shift(1)
        f["reversal"] = (close.rolling(20).mean() / close - 1).shift(1)
        relative_volume = f["volume"] / f["volume"].rolling(20).mean() - 1
        f["volume_momentum"] = (change * relative_volume).shift(1)
        f["lag_volume"] = f["volume"].rolling(20).mean().shift(1)
        f["lag_volatility"] = change.rolling(20).std().shift(1)
        # A label for fitting/settlement only; never exposed in a live observation.
        f["target"] = f["close"] / f["open"] - 1
        frames.append(f)
    return pd.concat(frames).sort_values(["date", "symbol"]).reset_index(drop=True)

