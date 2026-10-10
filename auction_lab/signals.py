"""Rolling, sector-specific prediction; all training dates strictly precede today."""
import numpy as np

from .data import FEATURES

STRATEGIES = (
    "no_trade", "flat_quote", "tight_quote", "macd", "price_reversal",
    "volume_momentum", "sector_router", "orthogonal_ensemble", "opponent_aware",
)
CORE_STRATEGIES = tuple(name for name in STRATEGIES
                        if name not in {"no_trade", "flat_quote", "tight_quote"})
ROUTE = {"technology": 0, "commodities": 2, "financials": 1}


def fit_whitener(x):
    mean = x.mean(axis=0)
    scale = x.std(axis=0, ddof=1)
    scale = np.where(scale > 1e-12, scale, 1.0)
    z = (x - mean) / scale
    cov = z.T @ z / max(1, len(z) - 1)
    values, vectors = np.linalg.eigh(cov)
    keep = values > 1e-8
    matrix = vectors[:, keep] / np.sqrt(values[keep])
    return mean, scale, matrix


def ridge_predict(x, y, current, columns=None, whiten=False, shrinkage=0.25):
    if columns is not None:
        x, current = x[:, columns], current[:, columns]
    if len(x) < 40:
        return np.zeros(len(current))
    mean, scale, matrix = fit_whitener(x)
    z, now = (x - mean) / scale, (current - mean) / scale
    if whiten:
        z, now = z @ matrix, now @ matrix
    # Predeclared ridge penalty and no fitted intercept: constrain unconditional drift to zero.
    # This makes the comparison focus on indicators rather than noisy sample drift.
    beta = np.linalg.solve(z.T @ z + len(z) * shrinkage * np.eye(z.shape[1]), z.T @ y)
    return np.clip(now @ beta, -0.01, 0.01)


def predict_day(features, date, lookback=126):
    today = features[features["date"] == date].sort_values("symbol")
    past_dates = sorted(features.loc[features["date"] < date, "date"].unique())[-lookback:]
    train = features[features["date"].isin(past_dates)].dropna(subset=FEATURES + ["target"])
    output = {symbol: {name: 0.0 for name in STRATEGIES} for symbol in today["symbol"]}
    for sector, current in today.groupby("sector", sort=True):
        historical = train[train["sector"] == sector]
        if len(historical) < 40:
            continue
        x = historical[FEATURES].to_numpy()
        y = historical["target"].to_numpy()
        now = current[FEATURES].to_numpy()
        estimates = {
            "macd": ridge_predict(x, y, now, [0]),
            "price_reversal": ridge_predict(x, y, now, [1]),
            "volume_momentum": ridge_predict(x, y, now, [2]),
            "sector_router": ridge_predict(x, y, now, [ROUTE[sector]]),
            "orthogonal_ensemble": ridge_predict(x, y, now, whiten=True),
        }
        estimates["opponent_aware"] = estimates["sector_router"].copy()
        for name, predictions in estimates.items():
            for symbol, estimate in zip(current["symbol"], predictions):
                output[symbol][name] = float(estimate)
    return output


def whitening_diagnostics(features, first_date, last_date, lookback=126):
    """Freeze the first training transform, then examine genuinely later features."""
    dates = sorted(features.loc[features["date"] < first_date, "date"].unique())[-lookback:]
    train = features[features["date"].isin(dates)].dropna(subset=FEATURES)
    test = features[features["date"].between(first_date, last_date)].dropna(subset=FEATURES)
    result = {}
    for sector, rows in train.groupby("sector", sort=True):
        mean, scale, transform = fit_whitener(rows[FEATURES].to_numpy())
        ztrain = (rows[FEATURES].to_numpy() - mean) / scale @ transform
        ztest = (test.loc[test["sector"] == sector, FEATURES].to_numpy() - mean) / scale @ transform
        result[sector] = {
            "retained_dimensions": int(transform.shape[1]),
            "train_covariance": np.atleast_2d(np.cov(ztrain, rowvar=False)).tolist(),
            "test_covariance": np.atleast_2d(np.cov(ztest, rowvar=False)).tolist(),
            "note": "A transform frozen before evaluation; identity train covariance does not imply independent P&Ls.",
        }
    return result
