"""
F1 Race Weekend Terminal Dashboard — Rich + plotext.

Displays prediction results, qualifying/sprint data, and probability charts
in a fast, lightweight terminal UI.

Usage:
    python -m data.dashboard                           # Auto-detect latest prediction
    python -m data.dashboard --season 2026 --round 2   # Specific race
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import plotext as plt
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.shared import (
    DATA_DIR,
    TEAM_COLORS_RICH,
    TEAM_SHORT,
    available_predictions,
    driver_name,
    get_event_name,
    load_prediction,
    team_color_rich,
    team_name,
)


def load_feature_context(season: int, race_round: int) -> Optional[pd.DataFrame]:
    """Load feature matrix rows for race context (grid, team, etc.)."""
    fm_path = DATA_DIR / "feature_matrix.parquet"
    try:
        fm = pd.read_parquet(fm_path)
    except FileNotFoundError:
        return None
    race = fm[(fm["season"] == season) & (fm["round"] == race_round)]
    if race.empty:
        return None
    return race[["driver_id", "constructor_id", "grid"]].copy()


def render_prediction_table(console: Console, pred: pd.DataFrame, ctx: Optional[pd.DataFrame]):
    """Render the main prediction table."""
    if ctx is not None:
        pred = pred.merge(ctx, on="driver_id", how="left")

    wide = console.width >= 100

    table = Table(
        title="Race Prediction",
        title_style="bold bright_white",
        border_style="bright_black",
        show_lines=False,
        padding=(0, 1),
    )

    table.add_column("#", style="dim", width=2, justify="right")
    table.add_column("Driver", width=12, no_wrap=True)
    if wide:
        table.add_column("Team", width=10, style="dim", no_wrap=True)
    table.add_column("GRD", width=3, justify="center")
    table.add_column("Pred", width=4, justify="right")
    table.add_column("Win%", width=5, justify="right")
    table.add_column("Pod%", width=5, justify="right")
    if wide:
        table.add_column("Pts%", width=5, justify="right")
    table.add_column("DNF%", width=5, justify="right")
    table.add_column("E[Pts]", width=5, justify="right")
    table.add_column("Med", width=3, justify="right")
    table.add_column("Range", width=5, justify="center")

    for i, (_, row) in enumerate(pred.iterrows(), 1):
        driver_id = row["driver_id"]
        name = driver_name(driver_id)
        cid = row.get("constructor_id", "")
        color = team_color_rich(cid)
        grid = row.get("grid", "")
        grid_str = str(int(grid)) if pd.notna(grid) else "-"

        win = row.get("sim_win_pct", 0)
        podium = row.get("sim_podium_pct", 0)
        points = row.get("sim_points_pct", 0)
        dnf = row.get("sim_dnf_pct", 0)
        exp_pts = row.get("sim_expected_points", 0)
        median = row.get("sim_median_position", 0)
        p25 = row.get("sim_position_25", 0)
        p75 = row.get("sim_position_75", 0)

        win_style = "bold bright_green" if win >= 10 else ("green" if win >= 1 else "dim")
        dnf_style = "bright_red" if dnf >= 20 else ("yellow" if dnf >= 15 else "dim")

        pos_str = f"[bold bright_white]{i}[/]" if i <= 3 else str(i)
        name_str = f"[{color}]{name}[/]" if color else name

        cols = [pos_str, name_str]
        if wide:
            cols.append(TEAM_SHORT.get(cid, cid) if cid else "")
        cols += [
            grid_str,
            f"{row.get('predicted_position', 0):.1f}",
            f"[{win_style}]{win:.1f}[/]",
            f"{podium:.1f}",
        ]
        if wide:
            cols.append(f"{points:.1f}")
        cols += [
            f"[{dnf_style}]{dnf:.1f}[/]",
            f"{exp_pts:.1f}",
            f"{median:.0f}",
            f"{int(p25)}-{int(p75)}",
        ]
        table.add_row(*cols)

    console.print(table)


def render_win_probability_chart(pred: pd.DataFrame, width: int = 60, height: int = 12):
    """Render horizontal bar chart of win probabilities."""
    contenders = pred[pred["sim_win_pct"] > 0.5].head(8)
    if contenders.empty:
        return ""

    names = [driver_name(d) for d in contenders["driver_id"]]
    wins = contenders["sim_win_pct"].tolist()

    plt.clf()
    plt.plotsize(width, height)
    plt.theme("dark")
    plt.title("Win Probability")
    plt.simple_bar(names, wins, color="bright-green", width=40)

    return plt.build()


def render_podium_chart(pred: pd.DataFrame, width: int = 60, height: int = 12):
    """Render podium probability chart."""
    contenders = pred[pred["sim_podium_pct"] > 5].head(8)
    if contenders.empty:
        return ""

    names = [driver_name(d) for d in contenders["driver_id"]]
    podiums = contenders["sim_podium_pct"].tolist()

    plt.clf()
    plt.plotsize(width, height)
    plt.theme("dark")
    plt.title("Podium Probability")
    plt.simple_bar(names, podiums, color="bright-cyan", width=40)

    return plt.build()


def render_expected_points_chart(pred: pd.DataFrame, width: int = 80, height: int = 14):
    """Render expected points chart."""
    top = pred.head(10)
    names = [driver_name(d) for d in top["driver_id"]]
    pts = top["sim_expected_points"].tolist()

    plt.clf()
    plt.plotsize(width, height)
    plt.theme("dark")
    plt.title("Expected Points (top 10)")
    plt.simple_bar(names, pts, color="bright-yellow", width=50)

    return plt.build()


def render_header(console: Console, season: int, race_round: int, event: str):
    """Render dashboard header."""
    header = Text()
    header.append("F1 PREDICTION ENGINE", style="bold bright_white")
    header.append("  |  ", style="dim")
    header.append(f"{season} {event}", style="bold bright_cyan")
    header.append(f"  Round {race_round}", style="dim")

    console.print(Panel(header, border_style="bright_cyan", padding=(0, 2)))


def render_insights(console: Console, pred: pd.DataFrame, ctx: Optional[pd.DataFrame]):
    """Quick textual insights from the prediction."""
    insights = []

    top = pred.iloc[0]
    insights.append(f"[bold bright_green]Predicted winner:[/] {driver_name(top['driver_id'])} ({top['sim_win_pct']:.1f}% win probability)")

    if len(pred) >= 2:
        gap = abs(pred.iloc[0]["sim_win_pct"] - pred.iloc[1]["sim_win_pct"])
        if gap < 5:
            d1 = driver_name(pred.iloc[0]["driver_id"])
            d2 = driver_name(pred.iloc[1]["driver_id"])
            insights.append(f"[bright_yellow]Close battle:[/] {d1} vs {d2} — only {gap:.1f}% separating them")

    if ctx is not None:
        merged = pred.merge(ctx, on="driver_id", how="left")
        merged["gain"] = merged["grid"] - merged["predicted_position"]
        best_gain = merged.loc[merged["gain"].idxmax()]
        if best_gain["gain"] > 1:
            insights.append(
                f"[bright_cyan]Biggest mover:[/] {driver_name(best_gain['driver_id'])} "
                f"— grid P{int(best_gain['grid'])} → predicted P{best_gain['predicted_position']:.1f} "
                f"(+{best_gain['gain']:.1f} places)"
            )
        worst_drop = merged.loc[merged["gain"].idxmin()]
        if worst_drop["gain"] < -1:
            insights.append(
                f"[bright_red]Biggest drop:[/] {driver_name(worst_drop['driver_id'])} "
                f"— grid P{int(worst_drop['grid'])} → predicted P{worst_drop['predicted_position']:.1f} "
                f"({worst_drop['gain']:.1f} places)"
            )

    high_dnf = pred[pred["sim_dnf_pct"] > 20]
    if not high_dnf.empty:
        names = ", ".join(driver_name(d) for d in high_dnf["driver_id"])
        insights.append(f"[bright_red]High DNF risk (>20%):[/] {names}")

    console.print(Panel("\n".join(insights), title="Insights", title_align="left", border_style="bright_white", padding=(1, 2)))


def render_dashboard(season: int, race_round: int, event: Optional[str] = None):
    """Render the full terminal dashboard."""
    console = Console()

    pred = load_prediction(season, race_round)
    if pred is None:
        console.print(f"[red]No prediction found for {season} Round {race_round}[/]")
        console.print(f"Run: python -m data.predict_weekend --season {season} --round {race_round}")
        return

    ctx = load_feature_context(season, race_round)
    event = event or get_event_name(season, race_round)

    console.print()
    render_header(console, season, race_round, event)
    console.print()

    render_prediction_table(console, pred, ctx)
    console.print()

    win_chart = render_win_probability_chart(pred)
    podium_chart = render_podium_chart(pred)

    if win_chart:
        console.print(Panel(win_chart, border_style="bright_green", title="Win %", title_align="left"))
    if podium_chart:
        console.print(Panel(podium_chart, border_style="bright_cyan", title="Podium %", title_align="left"))
    console.print()

    pts_chart = render_expected_points_chart(pred)
    if pts_chart:
        console.print(Panel(pts_chart, border_style="bright_yellow", title="Expected Points", title_align="left"))
    console.print()

    render_insights(console, pred, ctx)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F1 Terminal Dashboard")
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--round", type=int, default=None)
    args = parser.parse_args()

    if args.season and args.round:
        render_dashboard(args.season, args.round)
    else:
        preds = available_predictions()
        if preds:
            season, race_round, _ = preds[0]
            render_dashboard(season, race_round)
        else:
            Console().print("[red]No prediction files found. Run predict_weekend.py first.[/]")
