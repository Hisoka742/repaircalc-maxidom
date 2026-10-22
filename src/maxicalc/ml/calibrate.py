"""Confidence calibration and precision-targeted thresholds."""
from collections.abc import Sequence

import numpy as np
from sklearn.isotonic import IsotonicRegression


def pick_threshold(
    probs: Sequence[float], y: Sequence[int], target: float = 0.95, min_support: int = 5
) -> float | None:
    """Lowest threshold t (max coverage) such that precision of {p >= t} is >= target.

    Returns None when no threshold with at least `min_support` accepted items reaches the
    target; the label then always goes to review.
    """
    p = np.asarray(probs, dtype=float)
    t_arr = np.asarray(y, dtype=int)
    for t in np.unique(p):  # ascending
        sel = p >= t
        n = int(sel.sum())
        if n < min_support:
            break
        if t_arr[sel].sum() / n >= target:
            return float(t)
    return None


class Calibrator:
    """Isotonic calibration of raw model scores on a held-out dev set."""

    def __init__(self) -> None:
        self._iso: IsotonicRegression | None = None

    def fit(self, scores: Sequence[float], y: Sequence[int]) -> "Calibrator":
        y_arr = np.asarray(y, dtype=int)
        if len(set(y_arr.tolist())) < 2:  # nothing to calibrate against
            self._iso = None
            return self
        self._iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self._iso.fit(np.asarray(scores, dtype=float), y_arr)
        return self

    def transform(self, scores: Sequence[float]) -> np.ndarray:
        s = np.asarray(scores, dtype=float)
        return s if self._iso is None else np.asarray(self._iso.predict(s))
