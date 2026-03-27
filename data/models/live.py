"""
In-Race Live Prediction Engine — lap-by-lap probability updates.

Combines pre-race model predictions with real-time race state from OpenF1
to produce updated win/podium/points probabilities during the race.

Two predictors:
- LiveRacePredictor: Original heuristic-based predictor (lightweight, fast)
- InRacePredictor: Full Monte Carlo from current state (1000 sims per lap update)

The approach: Bayesian-inspired update where pre-race priors are adjusted
based on in-race evidence (current position, gaps, tire state, track status).
"""

from __future__ import annotations

import collections
import copy
import logging
import time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Tire compound encoding for vectorized operations
COMPOUND_CODE = {"soft": 1, "medium": 2, "hard": 3, "intermediate": 4, "wet": 5, "unknown": 2}

# Tire life thresholds — laps before significant degradation
COMPOUND_LIFE = {"soft": 18, "medium": 28, "hard": 38, "intermediate": 30, "wet": 25, "unknown": 22}

# Degradation rate (seconds per lap lost beyond threshold)
COMPOUND_DEG_RATE = {"soft": 0.12, "medium": 0.07, "hard": 0.04, "intermediate": 0.06, "wet": 0.03, "unknown": 0.07}

# Maximum degradation cap (seconds per lap) — tires plateau, don't degrade infinitely
COMPOUND_MAX_DEG = {"soft": 0.5, "medium": 0.35, "hard": 0.25, "intermediate": 0.4, "wet": 0.2, "unknown": 0.35}

# Safety car probability per lap by circuit type
# Derived from per-race rates in simulator.py: p_lap = 1 - (1 - p_race)^(1/57)
# street=0.65/race, high_speed=0.40, technical=0.35, mixed=0.45
SC_PROB_PER_LAP = {"street": 0.018, "high_speed": 0.009, "technical": 0.008, "mixed": 0.011}

# Overtaking: gap threshold (seconds) and success rate per attempt.
# 2026 uses Overtake Mode (electric boost) instead of DRS — higher success on all tracks.
# Calibrated from 2024-2025 overtake data + estimated 2026 boost impact.
OVERTAKE_GAP_THRESHOLD = {"street": 0.5, "high_speed": 1.0, "technical": 0.8, "mixed": 0.9}
OVERTAKE_SUCCESS_RATE = {"street": 0.12, "high_speed": 0.38, "technical": 0.22, "mixed": 0.28}

# DNF probability per lap — base rate modulated by constructor reliability
BASE_DNF_PER_LAP = 0.004
CONSTRUCTOR_DNF_MULT = {
    "mercedes": 0.6, "ferrari": 0.7, "red_bull": 0.8, "mclaren": 0.7,
    "aston_martin": 0.9, "alpine": 1.0, "williams": 1.1, "rb": 1.0,
    "haas": 1.2, "audi": 1.5, "cadillac": 1.8,
}


class RaceState:
    """Snapshot of the current race state for all drivers."""

    def __init__(self):
        self.lap: int = 0
        self.total_laps: int = 0
        self.track_status: str = "clear"  # clear, sc, vsc, red
        self.drivers: Dict[str, DriverState] = {}
        self.air_temp: float = 0.0
        self.track_temp: float = 0.0
        self.rainfall: bool = False
        self.driver_locations: Dict[str, tuple] = {}  # driver_id -> (x, y)
        self.track_outline: List[tuple] = []  # [(x, y), ...]

    @property
    def laps_remaining(self) -> int:
        return max(0, self.total_laps - self.lap)

    @property
    def race_progress(self) -> float:
        if self.total_laps == 0:
            return 0.0
        return self.lap / self.total_laps


class DriverState:
    """Current race state for a single driver."""

    def __init__(self, driver_id: str):
        self.driver_id = driver_id
        self.position: int = 0
        self.gap_to_leader: float = 0.0
        self.gap_to_ahead: float = 0.0
        self.tire_compound: str = "unknown"  # soft, medium, hard, intermediate, wet
        self.tire_age: int = 0
        self.pits_completed: int = 0
        self.last_lap_time: float = 0.0
        self.best_lap_time: float = 0.0
        self.is_in_pit: bool = False
        self.is_retired: bool = False
        self.sector1: float = 0.0
        self.sector2: float = 0.0
        self.sector3: float = 0.0
        # Car telemetry — OpenF1 (tracked drivers only, ~3.7Hz)
        self.speed: int = 0             # km/h
        self.rpm: int = 0               # rev/min
        self.gear: int = 0              # 0-8
        self.throttle: int = 0          # 0-100%
        self.brake: int = 0             # 0-100% (OpenF1: 0 or 100; F1 Live: 0-100)
        self.drs: int = 0               # DRS / active aero status code
        # F1 Live Timing enhancements (tracked drivers only)
        self.ers_deploy: int = 0        # ERS deployment mode (0=none, 1-4=levels)
        self.overtake_active: bool = False  # Overtake Mode / Boost engaged
        self.battery_soc: float = -1.0  # Estimated battery % (0-100, -1=unknown)
        self.lap_delta: float = 0.0     # Time gained/lost vs reference lap (seconds)
        self.tire_pressure_fl: float = 0.0  # Front-left PSI
        self.tire_pressure_fr: float = 0.0
        self.tire_pressure_rl: float = 0.0
        self.tire_pressure_rr: float = 0.0
        self.tire_temp_fl: float = 0.0  # Front-left °C
        self.tire_temp_fr: float = 0.0
        self.tire_temp_rl: float = 0.0
        self.tire_temp_rr: float = 0.0


class LiveRacePredictor:
    """
    Updates predictions during a live race using pre-race model + in-race state.

    Strategy:
    1. Start with pre-race predictions as prior
    2. As race progresses, weight shifts toward in-race evidence
    3. Current position becomes dominant predictor late in race
    4. Safety car / VSC increases uncertainty
    """

    def __init__(
        self,
        pre_race_predictions: pd.DataFrame,
        total_laps: int = 57,
        circuit_type: str = "mixed",
    ):
        """
        Args:
            pre_race_predictions: DataFrame from F1Predictor.predict_race()
                Must have: driver_id, predicted_position, prob_winner, prob_podium
            total_laps: Expected race distance in laps
            circuit_type: street/high_speed/technical/mixed
        """
        self.pre_race = pre_race_predictions.set_index("driver_id")
        self.total_laps = total_laps
        self.circuit_type = circuit_type
        self.current_state: Optional[RaceState] = None
        self.prediction_history: collections.deque = collections.deque(maxlen=200)

    def update(self, race_state: RaceState) -> pd.DataFrame:
        """
        Generate updated predictions from current race state.

        Args:
            race_state: Current snapshot of the race

        Returns:
            DataFrame with updated predictions per driver
        """
        self.current_state = race_state
        progress = race_state.race_progress

        # Evidence weight increases with race progress
        # Early race: trust pre-race model more
        # Late race: trust current positions more
        evidence_weight = self._evidence_weight(progress, race_state.track_status)
        prior_weight = 1.0 - evidence_weight

        results = []
        n_drivers = len(race_state.drivers)

        for driver_id, state in race_state.drivers.items():
            if state.is_retired:
                results.append({
                    "driver_id": driver_id,
                    "live_position": state.position,
                    "predicted_position": float(n_drivers + 1),
                    "win_prob": 0.0,
                    "podium_prob": 0.0,
                    "points_prob": 0.0,
                    "is_retired": True,
                    "tire_compound": state.tire_compound,
                    "tire_age": state.tire_age,
                    "pits_completed": state.pits_completed,
                    "gap_to_leader": state.gap_to_leader,
                })
                continue

            # Pre-race prior (if available)
            if driver_id in self.pre_race.index:
                prior_pos = self.pre_race.loc[driver_id, "predicted_position"]
                prior_win = self.pre_race.loc[driver_id].get("prob_winner", 0.05)
                prior_podium = self.pre_race.loc[driver_id].get("prob_podium", 0.15)
            else:
                prior_pos = 10.0
                prior_win = 1.0 / max(n_drivers, 1)
                prior_podium = 3.0 / max(n_drivers, 1)

            # In-race evidence
            evidence_pos = float(state.position)

            # Pace-adjusted position (factor in recent lap times vs field)
            pace_adjustment = self._pace_adjustment(state, race_state)
            adjusted_evidence_pos = evidence_pos + pace_adjustment

            # Tire strategy adjustment
            tire_adjustment = self._tire_strategy_adjustment(state, race_state)
            adjusted_evidence_pos += tire_adjustment

            # Bayesian-ish combination
            predicted_pos = prior_weight * prior_pos + evidence_weight * adjusted_evidence_pos

            # Probability updates
            win_prob = self._compute_live_win_prob(
                state, race_state, prior_win, evidence_weight,
            )
            podium_prob = self._compute_live_podium_prob(
                state, race_state, prior_podium, evidence_weight,
            )
            points_prob = self._compute_live_points_prob(
                state, race_state, evidence_weight,
            )

            results.append({
                "driver_id": driver_id,
                "live_position": state.position,
                "predicted_position": predicted_pos,
                "win_prob": win_prob,
                "podium_prob": podium_prob,
                "points_prob": points_prob,
                "is_retired": False,
                "tire_compound": state.tire_compound,
                "tire_age": state.tire_age,
                "pits_completed": state.pits_completed,
                "gap_to_leader": state.gap_to_leader,
                "pace_adjustment": pace_adjustment,
            })

        df = pd.DataFrame(results).sort_values("predicted_position")

        # Normalize probabilities
        active_mask = ~df["is_retired"]
        if active_mask.any():
            # Win probs must sum to 1.0
            win_total = df.loc[active_mask, "win_prob"].sum()
            if win_total > 0:
                df.loc[active_mask, "win_prob"] /= win_total

            # Podium probs must sum to min(3, n_active)
            n_active = active_mask.sum()
            podium_total = df.loc[active_mask, "podium_prob"].sum()
            target_sum = min(3.0, float(n_active))
            if podium_total > 0:
                df.loc[active_mask, "podium_prob"] *= target_sum / podium_total
                df["podium_prob"] = df["podium_prob"].clip(0, 1)

        # Record history
        self.prediction_history.append({
            "lap": race_state.lap,
            "predictions": df.to_dict("records"),
        })

        return df

    def _evidence_weight(self, progress: float, track_status: str) -> float:
        """
        How much to weight in-race evidence vs pre-race prior.

        Uses sigmoid curve: slow start, then rapid increase mid-race.
        Safety car reduces evidence weight (positions are compressed).
        """
        # Sigmoid: 0.1 at lap 0, 0.5 at 40% race, 0.95 at 80% race
        weight = 1.0 / (1.0 + np.exp(-10 * (progress - 0.4)))

        # Safety car reduces evidence weight (positions are misleading)
        if track_status == "sc":
            weight *= 0.7
        elif track_status == "vsc":
            weight *= 0.85
        elif track_status == "red":
            weight *= 0.5

        return float(np.clip(weight, 0.05, 0.98))

    def _pace_adjustment(self, driver: DriverState, race: RaceState) -> float:
        """
        Adjust predicted position based on pace vs field.

        Faster than average = likely to gain positions (negative adjustment).
        Slower = likely to lose (positive adjustment).
        """
        if driver.last_lap_time <= 0:
            return 0.0

        # Field median lap time
        lap_times = [
            d.last_lap_time for d in race.drivers.values()
            if d.last_lap_time > 0 and not d.is_retired and not d.is_in_pit
        ]
        if not lap_times:
            return 0.0

        median_time = np.median(lap_times)
        if median_time <= 0:
            return 0.0

        # Pace delta as fraction of median (positive = slower)
        pace_delta = (driver.last_lap_time - median_time) / median_time

        # Scale: pace delta to position change, adjusted by circuit overtaking difficulty
        pace_mult = {"street": 30.0, "high_speed": 60.0, "technical": 45.0, "mixed": 50.0}
        mult = pace_mult.get(self.circuit_type, 50.0)
        return pace_delta * mult

    def _tire_strategy_adjustment(self, driver: DriverState, race: RaceState) -> float:
        """
        Adjust for tire strategy using the same physics constants as the Monte Carlo.
        Returns estimated position loss from tire degradation.
        """
        compound = driver.tire_compound
        life = COMPOUND_LIFE.get(compound, 22)
        deg_rate = COMPOUND_DEG_RATE.get(compound, 0.07)
        max_deg = COMPOUND_MAX_DEG.get(compound, 0.35)

        excess_laps = max(0, driver.tire_age - life)
        pace_loss_sec = min(excess_laps * deg_rate, max_deg)

        # Convert seconds/lap to approximate position loss:
        # ~0.3s/lap gap between positions in a typical midfield battle
        return pace_loss_sec / 0.3

    def _compute_live_win_prob(
        self,
        driver: DriverState,
        race: RaceState,
        prior: float,
        evidence_weight: float,
    ) -> float:
        """Compute live win probability."""
        if driver.is_retired:
            return 0.0

        # Position-based evidence (exponential decay from P1)
        pos_factor = np.exp(-0.8 * (driver.position - 1))

        # Gap penalty (if gap to leader > 20s, win is very unlikely)
        if driver.gap_to_leader > 0:
            gap_factor = np.exp(-driver.gap_to_leader / 15.0)
        else:
            gap_factor = 1.0

        evidence_prob = pos_factor * gap_factor

        # Combine prior and evidence
        combined = (1 - evidence_weight) * prior + evidence_weight * evidence_prob

        return float(np.clip(combined, 0.001, 0.99))

    def _compute_live_podium_prob(
        self,
        driver: DriverState,
        race: RaceState,
        prior: float,
        evidence_weight: float,
    ) -> float:
        """Compute live podium probability."""
        if driver.is_retired:
            return 0.0

        # Position-based: P1-P3 high, drops off quickly
        if driver.position <= 3:
            pos_factor = 0.9 - 0.1 * (driver.position - 1)
        else:
            pos_factor = np.exp(-0.5 * (driver.position - 3))

        # Gap to P3
        p3_drivers = [d for d in race.drivers.values() if d.position == 3 and not d.is_retired]
        if p3_drivers and driver.position > 3:
            gap_to_p3 = driver.gap_to_leader - p3_drivers[0].gap_to_leader
            if gap_to_p3 > 0:
                pos_factor *= np.exp(-gap_to_p3 / 10.0)

        evidence_prob = pos_factor
        combined = (1 - evidence_weight) * prior + evidence_weight * evidence_prob

        return float(np.clip(combined, 0.001, 0.99))

    def _compute_live_points_prob(
        self,
        driver: DriverState,
        race: RaceState,
        evidence_weight: float,
    ) -> float:
        """Compute live points probability (P1-P10)."""
        if driver.is_retired:
            return 0.0

        if driver.position <= 10:
            evidence_prob = 0.95 - 0.03 * (driver.position - 1)
        else:
            evidence_prob = np.exp(-0.3 * (driver.position - 10))

        prior = 0.5
        combined = (1 - evidence_weight) * prior + evidence_weight * evidence_prob

        return float(np.clip(combined, 0.01, 0.99))


class InRacePredictor:
    """
    Recalculates race probabilities on every lap using live telemetry + mini Monte Carlo.

    On each lap update:
    1. Extract features from current RaceState (positions, gaps, tyre state, weather)
    2. Run a mini Monte Carlo (1000 sims) from current race state forward
    3. Blend live simulation probabilities with pre-race model predictions
    4. Output updated probabilities for each driver

    As the race progresses, uncertainty shrinks. Lap 1 predictions look like
    pre-race. By lap 40/53, they converge toward the actual result.
    """

    def __init__(
        self,
        pre_race_predictions: pd.DataFrame,
        total_laps: int = 57,
        circuit_id: Optional[str] = None,
        circuit_type: str = "mixed",
        n_sims: int = 1000,
    ):
        """
        Args:
            pre_race_predictions: DataFrame from F1Predictor.predict_race()
                Must have: driver_id, predicted_position, prob_winner, prob_podium
            total_laps: Total race laps
            circuit_id: For circuit-specific adjustments
            circuit_type: street/high_speed/technical/mixed
            n_sims: Number of Monte Carlo simulations per update
        """
        self.pre_race = pre_race_predictions.copy()
        if "driver_id" in self.pre_race.columns:
            self.pre_race = self.pre_race.set_index("driver_id")
        self.total_laps = total_laps
        self.circuit_id = circuit_id
        self.circuit_type = circuit_type
        self.n_sims = n_sims

        # Pre-race probabilities as dict for fast lookup
        self._pre_race_win: Dict[str, float] = {}
        self._pre_race_podium: Dict[str, float] = {}
        self._pre_race_points: Dict[str, float] = {}
        for did in self.pre_race.index:
            row = self.pre_race.loc[did]
            self._pre_race_win[did] = float(row.get("prob_winner", row.get("sim_win_pct", 5.0) / 100.0))
            self._pre_race_podium[did] = float(row.get("prob_podium", row.get("sim_podium_pct", 15.0) / 100.0))
            self._pre_race_points[did] = float(row.get("prob_points", row.get("sim_points_pct", 50.0) / 100.0))
            # Normalize: sim_*_pct is 0-100, prob_* is 0-1
            if self._pre_race_win[did] > 1.0:
                self._pre_race_win[did] /= 100.0
            if self._pre_race_podium[did] > 1.0:
                self._pre_race_podium[did] /= 100.0
            if self._pre_race_points[did] > 1.0:
                self._pre_race_points[did] /= 100.0

        # History: per-lap probability snapshots for sparkline charts
        self.history: Dict[str, Dict[str, List[float]]] = {}
        self._last_lap_updated: int = -1
        self._last_results: Optional[pd.DataFrame] = None

        # RNG for reproducible sims within a session
        self._rng = np.random.default_rng(42)

    def update(self, state: RaceState) -> pd.DataFrame:
        """
        Recalculate all probabilities given current race state.

        Called once per lap change. Returns DataFrame with columns:
            driver_id, position, gap_to_leader, tire_compound, tire_age,
            live_win_prob, live_podium_prob, live_points_prob, live_dnf_prob,
            pre_race_win_prob, pre_race_podium_prob,
            delta_win, delta_podium,
            trend (improving/declining/stable over last 5 laps)
        """
        # Skip recomputation if same lap (SSE ticks faster than lap changes)
        if state.lap == self._last_lap_updated and self._last_results is not None:
            return self._last_results

        t0 = time.monotonic()

        # Run mini Monte Carlo from current state
        sim_results = self._simulate_remaining(state)

        # Build results DataFrame
        rows = []
        n_active = sum(1 for d in state.drivers.values() if not d.is_retired)

        for driver_id, ds in state.drivers.items():
            pre_win = self._pre_race_win.get(driver_id, 1.0 / max(n_active, 1))
            pre_pod = self._pre_race_podium.get(driver_id, 3.0 / max(n_active, 1))
            pre_pts = self._pre_race_points.get(driver_id, 10.0 / max(n_active, 1))

            if ds.is_retired:
                rows.append({
                    "driver_id": driver_id,
                    "position": ds.position,
                    "gap_to_leader": ds.gap_to_leader,
                    "tire_compound": ds.tire_compound,
                    "tire_age": ds.tire_age,
                    "pits_completed": ds.pits_completed,
                    "live_win_prob": 0.0,
                    "live_podium_prob": 0.0,
                    "live_points_prob": 0.0,
                    "live_dnf_prob": 1.0,
                    "pre_race_win_prob": pre_win,
                    "pre_race_podium_prob": pre_pod,
                    "delta_win": -pre_win,
                    "delta_podium": -pre_pod,
                    "trend": "retired",
                    "is_retired": True,
                })
                continue

            sim = sim_results.get(driver_id, {})
            sim_win = sim.get("win_prob", 0.0)
            sim_pod = sim.get("podium_prob", 0.0)
            sim_pts = sim.get("points_prob", 0.0)
            sim_dnf = sim.get("dnf_prob", 0.0)

            # Bayesian blend: live_weight increases with race progress
            live_weight = min(1.0, state.race_progress * 1.5)

            blended_win = pre_win * (1.0 - live_weight) + sim_win * live_weight
            blended_pod = pre_pod * (1.0 - live_weight) + sim_pod * live_weight
            blended_pts = pre_pts * (1.0 - live_weight) + sim_pts * live_weight
            blended_dnf = sim_dnf  # DNF is purely from simulation

            delta_win = blended_win - pre_win
            delta_pod = blended_pod - pre_pod

            # Trend over last 5 laps
            trend = self._compute_trend(driver_id, blended_win)

            rows.append({
                "driver_id": driver_id,
                "position": ds.position,
                "gap_to_leader": ds.gap_to_leader,
                "gap_to_ahead": ds.gap_to_ahead,
                "tire_compound": ds.tire_compound,
                "tire_age": ds.tire_age,
                "pits_completed": ds.pits_completed,
                "live_win_prob": blended_win,
                "live_podium_prob": blended_pod,
                "live_points_prob": blended_pts,
                "live_dnf_prob": blended_dnf,
                "pre_race_win_prob": pre_win,
                "pre_race_podium_prob": pre_pod,
                "delta_win": delta_win,
                "delta_podium": delta_pod,
                "trend": trend,
                "is_retired": False,
            })

        df = pd.DataFrame(rows)

        # Normalize: win probs must sum to 1.0 among active drivers
        active = ~df["is_retired"]
        if active.any():
            win_total = df.loc[active, "live_win_prob"].sum()
            if win_total > 0:
                df.loc[active, "live_win_prob"] *= 1.0 / win_total
                # Recalculate deltas after normalization
                for idx in df.index[active]:
                    did = df.loc[idx, "driver_id"]
                    df.loc[idx, "delta_win"] = df.loc[idx, "live_win_prob"] - self._pre_race_win.get(did, 0.0)

            # Podium probs sum to min(3, n_active)
            n_act = int(active.sum())
            pod_total = df.loc[active, "live_podium_prob"].sum()
            target = min(3.0, float(n_act))
            if pod_total > 0:
                df.loc[active, "live_podium_prob"] *= target / pod_total
                df["live_podium_prob"] = df["live_podium_prob"].clip(0, 1)
                for idx in df.index[active]:
                    did = df.loc[idx, "driver_id"]
                    df.loc[idx, "delta_podium"] = df.loc[idx, "live_podium_prob"] - self._pre_race_podium.get(did, 0.0)

        df = df.sort_values("position")

        # Record history for sparklines
        self._record_history(state.lap, df)
        self._last_lap_updated = state.lap
        self._last_results = df

        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "InRacePredictor update: lap %d/%d, %d drivers, %d sims, %.0fms",
            state.lap, state.total_laps, len(state.drivers), self.n_sims, elapsed_ms,
        )

        return df

    def _simulate_remaining(self, state: RaceState) -> Dict[str, Dict[str, float]]:
        """
        Mini Monte Carlo from current race state.

        Vectorized across all simulations for performance.
        1000 sims x 50 remaining laps x 20 drivers must complete in <2 seconds.

        Returns: {driver_id: {win_prob, podium_prob, points_prob, dnf_prob}}
        """
        rng = self._rng
        n_sims = self.n_sims
        laps_remaining = state.laps_remaining

        # If race is over, just use current positions
        if laps_remaining <= 0:
            return self._positions_to_probs(state)

        # Build driver arrays (sorted by position for deterministic indexing)
        active_drivers = [
            (did, ds) for did, ds in state.drivers.items() if not ds.is_retired
        ]
        active_drivers.sort(key=lambda x: x[1].position)
        n_drivers = len(active_drivers)

        if n_drivers == 0:
            return {}

        driver_ids = [d[0] for d in active_drivers]

        # Current gaps (seconds behind leader) — shape (n_drivers,)
        gaps = np.array([d[1].gap_to_leader for d in active_drivers], dtype=np.float64)

        # Current tire state
        tire_ages = np.array([d[1].tire_age for d in active_drivers], dtype=np.float64)
        tire_lives = np.array(
            [COMPOUND_LIFE.get(d[1].tire_compound, 22) for d in active_drivers],
            dtype=np.float64,
        )
        tire_deg = np.array(
            [COMPOUND_DEG_RATE.get(d[1].tire_compound, 0.07) for d in active_drivers],
            dtype=np.float64,
        )
        tire_max_deg = np.array(
            [COMPOUND_MAX_DEG.get(d[1].tire_compound, 0.35) for d in active_drivers],
            dtype=np.float64,
        )
        pits_done = np.array([d[1].pits_completed for d in active_drivers], dtype=np.int32)

        if not hasattr(self, "_driver_constructor"):
            from data.ingest.live_feed import DRIVER_CONSTRUCTOR
            self._driver_constructor = DRIVER_CONSTRUCTOR
        dnf_rates = np.array([
            BASE_DNF_PER_LAP * CONSTRUCTOR_DNF_MULT.get(
                self._driver_constructor.get(d[0], "unknown"), 1.0
            ) for d in active_drivers
        ], dtype=np.float64)

        # Pace: use last lap time relative to leader as base pace delta
        leader_time = 0.0
        for did, ds in active_drivers:
            if ds.position == 1 and ds.last_lap_time > 0:
                leader_time = ds.last_lap_time
                break
        if leader_time <= 0:
            # Fallback: median of all valid lap times
            valid_times = [ds.last_lap_time for _, ds in active_drivers if ds.last_lap_time > 0]
            leader_time = float(np.median(valid_times)) if valid_times else 90.0

        base_pace_delta = np.zeros(n_drivers, dtype=np.float64)
        for i, (_, ds) in enumerate(active_drivers):
            if ds.last_lap_time > 0:
                base_pace_delta[i] = ds.last_lap_time - leader_time
            else:
                # No lap time: estimate from gap growth
                base_pace_delta[i] = gaps[i] / max(state.lap, 1)

        # SC and overtaking parameters
        sc_prob = SC_PROB_PER_LAP.get(self.circuit_type, 0.022)
        overtake_gap = OVERTAKE_GAP_THRESHOLD.get(self.circuit_type, 1.0)
        overtake_rate = OVERTAKE_SUCCESS_RATE.get(self.circuit_type, 0.30)

        # Expand to simulation dimensions: (n_sims, n_drivers)
        sim_gaps = np.tile(gaps, (n_sims, 1))
        sim_tire_age = np.tile(tire_ages, (n_sims, 1))
        sim_tire_life = np.tile(tire_lives, (n_sims, 1))
        sim_tire_deg = np.tile(tire_deg, (n_sims, 1))
        sim_tire_max_deg = np.tile(tire_max_deg, (n_sims, 1))
        sim_pits = np.tile(pits_done, (n_sims, 1))
        sim_dnf = np.zeros((n_sims, n_drivers), dtype=bool)

        # Track if driver has pitted in the remaining laps (to reset tire state)
        # Start with medium compound on pit: reasonable assumption
        medium_life = COMPOUND_LIFE["medium"]
        medium_deg = COMPOUND_DEG_RATE["medium"]
        hard_life = COMPOUND_LIFE["hard"]
        hard_deg = COMPOUND_DEG_RATE["hard"]

        # Simulate lap by lap
        for lap_offset in range(1, laps_remaining + 1):
            # Increment tire age
            sim_tire_age += 1

            # Tire degradation: extra pace loss when over compound life (capped)
            excess = np.maximum(0, sim_tire_age - sim_tire_life)
            tire_pace_loss = np.minimum(excess * sim_tire_deg, sim_tire_max_deg)

            # Random pace noise per driver per sim (std ~0.3s, typical F1 variation)
            noise = rng.normal(0, 0.3, (n_sims, n_drivers))

            # Weather: increase noise if rainfall
            if state.rainfall:
                noise *= 2.0

            # Pace delta for this lap (positive = slower than leader)
            lap_pace = base_pace_delta + tire_pace_loss + noise

            # Update gaps: leader stays at 0, others accumulate pace delta
            sim_gaps += lap_pace
            # Leader's gap is always 0 (they set the reference)
            sim_gaps[:, 0] = 0.0
            # Gaps can't go negative (would mean overtake happened)
            # Handle overtakes below

            # Pit stops: if tire age > life + random(0,5), pit
            pit_threshold = sim_tire_life + rng.uniform(0, 5, (n_sims, n_drivers))
            needs_pit = (sim_tire_age > pit_threshold) & (sim_pits < 2) & (~sim_dnf)
            # Pit stop adds ~22s to gap
            sim_gaps[needs_pit] += 22.0
            sim_tire_age[needs_pit] = 0
            # Stochastic compound: early pits favor medium, late pits favor hard
            pit_count = int(needs_pit.sum())
            if pit_count > 0:
                progress = lap_offset / laps_remaining if laps_remaining > 0 else 1.0
                hard_prob = min(0.7, 0.2 + progress * 0.5)
                picks_hard = rng.random(pit_count) < hard_prob
                life_vals = np.where(picks_hard, hard_life, medium_life)
                deg_vals = np.where(picks_hard, hard_deg, medium_deg)
                max_deg_vals = np.where(picks_hard, COMPOUND_MAX_DEG["hard"], COMPOUND_MAX_DEG["medium"])
                sim_tire_life[needs_pit] = life_vals
                sim_tire_deg[needs_pit] = deg_vals
                sim_tire_max_deg[needs_pit] = max_deg_vals
            sim_pits[needs_pit] += 1

            # Safety car: random per sim
            sc_this_lap = rng.random(n_sims) < sc_prob
            if sc_this_lap.any():
                sc_indices = np.where(sc_this_lap)[0]
                # Bunch the field: compress gaps to max 1.5s between cars
                sc_gaps = sim_gaps[sc_indices].copy()  # (n_sc, n_drivers)
                sc_order = np.argsort(sc_gaps, axis=1)
                sc_sorted = np.take_along_axis(sc_gaps, sc_order, axis=1)
                # Compress inter-car gaps to max 1.5s
                sc_diffs = np.diff(sc_sorted, axis=1)
                sc_diffs = np.minimum(sc_diffs, 1.5)
                sc_new_sorted = np.zeros_like(sc_sorted)
                sc_new_sorted[:, 1:] = np.cumsum(sc_diffs, axis=1)
                # Scatter back to original driver order
                np.put_along_axis(sc_gaps, sc_order, sc_new_sorted, axis=1)
                sim_gaps[sc_indices] = sc_gaps

            # DNF: random per driver per lap
            dnf_this_lap = (rng.random((n_sims, n_drivers)) < dnf_rates) & (~sim_dnf)
            sim_dnf |= dnf_this_lap
            sim_gaps[sim_dnf] = 9999.0

            # Overtakes: vectorized approach
            # Sort each sim's gaps, compute inter-car gaps, apply overtake probability
            if not sc_this_lap.all():
                # Get sorted order for all sims at once
                sort_order = np.argsort(sim_gaps, axis=1)  # (n_sims, n_drivers)
                sorted_gaps = np.take_along_axis(sim_gaps, sort_order, axis=1)
                sorted_pace = np.take_along_axis(lap_pace, sort_order, axis=1)

                # Inter-car gaps (gap between consecutive positions)
                inter_gaps = np.diff(sorted_gaps, axis=1)  # (n_sims, n_drivers-1)

                # Pace advantage of car behind over car ahead (positive = behind is faster)
                pace_adv = sorted_pace[:, :-1] - sorted_pace[:, 1:]

                # Overtake conditions: close gap + pace advantage + random success
                can_attempt = (inter_gaps < overtake_gap) & (pace_adv > 0.2)
                roll = rng.random((n_sims, n_drivers - 1))
                overtakes = can_attempt & (roll < overtake_rate) & ~sc_this_lap[:, np.newaxis]

                # Apply swaps: for each overtake, swap the gaps of adjacent cars
                for k in range(n_drivers - 1):
                    swap_mask = overtakes[:, k]
                    if swap_mask.any():
                        # Identify the actual driver indices from sort_order
                        behind = sort_order[swap_mask, k + 1]
                        ahead = sort_order[swap_mask, k]
                        # Swap their gaps
                        sims = np.where(swap_mask)[0]
                        tmp = sim_gaps[sims, behind].copy()
                        sim_gaps[sims, behind] = sim_gaps[sims, ahead]
                        sim_gaps[sims, ahead] = tmp

        # Convert final gaps to finishing positions via argsort (fully vectorized)
        finish_positions = sim_gaps.argsort(axis=1).argsort(axis=1) + 1

        # DNF drivers get position = n_drivers + 1
        finish_positions[sim_dnf] = n_drivers + 1

        # Aggregate results
        results: Dict[str, Dict[str, float]] = {}
        for i, did in enumerate(driver_ids):
            positions = finish_positions[:, i]
            is_dnf = sim_dnf[:, i]
            n_classified = int((~is_dnf).sum())

            results[did] = {
                "win_prob": float((positions == 1).sum()) / n_sims,
                "podium_prob": float((positions <= 3).sum()) / n_sims,
                "points_prob": float(((positions <= 10) & ~is_dnf).sum()) / n_sims,
                "dnf_prob": float(is_dnf.sum()) / n_sims,
                "median_position": float(np.median(positions[~is_dnf])) if n_classified > 0 else float(n_drivers),
            }

        return results

    def _positions_to_probs(self, state: RaceState) -> Dict[str, Dict[str, float]]:
        """Convert final positions to near-certain probabilities (race is over)."""
        results: Dict[str, Dict[str, float]] = {}
        for did, ds in state.drivers.items():
            if ds.is_retired:
                results[did] = {"win_prob": 0.0, "podium_prob": 0.0, "points_prob": 0.0, "dnf_prob": 1.0}
            else:
                results[did] = {
                    "win_prob": 1.0 if ds.position == 1 else 0.0,
                    "podium_prob": 1.0 if ds.position <= 3 else 0.0,
                    "points_prob": 1.0 if ds.position <= 10 else 0.0,
                    "dnf_prob": 0.0,
                }
        return results

    def _compute_trend(self, driver_id: str, current_win_prob: float) -> str:
        """Compute trend over last 5 laps for a driver."""
        hist = self.history.get(driver_id)
        if not hist or len(hist.get("win_prob", [])) < 3:
            return "stable"

        recent = hist["win_prob"][-5:]
        if len(recent) < 2:
            return "stable"

        slope = recent[-1] - recent[0]
        if slope > 0.02:
            return "improving"
        elif slope < -0.02:
            return "declining"
        return "stable"

    def _record_history(self, lap: int, df: pd.DataFrame) -> None:
        """Record per-driver probabilities at this lap for sparkline charts."""
        for _, row in df.iterrows():
            did = row["driver_id"]
            if did not in self.history:
                self.history[did] = {"laps": [], "win_prob": [], "podium_prob": []}
            h = self.history[did]
            # Avoid duplicate lap entries
            if h["laps"] and h["laps"][-1] == lap:
                continue
            h["laps"].append(lap)
            h["win_prob"].append(float(row["live_win_prob"]))
            h["podium_prob"].append(float(row["live_podium_prob"]))

    def get_probability_history(self) -> Dict[str, Dict[str, List]]:
        """
        Return the full probability evolution over the race.

        Returns: {
            driver_id: {
                laps: [1, 2, 3, ...],
                win_prob: [0.18, 0.20, 0.25, ...],
                podium_prob: [0.61, 0.58, 0.72, ...],
            }
        }

        This powers the probability evolution sparklines on the dashboard.
        """
        return self.history

    # ------------------------------------------------------------------
    # What-If Scenario Simulator
    # ------------------------------------------------------------------

    def simulate_scenario(self, state: RaceState, scenario: dict) -> dict:
        """
        Simulate a what-if scenario from current race state.

        Clones the state, applies the scenario modifications, runs Monte Carlo
        on both original and modified states, and returns the diff.

        Args:
            state: Current RaceState
            scenario: Dict like {"type": "safety_car"} or
                      {"scenarios": [{"type": "safety_car"}, {"type": "driver_pits", ...}]}

        Returns dict with current, scenario, diff, biggest_movers, verdict, sim_count, elapsed_ms.
        """
        t0 = time.time()

        # Run MC on current state
        current_results = self._simulate_remaining(state)

        # Deep-copy and apply scenario
        modified = copy.deepcopy(state)
        scenarios = scenario.get("scenarios", [scenario])
        applied_labels = []
        for s in scenarios:
            label = self._apply_scenario(modified, s)
            if label:
                applied_labels.append(label)

        # Run MC on modified state
        scenario_results = self._simulate_remaining(modified)

        # Build probability dicts (_simulate_remaining returns *_prob in 0-1 scale)
        current_probs = {}
        scenario_probs = {}
        diff_probs = {}

        for did in current_results:
            c = current_results[did]
            s = scenario_results.get(did, c)
            c_win = c.get("win_prob", 0) * 100
            c_pod = c.get("podium_prob", 0) * 100
            c_pts = c.get("points_prob", 0) * 100
            s_win = s.get("win_prob", 0) * 100
            s_pod = s.get("podium_prob", 0) * 100
            s_pts = s.get("points_prob", 0) * 100

            current_probs[did] = {"win": round(c_win, 1), "podium": round(c_pod, 1), "points": round(c_pts, 1)}
            scenario_probs[did] = {"win": round(s_win, 1), "podium": round(s_pod, 1), "points": round(s_pts, 1)}
            diff_probs[did] = {
                "win": round(s_win - c_win, 1),
                "podium": round(s_pod - c_pod, 1),
                "points": round(s_pts - c_pts, 1),
            }

        # Handle retired drivers (in scenario but not current)
        for did in set(scenario_results.keys()) - set(current_results.keys()):
            s = scenario_results[did]
            scenario_probs[did] = {
                "win": round(s.get("win_prob", 0) * 100, 1),
                "podium": round(s.get("podium_prob", 0) * 100, 1),
                "points": round(s.get("points_prob", 0) * 100, 1),
            }

        # Find biggest movers by absolute win delta
        from data.ingest.live_feed import DRIVER_CODES, DRIVER_CONSTRUCTOR
        movers = []
        for did, d in sorted(diff_probs.items(), key=lambda x: abs(x[1]["win"]), reverse=True):
            movers.append({
                "driver_id": did,
                "code": DRIVER_CODES.get(did, did[:3].upper()),
                "team": DRIVER_CONSTRUCTOR.get(did, "unknown"),
                "delta_win": d["win"],
                "delta_podium": d["podium"],
                "current_win": current_probs.get(did, {}).get("win", 0),
                "scenario_win": scenario_probs.get(did, {}).get("win", 0),
            })

        verdict = self._generate_verdict(movers, applied_labels, state)
        elapsed_ms = int((time.time() - t0) * 1000)

        return {
            "current": current_probs,
            "scenario": scenario_probs,
            "diff": diff_probs,
            "biggest_movers": movers[:20],
            "verdict": verdict,
            "sim_count": self.n_sims,
            "elapsed_ms": elapsed_ms,
        }

    def _apply_scenario(self, state: RaceState, scenario: dict) -> Optional[str]:
        """Apply a single scenario modification to a RaceState. Returns label."""
        stype = scenario.get("type", "")

        if stype == "safety_car":
            state.track_status = "SafetyCar"
            # Compress gaps
            for did, ds in state.drivers.items():
                ds.gap_to_leader = min(ds.gap_to_leader, 1.5 * (ds.position - 1))
            return "Safety Car"

        elif stype == "vsc":
            state.track_status = "VirtualSafetyCar"
            return "VSC"

        elif stype == "red_flag":
            state.track_status = "RedFlag"
            # Reset gaps, allow fresh tyres
            for did, ds in state.drivers.items():
                ds.gap_to_leader = 0.0
                ds.tyre_age = 0
            return "Red Flag"

        elif stype == "rain":
            # Switch all to intermediates, increase chaos
            for did, ds in state.drivers.items():
                ds.tyre_compound = "INTERMEDIATE"
                ds.tyre_age = 0
            state._rain_scenario = True
            in_laps = scenario.get("in_laps", 0)
            return f"Rain (in {in_laps} laps)" if in_laps else "Rain"

        elif stype == "driver_pits":
            did = scenario.get("driver_id", "")
            if did in state.drivers:
                ds = state.drivers[did]
                ds.gap_to_leader += 22.0
                ds.tyre_age = 0
                ds.tyre_compound = scenario.get("compound", "MEDIUM")
                ds.pit_stops = (ds.pit_stops or 0) + 1
                self._recalculate_positions(state)
                from data.ingest.live_feed import DRIVER_CODES
                return f"{DRIVER_CODES.get(did, did[:3].upper())} Pits ({ds.tyre_compound})"

        elif stype == "driver_retires":
            did = scenario.get("driver_id", "")
            if did in state.drivers:
                del state.drivers[did]
                self._recalculate_positions(state)
                from data.ingest.live_feed import DRIVER_CODES
                return f"{DRIVER_CODES.get(did, did[:3].upper())} DNF"

        elif stype == "driver_penalty":
            did = scenario.get("driver_id", "")
            seconds = scenario.get("seconds", 5)
            if did in state.drivers:
                state.drivers[did].gap_to_leader += seconds
                self._recalculate_positions(state)
                from data.ingest.live_feed import DRIVER_CODES
                return f"{DRIVER_CODES.get(did, did[:3].upper())} +{seconds}s"

        elif stype == "driver_spin":
            did = scenario.get("driver_id", "")
            positions_lost = scenario.get("positions_lost", 3)
            if did in state.drivers:
                ds = state.drivers[did]
                ds.gap_to_leader += positions_lost * 2.5
                self._recalculate_positions(state)
                from data.ingest.live_feed import DRIVER_CODES
                return f"{DRIVER_CODES.get(did, did[:3].upper())} Spin (-{positions_lost})"

        return None

    @staticmethod
    def _recalculate_positions(state: RaceState):
        """Recalculate positions based on gap to leader."""
        sorted_drivers = sorted(state.drivers.values(), key=lambda d: d.gap_to_leader)
        for i, ds in enumerate(sorted_drivers):
            ds.position = i + 1

    @staticmethod
    def _generate_verdict(movers: list, labels: list, state: RaceState) -> str:
        """Generate a brief strategic insight about the scenario."""
        if not movers:
            return ""

        scenario_desc = " + ".join(labels) if labels else "Scenario"
        top = movers[0]
        bottom = movers[-1] if len(movers) > 1 else None

        parts = [f"{scenario_desc}: "]

        if top["delta_win"] > 5:
            parts.append(f"{top['code']} biggest winner (+{top['delta_win']:.1f}%)")
        elif top["delta_win"] > 0:
            parts.append(f"{top['code']} gains slightly (+{top['delta_win']:.1f}%)")

        if bottom and bottom["delta_win"] < -5:
            parts.append(f", {bottom['code']} hurt most ({bottom['delta_win']:.1f}%)")
        elif bottom and bottom["delta_win"] < -2:
            parts.append(f", {bottom['code']} loses ({bottom['delta_win']:.1f}%)")

        return "".join(parts)
