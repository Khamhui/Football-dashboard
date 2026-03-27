"""
Battery State of Charge (SOC) Estimation — 2026 F1 Regulations.

The battery SOC is not broadcast by F1. This module infers it from
observable telemetry (throttle, brake, speed) using the 2026 MGU-K physics.

2026 Power Unit specs:
- MGU-K max power: 350 kW (deploy)
- MGU-K max harvest: ~150 kW braking regen (peak)
- Battery capacity: ~4 MJ usable SOC delta
- Max harvest per lap: 8.5 MJ
- Deploy tapers above 290 km/h

The model tracks energy in / energy out between telemetry samples
and maintains a running SOC estimate per driver.
"""

from __future__ import annotations

import logging
from typing import Dict

logger = logging.getLogger(__name__)

MGUK_MAX_DEPLOY_KW = 350.0
MGUK_MAX_HARVEST_KW = 150.0
BATTERY_CAPACITY_KJ = 4000.0  # 4 MJ usable
DEPLOY_TAPER_SPEED_KPH = 290
SAMPLE_INTERVAL_S = 5.0

# Duty cycle: fraction of max power actually deployed on average.
# Street circuits have more braking zones (lower throttle duty), high-speed tracks
# have longer full-throttle sections. Derived from 2024 throttle trace analysis.
DEPLOY_DUTY_CYCLE = {
    "street": 0.30, "high_speed": 0.50, "technical": 0.35, "mixed": 0.40,
}
# Harvest efficiency: friction brakes absorb some energy before MGU-K can harvest.
HARVEST_EFFICIENCY = 0.6


class BatteryEstimator:
    """Estimates battery SOC for tracked drivers from telemetry."""

    def __init__(self, circuit_type: str = "mixed"):
        self._soc: Dict[str, float] = {}
        self._initialized: Dict[str, bool] = {}
        self._duty_cycle = DEPLOY_DUTY_CYCLE.get(circuit_type, 0.40)

    def update(self, driver_id: str, throttle: int, brake: int, speed: int,
               overtake_active: bool = False, dt: float = SAMPLE_INTERVAL_S) -> float:
        if driver_id not in self._initialized:
            self._soc[driver_id] = BATTERY_CAPACITY_KJ * 0.5
            self._initialized[driver_id] = True

        current_kj = self._soc[driver_id]

        if throttle > 10:
            throttle_frac = throttle / 100.0
            speed_factor = 1.0 if speed < DEPLOY_TAPER_SPEED_KPH else max(0.3, 1.0 - (speed - DEPLOY_TAPER_SPEED_KPH) / 60.0)
            boost_factor = 1.3 if overtake_active else 1.0
            deploy_kw = MGUK_MAX_DEPLOY_KW * throttle_frac * speed_factor * boost_factor * self._duty_cycle
            current_kj -= deploy_kw * dt

        if brake > 10:
            brake_frac = min(brake / 100.0, 1.0)
            harvest_kw = MGUK_MAX_HARVEST_KW * brake_frac * HARVEST_EFFICIENCY
            current_kj += harvest_kw * dt

        # Lift-off regen: small harvest when coasting (low throttle, no brake)
        if throttle < 10 and brake < 5 and speed > 50:
            current_kj += 15.0 * dt

        # Clamp to battery limits
        current_kj = max(0.0, min(BATTERY_CAPACITY_KJ, current_kj))
        self._soc[driver_id] = current_kj

        return (current_kj / BATTERY_CAPACITY_KJ) * 100.0

    def get_soc(self, driver_id: str) -> float:
        """Get current SOC estimate as percentage. Returns -1 if no data."""
        if driver_id not in self._soc:
            return -1.0
        return (self._soc[driver_id] / BATTERY_CAPACITY_KJ) * 100.0

    def reset(self, driver_id: str = None):
        """Reset SOC tracking for one or all drivers."""
        if driver_id:
            self._soc.pop(driver_id, None)
            self._initialized.pop(driver_id, None)
        else:
            self._soc.clear()
            self._initialized.clear()
