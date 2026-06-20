FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MYSTMON_CONFIG=/app/config.yaml
ENV MYSTMON_HOST=0.0.0.0
ENV MYSTMON_PORT=8072

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY mystmon ./mystmon
COPY config.yaml ./config.yaml

EXPOSE 8072 8073

CMD ["python", "-m", "mystmon.main"]
