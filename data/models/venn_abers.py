"""
Venn-ABERS Probability Calibration — theoretically guaranteed calibration.

Unlike Platt scaling or isotonic regression, Venn-ABERS provides validity
guarantees: calibrated probabilities are provably well-calibrated for any
underlying distribution.

Uses the Inductive Venn-ABERS Predictor (IVAP) approach: for each test
point, augment the calibration set and re-fit isotonic regression.
O(n * m log m) where n = test points, m = calibration set size.

The key advantage for betting: prediction intervals [p0, p1] allow
conservative Kelly sizing using the lower bound.

Reference:
    Vovk, Petej, & Fedorova (2015) "Large-scale probabilistic predictors
    with and without guarantees of validity" (NeurIPS)
"""

import logging
from typing import Optional

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import StratifiedShuffleSplit

logger = logging.getLogger(__name__)


class VennAbersCalibrator(BaseEstimator, ClassifierMixin):
    """
    Inductive Venn-ABERS Predictor (IVAP) for probability calibration.

    Wraps any sklearn-compatible classifier and produces calibrated
    probabilities with theoretical validity guarantees.

    The calibrator also provides prediction intervals [p0, p1] which
    are useful for conservative Kelly criterion stake sizing.
    """

    def __init__(
        self,
        base_estimator,
        cal_fraction: float = 0.3,
        random_state: int = 42,
    ):
        """
        Args:
            base_estimator: sklearn classifier with predict_proba
            cal_fraction: fraction of training data held out for calibration
            random_state: random seed for train/calibration split
        """
        self.base_estimator = base_estimator
        self.cal_fraction = cal_fraction
        self.random_state = random_state

        self._model = None
        self._cal_scores: Optional[np.ndarray] = None
        self._cal_labels: Optional[np.ndarray] = None
        self.classes_ = None

    def fit(self, X, y):
        """
        Train base estimator on proper training set, then build calibration
        mapping from held-out calibration set.
        """
        X = np.asarray(X)
        y = np.asarray(y).ravel()
        self.classes_ = np.unique(y)

        if len(self.classes_) != 2:
            raise ValueError(
                f"VennAbersCalibrator requires binary labels, got {len(self.classes_)} classes"
            )

        # Split into proper training and calibration sets
        n = len(y)
        min_class_count = min(np.sum(y == c) for c in self.classes_)

        if min_class_count < 4:
            logger.warning(
                "Too few samples for Venn-ABERS split (min class=%d), "
                "training on full data with degraded calibration",
                min_class_count,
            )
            self._model = clone(self.base_estimator)
            self._model.fit(X, y)
            scores = self._model.predict_proba(X)[:, 1]
            self._build_isotonic_regressors(scores, y)
            return self

        splitter = StratifiedShuffleSplit(
            n_splits=1,
            test_size=self.cal_fraction,
            random_state=self.random_state,
        )
        train_idx, cal_idx = next(splitter.split(X, y))

        self._model = clone(self.base_estimator)
        self._model.fit(X[train_idx], y[train_idx])

        # Get uncalibrated scores on calibration set
        cal_scores = self._model.predict_proba(X[cal_idx])[:, 1]
        cal_labels = y[cal_idx]

        self._build_isotonic_regressors(cal_scores, cal_labels)

        return self

    def _build_isotonic_regressors(self, scores: np.ndarray, labels: np.ndarray):
        """
        Store calibration scores and labels for IVAP prediction.

        At prediction time, each test point is augmented into the calibration
        set twice (once with label=0, once with label=1) and isotonic
        regression is re-fit. This is the correct IVAP algorithm — fitting
        once on unaugmented data would produce identical p0/p1, collapsing
        prediction intervals to zero width.
        """
        self._cal_scores = scores.copy()
        self._cal_labels = labels.copy()

    def predict_proba(self, X) -> np.ndarray:
        """
        Return Venn-ABERS calibrated probabilities.

        For each test point with score s:
        - p0 = isotonic_0(s) — probability estimate assuming y=0
        - p1 = isotonic_1(s) — probability estimate assuming y=1
        - calibrated_p = p1 / (1 - p0 + p1)

        Returns:
            Array of shape (n_samples, 2) with [P(class=0), P(class=1)]
        """
        p0, p1 = self._raw_intervals(X)

        # Venn-ABERS multiprobability: geometric mean of the two estimates
        # p_calibrated = p1 / (1 - p0 + p1) — standard IVAP formula
        denom = (1.0 - p0) + p1
        # Avoid division by zero
        denom = np.where(denom == 0, 1e-10, denom)
        p_calibrated = p1 / denom
        p_calibrated = np.clip(p_calibrated, 0.0, 1.0)

        proba = np.column_stack([1.0 - p_calibrated, p_calibrated])
        return proba

    def predict_proba_with_interval(self, X) -> tuple:
        """
        Return calibrated probability intervals [lower, upper].

        The interval width reflects model uncertainty — wider intervals
        mean less confident predictions. Use the lower bound for
        conservative Kelly criterion stake sizing.

        Returns:
            (lower_bounds, upper_bounds) — each array of shape (n_samples,)
        """
        p0, p1 = self._raw_intervals(X)

        # p0 is the probability estimate under hypothesis y=0 (lower bound)
        # p1 is the probability estimate under hypothesis y=1 (upper bound)
        lower = np.clip(p0, 0.0, 1.0)
        upper = np.clip(p1, 0.0, 1.0)

        # Ensure lower <= upper
        lower, upper = np.minimum(lower, upper), np.maximum(lower, upper)

        return lower, upper

    def _raw_intervals(self, X) -> tuple:
        """
        Get raw p0, p1 via per-point IVAP augmentation.

        For each test score s, we augment the calibration set with (s, 0)
        and (s, 1) respectively, fit isotonic regression, and read off
        the prediction at s. This produces genuinely different p0 and p1,
        giving meaningful prediction intervals.
        """
        X = np.asarray(X)
        scores = self._model.predict_proba(X)[:, 1]

        cal_s = self._cal_scores
        cal_y = self._cal_labels

        p0 = np.empty(len(scores))
        p1 = np.empty(len(scores))

        iso_0 = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        iso_1 = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")

        for i, s in enumerate(scores):
            aug_s = np.append(cal_s, s)
            iso_0.fit(aug_s, np.append(cal_y, 0))
            iso_1.fit(aug_s, np.append(cal_y, 1))
            p0[i] = iso_0.predict([s])[0]
            p1[i] = iso_1.predict([s])[0]

        return p0, p1

    def predict(self, X) -> np.ndarray:
        """Standard binary prediction."""
        proba = self.predict_proba(X)
        return (proba[:, 1] >= 0.5).astype(int)


if __name__ == "__main__":
    from sklearn.datasets import make_classification
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import train_test_split

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    X, y = make_classification(
        n_samples=2000, n_features=20, n_informative=10,
        random_state=42, weights=[0.85, 0.15],
    )
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42,
    )

    base = GradientBoostingClassifier(n_estimators=100, random_state=42)
    va = VennAbersCalibrator(base)
    va.fit(X_train, y_train)

    proba = va.predict_proba(X_test)
    lo, hi = va.predict_proba_with_interval(X_test)

    print(f"Predictions: {len(X_test)}")
    print(f"Mean P(1): {proba[:, 1].mean():.4f}")
    print(f"Actual rate: {y_test.mean():.4f}")
    print(f"Mean interval width: {(hi - lo).mean():.4f}")
    print(f"Accuracy: {(va.predict(X_test) == y_test).mean():.4f}")

    # ECE comparison
    from sklearn.calibration import CalibratedClassifierCV

    base2 = GradientBoostingClassifier(n_estimators=100, random_state=42)
    platt = CalibratedClassifierCV(base2, cv=3, method="isotonic")
    platt.fit(X_train, y_train)
    platt_proba = platt.predict_proba(X_test)

    def ece(probs, labels, n_bins=10):
        bin_edges = np.linspace(0, 1, n_bins + 1)
        err = 0.0
        for lo_e, hi_e in zip(bin_edges[:-1], bin_edges[1:]):
            mask = (probs >= lo_e) & (probs < hi_e)
            if mask.sum() == 0:
                continue
            err += mask.sum() / len(probs) * abs(labels[mask].mean() - probs[mask].mean())
        return err

    print(f"\nECE (Venn-ABERS): {ece(proba[:, 1], y_test):.4f}")
    print(f"ECE (Isotonic CV): {ece(platt_proba[:, 1], y_test):.4f}")
