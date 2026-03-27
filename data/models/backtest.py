"""
Walk-forward betting backtest for F1 predictions.

For each race in the test period:
1. Train model on all prior races (no data leakage)
2. Generate calibrated probability predictions
3. Compare to simulated market odds (or real cached odds)
4. Apply fractional Kelly criterion to size bets
5. Track P&L, CLV, Brier scores, ROI, drawdown, Sharpe

This answers: "Would this model have made money historically?"

Usage:
    python -m data.models.backtest                                # Default 2024-2025
    python -m data.models.backtest --start 2024 --end 2025        # Explicit range
    python -m data.models.backtest --bankroll 1000 --kelly 0.25   # Custom sizing
    python -m data.models.backtest --markets winner podium        # Specific markets
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import mean_absolute_error

from data.models.value import (
    CLVTracker,
    ValueDetector,
    _raw_kelly,
    brier_score,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "cache" / "processed"
CACHE_DIR = Path(__file__).parent.parent / "cache"

# Markets supported by the backtest
SUPPORTED_MARKETS = ("winner", "podium", "points", "dnf")


@dataclass
class Bet:
    """Single bet record."""

    race_id: str
    season: int
    round: int
    circuit_id: str
    market: str
    driver_id: str
    model_prob: float
    market_prob: float
    kelly_stake_frac: float
    stake_amount: float
    decimal_odds: float
    won: bool
    payout: float
    pnl: float
    bankroll_after: float
    prob_lo: Optional[float] = None
    prob_hi: Optional[float] = None


@dataclass
class RaceResult:
    """Per-race aggregated result."""

    race_id: str
    season: int
    round: int
    circuit_id: str
    n_drivers: int
    n_bets: int
    race_pnl: float
    bankroll_after: float
    mae: float
    spearman_corr: float
    correct_winner: bool
    podium_overlap: float
    brier_win: Optional[float] = None
    brier_podium: Optional[float] = None
    brier_points: Optional[float] = None
    brier_dnf: Optional[float] = None
    flat_bet_pnl: float = 0.0


class BettingBacktest:
    """
    Walk-forward backtest for the F1 betting strategy.

    For each race from start_season to end_season:
    1. Train model on all data up to (but not including) this race
    2. Generate predictions
    3. Compare to simulated market odds (or real odds if cached)
    4. Apply Kelly criterion to size bets
    5. Track P&L, CLV, Brier scores, ROI

    This answers: "Would this model have made money historically?"
    """

    def __init__(
        self,
        bankroll: float = 1000.0,
        kelly_fraction: float = 0.25,
        min_edge: float = 0.05,
        min_prob: float = 0.02,
        flat_bet_unit: float = 10.0,
        market_noise_std: float = 0.04,
    ):
        """
        Args:
            bankroll: Starting bankroll
            kelly_fraction: Fraction of full Kelly to use (0.25 = quarter Kelly)
            min_edge: Minimum edge (model_prob - market_prob) to place a bet
            min_prob: Minimum model probability to consider
            flat_bet_unit: Fixed stake for flat-bet comparison track
            market_noise_std: Std dev of noise added to model probs to simulate market
        """
        self.bankroll = bankroll
        self.initial_bankroll = bankroll
        self.kelly_fraction = kelly_fraction
        self.min_edge = min_edge
        self.min_prob = min_prob
        self.flat_bet_unit = flat_bet_unit
        self.market_noise_std = market_noise_std

        self.bet_history: list[Bet] = []
        self.race_history: list[RaceResult] = []
        self.bankroll_curve: list[float] = [bankroll]
        self.clv_tracker = CLVTracker()

        # Flat-bet tracking (same bets, fixed stake)
        self._flat_bankroll = bankroll
        self._flat_curve: list[float] = [bankroll]

    def run(
        self,
        feature_matrix: pd.DataFrame,
        start_season: int = 2024,
        end_season: int = 2025,
        markets: list[str] | None = None,
        min_train_races: int = 100,
    ) -> dict:
        """
        Run the full walk-forward backtest.

        Args:
            feature_matrix: Full feature matrix with season, round, driver_id, etc.
            start_season: First season to test on
            end_season: Last season to test on
            markets: Which markets to bet on ("winner", "podium", "points", "dnf")
            min_train_races: Minimum number of training races before starting

        Returns:
            Comprehensive backtest results dict
        """
        from data.features.engineer import prepare_training_data
        from data.models.predictor import F1Predictor, create_model

        if markets is None:
            markets = ["winner", "podium"]

        for m in markets:
            if m not in SUPPORTED_MARKETS:
                raise ValueError(f"Unknown market '{m}'. Supported: {SUPPORTED_MARKETS}")

        test_seasons = list(range(start_season, end_season + 1))
        rng = np.random.RandomState(42)

        races = (
            feature_matrix[["season", "round", "circuit_id"]]
            .drop_duplicates()
            .sort_values(["season", "round"])
        )
        test_races = races[races["season"].isin(test_seasons)]

        has_constructor = "constructor_id" in feature_matrix.columns

        for _, race in test_races.iterrows():
            season = int(race["season"])
            rnd = int(race["round"])
            circuit_id = str(race["circuit_id"])
            race_id = f"{season}_R{rnd:02d}"

            # Training data: everything before this race
            train_mask = (
                (feature_matrix["season"] < season)
                | (
                    (feature_matrix["season"] == season)
                    & (feature_matrix["round"] < rnd)
                )
            )
            test_mask = (
                (feature_matrix["season"] == season)
                & (feature_matrix["round"] == rnd)
            )

            train_data = feature_matrix[train_mask]
            test_data = feature_matrix[test_mask]

            if len(train_data) < min_train_races * 15:
                continue

            try:
                X_train, y_train = prepare_training_data(train_data, target="position")
                X_test, y_test = prepare_training_data(test_data, target="position")
            except Exception as e:
                logger.warning("Skipping %s: %s", race_id, e)
                continue

            if X_test.empty or y_test.empty:
                continue

            # Align columns
            for col in set(X_train.columns) - set(X_test.columns):
                X_test[col] = 0
            for col in set(X_test.columns) - set(X_train.columns):
                X_train[col] = 0
            X_test = X_test[X_train.columns]

            # Train full predictor (classifiers for probabilities)
            predictor = F1Predictor()
            train_dnf = train_data.reindex(X_train.index).get(
                "dnf", pd.Series(dtype=float)
            )
            train_dnf = train_dnf.fillna(0).astype(int)

            try:
                predictor.train(X_train, y_train, y_dnf=train_dnf)
            except Exception as e:
                logger.warning("Training failed for %s: %s", race_id, e)
                continue

            # Generate predictions
            predictions = predictor.predict_race(X_test)

            # Attach actuals
            predictions["actual_position"] = y_test
            test_dnf = test_data.reindex(X_test.index).get(
                "dnf", pd.Series(dtype=float)
            )
            predictions["actual_dnf"] = test_dnf.fillna(0).astype(int).values

            # Attach driver IDs from the original feature matrix
            driver_ids = test_data.reindex(X_test.index).get("driver_id")
            if driver_ids is not None:
                predictions["driver_id"] = driver_ids.values
            else:
                predictions["driver_id"] = [f"driver_{i}" for i in range(len(predictions))]

            # Build actual outcomes
            actual_winner_idx = y_test.idxmin()
            actual_top3_idx = set(y_test.nsmallest(3).index)
            actual_top10_idx = set(y_test.nsmallest(10).index)

            # Position metrics
            y_pred = predictions["predicted_position"].values
            mae = mean_absolute_error(y_test, y_pred)
            pred_ranks = pd.Series(y_pred, index=y_test.index).rank()
            actual_ranks = y_test.rank()
            spearman_corr, _ = spearmanr(actual_ranks, pred_ranks)
            pred_series = pd.Series(y_pred, index=y_test.index)
            correct_winner = pred_series.idxmin() == actual_winner_idx
            pred_top3 = set(pred_series.nsmallest(3).index)
            podium_overlap = len(pred_top3 & actual_top3_idx) / 3

            # Brier scores per market
            brier_win = None
            brier_podium = None
            brier_points = None
            brier_dnf = None

            y_win_actual = (y_test == 1).astype(int)
            y_podium_actual = (y_test <= 3).astype(int)
            y_points_actual = (y_test <= 10).astype(int)

            if "prob_winner" in predictions.columns:
                brier_win = brier_score(
                    predictions["prob_winner"].values, y_win_actual.values
                )
            if "prob_podium" in predictions.columns:
                brier_podium = brier_score(
                    predictions["prob_podium"].values, y_podium_actual.values
                )
            if "prob_points" in predictions.columns:
                brier_points = brier_score(
                    predictions["prob_points"].values, y_points_actual.values
                )
            if "prob_dnf" in predictions.columns:
                brier_dnf = brier_score(
                    predictions["prob_dnf"].values,
                    predictions["actual_dnf"].values,
                )

            # Simulate market odds (or load real ones)
            market_df = self._simulate_market_odds(
                predictions, season, rnd, rng, markets
            )

            # Place bets
            race_bets = []
            race_flat_pnl = 0.0

            for market in markets:
                prob_col = f"prob_{self._market_to_prob_col(market)}"
                if prob_col not in predictions.columns:
                    continue

                mkt_col = f"market_prob_{market}"
                if mkt_col not in market_df.columns:
                    continue

                merged = predictions.merge(
                    market_df[["driver_id", mkt_col]],
                    on="driver_id",
                    how="inner",
                )

                for _, row in merged.iterrows():
                    model_p = float(row[prob_col])
                    market_p = float(row[mkt_col])
                    driver_id = str(row["driver_id"])

                    if model_p < self.min_prob or market_p <= 0 or market_p >= 1:
                        continue

                    edge = model_p - market_p
                    if edge < self.min_edge:
                        continue

                    # Determine outcome
                    idx = row.name if hasattr(row, "name") else None
                    won = self._resolve_outcome(
                        market, driver_id, idx,
                        actual_winner_idx, actual_top3_idx,
                        actual_top10_idx, predictions,
                    )

                    # Kelly stake sizing
                    prob_lo = row.get(f"prob_{self._market_to_prob_col(market)}_lo")
                    prob_hi = row.get(f"prob_{self._market_to_prob_col(market)}_hi")

                    kelly_frac = self._apply_kelly(
                        model_p, market_p,
                        float(prob_lo) if pd.notna(prob_lo) else None,
                        float(prob_hi) if pd.notna(prob_hi) else None,
                    )

                    if kelly_frac <= 0:
                        continue

                    stake = kelly_frac * self.bankroll
                    # Cap at 5% of bankroll per bet for safety
                    stake = min(stake, 0.05 * self.bankroll)

                    if stake < 0.01:
                        continue

                    decimal_odds = 1.0 / market_p
                    payout = stake * decimal_odds if won else 0.0
                    bet_pnl = payout - stake

                    self.bankroll += bet_pnl

                    bet = Bet(
                        race_id=race_id,
                        season=season,
                        round=rnd,
                        circuit_id=circuit_id,
                        market=market,
                        driver_id=driver_id,
                        model_prob=model_p,
                        market_prob=market_p,
                        kelly_stake_frac=kelly_frac,
                        stake_amount=stake,
                        decimal_odds=decimal_odds,
                        won=won,
                        payout=payout,
                        pnl=bet_pnl,
                        bankroll_after=self.bankroll,
                        prob_lo=float(prob_lo) if pd.notna(prob_lo) else None,
                        prob_hi=float(prob_hi) if pd.notna(prob_hi) else None,
                    )
                    race_bets.append(bet)
                    self.bet_history.append(bet)

                    # Flat-bet tracking (same selection, fixed stake)
                    flat_payout = self.flat_bet_unit * decimal_odds if won else 0.0
                    flat_pnl = flat_payout - self.flat_bet_unit
                    self._flat_bankroll += flat_pnl
                    race_flat_pnl += flat_pnl

                    # CLV tracking (use market_p as both opening and closing
                    # since we don't have real line movement data)
                    self.clv_tracker.add_bet(
                        race_id=race_id,
                        driver_id=driver_id,
                        model_prob=model_p,
                        opening_prob=market_p,
                        closing_prob=market_p,
                        actual_outcome=1 if won else 0,
                    )

            self.bankroll_curve.append(self.bankroll)
            self._flat_curve.append(self._flat_bankroll)

            race_pnl = sum(b.pnl for b in race_bets)

            self.race_history.append(
                RaceResult(
                    race_id=race_id,
                    season=season,
                    round=rnd,
                    circuit_id=circuit_id,
                    n_drivers=len(y_test),
                    n_bets=len(race_bets),
                    race_pnl=race_pnl,
                    bankroll_after=self.bankroll,
                    mae=mae,
                    spearman_corr=spearman_corr,
                    correct_winner=correct_winner,
                    podium_overlap=podium_overlap,
                    brier_win=brier_win,
                    brier_podium=brier_podium,
                    brier_points=brier_points,
                    brier_dnf=brier_dnf,
                    flat_bet_pnl=race_flat_pnl,
                )
            )

            logger.info(
                "%s %-18s  bets=%d  pnl=%+.2f  bankroll=%.2f  MAE=%.2f  Winner=%s",
                race_id,
                circuit_id[:18],
                len(race_bets),
                race_pnl,
                self.bankroll,
                mae,
                "Y" if correct_winner else "N",
            )

            # Ruin check
            if self.bankroll <= 0:
                logger.warning("BANKROLL DEPLETED at %s — stopping backtest", race_id)
                break

        return self.summary()

    def _market_to_prob_col(self, market: str) -> str:
        """Map market name to the prediction column suffix."""
        return {"winner": "winner", "podium": "podium", "points": "points", "dnf": "dnf"}[market]

    def _resolve_outcome(
        self,
        market: str,
        driver_id: str,
        idx,
        actual_winner_idx,
        actual_top3_idx: set,
        actual_top10_idx: set,
        predictions: pd.DataFrame,
    ) -> bool:
        """Determine whether a bet won based on actual results."""
        if market == "winner":
            # Check by index position matching
            if idx is not None and idx == actual_winner_idx:
                return True
            # Fallback: check by driver_id
            winner_rows = predictions[predictions.index == actual_winner_idx]
            if not winner_rows.empty and "driver_id" in predictions.columns:
                return str(winner_rows.iloc[0].get("driver_id")) == driver_id
            return False

        elif market == "podium":
            if idx is not None and idx in actual_top3_idx:
                return True
            return False

        elif market == "points":
            if idx is not None and idx in actual_top10_idx:
                return True
            return False

        elif market == "dnf":
            if "actual_dnf" in predictions.columns and idx is not None:
                try:
                    return bool(predictions.loc[idx, "actual_dnf"] == 1)
                except KeyError:
                    return False
            return False

        return False

    def _simulate_market_odds(
        self,
        predictions: pd.DataFrame,
        season: int,
        rnd: int,
        rng: np.random.RandomState,
        markets: list[str],
    ) -> pd.DataFrame:
        """
        Generate simulated market odds for backtesting.

        Approach: Use the model's probabilities + random noise to simulate a market.
        The noise represents information the market has that the model doesn't.
        This gives a conservative backtest -- real edge would be larger if the model
        is genuinely better than the market.

        If real cached odds exist for this race, use those instead.
        """
        # Try loading real odds first
        real_odds = self._load_real_odds(season, rnd)
        if real_odds is not None:
            return real_odds

        # Simulate: model prob + noise + vig
        result = predictions[["driver_id"]].copy()

        for market in markets:
            prob_col = f"prob_{self._market_to_prob_col(market)}"
            if prob_col not in predictions.columns:
                continue

            model_probs = predictions[prob_col].values.copy()

            # Add noise (market disagreement) - scaled by probability level
            # Higher probabilities get less noise (favorites are better priced)
            noise_scale = self.market_noise_std * (1.0 - 0.5 * model_probs)
            noise = rng.normal(0, noise_scale, size=len(model_probs))
            market_probs = model_probs + noise

            # Clip to valid probability range
            market_probs = np.clip(market_probs, 0.005, 0.995)

            # Normalize winner/podium markets so probabilities sum to ~1 + vig
            if market in ("winner", "podium", "points"):
                vig = 1.05 + rng.uniform(0, 0.03)  # 5-8% overround
                total = market_probs.sum()
                if total > 0:
                    market_probs = market_probs * (vig / total)
                    # Re-clip after normalization
                    market_probs = np.clip(market_probs, 0.005, 0.995)

            result[f"market_prob_{market}"] = market_probs

        return result

    def _load_real_odds(self, season: int, rnd: int) -> Optional[pd.DataFrame]:
        """Try to load real cached odds for a specific race."""
        odds_path = DATA_DIR / f"odds_{season}_R{rnd:02d}.parquet"
        if not odds_path.exists():
            return None

        try:
            from data.ingest.odds import OddsClient

            odds_df = pd.read_parquet(odds_path)
            consensus = OddsClient.consensus_odds(odds_df)
            if consensus.empty:
                return None

            result = consensus[["driver_id", "market_win_pct"]].copy()
            result = result.rename(columns={"market_win_pct": "market_prob_winner"})
            return result
        except Exception as e:
            logger.debug("Could not load real odds for S%d R%02d: %s", season, rnd, e)
            return None

    def _apply_kelly(
        self,
        model_prob: float,
        market_prob: float,
        prob_lo: Optional[float] = None,
        prob_hi: Optional[float] = None,
    ) -> float:
        """
        Apply Kelly criterion with conservative adjustments.

        If Venn-ABERS intervals are available, uses the lower bound
        and applies a confidence penalty based on interval width.
        Otherwise uses standard fractional Kelly.
        """
        if prob_lo is not None and prob_hi is not None:
            return ValueDetector.fractional_kelly_with_uncertainty(
                prob_lower=prob_lo,
                prob_upper=prob_hi,
                market_prob=market_prob,
                fraction=self.kelly_fraction,
            )

        return ValueDetector.kelly_fraction(
            model_prob=model_prob,
            market_prob=market_prob,
            fraction=self.kelly_fraction,
        )

    def summary(self) -> dict:
        """Return comprehensive backtest summary."""
        if not self.bet_history:
            return {
                "total_pnl": 0.0,
                "roi_pct": 0.0,
                "bet_count": 0,
                "races_evaluated": len(self.race_history),
                "error": "no_bets_placed",
            }

        total_wagered = sum(b.stake_amount for b in self.bet_history)
        total_pnl = self.bankroll - self.initial_bankroll
        wins = sum(1 for b in self.bet_history if b.won)
        roi = total_pnl / total_wagered if total_wagered > 0 else 0.0

        # Max drawdown from bankroll curve
        curve = np.array(self.bankroll_curve)
        peak = np.maximum.accumulate(curve)
        drawdown = (peak - curve) / peak
        max_drawdown = float(drawdown.max())
        max_drawdown_idx = int(drawdown.argmax())

        # Sharpe ratio (annualized, using per-race returns)
        race_returns = []
        prev = self.initial_bankroll
        for br in self.bankroll_curve[1:]:
            ret = (br - prev) / prev if prev > 0 else 0.0
            race_returns.append(ret)
            prev = br

        race_returns = np.array(race_returns)
        if len(race_returns) > 1 and race_returns.std() > 0:
            # ~24 races per year
            sharpe = (race_returns.mean() / race_returns.std()) * np.sqrt(24)
        else:
            sharpe = 0.0

        # Per-market breakdown
        per_market = {}
        for market in SUPPORTED_MARKETS:
            market_bets = [b for b in self.bet_history if b.market == market]
            if not market_bets:
                continue
            m_wagered = sum(b.stake_amount for b in market_bets)
            m_pnl = sum(b.pnl for b in market_bets)
            m_wins = sum(1 for b in market_bets if b.won)
            per_market[market] = {
                "bet_count": len(market_bets),
                "win_count": m_wins,
                "win_rate": round(m_wins / len(market_bets), 4),
                "total_wagered": round(m_wagered, 2),
                "total_pnl": round(m_pnl, 2),
                "roi_pct": round(m_pnl / m_wagered * 100, 2) if m_wagered > 0 else 0.0,
                "avg_odds": round(
                    np.mean([b.decimal_odds for b in market_bets]), 2
                ),
                "avg_edge": round(
                    np.mean([b.model_prob - b.market_prob for b in market_bets]), 4
                ),
            }

        # Flat-bet comparison
        flat_pnl = self._flat_bankroll - self.initial_bankroll
        flat_wagered = len(self.bet_history) * self.flat_bet_unit
        flat_roi = flat_pnl / flat_wagered * 100 if flat_wagered > 0 else 0.0

        # Per-race results
        per_race = []
        for r in self.race_history:
            per_race.append({
                "race_id": r.race_id,
                "season": r.season,
                "round": r.round,
                "circuit_id": r.circuit_id,
                "n_drivers": r.n_drivers,
                "n_bets": r.n_bets,
                "race_pnl": round(r.race_pnl, 2),
                "bankroll_after": round(r.bankroll_after, 2),
                "mae": round(r.mae, 3),
                "spearman_corr": round(r.spearman_corr, 3),
                "correct_winner": r.correct_winner,
                "podium_overlap": round(r.podium_overlap, 3),
                "brier_win": round(r.brier_win, 6) if r.brier_win is not None else None,
                "brier_podium": round(r.brier_podium, 6) if r.brier_podium is not None else None,
                "flat_bet_pnl": round(r.flat_bet_pnl, 2),
            })

        # Brier scores (aggregate)
        brier_wins = [r.brier_win for r in self.race_history if r.brier_win is not None]
        brier_podiums = [r.brier_podium for r in self.race_history if r.brier_podium is not None]

        # CLV
        clv_summary = self.clv_tracker.summary()

        # Streak analysis
        current_streak = 0
        max_win_streak = 0
        max_loss_streak = 0
        streak_type = None
        for b in self.bet_history:
            if b.won:
                if streak_type == "win":
                    current_streak += 1
                else:
                    current_streak = 1
                    streak_type = "win"
                max_win_streak = max(max_win_streak, current_streak)
            else:
                if streak_type == "loss":
                    current_streak += 1
                else:
                    current_streak = 1
                    streak_type = "loss"
                max_loss_streak = max(max_loss_streak, current_streak)

        return {
            "total_pnl": round(total_pnl, 2),
            "roi_pct": round(roi * 100, 2),
            "total_wagered": round(total_wagered, 2),
            "final_bankroll": round(self.bankroll, 2),
            "initial_bankroll": self.initial_bankroll,
            "max_drawdown": round(max_drawdown, 4),
            "max_drawdown_pct": round(max_drawdown * 100, 2),
            "max_drawdown_race": self.race_history[max(0, max_drawdown_idx - 1)].race_id
            if self.race_history
            else None,
            "sharpe_ratio": round(sharpe, 3),
            "bet_count": len(self.bet_history),
            "win_count": wins,
            "win_rate": round(wins / len(self.bet_history), 4),
            "avg_stake": round(total_wagered / len(self.bet_history), 2),
            "avg_odds": round(
                np.mean([b.decimal_odds for b in self.bet_history]), 2
            ),
            "avg_edge": round(
                np.mean([b.model_prob - b.market_prob for b in self.bet_history]),
                4,
            ),
            "races_evaluated": len(self.race_history),
            "races_with_bets": sum(1 for r in self.race_history if r.n_bets > 0),
            "brier_win_avg": round(np.mean(brier_wins), 6) if brier_wins else None,
            "brier_podium_avg": round(np.mean(brier_podiums), 6) if brier_podiums else None,
            "clv_summary": clv_summary,
            "per_market": per_market,
            "per_race": per_race,
            "bankroll_curve": [round(b, 2) for b in self.bankroll_curve],
            "flat_bet_comparison": {
                "flat_pnl": round(flat_pnl, 2),
                "flat_roi_pct": round(flat_roi, 2),
                "flat_final_bankroll": round(self._flat_bankroll, 2),
                "kelly_pnl": round(total_pnl, 2),
                "kelly_roi_pct": round(roi * 100, 2),
                "kelly_advantage": round((roi * 100) - flat_roi, 2),
            },
            "flat_bankroll_curve": [round(b, 2) for b in self._flat_curve],
            "streaks": {
                "max_win_streak": max_win_streak,
                "max_loss_streak": max_loss_streak,
            },
            "prediction_quality": {
                "avg_mae": round(
                    np.mean([r.mae for r in self.race_history]), 3
                ),
                "avg_spearman": round(
                    np.mean([r.spearman_corr for r in self.race_history]), 3
                ),
                "winner_hit_rate": round(
                    np.mean([r.correct_winner for r in self.race_history]), 3
                ),
                "avg_podium_overlap": round(
                    np.mean([r.podium_overlap for r in self.race_history]), 3
                ),
            },
        }

    def print_report(self):
        """Print a formatted backtest report to stdout."""
        s = self.summary()

        if s.get("error"):
            print(f"\nBacktest completed with no bets placed ({s['error']}).")
            print(f"Races evaluated: {s['races_evaluated']}")
            return

        print()
        print("=" * 72)
        print("  F1 BETTING BACKTEST REPORT")
        print("=" * 72)

        # Overview
        print(f"\n  Races evaluated:   {s['races_evaluated']}")
        print(f"  Races with bets:   {s['races_with_bets']}")
        print(f"  Total bets:        {s['bet_count']}")
        print(f"  Win rate:          {s['win_rate']:.1%}")

        # P&L
        print(f"\n--- P&L ---")
        print(f"  Initial bankroll:  ${s['initial_bankroll']:,.2f}")
        print(f"  Final bankroll:    ${s['final_bankroll']:,.2f}")
        pnl_sign = "+" if s["total_pnl"] >= 0 else ""
        print(f"  Total P&L:         {pnl_sign}${s['total_pnl']:,.2f}")
        print(f"  Total wagered:     ${s['total_wagered']:,.2f}")
        print(f"  ROI:               {pnl_sign}{s['roi_pct']:.2f}%")

        # Risk
        print(f"\n--- Risk ---")
        print(f"  Max drawdown:      {s['max_drawdown_pct']:.1f}%")
        if s["max_drawdown_race"]:
            print(f"  Max DD at:         {s['max_drawdown_race']}")
        print(f"  Sharpe ratio:      {s['sharpe_ratio']:.3f}")
        print(f"  Max win streak:    {s['streaks']['max_win_streak']}")
        print(f"  Max loss streak:   {s['streaks']['max_loss_streak']}")

        # Betting
        print(f"\n--- Betting ---")
        print(f"  Avg stake:         ${s['avg_stake']:,.2f}")
        print(f"  Avg odds:          {s['avg_odds']:.2f}")
        print(f"  Avg edge:          {s['avg_edge']:.1%}")

        # Per-market breakdown
        if s["per_market"]:
            print(f"\n--- Per Market ---")
            header = f"  {'Market':<10} {'Bets':>5} {'Wins':>5} {'Rate':>6} {'P&L':>10} {'ROI':>8}"
            print(header)
            print(f"  {'-' * 10} {'-' * 5} {'-' * 5} {'-' * 6} {'-' * 10} {'-' * 8}")
            for market, data in s["per_market"].items():
                pnl_str = f"{'+'if data['total_pnl'] >= 0 else ''}{data['total_pnl']:,.2f}"
                print(
                    f"  {market:<10} {data['bet_count']:>5} {data['win_count']:>5} "
                    f"{data['win_rate']:>5.1%} {pnl_str:>10} {data['roi_pct']:>7.1f}%"
                )

        # Kelly vs Flat comparison
        flat = s["flat_bet_comparison"]
        print(f"\n--- Kelly vs Flat Bet ---")
        print(f"  {'':16} {'Kelly':>12} {'Flat':>12} {'Diff':>12}")
        print(f"  {'-' * 16} {'-' * 12} {'-' * 12} {'-' * 12}")
        k_pnl = f"{'+'if flat['kelly_pnl'] >= 0 else ''}{flat['kelly_pnl']:,.2f}"
        f_pnl = f"{'+'if flat['flat_pnl'] >= 0 else ''}{flat['flat_pnl']:,.2f}"
        d_pnl = flat["kelly_advantage"]
        print(f"  {'P&L':<16} {k_pnl:>12} {f_pnl:>12} {'+' if d_pnl >= 0 else ''}{d_pnl:>11.2f}")
        print(
            f"  {'ROI':<16} {flat['kelly_roi_pct']:>11.1f}% "
            f"{flat['flat_roi_pct']:>11.1f}% "
            f"{'+' if flat['kelly_advantage'] >= 0 else ''}{flat['kelly_advantage']:>11.1f}%"
        )

        # Calibration
        print(f"\n--- Model Quality ---")
        pq = s["prediction_quality"]
        print(f"  Avg position MAE:  {pq['avg_mae']:.3f}")
        print(f"  Avg Spearman:      {pq['avg_spearman']:.3f}")
        print(f"  Winner hit rate:   {pq['winner_hit_rate']:.1%}")
        print(f"  Podium overlap:    {pq['avg_podium_overlap']:.1%}")

        if s["brier_win_avg"] is not None:
            print(f"  Brier (win):       {s['brier_win_avg']:.4f}")
        if s["brier_podium_avg"] is not None:
            print(f"  Brier (podium):    {s['brier_podium_avg']:.4f}")

        # CLV
        clv = s.get("clv_summary", {})
        if clv.get("n_bets", 0) > 0:
            print(f"\n--- CLV ---")
            print(f"  Bets tracked:      {clv['n_bets']}")
            print(f"  Brier (model):     {clv['brier_model']:.6f}")
            print(f"  Brier (closing):   {clv['brier_closing']:.6f}")
            ba = clv["brier_advantage"]
            print(f"  Brier advantage:   {'+'if ba >= 0 else ''}{ba:.6f}")

        # Per-race table (compact)
        print(f"\n--- Per Race ---")
        header = f"  {'Race':<12} {'Bets':>4} {'P&L':>9} {'Bankroll':>10} {'MAE':>5} {'Win':>4}"
        print(header)
        print(f"  {'-' * 12} {'-' * 4} {'-' * 9} {'-' * 10} {'-' * 5} {'-' * 4}")
        for r in s["per_race"]:
            pnl_str = f"{'+'if r['race_pnl'] >= 0 else ''}{r['race_pnl']:.2f}"
            win_str = "Y" if r["correct_winner"] else "N"
            print(
                f"  {r['race_id']:<12} {r['n_bets']:>4} {pnl_str:>9} "
                f"${r['bankroll_after']:>9,.2f} {r['mae']:>5.2f} {win_str:>4}"
            )

        print()
        print("=" * 72)


def run_backtest(
    feature_matrix: pd.DataFrame,
    start_season: int = 2024,
    end_season: int = 2025,
    bankroll: float = 1000.0,
    kelly_fraction: float = 0.25,
    markets: list[str] | None = None,
) -> dict:
    """
    Convenience function to run a full betting backtest.

    Returns the summary dict.
    """
    bt = BettingBacktest(bankroll=bankroll, kelly_fraction=kelly_fraction)
    results = bt.run(
        feature_matrix,
        start_season=start_season,
        end_season=end_season,
        markets=markets,
    )
    bt.print_report()
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Walk-forward betting backtest for F1 predictions"
    )
    parser.add_argument("--start", type=int, default=2024, help="Start season")
    parser.add_argument("--end", type=int, default=2025, help="End season")
    parser.add_argument(
        "--bankroll", type=float, default=1000.0, help="Starting bankroll"
    )
    parser.add_argument(
        "--kelly", type=float, default=0.25, help="Kelly fraction (0.25 = quarter Kelly)"
    )
    parser.add_argument(
        "--markets",
        nargs="+",
        default=["winner", "podium"],
        choices=["winner", "podium", "points", "dnf"],
        help="Markets to bet on",
    )
    parser.add_argument(
        "--min-edge",
        type=float,
        default=0.05,
        help="Minimum edge (model_prob - market_prob) to place a bet",
    )
    parser.add_argument(
        "--min-prob",
        type=float,
        default=0.02,
        help="Minimum model probability to consider",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Load feature matrix
    fm_path = DATA_DIR / "feature_matrix.parquet"
    if not fm_path.exists():
        logger.error(
            "Feature matrix not found at %s. Run the feature pipeline first.", fm_path
        )
        raise SystemExit(1)

    logger.info("Loading feature matrix from %s ...", fm_path)
    fm = pd.read_parquet(fm_path)
    logger.info(
        "Feature matrix: %d rows, seasons %d-%d",
        len(fm),
        int(fm["season"].min()),
        int(fm["season"].max()),
    )

    # Run backtest
    bt = BettingBacktest(
        bankroll=args.bankroll,
        kelly_fraction=args.kelly,
        min_edge=args.min_edge,
        min_prob=args.min_prob,
    )
    results = bt.run(
        fm,
        start_season=args.start,
        end_season=args.end,
        markets=args.markets,
    )

    bt.print_report()

    # Save results
    output_path = CACHE_DIR / "backtest_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Make JSON-serializable (convert numpy types)
    def _serialize(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=_serialize)

    logger.info("\nResults saved to %s", output_path)
