"""
Value Detection — compares model predictions against bookmaker odds.

Identifies situations where the model assigns a higher probability than the
market (positive edge), computes fractional Kelly stakes, and tracks
cumulative performance (P&L, ROI, Brier score).

Usage:
    python -m data.models.value --season 2026 --round 3
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def brier_score(predicted_probs: np.ndarray, actual_outcomes: np.ndarray) -> float:
    """
    Compute the Brier score (mean squared error of probability forecasts).

    Lower is better. Perfect = 0.0, random baseline for 20-driver field ~ 0.095.

    Args:
        predicted_probs: Array of predicted probabilities (one per driver)
        actual_outcomes: Binary array — 1 for the winner, 0 for everyone else

    Returns:
        Brier score (float)
    """
    predicted_probs = np.asarray(predicted_probs, dtype=float)
    actual_outcomes = np.asarray(actual_outcomes, dtype=float)

    if len(predicted_probs) != len(actual_outcomes):
        raise ValueError("predicted_probs and actual_outcomes must have the same length")

    return float(np.mean((predicted_probs - actual_outcomes) ** 2))


class ValueDetector:
    """Detects value bets by comparing model probabilities to market odds."""

    def __init__(self, min_edge: float = 0.05, min_prob: float = 0.02):
        """
        Args:
            min_edge: Minimum probability advantage to flag a value bet
                      (e.g. 0.05 = model must be at least 5pp above market)
            min_prob: Minimum model probability to consider a driver
                      (filters out extreme longshots where estimates are noisy)
        """
        self.min_edge = min_edge
        self.min_prob = min_prob

    def find_value(
        self,
        model_probs: pd.DataFrame,
        market_probs: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Compare model win probabilities against market consensus.

        Args:
            model_probs: DataFrame with columns: driver_id, model_win_pct
                         (model_win_pct as a proportion, 0-1)
            market_probs: DataFrame with columns: driver_id, market_win_pct
                          (market_win_pct as a proportion, 0-1)

        Returns:
            DataFrame sorted by edge (descending) with columns:
                driver_id, model_win_pct, market_win_pct, edge,
                kelly_fraction, fair_odds, market_odds, value_rating
        """
        merged = pd.merge(model_probs, market_probs, on="driver_id", how="inner")

        if merged.empty:
            logger.warning("No overlapping drivers between model and market")
            return pd.DataFrame(columns=[
                "driver_id", "model_win_pct", "market_win_pct", "edge",
                "kelly_fraction", "fair_odds", "market_odds", "value_rating",
            ])

        merged["edge"] = merged["model_win_pct"] - merged["market_win_pct"]

        # Fair odds (from model) and market odds
        merged["fair_odds"] = merged["model_win_pct"].apply(
            lambda p: round(1.0 / p, 2) if p > 0 else float("inf")
        )
        merged["market_odds"] = merged["market_win_pct"].apply(
            lambda p: round(1.0 / p, 2) if p > 0 else float("inf")
        )

        # Kelly fraction for each row
        merged["kelly_fraction"] = merged.apply(
            lambda r: self.kelly_fraction(r["model_win_pct"], r["market_win_pct"]),
            axis=1,
        )

        # Value rating: edge relative to market probability (how mispriced)
        merged["value_rating"] = merged.apply(
            lambda r: round(r["edge"] / r["market_win_pct"], 3) if r["market_win_pct"] > 0 else 0.0,
            axis=1,
        )

        # Filter to actionable values
        value = merged[
            (merged["edge"] >= self.min_edge)
            & (merged["model_win_pct"] >= self.min_prob)
        ].copy()

        col_order = [
            "driver_id", "model_win_pct", "market_win_pct", "edge",
            "kelly_fraction", "fair_odds", "market_odds", "value_rating",
        ]
        available = [c for c in col_order if c in value.columns]

        return value[available].sort_values("edge", ascending=False).reset_index(drop=True)

    @staticmethod
    def kelly_fraction(
        model_prob: float,
        market_prob: float,
        fraction: float = 0.25,
    ) -> float:
        """
        Fractional Kelly criterion — optimal stake sizing.

        Full Kelly is bankroll-optimal but volatile. Fractional (default 25%)
        reduces variance at the cost of slower growth.

        Args:
            model_prob: Our estimated probability of winning
            market_prob: Market-implied probability (1 / decimal_odds)
            fraction: Kelly fraction (0.25 = quarter Kelly)

        Returns:
            Recommended stake as a fraction of bankroll (0 if no edge)
        """
        if market_prob <= 0 or market_prob >= 1 or model_prob <= 0:
            return 0.0

        decimal_odds = 1.0 / market_prob
        b = decimal_odds - 1.0  # net odds (profit per unit staked)

        if b <= 0:
            return 0.0

        # Kelly formula: f* = (bp - q) / b  where p = model_prob, q = 1 - p
        kelly = (b * model_prob - (1.0 - model_prob)) / b

        if kelly <= 0:
            return 0.0

        return round(kelly * fraction, 4)

    def track_performance(
        self,
        predictions: List[Dict],
        results: List[Dict],
    ) -> Dict:
        """
        Track cumulative performance of value betting strategy.

        Args:
            predictions: List of dicts, each with:
                - race_id (str): unique race identifier (e.g. "2026_R03")
                - driver_id (str)
                - model_win_pct (float): model probability
                - market_win_pct (float): market probability
                - stake (float): fraction of bankroll wagered
            results: List of dicts, each with:
                - race_id (str)
                - winner_id (str): driver_id of the actual winner

        Returns:
            Dict with:
                - total_staked (float)
                - total_return (float)
                - pnl (float)
                - roi (float): return on investment as a proportion
                - n_bets (int)
                - n_wins (int)
                - strike_rate (float)
                - brier_model (float): Brier score of model predictions
                - brier_market (float): Brier score of market probabilities
                - brier_advantage (float): market - model (positive = model better)
        """
        # Build lookup: race_id -> winner_id
        winner_lookup: Dict[str, str] = {r["race_id"]: r["winner_id"] for r in results}

        total_staked = 0.0
        total_return = 0.0
        n_bets = 0
        n_wins = 0

        # Collect arrays for Brier score (per race)
        race_model_probs: Dict[str, List[float]] = {}
        race_market_probs: Dict[str, List[float]] = {}
        race_outcomes: Dict[str, List[float]] = {}

        for pred in predictions:
            race_id = pred["race_id"]
            driver_id = pred["driver_id"]
            model_p = pred["model_win_pct"]
            market_p = pred["market_win_pct"]
            stake = pred.get("stake", 0.0)

            winner_id = winner_lookup.get(race_id)
            if winner_id is None:
                continue

            won = driver_id == winner_id
            actual = 1.0 if won else 0.0

            # Accumulate for Brier
            race_model_probs.setdefault(race_id, []).append(model_p)
            race_market_probs.setdefault(race_id, []).append(market_p)
            race_outcomes.setdefault(race_id, []).append(actual)

            if stake > 0:
                decimal_odds = 1.0 / market_p if market_p > 0 else 0.0
                n_bets += 1
                total_staked += stake

                if won:
                    n_wins += 1
                    total_return += stake * decimal_odds
                # else: stake is lost (return = 0)

        pnl = total_return - total_staked
        roi = pnl / total_staked if total_staked > 0 else 0.0

        # Aggregate Brier scores across all races
        all_model_p = []
        all_market_p = []
        all_outcomes = []
        for race_id in race_model_probs:
            all_model_p.extend(race_model_probs[race_id])
            all_market_p.extend(race_market_probs[race_id])
            all_outcomes.extend(race_outcomes[race_id])

        brier_model = brier_score(np.array(all_model_p), np.array(all_outcomes)) if all_model_p else 0.0
        brier_market = brier_score(np.array(all_market_p), np.array(all_outcomes)) if all_market_p else 0.0

        return {
            "total_staked": round(total_staked, 4),
            "total_return": round(total_return, 4),
            "pnl": round(pnl, 4),
            "roi": round(roi, 4),
            "n_bets": n_bets,
            "n_wins": n_wins,
            "strike_rate": round(n_wins / n_bets, 4) if n_bets > 0 else 0.0,
            "brier_model": round(brier_model, 6),
            "brier_market": round(brier_market, 6),
            "brier_advantage": round(brier_market - brier_model, 6),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Demo: synthetic model vs market comparison
    drivers = [
        "max_verstappen", "norris", "leclerc", "piastri", "hamilton",
        "russell", "sainz", "alonso", "gasly", "hulkenberg",
    ]

    model = pd.DataFrame({
        "driver_id": drivers,
        "model_win_pct": [0.35, 0.22, 0.15, 0.10, 0.06, 0.04, 0.03, 0.02, 0.02, 0.01],
    })

    market = pd.DataFrame({
        "driver_id": drivers,
        "market_win_pct": [0.30, 0.20, 0.18, 0.12, 0.07, 0.05, 0.03, 0.02, 0.02, 0.01],
    })

    detector = ValueDetector(min_edge=0.02, min_prob=0.02)
    value_bets = detector.find_value(model, market)

    if not value_bets.empty:
        print("Value bets found:")
        print(value_bets.to_string(index=False))
    else:
        print("No value bets found with current thresholds.")

    # Brier score demo
    predicted = np.array([0.35, 0.22, 0.15, 0.10, 0.06, 0.04, 0.03, 0.02, 0.02, 0.01])
    actual = np.array([1, 0, 0, 0, 0, 0, 0, 0, 0, 0])  # Verstappen won
    print(f"\nBrier score (model): {brier_score(predicted, actual):.4f}")
    print(f"Brier score (uniform 10-driver): {brier_score(np.full(10, 0.1), actual):.4f}")
