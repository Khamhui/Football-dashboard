"""
F1 Prediction Engine — Web Dashboard.

Local Flask app for browsing predictions, results, standings, and news.

Usage:
    python -m src.app              # Start on http://localhost:5050
    python -m src.app --port 8080  # Custom port
"""

from __future__ import annotations

import time

import feedparser
import pandas as pd
from flask import Flask, render_template, request, jsonify

from src.shared import (
    DATA_DIR,
    available_predictions,
    driver_name,
    get_event_name,
    load_prediction,
    team_color_hex,
    team_name,
)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Data loaders (parquet files — cached by mtime)
# ---------------------------------------------------------------------------

_cache: dict = {}
_cache_ts: dict = {}


def _load(name: str) -> pd.DataFrame:
    path = DATA_DIR / f"{name}.parquet"
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return pd.DataFrame()
    if name in _cache and _cache_ts.get(name) == mtime:
        return _cache[name]
    df = pd.read_parquet(path)
    _cache[name] = df
    _cache_ts[name] = mtime
    return df


# Make helpers available in templates
app.jinja_env.globals.update(
    driver_name=driver_name,
    team_color=team_color_hex,
    team_name=team_name,
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Predictions dashboard — main page."""
    preds = available_predictions()
    if not preds:
        return render_template("predictions.html", pred=None, event_name="No predictions yet", season=0, race_round=0, available=preds)

    season = request.args.get("season", type=int)
    race_round = request.args.get("round", type=int)

    if not season or not race_round:
        season, race_round, _ = preds[0]

    pred = load_prediction(season, race_round)
    event = get_event_name(season, race_round)

    # Merge team/grid context only if prediction exists
    if pred is not None:
        fm = _load("feature_matrix")
        ctx = fm[(fm["season"] == season) & (fm["round"] == race_round)][["driver_id", "constructor_id", "grid"]]
        if not ctx.empty:
            pred = pred.merge(ctx, on="driver_id", how="left")

    return render_template(
        "predictions.html",
        pred=pred,
        event_name=event,
        season=season,
        race_round=race_round,
        available=preds,
    )


@app.route("/results")
def results():
    """Race results history."""
    rr = _load("race_results")
    q = _load("qualifying")
    sp = _load("sprints")

    seasons = sorted(rr["season"].unique(), reverse=True) if not rr.empty else [2026]
    season = request.args.get("season", type=int, default=seasons[0])

    season_results = rr[rr["season"] == season].sort_values(["round", "position"])
    rounds = sorted(season_results["round"].unique())

    race_round = request.args.get("round", type=int, default=int(rounds[-1]) if rounds else 1)

    race = season_results[season_results["round"] == race_round].sort_values("position")
    quali = q[(q["season"] == season) & (q["round"] == race_round)].sort_values("position")
    sprint = sp[(sp["season"] == season) & (sp["round"] == race_round)].sort_values("position") if not sp.empty else pd.DataFrame()

    event = get_event_name(season, race_round)

    return render_template(
        "results.html",
        race=race,
        quali=quali,
        sprint=sprint,
        event_name=event,
        season=season,
        race_round=race_round,
        rounds=rounds,
        seasons=seasons,
    )


@app.route("/standings")
def standings():
    """Championship standings."""
    ds = _load("driver_standings")
    cs = _load("constructor_standings")

    seasons = sorted(ds["season"].unique(), reverse=True) if not ds.empty else [2026]
    season = request.args.get("season", type=int, default=seasons[0])

    driver_s = ds[ds["season"] == season]
    if not driver_s.empty:
        latest_round = driver_s["round"].max()
        driver_s = driver_s[driver_s["round"] == latest_round].sort_values("points", ascending=False)
        driver_s["position"] = range(1, len(driver_s) + 1)
    else:
        driver_s = pd.DataFrame()

    constructor_s = cs[cs["season"] == season]
    if not constructor_s.empty:
        latest_round = constructor_s["round"].max()
        constructor_s = constructor_s[constructor_s["round"] == latest_round].sort_values("points", ascending=False)
        constructor_s["position"] = range(1, len(constructor_s) + 1)
    else:
        constructor_s = pd.DataFrame()

    return render_template(
        "standings.html",
        drivers=driver_s,
        constructors=constructor_s,
        season=season,
        seasons=seasons,
    )


@app.route("/news")
def news():
    """RSS news feed."""
    return render_template("news.html")


# RSS cache — avoid re-fetching on every page load
_news_cache: list = []
_news_cache_time: float = 0
NEWS_CACHE_TTL = 300  # 5 minutes


@app.route("/api/news")
def api_news():
    """Fetch RSS feeds (called via JS to avoid blocking page load)."""
    global _news_cache, _news_cache_time

    if _news_cache and (time.time() - _news_cache_time) < NEWS_CACHE_TTL:
        return jsonify(_news_cache)

    feeds = [
        ("Formula 1", "https://www.formula1.com/content/fom-website/en/latest/all.xml"),
        ("Autosport", "https://www.autosport.com/rss/f1/news/"),
        ("Motorsport.com", "https://www.motorsport.com/rss/f1/news/"),
    ]

    articles = []
    for source_name, url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                articles.append({
                    "source": source_name,
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary": entry.get("summary", "")[:200],
                })
        except Exception:
            continue

    _news_cache = articles
    _news_cache_time = time.time()
    return jsonify(articles)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def start(port: int = 5050, open_browser: bool = True):
    """Start the dashboard server."""
    if open_browser:
        import webbrowser
        import threading
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F1 Dashboard")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    start(port=args.port, open_browser=not args.no_browser)
