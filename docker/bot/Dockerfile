FROM python:3.9-slim

WORKDIR /app

COPY src/bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/bot/main.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"] 