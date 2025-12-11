#!/bin/bash
# Run the Acceso x402 API server

cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Check for .env file
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found. Copying from .env.example..."
    cp .env.example .env
    echo "Please edit .env with your configuration."
fi

# Run the server
echo "Starting Acceso x402 API on port 8402..."
cd src
python -m uvicorn x402.main:app --host 0.0.0.0 --port 8402 --reload
