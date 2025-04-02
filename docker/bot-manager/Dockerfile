FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY src/bot-manager/requirements.txt .
# Install OS dependencies needed for the docker library (to talk to the socket)
# Typically, the base python:slim image is enough, but if issues arise, 
# common packages like 'build-essential', 'libffi-dev', 'python3-dev' might be needed.
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/bot-manager/ .

# Set the default log level if not provided by environment
ENV LOG_LEVEL=INFO

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"] 