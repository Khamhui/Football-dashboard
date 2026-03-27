"""
Value Detection — compares model predictions against bookmaker odds.

Identifies situations where the model assigns a higher probability than the
market (positive edge), computes fractional Kelly stakes, and tracks
cumulative performance (P&L, ROI, Brier score).

Usage:
    python -m data.models.value --season 2026 --round 3
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent.parent / "cache" / "models"


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


class CLVTracker:
    """
    Closing Line Value tracker — the gold standard metric for betting edge.

    CLV measures whether you consistently get prices better than the closing
    line. If you do, you have an edge — even if short-term P&L is negative.

    Pinnacle closing lines show r²=0.997 correlation with outcomes across
    ~400k matches. Beating the closing line is the single most reliable
    indicator of long-term profitability.
    """

    def __init__(self):
        self.records: List[Dict] = []

    def add_bet(
        self,
        race_id: str,
        driver_id: str,
        model_prob: float,
        opening_prob: float,
        closing_prob: float,
        actual_outcome: int,
    ):
        """
        Record a bet with opening and closing market probabilities.

        Args:
            race_id: Unique race identifier (e.g. "2026_R03")
            driver_id: Driver identifier
            model_prob: Model's predicted probability at time of bet
            opening_prob: Market-implied probability when bet was placed
            closing_prob: Market-implied probability at race start (closing line)
            actual_outcome: 1 if the outcome occurred, 0 otherwise
        """
        self.records.append({
            "race_id": race_id,
            "driver_id": driver_id,
            "model_prob": model_prob,
            "opening_prob": opening_prob,
            "closing_prob": closing_prob,
            "actual_outcome": actual_outcome,
        })

    def compute_clv(self) -> pd.DataFrame:
        """
        Compute per-bet CLV metrics.

        Returns:
            DataFrame with columns: race_id, driver_id, model_prob,
            opening_prob, closing_prob, actual_outcome, clv, clv_pct,
            closing_moved_toward_model, cumulative_clv
        """
        if not self.records:
            return pd.DataFrame()

        df = pd.DataFrame(self.records)

        # CLV: how much value did we capture vs the closing line?
        # Positive = we got a better price than closing
        # clv = closing_prob - opening_prob (in probability space)
        # If closing moved toward our model, we captured line movement
        df["clv"] = df["closing_prob"] - df["opening_prob"]

        # CLV as percentage of opening probability
        df["clv_pct"] = np.where(
            df["opening_prob"] > 0,
            df["clv"] / df["opening_prob"],
            0.0,
        )

        # Did the closing line move toward our model's estimate?
        df["closing_moved_toward_model"] = (
            (df["closing_prob"] - df["opening_prob"])
            * np.sign(df["model_prob"] - df["opening_prob"])
        ) > 0

        # Cumulative CLV over time
        df["cumulative_clv"] = df["clv"].cumsum()

        return df

    def summary(self) -> Dict:
        """
        Return summary CLV metrics.

        Returns:
            Dict with avg_clv, median_clv, clv_hit_rate,
            brier_model, brier_closing, brier_advantage,
            edge_persistence (first vs second half comparison)
        """
        if not self.records:
            return {"n_bets": 0}

        df = self.compute_clv()
        n = len(df)

        # Brier scores: model vs closing line
        model_brier = brier_score(
            df["model_prob"].values, df["actual_outcome"].values
        )
        closing_brier = brier_score(
            df["closing_prob"].values, df["actual_outcome"].values
        )

        # Edge persistence: compare CLV hit rate in first half vs second half
        mid = n // 2
        first_half = df.iloc[:mid]
        second_half = df.iloc[mid:]
        first_hit = first_half["closing_moved_toward_model"].mean() if len(first_half) > 0 else 0.0
        second_hit = second_half["closing_moved_toward_model"].mean() if len(second_half) > 0 else 0.0

        return {
            "n_bets": n,
            "avg_clv": float(df["clv"].mean()),
            "median_clv": float(df["clv"].median()),
            "avg_clv_pct": float(df["clv_pct"].mean()),
            "clv_hit_rate": float(df["closing_moved_toward_model"].mean()),
            "brier_model": round(model_brier, 6),
            "brier_closing": round(closing_brier, 6),
            "brier_advantage": round(closing_brier - model_brier, 6),
            "edge_persistence": {
                "first_half_hit_rate": round(first_hit, 4),
                "second_half_hit_rate": round(second_hit, 4),
                "persistent": abs(first_hit - second_hit) < 0.15,
            },
        }

    def save(self, path: Optional[Path] = None):
        """Persist CLV history to JSON."""
        path = path or MODEL_DIR / "clv_history.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.records, f, indent=2)
        logger.info("CLV history saved to %s (%d records)", path, len(self.records))

    def load(self, path: Optional[Path] = None):
        """Load CLV history from JSON."""
        path = path or MODEL_DIR / "clv_history.json"
        if not path.exists():
            logger.warning("No CLV history found at %s", path)
            return
        with open(path) as f:
            self.records = json.load(f)
        logger.info("CLV history loaded: %d records", len(self.records))


def _raw_kelly(model_prob: float, market_prob: float) -> float:
    """
    Core Kelly criterion: f* = (bp - q) / b.

    Returns raw (full) Kelly fraction, or 0.0 if no edge.
    Caller is responsible for applying fractional scaling.
    """
    if market_prob <= 0 or market_prob >= 1 or model_prob <= 0:
        return 0.0
    b = (1.0 / market_prob) - 1.0  # net odds (profit per unit staked)
    if b <= 0:
        return 0.0
    kelly = (b * model_prob - (1.0 - model_prob)) / b
    return max(kelly, 0.0)


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
        merged["fair_odds"] = np.where(
            merged["model_win_pct"] > 0,
            np.round(1.0 / merged["model_win_pct"], 2),
            np.inf,
        )
        merged["market_odds"] = np.where(
            merged["market_win_pct"] > 0,
            np.round(1.0 / merged["market_win_pct"], 2),
            np.inf,
        )

        # Kelly fraction for each row (vectorized)
        model_p = merged["model_win_pct"].values
        market_p = merged["market_win_pct"].values
        decimal_odds = np.where(market_p > 0, 1.0 / market_p, 0.0)
        b = decimal_odds - 1.0
        kelly_full = np.where(b > 0, (b * model_p - (1.0 - model_p)) / b, 0.0)
        kelly_full = np.maximum(kelly_full, 0.0)
        merged["kelly_fraction"] = np.round(kelly_full * 0.25, 4)

        # Value rating: edge relative to market probability (how mispriced)
        merged["value_rating"] = np.where(
            merged["market_win_pct"] > 0,
            np.round(merged["edge"] / merged["market_win_pct"], 3),
            0.0,
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
        kelly = _raw_kelly(model_prob, market_prob)
        if kelly <= 0:
            return 0.0
        return round(kelly * fraction, 4)

    @staticmethod
    def fractional_kelly_with_uncertainty(
        prob_lower: float,
        prob_upper: float,
        market_prob: float,
        fraction: float = 0.25,
    ) -> float:
        """
        Kelly criterion using Venn-ABERS prediction intervals.

        Standard Kelly assumes exact probability estimates, which leads to
        overbetting when estimates are uncertain. This version uses the
        conservative (lower) bound from Venn-ABERS, plus a confidence
        penalty based on interval width.

        Args:
            prob_lower: Lower bound of Venn-ABERS interval
            prob_upper: Upper bound of Venn-ABERS interval
            market_prob: Market-implied probability
            fraction: Base Kelly fraction (default 0.25 = quarter Kelly)

        Returns:
            Recommended stake as fraction of bankroll (0 if no edge)
        """
        kelly = _raw_kelly(prob_lower, market_prob)
        if kelly <= 0:
            return 0.0

        # Confidence penalty: wider interval = less confident = smaller stake
        # Interval width of 0 = full fraction, width of 0.5+ = near-zero stake
        interval_width = max(0.0, prob_upper - prob_lower)
        confidence = max(0.0, 1.0 - 2.0 * interval_width)

        return round(kelly * fraction * confidence, 4)

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


CACHE_DIR = Path(__file__).parent.parent / "cache" / "processed"


def evaluate_season_clv(season: int) -> dict:
    """
    Load all predictions, odds, and results for a season.
    Compute CLV metrics for each race where all three are available.

    Returns comprehensive CLV report with per-race and aggregate metrics.
    """
    # 1. Find prediction CSVs
    pred_files = sorted(CACHE_DIR.glob(f"prediction_{season}_R*.csv"))
    if not pred_files:
        logger.warning("No prediction files found for season %d", season)
        return {"season": season, "error": "no_predictions", "races": []}

    # 2. Find odds parquets
    odds_files = sorted(CACHE_DIR.glob(f"odds_{season}_R*.parquet"))
    odds_by_round: Dict[int, pd.DataFrame] = {}
    for f in odds_files:
        # Extract round number from filename: odds_2026_R03.parquet
        rnd = int(f.stem.split("_R")[1])
        odds_by_round[rnd] = pd.read_parquet(f)

    # 3. Load race results
    rr_path = CACHE_DIR / "race_results.parquet"
    if not rr_path.exists():
        logger.warning("race_results.parquet not found")
        return {"season": season, "error": "no_results", "races": []}

    rr = pd.read_parquet(rr_path)
    season_results = rr[(rr["season"] == season) & rr["position"].notna()]

    # Build winner lookup: round -> driver_id
    winners: Dict[int, str] = {}
    for rnd, group in season_results.groupby("round"):
        top = group[group["position"] == group["position"].min()]
        if not top.empty:
            winners[int(rnd)] = top.iloc[0]["driver_id"]

    # 4. For each race with all three, compute CLV
    from data.ingest.odds import OddsClient

    tracker = CLVTracker()
    per_race = []
    races_used = 0

    for pred_file in pred_files:
        rnd = int(pred_file.stem.split("_R")[1].replace(".csv", ""))
        race_id = f"{season}_R{rnd:02d}"

        if rnd not in odds_by_round:
            continue
        if rnd not in winners:
            continue

        preds = pd.read_csv(pred_file)
        odds_df = odds_by_round[rnd]

        # Get consensus market probabilities
        consensus = OddsClient.consensus_odds(odds_df)
        if consensus.empty:
            continue

        winner_id = winners[rnd]
        races_used += 1

        # Merge prediction probs with market probs
        prob_col = "sim_win_pct" if "sim_win_pct" in preds.columns else "prob_winner"
        if prob_col not in preds.columns:
            continue

        for _, row in preds.iterrows():
            driver_id = row.get("driver_id")
            model_prob = row.get(prob_col, 0)
            if prob_col == "sim_win_pct":
                model_prob = model_prob / 100.0  # convert percentage to proportion

            market_row = consensus[consensus["driver_id"] == driver_id]
            if market_row.empty:
                continue

            market_prob = float(market_row.iloc[0]["market_win_pct"])
            actual = 1 if driver_id == winner_id else 0

            # Use market prob as both opening and closing (single snapshot)
            tracker.add_bet(
                race_id=race_id,
                driver_id=driver_id,
                model_prob=model_prob,
                opening_prob=market_prob,
                closing_prob=market_prob,
                actual_outcome=actual,
            )

        # Per-race Brier comparison
        race_preds_merged = preds.merge(
            consensus[["driver_id", "market_win_pct"]], on="driver_id", how="inner"
        )
        if not race_preds_merged.empty and prob_col in race_preds_merged.columns:
            model_probs = race_preds_merged[prob_col].values
            if prob_col == "sim_win_pct":
                model_probs = model_probs / 100.0
            market_probs = race_preds_merged["market_win_pct"].values
            outcomes = np.array([
                1.0 if d == winner_id else 0.0
                for d in race_preds_merged["driver_id"]
            ])
            per_race.append({
                "race_id": race_id,
                "round": rnd,
                "winner": winner_id,
                "n_drivers": len(race_preds_merged),
                "brier_model": round(brier_score(model_probs, outcomes), 6),
                "brier_market": round(brier_score(market_probs, outcomes), 6),
            })

    # 5. Aggregate
    summary = tracker.summary()
    summary["season"] = season
    summary["races_evaluated"] = races_used
    summary["per_race"] = per_race

    if per_race:
        avg_model_brier = np.mean([r["brier_model"] for r in per_race])
        avg_market_brier = np.mean([r["brier_market"] for r in per_race])
        summary["avg_race_brier_model"] = round(avg_model_brier, 6)
        summary["avg_race_brier_market"] = round(avg_market_brier, 6)
        summary["avg_race_brier_advantage"] = round(avg_market_brier - avg_model_brier, 6)

    return summary


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
