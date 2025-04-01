FROM python:3.9-slim

WORKDIR /app

COPY src/transcription-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/transcription-service/main.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"] 