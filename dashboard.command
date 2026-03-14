#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python -m data.dashboard
echo ""
echo "Press any key to close..."
read -n 1
