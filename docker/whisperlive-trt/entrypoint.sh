#!/bin/bash
set -e

MODEL_PATH="/app/TensorRT-LLM-examples/whisper/whisper_small_en_float16"

# Check if the model directory exists
if [ ! -d "$MODEL_PATH" ]; then
    echo "Model directory not found. Building the model..."
    # Ensure parent directory exists
    mkdir -p /app/TensorRT-LLM-examples/whisper
    # Build the model
    bash build_whisper_tensorrt.sh /app/TensorRT-LLM-examples small.en
    echo "Model build completed."
else
    echo "Model directory found at $MODEL_PATH. Skipping build."
fi

# Ensure websocket-client is installed
echo "Ensuring required packages are installed..."
pip install --no-cache-dir websocket-client
python3 -c "import websocket; print('WebSocket package successfully imported')"

# Start the server with the parameters passed to this script
echo "Starting WhisperLive server..."
exec python3 run_server.py "$@" 