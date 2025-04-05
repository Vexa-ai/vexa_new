#!/bin/bash
set -e

# Set environment variable for CUDNN
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib/python3.10/site-packages/nvidia/cudnn/lib:$LD_LIBRARY_PATH

# Ensure websocket-client is installed
echo "Ensuring required packages are installed..."
pip install --no-cache-dir websocket-client
python3 -c "import websocket; print('WebSocket package successfully imported')"

# Start the server with the parameters passed via CMD / docker-compose command
echo "Starting WhisperLive server with provided arguments..."
echo "Arguments received: $@"
cd /app
exec python3 run_server.py "$@" 