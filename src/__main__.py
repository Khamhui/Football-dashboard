"""Allow `python -m src` to start the dashboard."""
import argparse

from src.app import start

parser = argparse.ArgumentParser(description="F1 Dashboard")
parser.add_argument("--port", type=int, default=5050)
parser.add_argument("--no-browser", action="store_true")
args = parser.parse_args()

start(port=args.port, open_browser=not args.no_browser)
