"""
F1 Prediction Calibration Verification.

Measures whether predicted probabilities match actual outcomes.
If we predict 30% win -> the driver should win ~30% of the time.

Metrics:
- Reliability diagram (bin predicted vs observed frequencies)
- Brier score + decomposition (reliability, resolution, uncertainty)
- Expected Calibration Error (ECE)
- Log loss
- Conditional breakdown (circuit type, wet/dry, grid position bucket)

Usage:
    python -m data.models.calibration                     # Calibrate 2024-2025
    python -m data.models.calibration --season 2024 2025  # Specific seasons
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "cache" / "processed"

# Probability types produced by F1Predictor
PROB_TYPES = ["win", "podium", "points", "dnf"]


class CalibrationAnalyzer:
    """Analyzes calibration quality of probabilistic predictions."""

    def __init__(self, n_bins: int = 10):
        self.n_bins = n_bins

    def reliability_diagram(
        self,
        predicted_probs: np.ndarray,
        actual_outcomes: np.ndarray,
    ) -> dict:
        """
        Compute reliability diagram data.

        Bins predictions into n_bins equally-spaced buckets, then computes
        the observed frequency in each bin.

        Returns:
            bin_centers: midpoint of each bin
            bin_frequencies: actual positive rate in each bin
            bin_counts: number of samples per bin
        """
        bin_edges = np.linspace(0.0, 1.0, self.n_bins + 1)
        bin_centers = []
        bin_frequencies = []
        bin_counts = []

        for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
            mask = (predicted_probs >= lo) & (predicted_probs < hi)
            # Include the right edge for the last bin
            if hi == 1.0:
                mask = mask | (predicted_probs == 1.0)

            count = mask.sum()
            bin_counts.append(int(count))

            if count > 0:
                bin_centers.append((lo + hi) / 2)
                bin_frequencies.append(float(actual_outcomes[mask].mean()))
            else:
                bin_centers.append((lo + hi) / 2)
                bin_frequencies.append(np.nan)

        return {
            "bin_centers": np.array(bin_centers),
            "bin_frequencies": np.array(bin_frequencies),
            "bin_counts": np.array(bin_counts),
        }

    @staticmethod
    def brier_score(
        predicted_probs: np.ndarray,
        actual_outcomes: np.ndarray,
    ) -> float:
        """Brier score: mean squared error between probabilities and outcomes."""
        from data.models.value import brier_score
        return brier_score(predicted_probs, actual_outcomes)

    def brier_decomposition(
        self,
        predicted_probs: np.ndarray,
        actual_outcomes: np.ndarray,
    ) -> dict:
        """
        Murphy decomposition of Brier score into three components:

        Brier = Reliability - Resolution + Uncertainty

        - Reliability: how close predicted probs are to observed frequencies (lower is better)
        - Resolution: how much bins deviate from base rate (higher is better)
        - Uncertainty: base rate variance, independent of model (constant)
        """
        n = len(predicted_probs)
        base_rate = actual_outcomes.mean()
        uncertainty = base_rate * (1 - base_rate)

        bin_edges = np.linspace(0.0, 1.0, self.n_bins + 1)
        reliability = 0.0
        resolution = 0.0

        for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
            mask = (predicted_probs >= lo) & (predicted_probs < hi)
            if hi == 1.0:
                mask = mask | (predicted_probs == 1.0)

            n_k = mask.sum()
            if n_k == 0:
                continue

            mean_pred = predicted_probs[mask].mean()
            mean_actual = actual_outcomes[mask].mean()

            reliability += n_k * (mean_pred - mean_actual) ** 2
            resolution += n_k * (mean_actual - base_rate) ** 2

        reliability /= n
        resolution /= n

        return {
            "reliability": float(reliability),
            "resolution": float(resolution),
            "uncertainty": float(uncertainty),
            "brier_score": float(reliability - resolution + uncertainty),
        }

    def calibration_error(
        self,
        predicted_probs: np.ndarray,
        actual_outcomes: np.ndarray,
    ) -> float:
        """
        Expected Calibration Error (ECE).

        Weighted average of |observed_freq - predicted_prob| across bins.
        """
        n = len(predicted_probs)
        bin_edges = np.linspace(0.0, 1.0, self.n_bins + 1)
        ece = 0.0

        for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
            mask = (predicted_probs >= lo) & (predicted_probs < hi)
            if hi == 1.0:
                mask = mask | (predicted_probs == 1.0)

            n_k = mask.sum()
            if n_k == 0:
                continue

            mean_pred = predicted_probs[mask].mean()
            mean_actual = actual_outcomes[mask].mean()
            ece += (n_k / n) * abs(mean_actual - mean_pred)

        return float(ece)

    def log_loss(
        self,
        predicted_probs: np.ndarray,
        actual_outcomes: np.ndarray,
        eps: float = 1e-15,
    ) -> float:
        """
        Log loss (cross-entropy loss).

        Heavily penalizes confident wrong predictions.
        """
        p = np.clip(predicted_probs, eps, 1 - eps)
        return float(-np.mean(
            actual_outcomes * np.log(p) + (1 - actual_outcomes) * np.log(1 - p)
        ))

    def analyze_by_condition(
        self,
        backtest_results: pd.DataFrame,
        predictions: pd.DataFrame,
    ) -> dict:
        """
        Break down calibration by circuit type, wet/dry, and grid position bucket.

        Args:
            backtest_results: DataFrame with race-level metadata
                (circuit_id, is_wet, etc.)
            predictions: DataFrame with per-driver rows containing
                predicted probabilities and actual outcomes

        Returns:
            Dict of condition -> {metric_name -> value}
        """
        report = {}

        # By circuit type (if available)
        if "circuit_type" in predictions.columns:
            ct_report = {}
            for ct, group in predictions.groupby("circuit_type"):
                ct_metrics = {}
                for prob_type in PROB_TYPES:
                    prob_col = f"prob_{prob_type}"
                    actual_col = f"actual_{prob_type}"
                    if prob_col in group.columns and actual_col in group.columns:
                        probs = group[prob_col].values
                        actuals = group[actual_col].values
                        ct_metrics[f"{prob_type}_ece"] = self.calibration_error(probs, actuals)
                        ct_metrics[f"{prob_type}_brier"] = self.brier_score(probs, actuals)
                ct_report[ct] = ct_metrics
            report["by_circuit_type"] = ct_report

        # By wet/dry
        if "is_wet" in predictions.columns:
            wd_report = {}
            for label, wet_val in [("dry", 0), ("wet", 1)]:
                group = predictions[predictions["is_wet"] == wet_val]
                if group.empty:
                    continue
                wd_metrics = {}
                for prob_type in PROB_TYPES:
                    prob_col = f"prob_{prob_type}"
                    actual_col = f"actual_{prob_type}"
                    if prob_col in group.columns and actual_col in group.columns:
                        probs = group[prob_col].values
                        actuals = group[actual_col].values
                        wd_metrics[f"{prob_type}_ece"] = self.calibration_error(probs, actuals)
                        wd_metrics[f"{prob_type}_brier"] = self.brier_score(probs, actuals)
                wd_report[label] = wd_metrics
            report["by_weather"] = wd_report

        # By grid position bucket
        if "grid_position" in predictions.columns:
            bins = [(1, 3, "front_row"), (4, 10, "midfield"), (11, 20, "backfield")]
            gp_report = {}
            for lo, hi, label in bins:
                group = predictions[
                    (predictions["grid_position"] >= lo) &
                    (predictions["grid_position"] <= hi)
                ]
                if group.empty:
                    continue
                gp_metrics = {}
                for prob_type in PROB_TYPES:
                    prob_col = f"prob_{prob_type}"
                    actual_col = f"actual_{prob_type}"
                    if prob_col in group.columns and actual_col in group.columns:
                        probs = group[prob_col].values
                        actuals = group[actual_col].values
                        gp_metrics[f"{prob_type}_ece"] = self.calibration_error(probs, actuals)
                        gp_metrics[f"{prob_type}_brier"] = self.brier_score(probs, actuals)
                gp_report[label] = gp_metrics
            report["by_grid_position"] = gp_report

        return report


def evaluate_model_calibration(
    feature_matrix: pd.DataFrame,
    test_seasons: list[int],
) -> dict:
    """
    Top-level calibration evaluation using walk-forward predictions.

    1. Runs walk-forward predictions for test seasons
    2. Computes calibration metrics for each probability type (win, podium, points, DNF)
    3. Returns comprehensive calibration report

    Args:
        feature_matrix: Full feature matrix from build_feature_matrix()
        test_seasons: Seasons to evaluate

    Returns:
        Comprehensive calibration report dict
    """
    from data.features.engineer import prepare_training_data
    from data.models.predictor import _create_model, F1Predictor

    analyzer = CalibrationAnalyzer(n_bins=10)

    # Collect all per-driver predictions across test races
    all_predictions = []

    races = (
        feature_matrix[["season", "round", "circuit_id"]]
        .drop_duplicates()
        .sort_values(["season", "round"])
    )
    test_races = races[races["season"].isin(test_seasons)]

    for _, race in test_races.iterrows():
        season = int(race["season"])
        rnd = int(race["round"])
        circuit_id = race["circuit_id"]

        train_mask = (
            (feature_matrix["season"] < season) |
            ((feature_matrix["season"] == season) & (feature_matrix["round"] < rnd))
        )
        test_mask = (
            (feature_matrix["season"] == season) &
            (feature_matrix["round"] == rnd)
        )

        train_data = feature_matrix[train_mask]
        test_data = feature_matrix[test_mask]

        if len(train_data) < 100 * 15:
            continue

        try:
            X_train, y_train = prepare_training_data(train_data, target="position")
            X_test, y_test = prepare_training_data(test_data, target="position")
        except Exception as e:
            logger.warning("Skipping S%d R%02d: %s", season, rnd, e)
            continue

        if X_test.empty or y_test.empty:
            continue

        # Align columns
        for col in set(X_train.columns) - set(X_test.columns):
            X_test[col] = 0
        for col in set(X_test.columns) - set(X_train.columns):
            X_train[col] = 0
        X_test = X_test[X_train.columns]

        # Train full predictor (classifiers needed for probabilities)
        predictor = F1Predictor()
        train_dnf = train_data.reindex(X_train.index).get("dnf", pd.Series(dtype=float))
        train_dnf = train_dnf.fillna(0).astype(int)
        predictor.train(X_train, y_train, y_dnf=train_dnf)

        # Generate predictions with probabilities
        results = predictor.predict_race(X_test)

        # Attach actuals
        results["actual_position"] = y_test
        results["actual_win"] = (y_test == 1).astype(int).values
        results["actual_podium"] = (y_test <= 3).astype(int).values
        results["actual_points"] = (y_test <= 10).astype(int).values

        test_dnf = test_data.reindex(X_test.index).get("dnf", pd.Series(dtype=float))
        results["actual_dnf"] = test_dnf.fillna(0).astype(int).values

        results["season"] = season
        results["round"] = rnd
        results["circuit_id"] = circuit_id

        # Carry metadata columns for conditional analysis
        for meta_col in ["circuit_type", "is_wet", "grid_position", "constructor_id"]:
            if meta_col in test_data.columns:
                results[meta_col] = test_data.reindex(X_test.index)[meta_col].values

        all_predictions.append(results)

        logger.info(
            "S%d R%02d %-20s — %d drivers predicted",
            season, rnd, circuit_id[:20], len(results),
        )

    if not all_predictions:
        logger.warning("No predictions generated — check test_seasons and data")
        return {}

    predictions_df = pd.concat(all_predictions, ignore_index=True)

    # Compute calibration metrics per probability type
    report = {"n_predictions": len(predictions_df), "test_seasons": test_seasons}

    prob_map = {
        "win": ("prob_winner", "actual_win"),
        "podium": ("prob_podium", "actual_podium"),
        "points": ("prob_points", "actual_points"),
        "dnf": ("prob_dnf", "actual_dnf"),
    }

    for label, (prob_col, actual_col) in prob_map.items():
        if prob_col not in predictions_df.columns:
            continue

        probs = predictions_df[prob_col].values
        actuals = predictions_df[actual_col].values

        # Drop NaN pairs
        valid = ~(np.isnan(probs) | np.isnan(actuals))
        probs = probs[valid]
        actuals = actuals[valid]

        if len(probs) == 0:
            continue

        report[label] = {
            "brier_score": analyzer.brier_score(probs, actuals),
            "brier_decomposition": analyzer.brier_decomposition(probs, actuals),
            "ece": analyzer.calibration_error(probs, actuals),
            "log_loss": analyzer.log_loss(probs, actuals),
            "reliability_diagram": analyzer.reliability_diagram(probs, actuals),
            "n_samples": int(len(probs)),
            "base_rate": float(actuals.mean()),
        }

    # Conditional analysis
    report["conditional"] = analyzer.analyze_by_condition(
        backtest_results=predictions_df,
        predictions=predictions_df,
    )

    return report


def print_calibration_report(report: dict) -> None:
    """Pretty-print calibration results with ASCII reliability charts."""
    if not report:
        print("No calibration data to report.")
        return

    print("\n" + "=" * 70)
    print("  F1 PREDICTION CALIBRATION REPORT")
    print("=" * 70)
    print(f"  Seasons: {report.get('test_seasons', [])}")
    print(f"  Total predictions: {report.get('n_predictions', 0):,}")
    print()

    for prob_type in PROB_TYPES:
        if prob_type not in report:
            continue

        data = report[prob_type]
        print(f"--- {prob_type.upper()} probability ---")
        print(f"  Samples:    {data['n_samples']:,}  (base rate: {data['base_rate']:.3f})")
        print(f"  Brier:      {data['brier_score']:.4f}")
        print(f"  ECE:        {data['ece']:.4f}")
        print(f"  Log loss:   {data['log_loss']:.4f}")

        decomp = data["brier_decomposition"]
        print(f"  Brier decomposition:")
        print(f"    Reliability:  {decomp['reliability']:.4f}  (lower is better)")
        print(f"    Resolution:   {decomp['resolution']:.4f}  (higher is better)")
        print(f"    Uncertainty:  {decomp['uncertainty']:.4f}  (constant)")

        # ASCII reliability diagram
        rd = data["reliability_diagram"]
        centers = rd["bin_centers"]
        freqs = rd["bin_frequencies"]
        counts = rd["bin_counts"]

        print(f"\n  Reliability diagram ({prob_type}):")
        print(f"  {'Predicted':>10} {'Observed':>10} {'Count':>7}  Chart")
        print(f"  {'-' * 10} {'-' * 10} {'-' * 7}  {'-' * 30}")

        for c, f, n in zip(centers, freqs, counts):
            if n == 0 or np.isnan(f):
                print(f"  {c:10.2f} {'---':>10} {n:7d}")
                continue

            # Bar showing deviation from perfect calibration
            bar_len = int(f * 30)
            perfect_pos = int(c * 30)
            bar = "#" * bar_len
            marker = " " * perfect_pos + "|"

            print(f"  {c:10.2f} {f:10.3f} {n:7d}  {bar}")
            print(f"  {'':10} {'':10} {'':7}  {marker} (perfect)")

        print()

    # Conditional breakdowns
    conditional = report.get("conditional", {})

    if "by_weather" in conditional:
        print("--- BY WEATHER ---")
        for label, metrics in conditional["by_weather"].items():
            parts = [f"{k}={v:.4f}" for k, v in metrics.items()]
            print(f"  {label:6s}: {', '.join(parts)}")
        print()

    if "by_circuit_type" in conditional:
        print("--- BY CIRCUIT TYPE ---")
        for ct, metrics in conditional["by_circuit_type"].items():
            parts = [f"{k}={v:.4f}" for k, v in metrics.items()]
            print(f"  {ct:12s}: {', '.join(parts)}")
        print()

    if "by_grid_position" in conditional:
        print("--- BY GRID POSITION ---")
        for bucket, metrics in conditional["by_grid_position"].items():
            parts = [f"{k}={v:.4f}" for k, v in metrics.items()]
            print(f"  {bucket:12s}: {', '.join(parts)}")
        print()

    print("=" * 70)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F1 calibration verification")
    parser.add_argument("--season", type=int, nargs="+", default=[2024, 2025])
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    fm = pd.read_parquet(DATA_DIR / "feature_matrix.parquet")

    report = evaluate_model_calibration(fm, test_seasons=args.season)
    print_calibration_report(report)
