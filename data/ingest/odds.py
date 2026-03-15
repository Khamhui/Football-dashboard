"""
Betting Odds Ingestion — fetches pre-race winner odds from public sources.

Primary source: The Odds API (https://the-odds-api.com/) — free tier: 500 req/month.
Fallback: manual CSV import for historical odds.

Outputs a standardised DataFrame with columns:
    driver_id, bookmaker, decimal_odds, implied_prob, fair_prob
"""

from __future__ import annotations

import csv
import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from thefuzz import fuzz

from src.shared import DRIVER_NAMES

logger = logging.getLogger(__name__)

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SPORT_KEY = "motorsport_formula_one"
CACHE_DIR = Path(__file__).parent.parent / "cache" / "processed"
ODDS_CACHE_DIR = Path(__file__).parent.parent / "cache" / "odds"

# Minimum fuzzy-match score (0-100) to consider a bookmaker name a match
_FUZZY_THRESHOLD = 70


def _resolve_driver_id(bookmaker_name: str) -> Optional[str]:
    """Map a bookmaker's driver name to an internal driver_id via fuzzy matching."""
    best_score = 0
    best_id: Optional[str] = None

    name_lower = bookmaker_name.lower().strip()

    # Build lookup: driver_id → list of candidate strings to match against
    for driver_id, display_name in DRIVER_NAMES.items():
        candidates = [
            display_name.lower(),
            driver_id.replace("_", " "),
        ]
        for candidate in candidates:
            score = fuzz.token_sort_ratio(name_lower, candidate)
            if score > best_score:
                best_score = score
                best_id = driver_id

    if best_score >= _FUZZY_THRESHOLD:
        return best_id

    logger.warning("Could not match bookmaker name %r (best score %d)", bookmaker_name, best_score)
    return None


class OddsClient:
    """Client for fetching and processing F1 betting odds."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ODDS_API_KEY")
        self.session = requests.Session()
        ODDS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ── API Methods ───────────────────────────────────────────────

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make an authenticated request to The Odds API."""
        if not self.api_key:
            raise ValueError(
                "ODDS_API_KEY not set. Provide it via constructor or env var, "
                "or use load_odds() / import_csv() for cached/offline data."
            )

        url = f"{ODDS_API_BASE}/{endpoint}"
        all_params = {"apiKey": self.api_key}
        if params:
            all_params.update(params)

        logger.debug("GET %s", url)
        resp = self.session.get(url, params=all_params, timeout=30)
        resp.raise_for_status()

        remaining = resp.headers.get("x-requests-remaining", "?")
        logger.info("Odds API requests remaining: %s", remaining)

        return resp.json()

    def fetch_current_odds(self) -> pd.DataFrame:
        """
        Get odds for the next upcoming F1 race.

        Returns:
            DataFrame with columns: driver_id, bookmaker, decimal_odds,
            implied_prob, fair_prob
        """
        data = self._get(
            f"sports/{SPORT_KEY}/odds",
            params={"regions": "eu", "markets": "h2h", "oddsFormat": "decimal"},
        )

        if not data:
            logger.warning("No upcoming race odds found")
            return pd.DataFrame(
                columns=["driver_id", "bookmaker", "decimal_odds", "implied_prob", "fair_prob"]
            )

        return self._parse_odds_response(data)

    def fetch_race_winner_odds(self, season: int, race_round: int) -> pd.DataFrame:
        """
        Get pre-race winner odds for a specific race.

        The Odds API free tier only covers upcoming events. For historical
        races, this checks the local cache first and falls back to the
        live API (which may not have the data).

        Args:
            season: Championship year
            race_round: Round number in the season

        Returns:
            DataFrame with columns: driver_id, bookmaker, decimal_odds,
            implied_prob, fair_prob
        """
        cached = self.load_odds(season, race_round)
        if cached is not None:
            return cached

        # The free tier only has upcoming events — try anyway
        logger.info("Fetching live odds (season=%d, round=%d)", season, race_round)
        df = self.fetch_current_odds()

        if not df.empty:
            self.save_odds(df, season, race_round)

        return df

    def _parse_odds_response(self, data: list[dict]) -> pd.DataFrame:
        """Parse The Odds API JSON into a standardised DataFrame."""
        rows = []

        for event in data:
            for bookmaker_data in event.get("bookmakers", []):
                bookmaker_name = bookmaker_data.get("title", "unknown")
                for market in bookmaker_data.get("markets", []):
                    if market.get("key") != "h2h":
                        continue
                    for outcome in market.get("outcomes", []):
                        driver_id = _resolve_driver_id(outcome["name"])
                        if driver_id is None:
                            continue
                        decimal_odds = float(outcome["price"])
                        rows.append({
                            "driver_id": driver_id,
                            "bookmaker": bookmaker_name,
                            "decimal_odds": decimal_odds,
                            "implied_prob": self.odds_to_implied_probability(decimal_odds),
                        })

        if not rows:
            return pd.DataFrame(
                columns=["driver_id", "bookmaker", "decimal_odds", "implied_prob", "fair_prob"]
            )

        df = pd.DataFrame(rows)

        # Compute fair probabilities per bookmaker (remove overround)
        fair_dfs = []
        for bk, group in df.groupby("bookmaker"):
            group = group.copy()
            group["fair_prob"] = self.remove_overround(group["implied_prob"])
            fair_dfs.append(group)

        return pd.concat(fair_dfs, ignore_index=True)

    # ── Probability Helpers ───────────────────────────────────────

    @staticmethod
    def odds_to_implied_probability(decimal_odds: float) -> float:
        """Convert European decimal odds to implied probability."""
        if decimal_odds <= 0:
            return 0.0
        return 1.0 / decimal_odds

    @staticmethod
    def remove_overround(probs: pd.Series) -> pd.Series:
        """
        Remove bookmaker margin by normalising implied probabilities to sum to 1.

        Args:
            probs: Series of implied probabilities (typically sum > 1)

        Returns:
            Series of fair probabilities (sum = 1)
        """
        total = probs.sum()
        if total == 0:
            return probs
        return probs / total

    # ── Persistence ───────────────────────────────────────────────

    def save_odds(self, odds: pd.DataFrame, season: int, race_round: int) -> Path:
        """
        Save odds DataFrame to parquet.

        Args:
            odds: DataFrame with odds data
            season: Championship year
            race_round: Round number

        Returns:
            Path to the saved file
        """
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = CACHE_DIR / f"odds_{season}_R{race_round:02d}.parquet"
        odds.to_parquet(path, index=False)
        logger.info("Saved odds to %s (%d rows)", path, len(odds))
        return path

    def load_odds(self, season: int, race_round: int) -> Optional[pd.DataFrame]:
        """
        Load odds from the local parquet cache.

        Args:
            season: Championship year
            race_round: Round number

        Returns:
            DataFrame if cached file exists, else None
        """
        path = CACHE_DIR / f"odds_{season}_R{race_round:02d}.parquet"
        if path.exists():
            logger.debug("Loading cached odds from %s", path)
            return pd.read_parquet(path)
        return None

    # ── CSV Fallback ──────────────────────────────────────────────

    def import_csv(
        self,
        csv_path: str | Path,
        season: int,
        race_round: int,
        driver_col: str = "driver",
        odds_col: str = "decimal_odds",
        bookmaker_col: Optional[str] = "bookmaker",
    ) -> pd.DataFrame:
        """
        Import historical odds from a CSV file.

        Expected CSV columns (configurable):
            driver — bookmaker's driver name (fuzzy-matched to driver_id)
            decimal_odds — European decimal odds
            bookmaker — (optional) bookmaker name, defaults to "csv_import"

        Args:
            csv_path: Path to the CSV file
            season: Championship year to tag the data with
            race_round: Round number
            driver_col: Column name for driver names
            odds_col: Column name for decimal odds
            bookmaker_col: Column name for bookmaker (None = use default)

        Returns:
            DataFrame with standardised columns, also saved to cache
        """
        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        raw = pd.read_csv(csv_path)
        logger.info("Importing %d rows from %s", len(raw), csv_path)

        rows = []
        for _, row in raw.iterrows():
            driver_id = _resolve_driver_id(str(row[driver_col]))
            if driver_id is None:
                continue

            decimal_odds = float(row[odds_col])
            bookmaker = str(row.get(bookmaker_col, "csv_import")) if bookmaker_col and bookmaker_col in raw.columns else "csv_import"

            rows.append({
                "driver_id": driver_id,
                "bookmaker": bookmaker,
                "decimal_odds": decimal_odds,
                "implied_prob": self.odds_to_implied_probability(decimal_odds),
            })

        if not rows:
            logger.warning("No rows matched from CSV")
            return pd.DataFrame(
                columns=["driver_id", "bookmaker", "decimal_odds", "implied_prob", "fair_prob"]
            )

        df = pd.DataFrame(rows)

        # Fair probs per bookmaker
        fair_dfs = []
        for _, group in df.groupby("bookmaker"):
            group = group.copy()
            group["fair_prob"] = self.remove_overround(group["implied_prob"])
            fair_dfs.append(group)

        df = pd.concat(fair_dfs, ignore_index=True)
        self.save_odds(df, season, race_round)

        return df

    # ── Aggregation ───────────────────────────────────────────────

    @staticmethod
    def consensus_odds(odds: pd.DataFrame) -> pd.DataFrame:
        """
        Average fair probabilities across bookmakers for each driver.

        Args:
            odds: Full odds DataFrame (may have multiple bookmakers)

        Returns:
            DataFrame with one row per driver_id: driver_id, market_win_pct,
            avg_decimal_odds, n_bookmakers
        """
        if odds.empty:
            return pd.DataFrame(columns=["driver_id", "market_win_pct", "avg_decimal_odds", "n_bookmakers"])

        agg = (
            odds.groupby("driver_id")
            .agg(
                market_win_pct=("fair_prob", "mean"),
                avg_decimal_odds=("decimal_odds", "mean"),
                n_bookmakers=("bookmaker", "nunique"),
            )
            .reset_index()
            .sort_values("market_win_pct", ascending=False)
        )

        # Re-normalise after averaging
        total = agg["market_win_pct"].sum()
        if total > 0:
            agg["market_win_pct"] = agg["market_win_pct"] / total

        return agg


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    client = OddsClient()

    if client.api_key:
        print("Fetching current odds from The Odds API...")
        df = client.fetch_current_odds()
        if not df.empty:
            consensus = client.consensus_odds(df)
            print("\nConsensus market probabilities:")
            print(consensus.to_string(index=False))
        else:
            print("No odds returned (no upcoming race?)")
    else:
        print("ODDS_API_KEY not set. Use import_csv() or set the env var.")
        print("Example: ODDS_API_KEY=abc123 python -m data.ingest.odds")
