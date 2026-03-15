"""
Monte Carlo Race Simulator — transforms point predictions into distributions.

Instead of "Verstappen finishes P1", produces:
- P(win) = 45%, P(podium) = 78%, P(points) = 95%
- Expected points: 18.3 (±4.2)
- Full position distribution: [45%, 22%, 11%, 8%, ...]

Uses calibrated probabilities from F1Predictor for:
1. DNF sampling (team-correlated per constructor)
2. Position sampling (correlated via predicted positions + noise)
3. Safety car injection (historical rates per circuit, time-of-race aware)
4. Wet/mixed condition volatility
5. Pit strategy variation (team-correlated)
6. Full championship simulation with win/podium probabilities
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# F1 points system (2010-present)
POINTS: Dict[int, int] = {
    1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1,
}

# Historical safety car probability by circuit type
SC_RATES: Dict[str, float] = {
    "street": 0.65,       # Monaco, Baku, etc — high SC rate
    "high_speed": 0.40,   # Monza, Spa
    "technical": 0.35,    # Hungary, Barcelona
    "mixed": 0.45,        # Default
}

# --- Wet race volatility multipliers ---
WET_POSITION_NOISE_MULT = 2.5
MIXED_POSITION_NOISE_MULT = 1.5
WET_DNF_MULT = 1.5
MIXED_DNF_MULT = 1.2

# --- Correlated team failures ---
TEAM_DNF_CORRELATION = 3.0

# --- Pit strategy variation ---
PIT_STRATEGY_NOISE = 1.5
PIT_STRATEGY_TEAM_CORRELATION = 0.7  # teammates share ~70% of strategy offset

# --- Safety car timing weights (lap-phase multipliers) ---
SC_EARLY_LAPS_MULT = 1.5     # first 10 laps — more incidents on cold tyres
SC_PIT_WINDOW_MULT = 1.2     # pit windows — traffic causes incidents
SC_LATE_RACE_MULT = 0.8      # end of race — field spread, fewer incidents
SC_EARLY_SHUFFLE_POSITIONS = 3.0   # SC during race shuffles more than at start
SC_START_SHUFFLE_POSITIONS = 2.5   # SC at start — field already bunched

# --- Multi-car incident probabilities (lap-1 collisions, chain reactions) ---
MULTI_CAR_INCIDENT_RATES: Dict[str, float] = {
    "street": 0.30,       # Tight circuits — high lap-1 risk
    "high_speed": 0.15,   # More spread out, but high-speed incidents
    "technical": 0.12,    # Lower risk at low-speed circuits
    "mixed": 0.18,
}
MULTI_CAR_MIN_INVOLVED = 2
MULTI_CAR_MAX_INVOLVED = 5


class RaceSimulator:
    """Monte Carlo race simulator for F1 predictions."""

    def __init__(self, n_simulations: int = 10000, random_seed: int = 42):
        self.n_simulations = n_simulations
        self.rng = np.random.default_rng(random_seed)

    @staticmethod
    def _build_constructor_groups(
        driver_ids: np.ndarray,
        constructor_map: Optional[Dict[str, str]],
    ) -> Dict[str, List[int]]:
        """Build constructor_id → list of driver indices mapping."""
        if constructor_map is None:
            return {}
        groups: Dict[str, List[int]] = {}
        for idx, driver_id in enumerate(driver_ids):
            cid = constructor_map.get(str(driver_id))
            if cid is not None:
                groups.setdefault(cid, []).append(idx)
        return groups

    @staticmethod
    def _condition_multipliers(conditions: str) -> tuple:
        """Return (noise_mult, dnf_mult) for race conditions."""
        if conditions == "wet":
            return WET_POSITION_NOISE_MULT, WET_DNF_MULT
        elif conditions == "mixed":
            return MIXED_POSITION_NOISE_MULT, MIXED_DNF_MULT
        return 1.0, 1.0

    def _run_simulation_core(
        self,
        predictions: pd.DataFrame,
        circuit_type: str = "mixed",
        conditions: str = "dry",
        constructor_map: Optional[Dict[str, str]] = None,
    ) -> tuple:
        """
        Shared simulation core — returns raw arrays for callers to aggregate.

        Returns:
            (finish_positions, dnf_flags, all_points, driver_ids) where each
            matrix has shape (n_sims, n_drivers).
        """
        n_drivers = len(predictions)
        pred_positions = predictions["predicted_position"].values.astype(float)
        driver_ids = predictions["driver_id"].values

        if "prob_dnf" in predictions.columns:
            base_prob_dnf = predictions["prob_dnf"].values.astype(float)
        else:
            base_prob_dnf = np.zeros(n_drivers)

        noise_mult, dnf_mult = self._condition_multipliers(conditions)
        prob_dnf = np.clip(base_prob_dnf * dnf_mult, 0.0, 0.95)

        sc_rate = SC_RATES.get(circuit_type, SC_RATES["mixed"])
        n_sims = self.n_simulations
        constructor_groups = self._build_constructor_groups(driver_ids, constructor_map)

        # Safety car timing (per-sim phase-aware probability)
        phase_draw = self.rng.random(n_sims)
        sc_phase_mult = np.where(
            phase_draw < 0.33, SC_EARLY_LAPS_MULT,
            np.where(phase_draw < 0.66, SC_PIT_WINDOW_MULT, SC_LATE_RACE_MULT),
        )
        adjusted_sc_rate = np.clip(sc_rate * sc_phase_mult, 0.0, 0.95)
        has_sc = self.rng.random(n_sims) < adjusted_sc_rate

        sc_shuffle = np.where(
            phase_draw < 0.33,
            SC_START_SHUFFLE_POSITIONS,
            SC_EARLY_SHUFFLE_POSITIONS,
        )
        noise_scale = np.where(has_sc, sc_shuffle, 1.5)[:, np.newaxis]
        noise_scale = noise_scale * noise_mult

        # Team-correlated DNF sampling
        dnf_flags = self._sample_correlated_dnfs(
            n_sims, n_drivers, prob_dnf, driver_ids, constructor_groups,
        )

        # Multi-car incidents (lap-1 collisions, chain reactions)
        multi_car_dnfs = self._sample_multi_car_incidents(
            n_sims, n_drivers, pred_positions, circuit_type,
        )
        dnf_flags |= multi_car_dnfs

        # Pit strategy variation (team-correlated)
        pit_offsets = self._sample_pit_strategy(
            n_sims, n_drivers, driver_ids, constructor_groups,
        )

        # Build performance matrix
        performance = (
            pred_positions
            + self.rng.normal(0, 1, (n_sims, n_drivers)) * noise_scale
            + pit_offsets
        )
        performance[dnf_flags] = 100 + self.rng.random(int(dnf_flags.sum())) * 10

        # Convert to positions via double-argsort (rank constraint — no ties)
        finish_positions = performance.argsort(axis=1).argsort(axis=1) + 1

        # Points lookup
        points_lookup = np.array([POINTS.get(p, 0) for p in range(n_drivers + 1)])
        all_points = points_lookup[finish_positions]
        all_points[dnf_flags] = 0

        return finish_positions, dnf_flags, all_points, driver_ids

    def simulate_race(
        self,
        predictions: pd.DataFrame,
        circuit_type: str = "mixed",
        conditions: str = "dry",
        constructor_map: Optional[Dict[str, str]] = None,
    ) -> pd.DataFrame:
        """
        Run Monte Carlo simulation on model predictions.

        Args:
            predictions: DataFrame with predicted_position, prob_dnf, driver_id
            circuit_type: For safety car probability lookup
            conditions: "dry", "wet", or "mixed"
            constructor_map: Optional driver_id → constructor_id mapping

        Returns:
            DataFrame with simulation statistics per driver.
        """
        finish_positions, dnf_flags, all_points, _ = self._run_simulation_core(
            predictions, circuit_type, conditions, constructor_map,
        )

        n_sims = self.n_simulations
        n_drivers = len(predictions)

        sim_stats: List[Dict] = []
        for i in range(n_drivers):
            driver_positions = finish_positions[:, i]
            driver_dnfs = dnf_flags[:, i]
            classified = driver_positions[~driver_dnfs]
            n_classified = len(classified)

            if n_classified > 0:
                counts = np.bincount(classified, minlength=n_drivers + 1)
                pos_dist = counts[1:].astype(float) / n_sims
            else:
                pos_dist = np.zeros(n_drivers)

            points_per_sim = all_points[:, i]

            sim_stats.append({
                "sim_win_pct": float((driver_positions == 1).sum()) / n_sims * 100,
                "sim_podium_pct": float((driver_positions <= 3).sum()) / n_sims * 100,
                "sim_points_pct": float(((driver_positions <= 10) & ~driver_dnfs).sum()) / n_sims * 100,
                "sim_dnf_pct": float(driver_dnfs.sum()) / n_sims * 100,
                "sim_expected_points": float(points_per_sim.mean()),
                "sim_points_std": float(points_per_sim.std()),
                "sim_median_position": float(np.median(classified)) if n_classified > 0 else float(n_drivers),
                "sim_position_25": float(np.percentile(classified, 25)) if n_classified > 0 else float(n_drivers),
                "sim_position_75": float(np.percentile(classified, 75)) if n_classified > 0 else float(n_drivers),
                "sim_position_dist": pos_dist.tolist(),
            })

        sim_df = pd.DataFrame(sim_stats, index=predictions.index)
        results = pd.concat([predictions, sim_df], axis=1)

        return results.sort_values("sim_expected_points", ascending=False)

    def _sample_correlated_dnfs(
        self,
        n_sims: int,
        n_drivers: int,
        prob_dnf: np.ndarray,
        driver_ids: np.ndarray,
        constructor_groups: Dict[str, List[int]],
    ) -> np.ndarray:
        """
        Sample DNF flags with optional team correlation.

        Args:
            constructor_groups: Pre-built constructor_id → driver indices mapping
        """
        dnf_flags = self.rng.random((n_sims, n_drivers)) < prob_dnf

        if not constructor_groups:
            return dnf_flags

        for _cid, indices in constructor_groups.items():
            if len(indices) < 2:
                continue

            for i, idx_a in enumerate(indices):
                for idx_b in indices[i + 1:]:
                    a_dnf_only = dnf_flags[:, idx_a] & ~dnf_flags[:, idx_b]
                    boosted_prob_b = np.clip(prob_dnf[idx_b] * TEAM_DNF_CORRELATION, 0.0, 0.95)
                    new_rolls_b = self.rng.random(n_sims) < boosted_prob_b
                    dnf_flags[:, idx_b] |= (a_dnf_only & new_rolls_b)

                    b_dnf_only = dnf_flags[:, idx_b] & ~dnf_flags[:, idx_a]
                    boosted_prob_a = np.clip(prob_dnf[idx_a] * TEAM_DNF_CORRELATION, 0.0, 0.95)
                    new_rolls_a = self.rng.random(n_sims) < boosted_prob_a
                    dnf_flags[:, idx_a] |= (b_dnf_only & new_rolls_a)

        return dnf_flags

    def _sample_pit_strategy(
        self,
        n_sims: int,
        n_drivers: int,
        driver_ids: np.ndarray,
        constructor_groups: Dict[str, List[int]],
    ) -> np.ndarray:
        """
        Sample pit strategy offsets with team correlation.

        Args:
            constructor_groups: Pre-built constructor_id → driver indices mapping
        """
        individual_noise = self.rng.normal(0, PIT_STRATEGY_NOISE, (n_sims, n_drivers))

        if not constructor_groups:
            return individual_noise

        rho = PIT_STRATEGY_TEAM_CORRELATION
        for _cid, indices in constructor_groups.items():
            if len(indices) < 2:
                continue

            team_draw = self.rng.normal(0, PIT_STRATEGY_NOISE, (n_sims, 1))

            for idx in indices:
                individual_noise[:, idx] = (
                    rho * team_draw[:, 0]
                    + np.sqrt(1 - rho ** 2) * individual_noise[:, idx]
                )

        return individual_noise

    def _sample_multi_car_incidents(
        self,
        n_sims: int,
        n_drivers: int,
        pred_positions: np.ndarray,
        circuit_type: str,
    ) -> np.ndarray:
        """
        Sample multi-car incidents (lap-1 collisions, chain reactions).

        Unlike team-correlated DNFs, these affect random cars from different
        teams — typically in the midfield pack where cars are bunched together.

        Returns:
            Boolean array (n_sims, n_drivers) of additional DNFs from incidents.
        """
        incident_rate = MULTI_CAR_INCIDENT_RATES.get(
            circuit_type, MULTI_CAR_INCIDENT_RATES["mixed"]
        )
        incident_flags = np.zeros((n_sims, n_drivers), dtype=bool)

        # Which simulations have a multi-car incident?
        has_incident = self.rng.random(n_sims) < incident_rate
        incident_sims = np.where(has_incident)[0]
        if len(incident_sims) == 0:
            return incident_flags

        # Midfield cars (predicted P4-P16) are more likely to be involved
        # Weight: Gaussian centered around P10, sigma=4
        grid_weights = np.exp(-0.5 * ((pred_positions - 10) / 4) ** 2)
        grid_weights /= grid_weights.sum()

        for sim_idx in incident_sims:
            n_involved = self.rng.integers(
                MULTI_CAR_MIN_INVOLVED, MULTI_CAR_MAX_INVOLVED + 1
            )
            n_involved = min(n_involved, n_drivers)
            involved = self.rng.choice(
                n_drivers, size=n_involved, replace=False, p=grid_weights,
            )
            incident_flags[sim_idx, involved] = True

        return incident_flags

    def simulate_championship(
        self,
        race_predictions: List[pd.DataFrame],
        circuit_types: List[str],
        current_standings: Optional[Dict[str, float]] = None,
        conditions_per_race: Optional[List[str]] = None,
        constructor_map: Optional[Dict[str, str]] = None,
    ) -> pd.DataFrame:
        """
        Simulate remaining championship races with full Monte Carlo tracking.

        Runs the full n_simulations across all remaining races simultaneously,
        tracking cumulative points per driver per simulation to produce
        championship win probabilities and standings distributions.

        Args:
            race_predictions: List of prediction DataFrames (one per remaining race)
            circuit_types: Circuit type for each race
            current_standings: Optional dict of driver_id → current points total.
                Added to simulated points before determining championship positions.
            conditions_per_race: Optional list of conditions ("dry"/"wet"/"mixed")
                per race. Defaults to "dry" for all races.
            constructor_map: Optional driver_id → constructor_id for team correlation

        Returns:
            DataFrame with championship simulation results per driver:
                - driver_id: Driver identifier
                - expected_total_points: Mean total points (current + simulated)
                - points_std: Standard deviation of total points
                - championship_win_pct: % of simulations where driver finishes P1
                - podium_finish_pct: % of simulations where driver finishes top 3 in standings
        """
        if not race_predictions:
            return pd.DataFrame()

        if current_standings is None:
            current_standings = {}

        if conditions_per_race is None:
            conditions_per_race = ["dry"] * len(race_predictions)

        # Collect all unique drivers
        all_drivers: List[str] = []
        seen: set = set()
        for pred in race_predictions:
            for d in pred["driver_id"].values:
                if d not in seen:
                    all_drivers.append(d)
                    seen.add(d)

        n_drivers_total = len(all_drivers)
        driver_to_idx = {d: i for i, d in enumerate(all_drivers)}
        n_sims = self.n_simulations

        # Cumulative points matrix: (n_sims, n_drivers_total)
        cumulative_points = np.zeros((n_sims, n_drivers_total))

        # Add current standings
        for driver_id, pts in current_standings.items():
            if driver_id in driver_to_idx:
                cumulative_points[:, driver_to_idx[driver_id]] += pts

        # Simulate each remaining race
        for race_idx, (pred, ct) in enumerate(zip(race_predictions, circuit_types)):
            cond = conditions_per_race[race_idx] if race_idx < len(conditions_per_race) else "dry"
            race_points = self._simulate_race_points(
                pred, ct, cond, constructor_map,
            )

            # Map race points back to the global driver index
            for driver_id, points_array in race_points.items():
                if driver_id in driver_to_idx:
                    cumulative_points[:, driver_to_idx[driver_id]] += points_array

            logger.debug(
                "Championship sim: race %d/%d complete (%s, %s)",
                race_idx + 1, len(race_predictions), ct, cond,
            )

        # Determine championship positions per simulation
        # Lower rank = better (rank 1 = champion)
        championship_ranks = (-cumulative_points).argsort(axis=1).argsort(axis=1) + 1

        # Build championship stats per driver
        rows: List[Dict] = []
        for driver_id in all_drivers:
            idx = driver_to_idx[driver_id]
            driver_points = cumulative_points[:, idx]
            driver_ranks = championship_ranks[:, idx]

            rows.append({
                "driver_id": driver_id,
                "expected_total_points": float(driver_points.mean()),
                "points_std": float(driver_points.std()),
                "championship_win_pct": float((driver_ranks == 1).sum()) / n_sims * 100,
                "podium_finish_pct": float((driver_ranks <= 3).sum()) / n_sims * 100,
            })

        return pd.DataFrame(rows).sort_values("expected_total_points", ascending=False)

    def _simulate_race_points(
        self,
        predictions: pd.DataFrame,
        circuit_type: str,
        conditions: str,
        constructor_map: Optional[Dict[str, str]],
    ) -> Dict[str, np.ndarray]:
        """
        Run Monte Carlo for a single race and return per-driver points arrays.

        Returns:
            Dict mapping driver_id to numpy array of shape (n_sims,) with points
        """
        _, _, all_points, driver_ids = self._run_simulation_core(
            predictions, circuit_type, conditions, constructor_map,
        )

        result: Dict[str, np.ndarray] = {}
        for i, driver_id in enumerate(driver_ids):
            result[str(driver_id)] = all_points[:, i]
        return result


def run_simulation(
    predictor: object,
    feature_matrix: pd.DataFrame,
    season: int,
    race_round: int,
    circuit_type: str = "mixed",
    n_simulations: int = 10000,
    conditions: str = "dry",
    constructor_map: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """
    Convenience function: predict + simulate a specific race.

    Args:
        predictor: Trained F1Predictor instance
        feature_matrix: Full feature matrix
        season: Year
        race_round: Round number
        circuit_type: Circuit classification
        n_simulations: Number of Monte Carlo runs
        conditions: "dry", "wet", or "mixed"
        constructor_map: Optional driver_id → constructor_id mapping

    Returns:
        Simulation results DataFrame
    """
    race_data = feature_matrix[
        (feature_matrix["season"] == season)
        & (feature_matrix["round"] == race_round)
    ]

    if race_data.empty:
        logger.warning("No data for %d round %d", season, race_round)
        return pd.DataFrame()

    predictions = predictor.predict_race(race_data)

    simulator = RaceSimulator(n_simulations=n_simulations)
    results = simulator.simulate_race(
        predictions, circuit_type, conditions=conditions,
        constructor_map=constructor_map,
    )

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    from data.models.predictor import F1Predictor

    predictor = F1Predictor()
    predictor.load()

    feature_matrix = pd.read_parquet("data/cache/processed/feature_matrix.parquet")

    latest_season = int(feature_matrix["season"].max())
    latest_round = int(
        feature_matrix[feature_matrix["season"] == latest_season]["round"].max()
    )

    print(f"Simulating {latest_season} Round {latest_round}...")
    results = run_simulation(predictor, feature_matrix, latest_season, latest_round)

    if not results.empty:
        display_cols = [
            "driver_id",
            "predicted_position",
            "sim_win_pct",
            "sim_podium_pct",
            "sim_expected_points",
            "sim_median_position",
        ]
        available = [c for c in display_cols if c in results.columns]
        print(results[available].head(20).to_string())
