#!/bin/bash
set -e

# Define path for the target medium model
MODEL_PATH="/app/TensorRT-LLM-examples/whisper/whisper_medium_float16"
MODEL_NAME="medium" # Define the model name to build

# Check if the target model directory exists in the volume/image
if [ ! -d "$MODEL_PATH" ]; then
    echo "Model directory '$MODEL_PATH' not found. Attempting to build $MODEL_NAME model..."
    # Ensure parent directory exists (volume mount should handle this, but good practice)
    mkdir -p /app/TensorRT-LLM-examples/whisper
    # Build the medium model
    echo "Running: bash build_whisper_tensorrt.sh /app/TensorRT-LLM-examples $MODEL_NAME"
    bash build_whisper_tensorrt.sh /app/TensorRT-LLM-examples $MODEL_NAME
    echo "Model build script completed. Checking existence of $MODEL_PATH again..."
    # Check again if the expected directory was created
    if [ ! -d "$MODEL_PATH" ]; then
        echo "ERROR: Model directory '$MODEL_PATH' still not found after build attempt. Check build script logs and ensure it creates this specific directory."
        # Optionally list contents to help debug
        echo "Contents of /app/TensorRT-LLM-examples/whisper/ after build attempt:"
        ls -la /app/TensorRT-LLM-examples/whisper/
        exit 1 # Exit if build failed to create the expected path
    fi
else
    echo "Model directory found at $MODEL_PATH. Skipping build."
fi

# Ensure websocket-client is installed
echo "Ensuring required packages are installed..."
pip install --no-cache-dir websocket-client
python3 -c "import websocket; print('WebSocket package successfully imported')"

# Start the server with the parameters passed via CMD / docker-compose command
# These arguments should include the correct --trt_model_path
echo "Starting WhisperLive server with provided arguments..."
exec python3 run_server.py "$@" 