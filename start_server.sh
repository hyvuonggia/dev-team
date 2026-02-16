#!/bin/bash
# Start the Dev Team API server

cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Error: Virtual environment not found. Please set up the project first."
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found. Creating from .env.example..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "Please edit .env and add your OPENROUTER_API_KEY"
        exit 1
    else
        echo "Error: .env.example not found"
        exit 1
    fi
fi

# Start the server
echo "Starting Dev Team API server..."
echo "Swagger UI will be available at: http://localhost:8000/docs"
echo ""

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000