"""Upload pipeline results to Supabase for the iOS app to consume."""

import os
import sys
import psycopg2
import psycopg2.extras
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.shared import DRIVER_NAMES, TEAM_SHORT as TEAM_NAMES

load_dotenv()

SUPABASE_DB_PASSWORD = os.environ["SUPABASE_DB_PASSWORD"]

DB_CONFIG = {
    "host": "db.krfhvkbavtfbhsadzhee.supabase.co",
    "port": 5432,
    "dbname": "postgres",
    "user": "postgres",
    "password": SUPABASE_DB_PASSWORD,
    "sslmode": "require",
}

DRIVER_TEAMS = {
    "max_verstappen": "red_bull", "hadjar": "red_bull",
    "norris": "mclaren", "piastri": "mclaren",
    "leclerc": "ferrari", "hamilton": "ferrari",
    "russell": "mercedes", "antonelli": "mercedes",
    "alonso": "aston_martin", "stroll": "aston_martin",
    "gasly": "alpine", "colapinto": "alpine",
    "albon": "williams", "sainz": "williams",
    "hulkenberg": "audi", "bortoleto": "audi",
    "ocon": "haas", "bearman": "haas",
    "perez": "cadillac", "bottas": "cadillac",
    "lawson": "rb", "arvid_lindblad": "rb",
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def upload_race(season: int, round_num: int, name: str, circuit_id: str,
                circuit_name: str, circuit_type: str = "mixed", country: str = ""):
    race_id = f"{season}-r{round_num:02d}-{circuit_id}"
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO races (id, season, round, name, circuit_id, circuit_name, circuit_type, country)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (season, round) DO UPDATE SET
            name = EXCLUDED.name, circuit_type = EXCLUDED.circuit_type
    """, (race_id, season, round_num, name, circuit_id, circuit_name, circuit_type, country))
    conn.commit()
    conn.close()
    print(f"Race uploaded: {race_id}")
    return race_id


def upload_predictions(race_id: str, csv_path: str):
    df = pd.read_csv(csv_path)
    conn = get_conn()
    cur = conn.cursor()

    rows = []
    for _, row in df.iterrows():
        did = row["driver_id"]
        confidence = "high" if row["prob_winner"] >= 0.10 else \
                     "moderate" if row["prob_winner"] >= 0.03 else \
                     "volatile" if row["prob_winner"] >= 0.005 else "coin_flip"
        rows.append((
            race_id, did, DRIVER_NAMES.get(did, did), DRIVER_TEAMS.get(did, "unknown"),
            float(row["predicted_position"]), float(row["prob_winner"]),
            float(row["prob_podium"]), float(row["prob_points"]),
            float(row["prob_dnf"]), float(row["sim_expected_points"]),
            int(row["sim_median_position"]), int(row["sim_position_25"]),
            int(row["sim_position_75"]), confidence,
        ))

    psycopg2.extras.execute_values(cur, """
        INSERT INTO predictions (race_id, driver_id, driver_name, team_id,
            predicted_position, prob_winner, prob_podium, prob_points,
            prob_dnf, expected_points, sim_median_position, sim_position_25,
            sim_position_75, confidence)
        VALUES %s
        ON CONFLICT (race_id, driver_id) DO UPDATE SET
            predicted_position = EXCLUDED.predicted_position,
            prob_winner = EXCLUDED.prob_winner,
            prob_podium = EXCLUDED.prob_podium,
            prob_points = EXCLUDED.prob_points,
            prob_dnf = EXCLUDED.prob_dnf,
            expected_points = EXCLUDED.expected_points,
            confidence = EXCLUDED.confidence
    """, rows)
    conn.commit()
    conn.close()
    print(f"Predictions uploaded: {len(rows)} drivers for {race_id}")


def upload_standings(season: int):
    ds = pd.read_parquet("data/cache/processed/driver_standings.parquet")
    latest = ds[ds["season"] == season]
    latest = latest[latest["round"] == latest["round"].max()]

    conn = get_conn()
    cur = conn.cursor()

    rows = []
    for _, row in latest.iterrows():
        did = row["driver_id"]
        rows.append((
            season, did, DRIVER_NAMES.get(did, did),
            DRIVER_TEAMS.get(did, row.get("constructor_id", "unknown")),
            int(row["position"]), float(row["points"]), int(row["wins"]),
        ))

    psycopg2.extras.execute_values(cur, """
        INSERT INTO standings (season, driver_id, driver_name, team_id, position, points, wins)
        VALUES %s
        ON CONFLICT (season, driver_id) DO UPDATE SET
            position = EXCLUDED.position, points = EXCLUDED.points,
            wins = EXCLUDED.wins, team_id = EXCLUDED.team_id,
            updated_at = NOW()
    """, rows)

    # Constructor standings
    cs = pd.read_parquet("data/cache/processed/constructor_standings.parquet")
    latest_c = cs[cs["season"] == season]
    latest_c = latest_c[latest_c["round"] == latest_c["round"].max()]

    c_rows = []
    for _, row in latest_c.iterrows():
        cid = row["constructor_id"]
        c_rows.append((
            season, cid, TEAM_NAMES.get(cid, cid),
            int(row["position"]), float(row["points"]),
        ))

    psycopg2.extras.execute_values(cur, """
        INSERT INTO constructor_standings (season, team_id, team_name, position, points)
        VALUES %s
        ON CONFLICT (season, team_id) DO UPDATE SET
            position = EXCLUDED.position, points = EXCLUDED.points,
            updated_at = NOW()
    """, c_rows)

    conn.commit()
    conn.close()
    print(f"Standings uploaded: {len(rows)} drivers, {len(c_rows)} constructors")


if __name__ == "__main__":
    # Upload 2026 races
    races = [
        (2026, 1, "Australian Grand Prix", "albert_park", "Albert Park", "mixed", "Australia"),
        (2026, 2, "Chinese Grand Prix", "shanghai", "Shanghai International Circuit", "mixed", "China"),
        (2026, 3, "Japanese Grand Prix", "suzuka", "Suzuka International Racing Course", "technical", "Japan"),
    ]
    for r in races:
        upload_race(*r)

    # Upload predictions
    for round_num in [2, 3]:
        csv_path = f"data/cache/processed/prediction_2026_R{round_num:02d}.csv"
        race_id = f"2026-r{round_num:02d}-{'shanghai' if round_num == 2 else 'suzuka'}"
        if os.path.exists(csv_path):
            upload_predictions(race_id, csv_path)

    # Upload standings
    upload_standings(2026)

    print("\nDone! All data uploaded to Supabase.")
