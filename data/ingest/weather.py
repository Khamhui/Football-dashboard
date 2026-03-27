"""
Weather Forecast Ingestion — fetches race-weekend weather from Open-Meteo.

Open-Meteo is free, no API key needed (10,000 requests/day).
Two endpoints:
  - Historical forecast API (2021+): what the forecast WAS before the race
  - Current forecast API: 16-day ahead forecast for upcoming races

These are FORECAST features — what a bettor would know pre-race.
Different from FastF1 actual weather (measured during the session).
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "cache" / "weather"

# Open-Meteo endpoints
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
CURRENT_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Rate limit: be polite (free tier)
_REQUEST_DELAY = 0.3  # seconds between requests

# Lat/lon for every circuit in CIRCUIT_TYPES
CIRCUIT_COORDS: dict[str, tuple[float, float]] = {
    "albert_park": (-37.8497, 144.968),
    "bahrain": (26.0325, 50.5106),
    "jeddah": (21.6319, 39.1044),
    "suzuka": (34.8431, 136.541),
    "shanghai": (31.3389, 121.220),
    "miami": (25.9581, -80.2389),
    "imola": (44.3439, 11.7167),
    "monaco": (43.7347, 7.4206),
    "villeneuve": (45.5000, -73.5228),
    "catalunya": (41.5700, 2.2611),
    "red_bull_ring": (47.2197, 14.7647),
    "silverstone": (52.0786, -1.0169),
    "hungaroring": (47.5789, 19.2486),
    "spa": (50.4372, 5.9714),
    "zandvoort": (52.3888, 4.5409),
    "monza": (45.6156, 9.2811),
    "baku": (40.3725, 49.8533),
    "marina_bay": (1.2914, 103.864),
    "americas": (30.1328, -97.6411),
    "rodriguez": (19.4042, -99.0907),
    "interlagos": (-23.7036, -46.6997),
    "vegas": (36.1162, -115.174),
    "losail": (25.4900, 51.4542),
    "yas_marina": (24.4672, 54.6031),
    # Historic circuits (2018-2021)
    "ricard": (43.2506, 5.7917),
    "hockenheimring": (49.3278, 8.5656),
    "sochi": (43.4057, 39.9578),
    "mugello": (43.9975, 11.3719),
    "nurburgring": (50.3356, 6.9475),
    "portimao": (37.2270, -8.6267),
    "istanbul": (40.9517, 29.4050),
}

# Default race start hour (local time) — most F1 races start around 14:00-15:00
_DEFAULT_RACE_HOUR = 14

# Hourly variables (forecast API has precipitation_probability; archive API doesn't)
_FORECAST_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation_probability",
    "precipitation",
    "cloud_cover",
    "wind_speed_10m",
]
_ARCHIVE_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "cloud_cover",
    "wind_speed_10m",
]


class WeatherForecastClient:
    """Fetches weather forecasts for F1 circuits from Open-Meteo."""

    def __init__(self):
        self.session = requests.Session()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def fetch_race_forecast(
        self,
        circuit_id: str,
        race_date: str,
        race_hour: int = _DEFAULT_RACE_HOUR,
    ) -> Optional[dict]:
        """
        Fetch weather forecast for a race weekend.

        Uses Open-Meteo's historical forecast API (for past dates, 2021+)
        or current forecast API (for future dates within 16 days).

        Args:
            circuit_id: e.g. "silverstone"
            race_date: ISO date string "2026-03-15"
            race_hour: local hour for race start (default 14)

        Returns dict with:
            forecast_temp: predicted air temperature (C)
            forecast_rain_prob: precipitation probability (0-100)
            forecast_wind_speed: wind speed (km/h)
            forecast_humidity: relative humidity (%)
            forecast_cloud_cover: cloud cover (%)
            forecast_precip_mm: predicted precipitation (mm)
        Or None if data unavailable.
        """
        coords = CIRCUIT_COORDS.get(circuit_id)
        if coords is None:
            logger.warning("No coordinates for circuit %s", circuit_id)
            return None

        lat, lon = coords
        target = date.fromisoformat(race_date)
        today = date.today()

        if target <= today:
            # Archive API — actual weather data (available back to ~2000)
            url = ARCHIVE_URL
            params = {
                "latitude": lat,
                "longitude": lon,
                "start_date": target.isoformat(),
                "end_date": target.isoformat(),
                "hourly": ",".join(_ARCHIVE_VARS),
            }
            return self._fetch_and_extract(url, params, target, race_hour, circuit_id, is_archive=True)
        elif (target - today).days <= 16:
            # Current forecast for upcoming race
            url = CURRENT_FORECAST_URL
            params = {
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(_FORECAST_VARS),
                "forecast_days": 16,
            }
            return self._fetch_and_extract(url, params, target, race_hour, circuit_id, is_archive=False)
        else:
            logger.debug(
                "Date %s out of range for circuit %s (future needs <=16 days)",
                race_date,
                circuit_id,
            )
            return None

    def fetch_historical_forecasts(self, season: int) -> pd.DataFrame:
        """
        Backfill race-weekend forecasts for a full season.

        Fetches the 3-day-ahead forecast for each race date (2021+ only).
        Caches results to data/cache/weather/forecast_{season}.parquet.

        Returns DataFrame with columns:
            season, round, circuit_id, forecast_temp, forecast_rain_prob,
            forecast_wind_speed, forecast_humidity, forecast_cloud_cover,
            forecast_precip_mm
        """
        cache_path = CACHE_DIR / f"forecast_{season}.parquet"
        if cache_path.exists():
            logger.info("Loading cached weather forecasts for %d", season)
            return pd.read_parquet(cache_path)

        # Get the race schedule from Jolpica cached results
        schedule = self._load_season_schedule(season)
        if schedule.empty:
            logger.warning("No schedule found for %d — cannot fetch weather", season)
            return pd.DataFrame()

        rows = []
        for _, race in schedule.iterrows():
            circuit_id = race["circuit_id"]
            race_date = race["date"]
            rnd = int(race["round"])

            forecast = self.fetch_race_forecast(circuit_id, race_date)
            if forecast is not None:
                forecast["season"] = season
                forecast["round"] = rnd
                forecast["circuit_id"] = circuit_id
                rows.append(forecast)
                logger.debug(
                    "  %d R%02d %s: %.1f°C, %d%% rain",
                    season,
                    rnd,
                    circuit_id,
                    forecast["forecast_temp"],
                    forecast["forecast_rain_prob"],
                )
            else:
                logger.debug("  %d R%02d %s: no forecast available", season, rnd, circuit_id)

            time.sleep(_REQUEST_DELAY)

        df = pd.DataFrame(rows)
        if not df.empty:
            df.to_parquet(cache_path, index=False)
            logger.info("Cached %d weather forecasts for %d → %s", len(df), season, cache_path)
        else:
            logger.warning("No weather forecasts retrieved for %d", season)

        return df

    def fetch_current_forecast(self, circuit_id: str) -> Optional[dict]:
        """
        Fetch current 16-day forecast for an upcoming race circuit.

        Returns the same dict format as fetch_race_forecast, but picks
        the closest future date with data.
        """
        coords = CIRCUIT_COORDS.get(circuit_id)
        if coords is None:
            logger.warning("No coordinates for circuit %s", circuit_id)
            return None

        lat, lon = coords
        today = date.today()

        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(_FORECAST_VARS),
            "forecast_days": 16,
        }

        try:
            resp = self.session.get(CURRENT_FORECAST_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("Failed to fetch forecast for %s: %s", circuit_id, e)
            return None

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            return None

        # Build a DataFrame for easy slicing
        forecast_df = pd.DataFrame({"time": pd.to_datetime(times)})
        for var in _FORECAST_VARS:
            forecast_df[var] = hourly.get(var, [None] * len(times))

        # Return the full 16-day hourly forecast as a summary per day
        daily_rows = []
        for day_date, day_group in forecast_df.groupby(forecast_df["time"].dt.date):
            race_hour_row = day_group[day_group["time"].dt.hour == _DEFAULT_RACE_HOUR]
            if race_hour_row.empty:
                race_hour_row = day_group.iloc[len(day_group) // 2 : len(day_group) // 2 + 1]
            if race_hour_row.empty:
                continue
            r = race_hour_row.iloc[0]
            daily_rows.append({
                "date": str(day_date),
                "forecast_temp": r.get("temperature_2m"),
                "forecast_rain_prob": r.get("precipitation_probability"),
                "forecast_wind_speed": r.get("wind_speed_10m"),
                "forecast_humidity": r.get("relative_humidity_2m"),
                "forecast_cloud_cover": r.get("cloud_cover"),
                "forecast_precip_mm": r.get("precipitation"),
            })

        if not daily_rows:
            return None

        return {
            "circuit_id": circuit_id,
            "fetched_at": datetime.utcnow().isoformat(),
            "daily": daily_rows,
        }

    # ── Internal helpers ──────────────────────────────────────────────

    def _fetch_and_extract(
        self,
        url: str,
        params: dict,
        target_date: date,
        race_hour: int,
        circuit_id: str,
        is_archive: bool = False,
    ) -> Optional[dict]:
        """Make the API request and extract the race-hour forecast."""
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("Weather API error for %s on %s: %s", circuit_id, target_date, e)
            return None

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            logger.debug("No hourly data returned for %s on %s", circuit_id, target_date)
            return None

        # Find the target datetime (race day at race_hour)
        target_dt_str = f"{target_date.isoformat()}T{race_hour:02d}:00"

        # Find closest matching hour
        idx = None
        for i, t in enumerate(times):
            if t == target_dt_str:
                idx = i
                break

        if idx is None:
            # Fallback: find closest time on race day
            target_prefix = target_date.isoformat()
            candidates = [(i, t) for i, t in enumerate(times) if t.startswith(target_prefix)]
            if candidates:
                # Pick hour closest to race_hour
                idx = min(candidates, key=lambda x: abs(int(x[1][11:13]) - race_hour))[0]

        if idx is None:
            logger.debug("Could not find race-hour data for %s on %s", circuit_id, target_date)
            return None

        def _safe_get(var: str) -> Optional[float]:
            vals = hourly.get(var, [])
            return vals[idx] if idx < len(vals) and vals[idx] is not None else None

        precip_mm = _safe_get("precipitation")
        if is_archive:
            # Archive API has no precipitation_probability — derive from actual precip
            # >0.1mm = likely rain, scale up to 100% at 5mm+
            rain_prob = min(100.0, (precip_mm or 0.0) * 20.0) if precip_mm else 0.0
        else:
            rain_prob = _safe_get("precipitation_probability")

        return {
            "forecast_temp": _safe_get("temperature_2m"),
            "forecast_rain_prob": rain_prob,
            "forecast_wind_speed": _safe_get("wind_speed_10m"),
            "forecast_humidity": _safe_get("relative_humidity_2m"),
            "forecast_cloud_cover": _safe_get("cloud_cover"),
            "forecast_precip_mm": precip_mm,
        }

    @staticmethod
    def _load_season_schedule(season: int) -> pd.DataFrame:
        """
        Load race schedule for a season from cached Jolpica data or FastF1.

        Returns DataFrame with columns: round, circuit_id, date
        """
        # Try Jolpica cached results first (has date + circuit_id)
        jolpica_dir = Path(__file__).parent.parent / "cache" / "jolpica"
        results_file = jolpica_dir / f"{season}_results_Races_L100_O0.json"

        if results_file.exists():
            import json
            with open(results_file) as f:
                data = json.load(f)

            races_raw = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
            seen = set()
            rows = []
            for race in races_raw:
                rnd = int(race["round"])
                if rnd in seen:
                    continue
                seen.add(rnd)
                rows.append({
                    "round": rnd,
                    "circuit_id": race["Circuit"]["circuitId"],
                    "date": race["date"],
                })

            if rows:
                return pd.DataFrame(rows).sort_values("round").reset_index(drop=True)

        # Fallback: scan all Jolpica cache files for this season
        if jolpica_dir.exists():
            import json
            seen = set()
            rows = []
            for path in sorted(jolpica_dir.glob(f"{season}_results_*.json")):
                try:
                    with open(path) as f:
                        data = json.load(f)
                    races_raw = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
                    for race in races_raw:
                        rnd = int(race["round"])
                        if rnd in seen:
                            continue
                        seen.add(rnd)
                        rows.append({
                            "round": rnd,
                            "circuit_id": race["Circuit"]["circuitId"],
                            "date": race["date"],
                        })
                except Exception:
                    continue

            if rows:
                return pd.DataFrame(rows).sort_values("round").reset_index(drop=True)

        # Last resort: FastF1 schedule
        try:
            import fastf1
            schedule = fastf1.get_event_schedule(season, include_testing=False)
            rows = []
            for _, event in schedule.iterrows():
                rnd = event.get("RoundNumber", 0)
                if rnd == 0:
                    continue
                # FastF1 uses Location/Country, but we need circuit_id
                # Use EventDate for the date
                event_date = event.get("EventDate")
                if hasattr(event_date, "date"):
                    event_date = event_date.date()
                circuit_name = str(event.get("Location", "")).lower().replace(" ", "_")
                rows.append({
                    "round": int(rnd),
                    "circuit_id": circuit_name,
                    "date": str(event_date),
                })
            if rows:
                return pd.DataFrame(rows).sort_values("round").reset_index(drop=True)
        except Exception as e:
            logger.warning("FastF1 schedule fallback failed: %s", e)

        return pd.DataFrame()


def build_weather_forecast_index(
    data_dir: Path,
) -> dict[tuple[int, int], dict]:
    """
    Load cached weather forecast parquet files and build a feature index.

    Returns dict: (season, round) -> {forecast_temp, forecast_rain_prob, ...}
    """
    weather_dir = Path(__file__).parent.parent / "cache" / "weather"
    if not weather_dir.exists():
        return {}

    index: dict[tuple[int, int], dict] = {}
    for path in sorted(weather_dir.glob("forecast_*.parquet")):
        try:
            df = pd.read_parquet(path)
            if df.empty:
                continue
            for _, row in df.iterrows():
                key = (int(row["season"]), int(row["round"]))
                index[key] = {
                    "forecast_temp": row.get("forecast_temp"),
                    "forecast_rain_prob": row.get("forecast_rain_prob"),
                    "forecast_wind_speed": row.get("forecast_wind_speed"),
                }
        except Exception as e:
            logger.warning("Failed to load weather file %s: %s", path.name, e)

    if index:
        n_seasons = len({s for s, _ in index})
        logger.info("Loaded weather forecasts for %d races across %d seasons", len(index), n_seasons)
    return index


# ── CLI entrypoint ────────────────────────────────────────────────

def main():
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Fetch Open-Meteo weather forecasts for F1 race weekends.",
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season year to backfill (2021+)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch even if cache exists",
    )
    args = parser.parse_args()

    client = WeatherForecastClient()

    if args.force:
        cache_path = CACHE_DIR / f"forecast_{args.season}.parquet"
        if cache_path.exists():
            cache_path.unlink()
            logger.info("Removed cached file %s", cache_path)

    df = client.fetch_historical_forecasts(args.season)
    if df.empty:
        logger.warning("No forecasts retrieved for %d", args.season)
    else:
        logger.info(
            "Done: %d forecasts for %d\n%s",
            len(df),
            args.season,
            df[["round", "circuit_id", "forecast_temp", "forecast_rain_prob"]].to_string(index=False),
        )


if __name__ == "__main__":
    main()
