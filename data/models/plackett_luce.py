"""
Dynamic Plackett-Luce Ranking Model for F1 Predictions.

The Plackett-Luce model is the mathematically correct generalization of
Bradley-Terry to full rankings. Unlike Elo (pairwise comparisons in a
multi-competitor field), PL natively models the probability of an entire
finishing order:

    P(ranking) = ∏(k=1 to n-1) [ λ_r(k) / Σ(j=k to n) λ_r(j) ]

Each competitor's strength λ is decomposed as:
    log(λ) = θ_driver + θ_constructor

Strengths evolve over time via exponential decay weighting, giving more
influence to recent races.

References:
    - Henderson & Sherlock (2018) "A Comparison of Truncated and
      Time-Weighted Plackett-Luce Models for Probabilistic Forecasting
      of Formula One Results" (Bayesian Analysis)
    - Luce (1959) "Individual Choice Behavior"

Usage:
    python -m data.models.plackett_luce
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import softmax

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent.parent / "cache" / "models"

_DEFAULT_STRENGTH = 0.0  # log-space: exp(0) = 1.0


class PlackettLuceModel:
    """
    Dynamic Plackett-Luce model for multi-competitor ranking prediction.

    Decomposes competitor strength into driver + constructor components,
    fit via maximum likelihood with L2 regularization and exponential
    time decay.
    """

    def __init__(
        self,
        decay_rate: float = 0.02,
        reg_lambda: float = 0.01,
        n_simulations: int = 10000,
    ):
        """
        Args:
            decay_rate: Exponential decay per race for time weighting
                        (higher = more recency bias)
            reg_lambda: L2 regularization strength on log-strengths
            n_simulations: Number of PL samples for ranking prediction
        """
        self.decay_rate = decay_rate
        self.reg_lambda = reg_lambda
        self.n_simulations = n_simulations

        self.driver_strengths: Dict[str, float] = {}
        self.constructor_strengths: Dict[str, float] = {}
        self.driver_history: Dict[str, List[float]] = {}
        self.constructor_history: Dict[str, List[float]] = {}
        self._races_fitted: int = 0

    def fit(self, race_results: pd.DataFrame):
        """
        Fit model on historical race results via MLE.

        Args:
            race_results: DataFrame with columns: season, round, driver_id,
                          constructor_id, position. Must be sorted chronologically.
        """
        race_results = race_results.sort_values(["season", "round"]).copy()
        race_results = race_results.dropna(subset=["position"])
        race_results["position"] = race_results["position"].astype(int)

        # Collect all drivers and constructors
        all_drivers = sorted(race_results["driver_id"].unique())
        all_constructors = sorted(race_results["constructor_id"].unique())

        driver_to_idx = {d: i for i, d in enumerate(all_drivers)}
        constructor_to_idx = {c: i for i, c in enumerate(all_constructors)}
        n_drivers = len(all_drivers)
        n_constructors = len(all_constructors)

        # Build race data structure: list of (ranking, driver_indices, constructor_indices, time_weight)
        races = []
        race_groups = race_results.groupby(["season", "round"])
        total_races = len(race_groups)

        for race_idx, ((season, rnd), group) in enumerate(race_groups):
            group = group.sort_values("position")
            d_idxs = [driver_to_idx[d] for d in group["driver_id"]]
            c_idxs = [constructor_to_idx[c] for c in group["constructor_id"]]

            # Exponential decay: most recent race has weight 1.0
            races_ago = total_races - race_idx - 1
            weight = np.exp(-self.decay_rate * races_ago)

            races.append((d_idxs, c_idxs, weight))

        logger.info(
            "Fitting Plackett-Luce on %d races, %d drivers, %d constructors",
            total_races, n_drivers, n_constructors,
        )

        # Pre-convert race indices to numpy arrays for vectorized access
        races_np = [
            (np.array(d_idxs, dtype=np.intp), np.array(c_idxs, dtype=np.intp), weight)
            for d_idxs, c_idxs, weight in races
        ]

        # Initialize parameters: [driver_strengths..., constructor_strengths...]
        x0 = np.zeros(n_drivers + n_constructors)

        def neg_log_likelihood(params):
            driver_params = params[:n_drivers]
            constructor_params = params[n_drivers:]

            nll = 0.0
            for d_idxs, c_idxs, weight in races_np:
                log_strengths = driver_params[d_idxs] + constructor_params[c_idxs]

                # Reverse cumulative logsumexp: log_cumsum[k] = logsumexp(log_strengths[k:])
                # Computed in O(n) via backward pass instead of O(n²)
                n = len(log_strengths)
                log_cumsum = np.empty(n)
                log_cumsum[n - 1] = log_strengths[n - 1]
                for k in range(n - 2, -1, -1):
                    a, b = log_cumsum[k + 1], log_strengths[k]
                    mx = max(a, b)
                    log_cumsum[k] = mx + np.log(np.exp(a - mx) + np.exp(b - mx))

                nll -= weight * np.sum(log_strengths[:n - 1] - log_cumsum[:n - 1])

            # L2 regularization
            nll += self.reg_lambda * (
                np.sum(driver_params ** 2) + np.sum(constructor_params ** 2)
            )

            return nll

        def gradient(params):
            driver_params = params[:n_drivers]
            constructor_params = params[n_drivers:]

            grad = np.zeros_like(params)

            for d_idxs, c_idxs, weight in races_np:
                log_strengths = driver_params[d_idxs] + constructor_params[c_idxs]
                n = len(log_strengths)

                # Reverse cumulative logsumexp
                log_cumsum = np.empty(n)
                log_cumsum[n - 1] = log_strengths[n - 1]
                for k in range(n - 2, -1, -1):
                    a, b = log_cumsum[k + 1], log_strengths[k]
                    mx = max(a, b)
                    log_cumsum[k] = mx + np.log(np.exp(a - mx) + np.exp(b - mx))

                # Vectorized gradient: for each competitor j, the normalizer contribution
                # is weight * exp(log_strengths[j]) * sum_{k<=j, k<n-1} exp(-log_cumsum[k])
                inv_cumsum = np.exp(-log_cumsum[:n - 1])
                cum_inv = np.cumsum(inv_cumsum)

                normalizer_contrib = np.empty(n)
                normalizer_contrib[:n - 1] = np.exp(log_strengths[:n - 1]) * cum_inv
                normalizer_contrib[n - 1] = np.exp(log_strengths[n - 1]) * cum_inv[n - 2]

                # Winner contribution: positions 0..n-2 get -weight
                total = weight * normalizer_contrib
                total[:n - 1] -= weight

                np.add.at(grad[:n_drivers], d_idxs, total)
                np.add.at(grad[n_drivers:], c_idxs, total)

            # L2 regularization gradient
            grad += 2 * self.reg_lambda * params

            return grad

        result = minimize(
            neg_log_likelihood,
            x0,
            jac=gradient,
            method="L-BFGS-B",
            options={"maxiter": 500, "ftol": 1e-8},
        )

        if not result.success:
            logger.warning("PL optimization did not converge: %s", result.message)

        # Extract fitted parameters
        driver_params = result.x[:n_drivers]
        constructor_params = result.x[n_drivers:]

        # Center parameters (identifiability: mean = 0)
        driver_params -= driver_params.mean()
        constructor_params -= constructor_params.mean()

        self.driver_strengths = {d: float(driver_params[i]) for d, i in driver_to_idx.items()}
        self.constructor_strengths = {c: float(constructor_params[i]) for c, i in constructor_to_idx.items()}
        self._races_fitted = total_races

        # Record history (simplified: final values)
        for d in all_drivers:
            self.driver_history.setdefault(d, []).append(self.driver_strengths[d])
        for c in all_constructors:
            self.constructor_history.setdefault(c, []).append(self.constructor_strengths[c])

        logger.info(
            "PL fit complete (NLL=%.2f). Top drivers: %s",
            result.fun,
            ", ".join(f"{d}={v:.2f}" for d, v in
                      sorted(self.driver_strengths.items(), key=lambda x: -x[1])[:5]),
        )

    def _combined_strength(self, driver_id: str, constructor_id: str) -> float:
        """Get combined log-strength for a driver-constructor pair."""
        d = self.driver_strengths.get(driver_id, _DEFAULT_STRENGTH)
        c = self.constructor_strengths.get(constructor_id, _DEFAULT_STRENGTH)
        return d + c

    def predict_win_probs(
        self,
        driver_ids: List[str],
        constructor_ids: List[str],
    ) -> Dict[str, float]:
        """
        Compute P(win) for each driver using the PL formula.

        P(driver i wins) = λ_i / Σ_j λ_j = softmax(log_λ)_i
        """
        log_strengths = np.array([
            self._combined_strength(d, c)
            for d, c in zip(driver_ids, constructor_ids)
        ])

        # Softmax for win probabilities
        probs = softmax(log_strengths)
        return {d: float(p) for d, p in zip(driver_ids, probs)}

    def predict_race(
        self,
        driver_ids: List[str],
        constructor_ids: List[str],
    ) -> pd.DataFrame:
        """
        Predict full race probabilities via PL sampling.

        Returns DataFrame with columns: driver_id, pl_win_prob, pl_podium_prob,
        pl_points_prob, pl_expected_position, pl_position_std
        """
        n = len(driver_ids)
        log_strengths = np.array([
            self._combined_strength(d, c)
            for d, c in zip(driver_ids, constructor_ids)
        ])

        # Sample rankings using Gumbel-max trick
        # PL sample: add Gumbel(0,1) noise to log-strengths, then argsort
        rng = np.random.default_rng(42)
        gumbel_noise = rng.gumbel(size=(self.n_simulations, n))
        perturbed = log_strengths + gumbel_noise

        # Rankings: argsort of descending perturbed scores
        rankings = (-perturbed).argsort(axis=1).argsort(axis=1) + 1

        rows = []
        for i in range(n):
            positions = rankings[:, i]
            rows.append({
                "driver_id": driver_ids[i],
                "constructor_id": constructor_ids[i],
                "pl_driver_strength": self.driver_strengths.get(driver_ids[i], _DEFAULT_STRENGTH),
                "pl_constructor_strength": self.constructor_strengths.get(constructor_ids[i], _DEFAULT_STRENGTH),
                "pl_combined_strength": float(log_strengths[i]),
                "pl_win_prob": float((positions == 1).mean()),
                "pl_podium_prob": float((positions <= 3).mean()),
                "pl_points_prob": float((positions <= 10).mean()),
                "pl_expected_position": float(positions.mean()),
                "pl_position_std": float(positions.std()),
            })

        return pd.DataFrame(rows).sort_values("pl_expected_position")

    def predict_full_ranking(
        self,
        driver_ids: List[str],
        constructor_ids: List[str],
    ) -> np.ndarray:
        """
        Return expected finishing order via PL sampling.

        Returns array of driver_ids sorted by expected position.
        """
        result = self.predict_race(driver_ids, constructor_ids)
        return result["driver_id"].values

    def get_driver_strengths(self) -> pd.DataFrame:
        """Current driver strength parameters (log-space)."""
        rows = [
            {"driver_id": d, "strength": v, "exp_strength": np.exp(v)}
            for d, v in self.driver_strengths.items()
        ]
        return pd.DataFrame(rows).sort_values("strength", ascending=False)

    def get_constructor_strengths(self) -> pd.DataFrame:
        """Current constructor strength parameters (log-space)."""
        rows = [
            {"constructor_id": c, "strength": v, "exp_strength": np.exp(v)}
            for c, v in self.constructor_strengths.items()
        ]
        return pd.DataFrame(rows).sort_values("strength", ascending=False)

    def save(self, path: Optional[Path] = None):
        """Save model to disk."""
        import joblib
        path = path or MODEL_DIR
        path.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "driver_strengths": self.driver_strengths,
            "constructor_strengths": self.constructor_strengths,
            "driver_history": self.driver_history,
            "constructor_history": self.constructor_history,
            "decay_rate": self.decay_rate,
            "reg_lambda": self.reg_lambda,
            "races_fitted": self._races_fitted,
        }, path / "plackett_luce.joblib")
        logger.info("Plackett-Luce model saved to %s", path)

    def load(self, path: Optional[Path] = None):
        """Load model from disk."""
        import joblib
        path = path or MODEL_DIR
        data = joblib.load(path / "plackett_luce.joblib")
        self.driver_strengths = data["driver_strengths"]
        self.constructor_strengths = data["constructor_strengths"]
        self.driver_history = data["driver_history"]
        self.constructor_history = data["constructor_history"]
        self.decay_rate = data["decay_rate"]
        self.reg_lambda = data["reg_lambda"]
        self._races_fitted = data["races_fitted"]
        logger.info("Plackett-Luce model loaded (%d races)", self._races_fitted)


def build_plackett_luce(race_results: pd.DataFrame) -> PlackettLuceModel:
    """
    Convenience builder: fit PL model on historical race data.

    Args:
        race_results: DataFrame with season, round, driver_id,
                      constructor_id, position columns
    """
    model = PlackettLuceModel()
    model.fit(race_results)
    return model


def plackett_luce_features(
    model: PlackettLuceModel,
    driver_ids: List[str],
    constructor_ids: List[str],
) -> pd.DataFrame:
    """
    Generate PL-derived features for the XGBoost feature matrix.

    Returns DataFrame with columns:
        pl_driver_strength, pl_constructor_strength, pl_combined_strength,
        pl_win_prob, pl_podium_prob, pl_field_rank
    """
    result = model.predict_race(driver_ids, constructor_ids)

    features = pd.DataFrame({
        "driver_id": result["driver_id"],
        "pl_driver_strength": result["pl_driver_strength"],
        "pl_constructor_strength": result["pl_constructor_strength"],
        "pl_combined_strength": result["pl_combined_strength"],
        "pl_win_prob": result["pl_win_prob"],
        "pl_podium_prob": result["pl_podium_prob"],
        "pl_field_rank": result["pl_expected_position"].rank().astype(int),
    })

    return features


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Demo with synthetic data
    np.random.seed(42)

    drivers = ["verstappen", "norris", "leclerc", "hamilton", "russell",
               "piastri", "sainz", "alonso", "gasly", "hulkenberg"]
    constructors = ["red_bull", "mclaren", "ferrari", "ferrari", "mercedes",
                    "mclaren", "williams", "aston_martin", "alpine", "sauber"]
    driver_constructor = dict(zip(drivers, constructors))

    # Generate synthetic race results (20 races)
    rows = []
    true_strength = np.array([3.0, 2.5, 2.3, 1.8, 2.0, 2.2, 1.5, 1.0, 1.2, 0.8])

    for season in [2024, 2025]:
        for rnd in range(1, 11):
            noise = np.random.gumbel(size=len(drivers))
            performance = true_strength + noise
            order = (-performance).argsort()
            for pos, idx in enumerate(order, 1):
                rows.append({
                    "season": season,
                    "round": rnd,
                    "driver_id": drivers[idx],
                    "constructor_id": constructors[idx],
                    "position": pos,
                    "circuit_id": f"circuit_{rnd}",
                })

    race_results = pd.DataFrame(rows)

    # Fit model
    model = build_plackett_luce(race_results)

    # Show strengths
    print("\n--- Driver Strengths ---")
    print(model.get_driver_strengths().to_string(index=False))

    print("\n--- Constructor Strengths ---")
    print(model.get_constructor_strengths().to_string(index=False))

    # Predict next race
    print("\n--- Next Race Prediction ---")
    pred = model.predict_race(drivers, constructors)
    display_cols = ["driver_id", "pl_win_prob", "pl_podium_prob", "pl_expected_position"]
    print(pred[display_cols].to_string(index=False))

    # Generate features for XGBoost integration
    print("\n--- XGBoost Features ---")
    feats = plackett_luce_features(model, drivers, constructors)
    print(feats.to_string(index=False))
