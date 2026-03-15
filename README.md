# F1 Prediction Engine

AI-powered Formula 1 race prediction system using 75 years of historical data, multi-dimensional ELO ratings, Monte Carlo simulation, and XGBoost machine learning.

Inspired by [theGreenCoding's tennis prediction model](https://github.com/theGreenCoding) that achieved 85% accuracy at the Australian Open.

## What It Predicts

- **Race winner** and full finishing order (XGBoost + stacking ensemble)
- **Win / podium / points probabilities** via 10,000 Monte Carlo simulations
- **Expected points** and position confidence ranges (25th–75th percentile)
- **DNF risk** per driver (circuit-type aware)
- **Head-to-head** matchups between any two drivers
- **ELO power rankings** across 6 dimensions with trend sparklines

## How It Works

### Data Pipeline

```
Ingest (3 sources) → Feature Engineering (81+ features) → XGBoost Train → Predict → Monte Carlo Sim → Dashboard
```

### Data Sources

| Source | Coverage | Data |
|--------|----------|------|
| **Jolpica-F1** | 1950–present | Race results, qualifying, standings, circuits, pit stops, lap times |
| **FastF1** | 2018+ | Granular lap data, tire compounds, sector times, speed traps, weather, telemetry |
| **OpenF1** | 2023+ | Real-time telemetry (3.7Hz), overtakes, intervals, live positions |

### ELO Rating System

Adapted from chess for multi-player motorsport — each race generates (n*(n-1))/2 pairwise comparisons:

| Dimension | K-factor | Description |
|-----------|----------|-------------|
| **Overall** | 6 | General race performance |
| **Circuit-type** | 6 | Street / high-speed / technical / mixed specialization |
| **Qualifying** | 4 | One-lap pace (lower K — less variance) |
| **Wet-weather** | 8 | Performance in rain (higher K — reveals more delta) |
| **Constructor** | 4 | Team/car performance |
| **Teammate H2H** | 6 | Intra-team head-to-head |

ELO ratings are rebuilt chronologically from history and updated after each race/qualifying session.

### Feature Matrix (81+ features per driver per race)

- ELO ratings and differentials (6 dimensions)
- Rolling form windows (last 3/5/10/20 races)
- Circuit-specific performance history
- Grid position and qualifying pace
- Season momentum and trend
- Tire degradation and strategy (2018+)
- Weather conditions
- Constructor strength
- Practice session pace (FastF1)
- Safety car probability by circuit type

### Model

**XGBoost stacking ensemble** with calibrated auxiliary classifiers:
- Position predictor (regression)
- Win classifier (binary)
- Podium classifier (binary)
- Points classifier (binary)
- DNF classifier (binary)

Trained with time-series cross-validation to prevent data leakage. Features are extracted at the state *before* each race (no future information).

### Monte Carlo Simulation

10,000 vectorized simulations (NumPy) per race weekend:
- Position noise with correlated team effects
- DNF sampling using circuit-type-aware probabilities
- Safety car probability by circuit type
- Outputs: win%, podium%, points%, expected points, median position, IQR range

## Quick Start

### Double-click launchers (macOS)

The easiest way — no terminal needed:

- **`web-dashboard.command`** — Opens the web dashboard in your browser
- **`dashboard.command`** — Opens the terminal (Rich) dashboard

### Command line

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run full pipeline (ingest → features → train)
python -m data.pipeline --step all

# Predict next weekend
python -m data.predict_weekend

# Launch web dashboard
python -m src.app                 # http://localhost:5050
python -m src.app --port 8080     # Custom port
```

## Web Dashboard

Terminal-aesthetic single-page dashboard with 4-column layout:

| Column | Content |
|--------|---------|
| **Predictions** | Stat pills (predicted winner, win%, gap to P2), full 20-driver prediction grid, gain/loss insights |
| **Session Results** | Qualifying (Q1/Q2/Q3), sprint race, race result with grid-to-finish delta (+/-) |
| **Standings + ELO** | Driver championship, constructor standings (with ELO), ELO power rankings with SVG sparklines |
| **Charts + News** | Win probability, expected points, podium probability, DNF risk (horizontal bar charts), RSS news feed |

Features:
- OLED black dark mode / pure white light mode (toggle + localStorage persistence)
- Circuit type badges (street / high-speed / technical / mixed)
- Team color bars throughout
- Race/round selector for historical predictions
- Zero JavaScript dependencies — pure CSS charts, SVG sparklines, vanilla JS for theme toggle and RSS fetch

## Terminal Dashboard

Rich-based terminal UI (alternative to web):

```bash
python -m data.dashboard
```

## Project Structure

```
├── data/
│   ├── ingest/                  # Data source clients
│   │   ├── jolpica.py           # Jolpica-F1 API (1950–present)
│   │   ├── fastf1_ingest.py     # FastF1 library (2018+)
│   │   ├── openf1_client.py     # OpenF1 real-time API (2023+)
│   │   └── openf1_penalties.py  # Penalty data extraction
│   ├── features/                # Feature engineering
│   │   ├── elo.py               # Multi-dimensional ELO system
│   │   └── engineer.py          # Full feature matrix builder (81+ features)
│   ├── models/                  # ML models
│   │   ├── predictor.py         # XGBoost stacking ensemble
│   │   ├── simulator.py         # 10k Monte Carlo simulation
│   │   ├── tuner.py             # Hyperparameter tuning
│   │   ├── backtest.py          # Historical backtesting
│   │   └── explain.py           # SHAP / feature importance
│   ├── pipeline.py              # End-to-end pipeline orchestrator
│   ├── predict_weekend.py       # Predict next race weekend
│   ├── dashboard.py             # Rich terminal dashboard
│   └── cache/                   # Cached data (gitignored)
│       └── processed/           # Parquet files + prediction CSVs
├── src/                         # Flask web dashboard
│   ├── app.py                   # Routes, data loading, template context
│   ├── shared.py                # Constants (drivers, teams, colors, helpers)
│   ├── templates/
│   │   └── terminal.html        # Single-page Jinja2 template
│   └── static/
│       └── style.css            # Terminal-aesthetic CSS
├── dashboard.command             # macOS launcher (terminal dashboard)
├── web-dashboard.command         # macOS launcher (web dashboard)
├── requirements.txt
└── .env.example
```

## Roadmap

- [x] Jolpica historical data ingestion (1950–present)
- [x] FastF1 granular data ingestion (2018+)
- [x] OpenF1 real-time client (2023+)
- [x] Multi-dimensional ELO rating system (6 dimensions)
- [x] Feature engineering pipeline (81+ features)
- [x] XGBoost stacking ensemble (position, podium, winner, points, DNF)
- [x] Monte Carlo simulation (10k sims, vectorized)
- [x] Web dashboard (Flask, 4-column terminal aesthetic)
- [x] Terminal dashboard (Rich)
- [x] macOS double-click launchers
- [ ] Wet race detection (automated from weather data)
- [ ] Real-time race predictions during qualifying/race
- [ ] Championship probability simulations (full season Monte Carlo)
- [ ] Betting odds integration and value detection
