FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY src/transcription-collector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/transcription-collector/ .

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"] 