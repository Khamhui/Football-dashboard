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

    def fetch_historical_odds(self, season: int, event_id: str) -> pd.DataFrame:
        """
        Fetch historical odds from The Odds API.

        The Odds API historical endpoint: /v4/historical/sports/{sport}/odds
        Requires: date parameter (ISO 8601 format).

        This uses the historical odds endpoint which may require a paid plan.
        Falls back gracefully if not available.

        Args:
            season: Championship year (used for logging/context)
            event_id: ISO 8601 date string (e.g. "2025-03-16T12:00:00Z")
                      representing a point before the race start.

        Returns:
            DataFrame with standard odds columns, or empty DataFrame on failure.
        """
        try:
            data = self._get(
                f"historical/sports/{SPORT_KEY}/odds",
                params={
                    "regions": "eu",
                    "markets": "h2h",
                    "oddsFormat": "decimal",
                    "date": event_id,
                },
            )
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (401, 403, 422):
                logger.warning(
                    "Historical odds not available (plan limitation?) for %s: %s",
                    event_id, e,
                )
            else:
                logger.warning("Historical odds request failed for %s: %s", event_id, e)
            return pd.DataFrame(
                columns=["driver_id", "bookmaker", "decimal_odds", "implied_prob", "fair_prob"]
            )
        except Exception as e:
            logger.warning("Historical odds request failed for %s: %s", event_id, e)
            return pd.DataFrame(
                columns=["driver_id", "bookmaker", "decimal_odds", "implied_prob", "fair_prob"]
            )

        # The historical endpoint wraps data inside a "data" key
        odds_data = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(odds_data, dict):
            odds_data = odds_data.get("data", [])
        if not isinstance(odds_data, list):
            odds_data = []

        if not odds_data:
            logger.info("No historical odds returned for %s (season %d)", event_id, season)
            return pd.DataFrame(
                columns=["driver_id", "bookmaker", "decimal_odds", "implied_prob", "fair_prob"]
            )

        return self._parse_odds_response(odds_data)

    def backfill_season(self, season: int) -> dict:
        """
        Attempt to fetch odds for all races in a season.

        Gets race dates from the cached race_results parquet, then fetches
        historical odds for each race date (morning before the race).

        Returns:
            dict of {round_number: DataFrame or None}
        """
        results_path = CACHE_DIR / "race_results.parquet"
        if not results_path.exists():
            logger.error("race_results.parquet not found — run the ingest pipeline first")
            return {}

        rr = pd.read_parquet(results_path)
        season_races = rr[rr["season"] == season]

        if season_races.empty:
            logger.error("No race data found for season %d", season)
            return {}

        # Build unique (round, date) pairs
        race_schedule = (
            season_races.groupby("round")
            .agg(date=("date", "first"))
            .reset_index()
            .sort_values("round")
        )

        backfill_results = {}
        for _, row in race_schedule.iterrows():
            rnd = int(row["round"])
            race_date = str(row["date"])

            # Skip if already cached
            cached = self.load_odds(season, rnd)
            if cached is not None and not cached.empty:
                logger.info("Round %d already cached (%d rows) — skipping", rnd, len(cached))
                backfill_results[rnd] = cached
                continue

            # Build ISO 8601 timestamp: morning of race day (08:00 UTC)
            # This captures pre-race odds before the market closes
            date_str = race_date[:10]  # YYYY-MM-DD
            event_id = f"{date_str}T08:00:00Z"

            logger.info("Backfilling Round %d (date=%s)...", rnd, date_str)
            odds = self.fetch_historical_odds(season, event_id)

            if odds is not None and not odds.empty:
                self.save_odds(odds, season, rnd)
                backfill_results[rnd] = odds
                logger.info("  Round %d: %d rows saved", rnd, len(odds))
            else:
                backfill_results[rnd] = None
                logger.info("  Round %d: no odds available", rnd)

        # Summary
        found = sum(1 for v in backfill_results.values() if v is not None)
        total = len(backfill_results)
        logger.info("Backfill complete: %d/%d rounds with odds", found, total)

        return backfill_results

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
    import argparse

    parser = argparse.ArgumentParser(
        description="F1 Betting Odds Ingestion",
        prog="python -m data.ingest.odds",
    )
    parser.add_argument(
        "--backfill", type=int, metavar="SEASON",
        help="Attempt historical odds backfill for an entire season",
    )
    parser.add_argument(
        "--clv", type=int, metavar="SEASON",
        help="Evaluate CLV (Closing Line Value) for a season",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.clv:
        # CLV evaluation mode
        from data.models.value import evaluate_season_clv
        import json

        print(f"Evaluating CLV for season {args.clv}...")
        report = evaluate_season_clv(args.clv)

        if report.get("error"):
            print(f"Error: {report['error']}")
        else:
            print(f"\nSeason {args.clv} CLV Report")
            print("=" * 50)
            print(f"  Races evaluated:  {report.get('races_evaluated', 0)}")
            print(f"  Total bets:       {report.get('n_bets', 0)}")

            if report.get("n_bets", 0) > 0:
                print(f"  Avg CLV:          {report.get('avg_clv', 0):+.4f}")
                print(f"  CLV hit rate:     {report.get('clv_hit_rate', 0):.1%}")
                print(f"  Brier (model):    {report.get('brier_model', 0):.6f}")
                print(f"  Brier (market):   {report.get('brier_closing', 0):.6f}")
                print(f"  Brier advantage:  {report.get('brier_advantage', 0):+.6f}")

            if report.get("per_race"):
                print(f"\nPer-race Brier scores:")
                for r in report["per_race"]:
                    adv = r["brier_market"] - r["brier_model"]
                    marker = "+" if adv > 0 else " "
                    print(
                        f"  {r['race_id']}: model={r['brier_model']:.4f}  "
                        f"market={r['brier_market']:.4f}  "
                        f"advantage={marker}{adv:.4f}  winner={r['winner']}"
                    )

    elif args.backfill:
        # Historical backfill mode
        client = OddsClient()
        if not client.api_key:
            print("ODDS_API_KEY required for backfill.")
            print("Example: ODDS_API_KEY=abc123 python -m data.ingest.odds --backfill 2025")
            raise SystemExit(1)

        print(f"Backfilling odds for season {args.backfill}...")
        results = client.backfill_season(args.backfill)

        found = sum(1 for v in results.values() if v is not None)
        print(f"\nBackfill complete: {found}/{len(results)} rounds with odds")

        for rnd in sorted(results.keys()):
            df = results[rnd]
            if df is not None:
                consensus = client.consensus_odds(df)
                top = consensus.head(3)["driver_id"].tolist()
                print(f"  R{rnd:02d}: {len(df)} rows — top 3: {', '.join(top)}")
            else:
                print(f"  R{rnd:02d}: no odds available")

    else:
        # Default: fetch current race odds
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
