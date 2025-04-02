FROM ghcr.io/collabora/whisperlive-tensorrt:latest

# Install additional dependencies
RUN pip install --no-cache-dir websocket-client

# Copy our entrypoint script
COPY docker/whisperlive-trt/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Set it as the entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Default CMD pointing to the medium model path and multilingual flag
# The entrypoint script will attempt to build this if it doesn't exist in the volume
CMD ["--port", "9090", "--backend", "tensorrt", "--trt_model_path", "/app/TensorRT-LLM-examples/whisper/whisper_medium_float16", "--trt_multilingual"]

# Make sure websocket is installed correctly (still needed)
RUN pip install --no-cache-dir websocket-client && \
    python3 -c "import websocket; print('WebSocket package installed successfully')"