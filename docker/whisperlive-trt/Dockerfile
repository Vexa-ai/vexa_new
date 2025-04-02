FROM ghcr.io/collabora/whisperlive-tensorrt:latest

# Install additional dependencies
RUN pip install --no-cache-dir websocket-client

# Copy our entrypoint script
COPY docker/whisperlive-trt/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Set it as the entrypoint
ENTRYPOINT ["/entrypoint.sh"]
# Default CMD will be passed to the entrypoint
CMD ["--port", "9090", "--backend", "tensorrt", "--trt_model_path", "/app/TensorRT-LLM-examples/whisper/whisper_small_en_float16"]

# Execute all steps in a single layer to maintain context
# and capture the build script's output
RUN set -e && \
    mkdir -p /app/TensorRT-LLM-examples/whisper && \
    bash build_whisper_tensorrt.sh /app/TensorRT-LLM-examples small.en > /tmp/build_script.log 2>&1 && \
    cat /tmp/build_script.log && \
    echo "Verifying the whisper directory contents:" && \
    ls -la /app/TensorRT-LLM-examples/whisper/ && \
    echo "Build script execution complete."

# Make sure websocket is installed correctly in the Python environment used by the app
RUN pip install --no-cache-dir websocket-client && \
    python3 -c "import websocket; print('WebSocket package installed successfully')"

# Since the model should now be built during image creation,
# the container can just run the server directly 