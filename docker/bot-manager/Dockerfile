FROM python:3.9-slim

WORKDIR /app

# Install required packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY src/bot-manager/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /app/app/kubernetes /app/app/database /app/app/tasks /app/app/docker

COPY src/bot-manager/main.py .
COPY src/bot-manager/app /app/app/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=local

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"] 