FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MYSTMON_CONFIG=/app/config.yaml \
    MYSTMON_HOST=0.0.0.0 \
    MYSTMON_PORT=8072

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client sshpass \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mystmon ./mystmon
COPY config.example.yaml ./config.yaml

EXPOSE 8072 8073

CMD ["python", "-m", "mystmon.main"]
