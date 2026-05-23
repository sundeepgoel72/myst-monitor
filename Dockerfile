FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MYSTMON_CONFIG=/app/config.yaml \
    MYSTMON_HOST=0.0.0.0 \
    MYSTMON_PORT=8072

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mystmon ./mystmon
COPY config.example.yaml ./config.yaml

EXPOSE 8072

CMD ["python", "-m", "mystmon.main"]

