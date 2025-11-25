#!/bin/bash
# This script launches all the agents in the multi-agent system.

echo "Starting all agents..."

# Start each agent in the background
uvicorn agents.scraper.main:app --host 0.0.0.0 --port 8001 &
UVICORN_PID_SCRAPER=$!
echo "Scraper Agent started with PID $UVICORN_PID_SCRAPER"
sleep 2

uvicorn agents.analyzer.main:app --host 0.0.0.0 --port 8002 &
UVICORN_PID_ANALYZER=$!
echo "Analyzer Agent started with PID $UVICORN_PID_ANALYZER"
sleep 2

uvicorn agents.stock.main:app --host 0.0.0.0 --port 8003 &
UVICORN_PID_STOCK=$!
echo "Stock Agent started with PID $UVICORN_PID_STOCK"
sleep 2

uvicorn agents.memory.main:app --host 0.0.0.0 --port 8004 &
UVICORN_PID_MEMORY=$!
echo "Memory Agent started with PID $UVICORN_PID_MEMORY"
sleep 2

uvicorn agents.evaluation.main:app --host 0.0.0.0 --port 8005 &
UVICORN_PID_EVALUATION=$!
echo "Evaluation Agent started with PID $UVICORN_PID_EVALUATION"
sleep 2

uvicorn agents.trading.main:app --host 0.0.0.0 --port 8006 &
UVICORN_PID_TRADING=$!
echo "Trading Agent started with PID $UVICORN_PID_TRADING"
sleep 2

# Start the coordinator last
uvicorn agents.coordinator.main:app --host 0.0.0.0 --port 8000 &
UVICORN_PID_COORDINATOR=$!
echo "Coordinator Agent started with PID $UVICORN_PID_COORDINATOR"


echo "All agents started."
echo "Press [CTRL+C] to stop all agents."

# Function to clean up background processes
cleanup() {
    echo "Stopping all agents..."
    kill $UVICORN_PID_SCRAPER
    kill $UVICORN_PID_ANALYZER
    kill $UVICORN_PID_STOCK
    kill $UVICORN_PID_MEMORY
    kill $UVICORN_PID_EVALUATION
    kill $UVICORN_PID_TRADING
    kill $UVICORN_PID_COORDINATOR
    echo "All agents stopped."
}

# Trap SIGINT (Ctrl+C) and call cleanup
trap cleanup SIGINT

# Wait for all background processes to finish
wait
