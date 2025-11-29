#!/bin/bash

# Stop Premium Expiry Checker Service

if [ -f "premium_checker.pid" ]; then
    PID=$(cat premium_checker.pid)
    if kill -0 $PID 2>/dev/null; then
        echo "Stopping Premium Expiry Checker (PID: $PID)..."
        kill $PID
        rm premium_checker.pid
        echo "Premium Expiry Checker stopped"
    else
        echo "Premium Expiry Checker is not running"
        rm premium_checker.pid
    fi
else
    echo "No premium_checker.pid file found"
fi