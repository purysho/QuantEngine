"""Chronological model validation with explicit information clocks.

Row ``i`` is a decision made at observation clock ``i``. ``feature_available[i]``
is the clock at which every feature value in row ``i`` was known; it must be
``<= i``. ``label_end[i]`` is the clock at which the target for row ``i`` is
completed; it must be ``> i``. A model evaluated from clock ``s`` may train only
on rows whose labels completed strictly before ``s`` (purging overlapping labels).
"""
from __future__ import annotations

import math

import numpy as np


def _validate(features, targets, feature_available, label_end):
    x = np.asarray(features, dtype=np.float64)
    y = np.asarray(targets, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if x.ndim != 2 or y.ndim != 1 or len(x) != len(y) or not 1 <= x.shape[1] <= 256:
        raise ValueError("Features must be rows x 1–256 columns with one target per row.")
    if not (np.isfinite(x).all() and np.isfinite(y).all()):
        raise ValueError("Features and targets must be finite; missing values are not imputed.")
    available = np.asarray(feature_available)
    ends = np.asarray(label_end)
    if available.shape != (len(y),) or ends.shape != (len(y),) \
            or not np.issubdtype(available.dtype, np.integer) or not np.issubdtype(ends.dtype, np.integer):
        raise ValueError("Feature availability and label completion must be one integer clock per row.")
    clock = np.arange(len(y))
    late = np.flatnonzero(available > clock)
    if len(late):
        i = int(late[0])
        raise ValueError(f"Leaked feature: row {i} uses information available at clock {int(available[i])}, "
                         f"after its decision clock {i} ({len(late)} rows affected).")
    early = np.flatnonzero(ends <= clock)
    if len(early):
        i = int(early[0])
        raise ValueError(f"Label for row {i} completes at clock {int(ends[i])}, not after its decision clock.")
    return x, y, ends


def _fit_ridge(x, y, alpha):
    """Ridge on train-standardised features; the intercept (target mean) is not penalised."""
    mean = x.mean(axis=0)
    scale = x.std(axis=0, ddof=0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    z = (x - mean) / scale
    target_mean = float(y.mean())
    gram = z.T @ z + alpha * np.eye(z.shape[1])
    beta = np.linalg.solve(gram, z.T @ (y - target_mean))
    return {"alpha": float(alpha), "feature_mean": mean, "feature_scale": scale,
            "coefficients": beta, "intercept": target_mean, "train_rows": int(len(y))}


def _predict(model, x):
    return model["intercept"] + ((x - model["feature_mean"]) / model["feature_scale"]) @ model["coefficients"]


def _scores(prediction, actual, train_mean):
    error = prediction - actual
    mse = float(np.mean(error ** 2))
    zero = float(np.mean(actual ** 2))
    mean = float(np.mean((train_mean - actual) ** 2))
    position = np.sign(prediction)
    return {"mse": mse, "zero_forecast_mse": zero, "training_mean_mse": mean,
            # Campbell–Thompson out-of-sample R^2 against the historical-mean forecast.
            "oos_r2_vs_mean": 1 - mse / mean if mean > 0 else 0.0,
            "oos_r2_vs_zero": 1 - mse / zero if zero > 0 else 0.0,
            "hit_rate": float(np.mean(np.sign(prediction) == np.sign(actual))),
            "sign_position_mean": float(np.mean(position * actual)),
            "observations": int(len(actual))}


def _train_rows(ends, start):
    return np.flatnonzero((np.arange(len(ends)) < start) & (ends < start))


def chronological_ridge(features, targets, *, feature_available, label_end, initial_train=120,
                        test_size=40, final_holdout=80, alphas=(.1, 1., 10., 100.)) -> dict:
    x, y, ends = _validate(features, targets, feature_available, label_end)
    n = len(y)
    for name, value in (("initial_train", initial_train), ("test_size", test_size), ("final_holdout", final_holdout)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer.")
    alphas = tuple(float(a) for a in alphas)
    if not 1 <= len(alphas) <= 32 or not all(math.isfinite(a) and a >= 0 for a in alphas):
        raise ValueError("Provide 1–32 finite nonnegative ridge penalties.")
    holdout_start = n - final_holdout
    if holdout_start - initial_train < test_size:
        raise ValueError("Data are too short for the initial training window, one inner block and the final holdout.")
    starts = list(range(initial_train, holdout_start - test_size + 1, test_size))
    ledger = []
    for alpha in alphas:
        blocks, errors = [], []
        for start in starts:
            rows = _train_rows(ends, start)
            if len(rows) < max(10, x.shape[1] + 2):
                raise ValueError(f"Too few completed labels before clock {start}.")
            model = _fit_ridge(x[rows], y[rows], alpha)
            block = slice(start, start + test_size)
            prediction = _predict(model, x[block])
            score = _scores(prediction, y[block], model["intercept"])
            errors.append(prediction - y[block])
            blocks.append({"evaluation_start": start, "evaluation_end": start + test_size,
                           "train_rows": int(len(rows)), "last_train_label_end": int(ends[rows].max()),
                           "mse": score["mse"], "predictions": prediction.tolist()})
        ledger.append({"alpha": alpha, "inner_mse": float(np.mean(np.concatenate(errors) ** 2)), "blocks": blocks})
    best = min(ledger, key=lambda row: (row["inner_mse"], -row["alpha"]))  # Ties favour more shrinkage.
    rows = _train_rows(ends, holdout_start)
    model = _fit_ridge(x[rows], y[rows], best["alpha"])
    prediction = _predict(model, x[holdout_start:])
    holdout = _scores(prediction, y[holdout_start:], model["intercept"])
    return {
        "selected_alpha": best["alpha"], "candidates_tried": len(alphas), "ledger": ledger,
        "inner_blocks": [[s, s + test_size] for s in starts],
        "final_model": {"alpha": model["alpha"], "train_rows": model["train_rows"],
                        "last_train_label_end": int(ends[rows].max()),
                        "feature_mean": model["feature_mean"].tolist(), "feature_scale": model["feature_scale"].tolist(),
                        "coefficients_standardised": model["coefficients"].tolist(), "intercept": model["intercept"]},
        "holdout": {**holdout, "start": holdout_start, "end": n, "predictions": prediction.tolist()},
        "baselines": {"zero_forecast": "cash / no position: forecast 0",
                      "training_mean": "constant forecast equal to the final training-label mean"},
        "protocol": ["Rows are decision clocks; features must be available at or before their row clock.",
                     "Training uses only rows whose labels completed strictly before each evaluation start (purged).",
                     "Feature scaling is fitted on each training set only.",
                     "The penalty is chosen on inner chronological blocks before the final holdout; the holdout is scored once.",
                     "Every candidate penalty and its inner-block errors are retained in the ledger."],
    }
