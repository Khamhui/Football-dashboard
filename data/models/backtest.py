"""
Walk-forward backtesting for F1 predictions.

Instead of a single train/test split, this evaluates the model on each race
sequentially: for race N, train on all races before N, predict N, record accuracy.

This reveals:
- True out-of-sample performance per race
- Where the model fails (specific circuits, conditions)
- Consistency of predictions across the season
- Calibration of probability predictions (Brier score)
- Per-constructor accuracy breakdown
- Confidence coverage (how often actuals fall within predicted range)

Usage:
    python -m data.models.backtest                     # Backtest 2025
    python -m data.models.backtest --season 2024       # Specific season
    python -m data.models.backtest --season 2024 2025  # Multiple seasons
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import mean_absolute_error

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "cache" / "processed"


from data.models.value import brier_score as _brier_score


def _confidence_coverage(
    y_pred: np.ndarray,
    y_test: pd.Series,
    low_pct: float = 25.0,
    high_pct: float = 75.0,
) -> float:
    """
    What percentage of actual positions fall within the model's
    predicted percentile range.

    Uses prediction residual distribution to estimate spread:
    the predicted value +/- a margin derived from the percentile range
    of the raw predictions themselves.
    """
    pred_sorted = np.sort(y_pred)
    n = len(pred_sorted)
    if n < 4:
        return np.nan

    lo = np.percentile(y_pred, low_pct)
    hi = np.percentile(y_pred, high_pct)

    within = ((y_test.values >= lo) & (y_test.values <= hi)).sum()
    return float(within / len(y_test))


def walk_forward_backtest(
    feature_matrix: pd.DataFrame,
    test_seasons: list,
    min_train_races: int = 100,
) -> pd.DataFrame:
    """
    Walk-forward evaluation: for each race in test_seasons,
    train on all prior data and predict that race.

    Args:
        feature_matrix: Full feature matrix from build_feature_matrix()
        test_seasons: Seasons to evaluate (e.g., [2024, 2025])
        min_train_races: Minimum training races before starting predictions

    Returns:
        DataFrame with per-race metrics, predicted probabilities, and breakdowns
    """
    from data.features.engineer import prepare_training_data
    from data.models.predictor import create_model, F1Predictor

    results = []
    all_driver_predictions = []

    # Get all unique races in chronological order
    races = (
        feature_matrix[["season", "round", "circuit_id"]]
        .drop_duplicates()
        .sort_values(["season", "round"])
    )

    # Only evaluate races in test_seasons
    test_races = races[races["season"].isin(test_seasons)]
    all_race_keys = list(zip(races["season"], races["round"]))

    # Check if weather data is available
    has_weather = "is_wet" in feature_matrix.columns
    has_constructor = "constructor_id" in feature_matrix.columns

    for idx, (_, race) in enumerate(test_races.iterrows()):
        season = int(race["season"])
        rnd = int(race["round"])
        circuit_id = race["circuit_id"]

        # Training data: all races BEFORE this one
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

        if len(train_data) < min_train_races * 15:  # ~15 drivers per race
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

        # Train a quick model (no ensemble for speed)
        model = create_model(
            "regressor", n_estimators=500, max_depth=6,
            learning_rate=0.05, random_state=42,
        )
        model.fit(X_train, y_train)

        # Predict positions
        y_pred = model.predict(X_test)

        # Train classifiers for probability predictions
        prob_win = np.full(len(y_test), np.nan)
        prob_podium = np.full(len(y_test), np.nan)
        prob_points = np.full(len(y_test), np.nan)
        prob_dnf = np.full(len(y_test), np.nan)
        brier_win = np.nan
        brier_podium = np.nan
        brier_points = np.nan
        brier_dnf = np.nan

        try:
            y_win_train = (y_train == 1).astype(int)
            y_podium_train = (y_train <= 3).astype(int)
            y_points_train = (y_train <= 10).astype(int)

            y_win_actual = (y_test == 1).astype(int)
            y_podium_actual = (y_test <= 3).astype(int)
            y_points_actual = (y_test <= 10).astype(int)

            # Only train classifiers if there are positive examples
            for label, y_cls_train, y_cls_actual, depth, lr in [
                ("win", y_win_train, y_win_actual, 4, 0.03),
                ("podium", y_podium_train, y_podium_actual, 5, 0.05),
                ("points", y_points_train, y_points_actual, 5, 0.05),
            ]:
                if y_cls_train.sum() < 5:
                    continue

                spw = len(y_cls_train) / max(y_cls_train.sum(), 1) - 1
                clf = create_model(
                    "classifier", n_estimators=300, max_depth=depth,
                    learning_rate=lr, scale_pos_weight=spw, random_state=42,
                )
                clf.fit(X_train, y_cls_train)
                probs = clf.predict_proba(X_test)[:, 1]

                if label == "win":
                    prob_win = probs
                    brier_win = _brier_score(probs, y_cls_actual.values)
                elif label == "podium":
                    prob_podium = probs
                    brier_podium = _brier_score(probs, y_cls_actual.values)
                elif label == "points":
                    prob_points = probs
                    brier_points = _brier_score(probs, y_cls_actual.values)

            # DNF classifier
            train_dnf = train_data.reindex(X_train.index).get("dnf", pd.Series(dtype=float))
            train_dnf = train_dnf.fillna(0).astype(int)
            test_dnf = test_data.reindex(X_test.index).get("dnf", pd.Series(dtype=float))
            test_dnf = test_dnf.fillna(0).astype(int)

            if train_dnf.sum() >= 5:
                spw_dnf = len(train_dnf) / max(train_dnf.sum(), 1) - 1
                clf_dnf = create_model(
                    "classifier", n_estimators=300, max_depth=4,
                    learning_rate=0.03, scale_pos_weight=spw_dnf, random_state=42,
                )
                clf_dnf.fit(X_train, train_dnf)
                prob_dnf = clf_dnf.predict_proba(X_test)[:, 1]
                brier_dnf = _brier_score(prob_dnf, test_dnf.values)

        except Exception as e:
            logger.debug("Probability prediction failed for S%d R%02d: %s", season, rnd, e)

        # Metrics
        mae = mean_absolute_error(y_test, y_pred)

        # Position ranking
        pred_ranks = pd.Series(y_pred, index=y_test.index).rank()
        actual_ranks = y_test.rank()

        # Spearman rank correlation
        spearman_corr, _ = spearmanr(actual_ranks, pred_ranks)

        # Correct winner? (compare by index, not positional offset)
        pred_series = pd.Series(y_pred, index=y_test.index)
        correct_winner = int(pred_series.idxmin() == y_test.idxmin())

        # Correct podium (top 3 by index)
        pred_top3 = set(pred_series.nsmallest(3).index)
        actual_top3 = set(y_test.nsmallest(3).index)
        podium_overlap = len(pred_top3 & actual_top3) / 3

        # Confidence coverage: % of actual positions within predicted 25th-75th percentile
        conf_coverage = _confidence_coverage(y_pred, y_test)

        # Weather condition for this race
        is_wet = None
        if has_weather:
            race_wet = test_data["is_wet"]
            if not race_wet.empty:
                is_wet = int(race_wet.iloc[0])

        # Per-constructor MAE for this race
        constructor_maes = {}
        if has_constructor:
            test_constructors = test_data.reindex(X_test.index).get("constructor_id")
            if test_constructors is not None:
                for cid, group_idx in test_constructors.groupby(test_constructors).groups.items():
                    valid_idx = group_idx.intersection(y_test.index)
                    if len(valid_idx) >= 1:
                        constructor_maes[cid] = mean_absolute_error(
                            y_test.loc[valid_idx],
                            pred_series.loc[valid_idx],
                        )

        # Collect per-driver prediction rows
        for i, idx_val in enumerate(X_test.index):
            driver_row = {
                "season": season,
                "round": rnd,
                "circuit_id": circuit_id,
                "predicted_position": y_pred[i],
                "actual_position": y_test.iloc[i] if i < len(y_test) else np.nan,
                "prob_win": prob_win[i] if not np.isnan(prob_win[i]) else np.nan,
                "prob_podium": prob_podium[i] if not np.isnan(prob_podium[i]) else np.nan,
                "prob_points": prob_points[i] if not np.isnan(prob_points[i]) else np.nan,
                "prob_dnf": prob_dnf[i] if not np.isnan(prob_dnf[i]) else np.nan,
            }
            if has_constructor:
                cid_series = test_data.reindex(X_test.index).get("constructor_id")
                if cid_series is not None and idx_val in cid_series.index:
                    driver_row["constructor_id"] = cid_series.loc[idx_val]
            if has_weather:
                driver_row["is_wet"] = is_wet
            all_driver_predictions.append(driver_row)

        race_result = {
            "season": season,
            "round": rnd,
            "circuit_id": circuit_id,
            "n_drivers": len(y_test),
            "n_train_races": len(train_data) // 15,
            "mae": mae,
            "spearman_corr": spearman_corr,
            "correct_winner": correct_winner,
            "podium_overlap": podium_overlap,
            "confidence_coverage": conf_coverage,
            "brier_win": brier_win,
            "brier_podium": brier_podium,
            "brier_points": brier_points,
            "brier_dnf": brier_dnf,
        }

        if is_wet is not None:
            race_result["is_wet"] = is_wet

        results.append(race_result)

        logger.info(
            "S%d R%02d %-20s MAE=%.2f Spearman=%.3f Winner=%s Podium=%.0f%% Coverage=%.0f%%",
            season, rnd, circuit_id[:20], mae, spearman_corr,
            "Y" if correct_winner else "N", podium_overlap * 100,
            conf_coverage * 100 if not np.isnan(conf_coverage) else 0,
        )

    df = pd.DataFrame(results)

    if not df.empty:
        logger.info("\n=== Walk-Forward Backtest Summary ===")
        logger.info("Races evaluated: %d", len(df))
        logger.info("Mean MAE: %.3f (+/-%.3f)", df["mae"].mean(), df["mae"].std())
        logger.info("Mean Spearman: %.3f", df["spearman_corr"].mean())
        logger.info("Winner correct: %d/%d (%.1f%%)",
                    df["correct_winner"].sum(), len(df),
                    df["correct_winner"].mean() * 100)
        logger.info("Mean podium overlap: %.1f%%", df["podium_overlap"].mean() * 100)
        logger.info("Confidence coverage (25-75%%): %.1f%%",
                    df["confidence_coverage"].mean() * 100)

        # Brier scores
        for label in ["win", "podium", "points", "dnf"]:
            col = f"brier_{label}"
            if col in df.columns:
                valid = df[col].dropna()
                if not valid.empty:
                    logger.info("Brier (%s): %.4f", label, valid.mean())

        # Per-season breakdown
        for season, sdf in df.groupby("season"):
            logger.info(
                "  %d: MAE=%.3f, Winner=%.0f%%, Podium=%.0f%%, Spearman=%.3f, Coverage=%.0f%%",
                season, sdf["mae"].mean(),
                sdf["correct_winner"].mean() * 100,
                sdf["podium_overlap"].mean() * 100,
                sdf["spearman_corr"].mean(),
                sdf["confidence_coverage"].mean() * 100,
            )

        # Wet vs dry accuracy (if weather data present)
        if "is_wet" in df.columns:
            for label, wet_val in [("Dry", 0), ("Wet", 1)]:
                subset = df[df["is_wet"] == wet_val]
                if not subset.empty:
                    logger.info(
                        "  %s races (%d): MAE=%.3f, Spearman=%.3f",
                        label, len(subset),
                        subset["mae"].mean(), subset["spearman_corr"].mean(),
                    )
            df["wet_accuracy"] = df.apply(
                lambda r: r["mae"] if r.get("is_wet") == 1 else np.nan, axis=1,
            )
            df["dry_accuracy"] = df.apply(
                lambda r: r["mae"] if r.get("is_wet") == 0 else np.nan, axis=1,
            )

        # Per-constructor MAE breakdown (from driver-level predictions)
        if all_driver_predictions:
            dpred_df = pd.DataFrame(all_driver_predictions)
            if "constructor_id" in dpred_df.columns:
                dpred_df["abs_error"] = (
                    dpred_df["predicted_position"] - dpred_df["actual_position"]
                ).abs()
                constructor_mae = (
                    dpred_df.groupby("constructor_id")["abs_error"]
                    .agg(["mean", "count"])
                    .rename(columns={"mean": "mae", "count": "n_entries"})
                    .sort_values("mae")
                )
                logger.info("\n  Per-constructor MAE:")
                for cid, row in constructor_mae.iterrows():
                    logger.info("    %-20s MAE=%.3f (n=%d)", cid[:20], row["mae"], int(row["n_entries"]))

    # Attach driver-level predictions as an attribute for downstream consumers
    if all_driver_predictions:
        df.attrs["driver_predictions"] = pd.DataFrame(all_driver_predictions)

    return df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Walk-forward backtest")
    parser.add_argument("--season", type=int, nargs="+", default=[2025])
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    fm = pd.read_parquet(DATA_DIR / "feature_matrix.parquet")

    results = walk_forward_backtest(fm, test_seasons=args.season)

    if not results.empty:
        results.to_csv(DATA_DIR / "backtest_results.csv", index=False)
        print(f"\nResults saved to {DATA_DIR / 'backtest_results.csv'}")

        # Save driver-level predictions if available
        if "driver_predictions" in results.attrs:
            dpred = results.attrs["driver_predictions"]
            dpred.to_csv(DATA_DIR / "backtest_driver_predictions.csv", index=False)
            print(f"Driver predictions saved to {DATA_DIR / 'backtest_driver_predictions.csv'}")
