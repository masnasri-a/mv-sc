#!/bin/bash

# Premium Expiry Checker Service
# This script runs the premium expiry checker in the background

cd "$(dirname "$0")"

echo "Starting Premium Expiry Checker Service..."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "Virtual environment activated"
fi

# Run the expiry checker
python premium_expiry_checker.py &

# Save PID for later stopping
echo $! > premium_checker.pid

echo "Premium Expiry Checker started with PID $(cat premium_checker.pid)"
echo "To stop: kill $(cat premium_checker.pid) or run ./stop_premium_checker.sh"