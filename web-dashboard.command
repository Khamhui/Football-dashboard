#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
echo "Starting F1 Dashboard on http://localhost:5050 ..."
python -m src.app
