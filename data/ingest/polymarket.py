"""
Polymarket Integration — fetches F1 prediction markets from Polymarket's public API.

Polymarket is a decentralised prediction market where prices directly equal
implied probabilities (0.55 = 55% chance). No overround removal needed
(unlike traditional bookmakers).

Primary source: Gamma API (https://gamma-api.polymarket.com) — no API key required.

Outputs standardised DataFrames compatible with ValueDetector.find_value().

Usage:
    python -m data.ingest.polymarket              # Show active F1 markets
    python -m data.ingest.polymarket --compare     # Compare with model predictions
    python -m data.ingest.polymarket --snapshot 5  # Save snapshot for season round 5
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from src.shared import DRIVER_NAMES

logger = logging.getLogger(__name__)

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
CACHE_DIR = Path(__file__).parent.parent / "cache" / "polymarket"

# Polymarket uses full names — map to internal driver_ids
POLYMARKET_NAME_MAP = {
    "Max Verstappen": "max_verstappen",
    "Lando Norris": "norris",
    "Charles Leclerc": "leclerc",
    "Lewis Hamilton": "hamilton",
    "George Russell": "russell",
    "Oscar Piastri": "piastri",
    "Fernando Alonso": "alonso",
    "Lance Stroll": "stroll",
    "Pierre Gasly": "gasly",
    "Esteban Ocon": "ocon",
    "Alex Albon": "albon",
    "Nico Hulkenberg": "hulkenberg",
    "Nico Hülkenberg": "hulkenberg",
    "Valtteri Bottas": "bottas",
    "Sergio Perez": "perez",
    "Sergio Pérez": "perez",
    "Oliver Bearman": "bearman",
    "Ollie Bearman": "bearman",
    "Andrea Kimi Antonelli": "antonelli",
    "Kimi Antonelli": "antonelli",
    "Isack Hadjar": "hadjar",
    "Liam Lawson": "lawson",
    "Franco Colapinto": "colapinto",
    "Gabriel Bortoleto": "bortoleto",
    "Arvid Lindblad": "arvid_lindblad",
    "Carlos Sainz": "sainz",
    "Yuki Tsunoda": "tsunoda",
    "Daniel Ricciardo": "ricciardo",
    "Kevin Magnussen": "magnussen",
    "Guanyu Zhou": "zhou",
    "Logan Sargeant": "sargeant",
    "Jack Doohan": "doohan",
}

# Reverse lookup for display
_ID_TO_NAME = {v: k for k, v in POLYMARKET_NAME_MAP.items()}

# Common GP name patterns for matching market questions
_RACE_ALIASES = {
    "bahrain": ["bahrain"],
    "saudi": ["saudi", "jeddah"],
    "australia": ["australia", "melbourne"],
    "japan": ["japan", "suzuka"],
    "china": ["china", "shanghai"],
    "miami": ["miami"],
    "emilia": ["emilia", "imola"],
    "monaco": ["monaco"],
    "canada": ["canada", "montreal"],
    "spain": ["spain", "barcelona"],
    "austria": ["austria", "spielberg"],
    "britain": ["britain", "silverstone", "british"],
    "hungary": ["hungary", "hungaroring"],
    "belgium": ["belgium", "spa"],
    "netherlands": ["netherlands", "zandvoort", "dutch"],
    "italy": ["italy", "monza", "italian"],
    "azerbaijan": ["azerbaijan", "baku"],
    "singapore": ["singapore"],
    "usa": ["usa", "austin", "cota", "united states"],
    "mexico": ["mexico"],
    "brazil": ["brazil", "interlagos", "sao paulo"],
    "vegas": ["vegas", "las vegas"],
    "qatar": ["qatar", "lusail"],
    "abu dhabi": ["abu dhabi", "yas marina"],
}


def _resolve_driver_id(name: str) -> Optional[str]:
    """Map a Polymarket driver name to an internal driver_id."""
    # Exact match first
    if name in POLYMARKET_NAME_MAP:
        return POLYMARKET_NAME_MAP[name]

    # Case-insensitive match
    name_lower = name.lower().strip()
    for poly_name, driver_id in POLYMARKET_NAME_MAP.items():
        if poly_name.lower() == name_lower:
            return driver_id

    # Partial match — last name
    for poly_name, driver_id in POLYMARKET_NAME_MAP.items():
        if poly_name.split()[-1].lower() in name_lower:
            return driver_id

    logger.warning("Could not match Polymarket name %r to a driver_id", name)
    return None


def _match_race(question: str, race_name: Optional[str]) -> bool:
    """Check if a market question matches a specific race."""
    if race_name is None:
        return True

    q_lower = question.lower()
    race_lower = race_name.lower()

    # Direct substring match
    if race_lower in q_lower:
        return True

    # Check aliases
    for key, aliases in _RACE_ALIASES.items():
        if any(a in race_lower for a in aliases):
            if any(a in q_lower for a in aliases):
                return True

    return False


class PolymarketClient:
    """
    Fetches F1 prediction markets from Polymarket's public API.

    Polymarket API:
    - Markets list: GET https://gamma-api.polymarket.com/markets
      - Filter by: tag="f1" or search "Formula 1"
    - Market details include: question, outcomes, prices (= implied probabilities)
    - No API key needed for public read access
    """

    def __init__(self, timeout: int = 30):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.timeout = timeout
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _get_gamma(self, endpoint: str, params: Optional[dict] = None) -> list | dict:
        """Make a GET request to the Gamma API."""
        url = f"{GAMMA_URL}/{endpoint}"
        logger.debug("GET %s params=%s", url, params)
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _get_clob(self, endpoint: str, params: Optional[dict] = None) -> list | dict:
        """Make a GET request to the CLOB API."""
        url = f"{CLOB_URL}/{endpoint}"
        logger.debug("GET %s params=%s", url, params)
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def fetch_f1_markets(self) -> list[dict]:
        """
        Fetch all active F1 markets.

        Returns list of markets with: id, question, outcomes, prices, volume, end_date.
        Uses CLOB API (current) with Gamma API fallback.
        """
        markets = []
        seen_ids = set()

        # Primary: CLOB API — paginate through all active markets and filter for F1
        f1_keywords = {"formula 1", "f1", "grand prix", "gp winner", "race winner",
                       "verstappen", "norris", "leclerc", "hamilton", "constructor"}
        try:
            cursor = None
            for _ in range(10):  # max 10 pages
                params = {"limit": 100, "active": "true"}
                if cursor:
                    params["next_cursor"] = cursor
                data = self._get_clob("markets", params=params)
                items = data.get("data", data) if isinstance(data, dict) else data
                if not items:
                    break
                for m in (items if isinstance(items, list) else []):
                    q = (m.get("question") or m.get("description") or "").lower()
                    mid = m.get("condition_id") or m.get("id", "")
                    if mid in seen_ids:
                        continue
                    if any(kw in q for kw in f1_keywords):
                        seen_ids.add(mid)
                        markets.append(m)
                cursor = data.get("next_cursor") if isinstance(data, dict) else None
                if not cursor:
                    break
        except Exception as e:
            logger.debug("CLOB search failed: %s", e)

        # Fallback: Gamma API
        if not markets:
            for term in ["Formula 1", "F1 Grand Prix", "F1"]:
                try:
                    data = self._get_gamma("markets", params={
                        "closed": "false", "limit": 100, "active": "true", "tag": term,
                    })
                    if isinstance(data, list):
                        for m in data:
                            mid = m.get("id") or m.get("conditionId", "")
                            if mid and mid not in seen_ids:
                                seen_ids.add(mid)
                                markets.append(m)
                except Exception as e:
                    logger.debug("Gamma tag search %r failed: %s", term, e)

        # Filter to F1-related markets
        f1_markets = []
        f1_keywords = ["f1", "formula 1", "grand prix", "gp winner",
                        "world championship", "wdc", "wcc", "constructor"]
        for m in markets:
            q = (m.get("question") or "").lower()
            if any(kw in q for kw in f1_keywords):
                f1_markets.append(self._normalize_market(m))

        logger.info("Found %d active F1 markets", len(f1_markets))
        return f1_markets

    def _normalize_market(self, raw: dict) -> dict:
        """Extract consistent fields from a raw Gamma API market response."""
        # Parse outcomes and prices from the market data
        outcomes = []
        if "outcomes" in raw and "outcomePrices" in raw:
            outcome_names = raw["outcomes"]
            try:
                prices = json.loads(raw["outcomePrices"]) if isinstance(raw["outcomePrices"], str) else raw["outcomePrices"]
            except (json.JSONDecodeError, TypeError):
                prices = []

            if isinstance(outcome_names, str):
                try:
                    outcome_names = json.loads(outcome_names)
                except (json.JSONDecodeError, TypeError):
                    outcome_names = [outcome_names]

            for name, price in zip(outcome_names, prices):
                outcomes.append({
                    "name": name,
                    "price": float(price) if price else 0.0,
                })

        return {
            "id": raw.get("id") or raw.get("conditionId", ""),
            "question": raw.get("question", ""),
            "outcomes": outcomes,
            "volume": float(raw.get("volume", 0) or 0),
            "liquidity": float(raw.get("liquidity", 0) or 0),
            "end_date": raw.get("endDate") or raw.get("end_date_iso", ""),
            "active": raw.get("active", True),
            "closed": raw.get("closed", False),
        }

    def fetch_race_winner_market(self, race_name: str = None) -> Optional[pd.DataFrame]:
        """
        Fetch the race winner market for a specific GP.

        Args:
            race_name: GP name to match (e.g. "Monaco", "British").
                       If None, returns the first race winner market found.

        Returns:
            DataFrame with: driver_id, polymarket_prob, polymarket_volume
            Maps Polymarket driver names to internal driver_ids.
            Returns None if no matching market found.
        """
        markets = self.fetch_f1_markets()

        # Find race winner markets
        winner_keywords = ["win", "winner", "who will win"]
        race_markets = []
        for m in markets:
            q = m["question"].lower()
            if any(kw in q for kw in winner_keywords) and _match_race(m["question"], race_name):
                # Prefer markets with more outcomes (multi-driver markets, not Yes/No)
                if len(m["outcomes"]) > 2:
                    race_markets.append(m)

        if not race_markets:
            # Fall back to Yes/No style markets that might list individual drivers
            for m in markets:
                q = m["question"].lower()
                if _match_race(m["question"], race_name) and "championship" not in q:
                    race_markets.append(m)

        if not race_markets:
            logger.warning("No race winner market found for %s", race_name or "any race")
            return None

        # Use the market with the highest volume
        best_market = max(race_markets, key=lambda m: m["volume"])
        logger.info("Using market: %s (volume: $%.0f)", best_market["question"], best_market["volume"])

        rows = []
        for outcome in best_market["outcomes"]:
            name = outcome["name"]
            price = outcome["price"]

            # Skip "Other" or generic outcomes
            if name.lower() in ("other", "field", "none", "no", "yes"):
                continue

            driver_id = _resolve_driver_id(name)
            if driver_id is None:
                continue

            rows.append({
                "driver_id": driver_id,
                "polymarket_prob": price,
                "polymarket_volume": best_market["volume"],
            })

        if not rows:
            logger.warning("No driver matches found in market outcomes")
            return None

        df = pd.DataFrame(rows).sort_values("polymarket_prob", ascending=False).reset_index(drop=True)
        logger.info("Fetched %d drivers from Polymarket race winner market", len(df))
        return df

    def fetch_championship_market(self) -> Optional[pd.DataFrame]:
        """
        Fetch WDC/WCC championship winner markets.

        Returns:
            DataFrame with: entity (driver or team name), entity_id (driver_id or team),
            market_type (wdc/wcc), polymarket_prob, polymarket_volume
            Returns None if no championship market found.
        """
        markets = self.fetch_f1_markets()

        champ_keywords = ["championship", "wdc", "wcc", "world champion"]
        champ_markets = [
            m for m in markets
            if any(kw in m["question"].lower() for kw in champ_keywords)
        ]

        if not champ_markets:
            logger.warning("No championship markets found")
            return None

        rows = []
        for market in champ_markets:
            q_lower = market["question"].lower()
            market_type = "wcc" if any(kw in q_lower for kw in ["constructor", "wcc", "team"]) else "wdc"

            for outcome in market["outcomes"]:
                name = outcome["name"]
                price = outcome["price"]

                if name.lower() in ("other", "field", "none"):
                    continue

                entity_id = _resolve_driver_id(name) if market_type == "wdc" else name.lower().replace(" ", "_")

                rows.append({
                    "entity": name,
                    "entity_id": entity_id or name,
                    "market_type": market_type,
                    "polymarket_prob": price,
                    "polymarket_volume": market["volume"],
                })

        if not rows:
            return None

        return pd.DataFrame(rows).sort_values(
            ["market_type", "polymarket_prob"], ascending=[True, False]
        ).reset_index(drop=True)

    def compare_with_model(
        self,
        model_predictions: pd.DataFrame,
        race_name: str = None,
        min_edge: float = 0.0,
        kelly_fraction: float = 0.25,
    ) -> pd.DataFrame:
        """
        Compare model predictions with Polymarket prices.

        Args:
            model_predictions: DataFrame with driver_id and model_win_pct (or sim_win_pct).
            race_name: GP name to match on Polymarket.
            min_edge: Only include rows where edge > this threshold (0.0 = show all).
            kelly_fraction: Fractional Kelly multiplier (default 0.25 = quarter Kelly).

        Returns:
            DataFrame with:
            - driver_id, driver_name, model_pct, market_pct, edge, edge_pct, kelly_stake
            - Sorted by edge (highest value bets first)
        """
        polymarket_df = self.fetch_race_winner_market(race_name)
        if polymarket_df is None:
            logger.warning("No Polymarket data available for comparison")
            return pd.DataFrame()

        # Normalise model probability column
        pred = model_predictions.copy()
        if "sim_win_pct" in pred.columns and "model_win_pct" not in pred.columns:
            pred["model_win_pct"] = pred["sim_win_pct"] / 100.0
        if "model_win_pct" not in pred.columns:
            logger.error("model_predictions must have 'model_win_pct' or 'sim_win_pct' column")
            return pd.DataFrame()

        merged = pred[["driver_id", "model_win_pct"]].merge(
            polymarket_df[["driver_id", "polymarket_prob"]],
            on="driver_id",
            how="inner",
        )

        if merged.empty:
            logger.warning("No overlapping drivers between model and Polymarket")
            return pd.DataFrame()

        merged["edge"] = merged["model_win_pct"] - merged["polymarket_prob"]

        # Edge as percentage of market price
        merged["edge_pct"] = (merged["edge"] / merged["polymarket_prob"].clip(lower=0.001) * 100).round(1)

        # Quarter-Kelly stake sizing
        import numpy as np
        decimal_odds = np.where(merged["polymarket_prob"] > 0, 1.0 / merged["polymarket_prob"], 0.0)
        b = decimal_odds - 1.0
        kelly_full = np.where(b > 0, (b * merged["model_win_pct"] - (1.0 - merged["model_win_pct"])) / b, 0.0)
        kelly_full = np.maximum(kelly_full, 0.0)
        merged["kelly_stake"] = (kelly_full * kelly_fraction * 100).round(2)

        # Display columns
        merged["driver_name"] = merged["driver_id"].map(
            lambda d: DRIVER_NAMES.get(d, d.replace("_", " ").title())
        )
        merged["model_pct"] = (merged["model_win_pct"] * 100).round(1)
        merged["market_pct"] = (merged["polymarket_prob"] * 100).round(1)
        merged["edge"] = (merged["edge"] * 100).round(1)

        # Filter by minimum edge
        if min_edge > 0:
            merged = merged[merged["edge"] >= min_edge * 100]

        result = merged[[
            "driver_id", "driver_name", "model_pct", "market_pct",
            "edge", "edge_pct", "kelly_stake",
        ]].sort_values("edge", ascending=False).reset_index(drop=True)

        return result

    def save_snapshot(self, season: int, race_round: int):
        """
        Save current Polymarket odds to cache for CLV tracking.

        Saves both race winner and championship markets if available.
        """
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        race_df = self.fetch_race_winner_market()
        if race_df is not None:
            path = CACHE_DIR / f"race_{season}_R{race_round:02d}_{ts}.parquet"
            race_df.to_parquet(path, index=False)
            logger.info("Saved race snapshot to %s (%d rows)", path, len(race_df))

        champ_df = self.fetch_championship_market()
        if champ_df is not None:
            path = CACHE_DIR / f"champ_{season}_R{race_round:02d}_{ts}.parquet"
            champ_df.to_parquet(path, index=False)
            logger.info("Saved championship snapshot to %s (%d rows)", path, len(champ_df))

    def fetch_and_save(self, season: int, race_round: int):
        """Alias for save_snapshot — used by the prediction pipeline."""
        self.save_snapshot(season, race_round)

    def load_latest_snapshot(self, season: int, race_round: int) -> Optional[pd.DataFrame]:
        """Load the most recent race winner snapshot for a given round."""
        pattern = f"race_{season}_R{race_round:02d}_*.parquet"
        files = sorted(CACHE_DIR.glob(pattern))
        if not files:
            return None
        return pd.read_parquet(files[-1])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="F1 Polymarket Integration",
        prog="python -m data.ingest.polymarket",
    )
    parser.add_argument(
        "--compare", action="store_true",
        help="Compare Polymarket odds with latest model predictions",
    )
    parser.add_argument(
        "--race", type=str, default=None,
        help="Filter to a specific race (e.g. 'Monaco', 'British')",
    )
    parser.add_argument(
        "--snapshot", type=int, metavar="ROUND",
        help="Save Polymarket snapshot for given round (current season)",
    )
    parser.add_argument(
        "--championship", action="store_true",
        help="Show championship markets",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    client = PolymarketClient()

    if args.snapshot:
        season = datetime.now().year
        print(f"Saving Polymarket snapshot for {season} R{args.snapshot}...")
        client.save_snapshot(season, args.snapshot)
        print("Done.")

    elif args.championship:
        print("Fetching championship markets...")
        df = client.fetch_championship_market()
        if df is not None and not df.empty:
            for mtype in df["market_type"].unique():
                subset = df[df["market_type"] == mtype]
                label = "World Drivers' Championship" if mtype == "wdc" else "World Constructors' Championship"
                print(f"\n{label}:")
                print("-" * 50)
                for _, row in subset.iterrows():
                    prob = row["polymarket_prob"]
                    bar = "█" * int(prob * 40)
                    print(f"  {row['entity']:<25} {prob*100:5.1f}%  {bar}")
        else:
            print("No championship markets found on Polymarket.")

    elif args.compare:
        # Find latest prediction
        from src.shared import DATA_DIR
        pred_files = sorted(DATA_DIR.glob("prediction_*_R*.csv"), reverse=True)
        if not pred_files:
            print("No prediction files found. Run a prediction first.")
            raise SystemExit(1)

        latest = pred_files[0]
        # Extract season/round from filename
        parts = latest.stem.replace("prediction_", "").split("_R")
        season = int(parts[0])
        race_round = int(parts[1])

        print(f"Comparing model predictions ({season} R{race_round}) with Polymarket...")
        pred = pd.read_csv(latest)

        comparison = client.compare_with_model(pred, race_name=args.race)
        if comparison.empty:
            print("No comparison data available.")
        else:
            print(f"\n{'Driver':<18} {'Model%':>7} {'Mkt%':>7} {'Edge':>7} {'Edge%':>7} {'Kelly%':>7}")
            print("-" * 62)
            for _, row in comparison.iterrows():
                edge = row["edge"]
                edge_marker = "+" if edge > 0 else " "
                edge_color = "\033[32m" if edge > 0 else "\033[31m" if edge < 0 else ""
                reset = "\033[0m" if edge_color else ""
                print(
                    f"  {row['driver_name']:<16} {row['model_pct']:6.1f}% {row['market_pct']:6.1f}% "
                    f"{edge_color}{edge_marker}{edge:5.1f}%{reset} {row['edge_pct']:+6.1f}% {row['kelly_stake']:6.2f}%"
                )

            value_count = len(comparison[comparison["edge"] > 0])
            print(f"\n{value_count} value bet(s) detected.")

    else:
        # Default: show active F1 markets
        print("Fetching active F1 markets from Polymarket...\n")
        markets = client.fetch_f1_markets()

        if not markets:
            print("No active F1 markets found.")
        else:
            for m in sorted(markets, key=lambda x: x["volume"], reverse=True):
                print(f"  {m['question']}")
                print(f"  Volume: ${m['volume']:,.0f}  |  Liquidity: ${m['liquidity']:,.0f}")
                if m["outcomes"]:
                    top = sorted(m["outcomes"], key=lambda o: o["price"], reverse=True)[:5]
                    for o in top:
                        bar = "█" * int(o["price"] * 30)
                        print(f"    {o['name']:<25} {o['price']*100:5.1f}%  {bar}")
                print()

        # Also show race winner if available
        race_df = client.fetch_race_winner_market(args.race)
        if race_df is not None:
            print("\nRace Winner Probabilities (mapped to internal driver_ids):")
            print("-" * 45)
            for _, row in race_df.iterrows():
                name = DRIVER_NAMES.get(row["driver_id"], row["driver_id"])
                prob = row["polymarket_prob"]
                bar = "█" * int(prob * 40)
                print(f"  {name:<18} {prob*100:5.1f}%  {bar}")
