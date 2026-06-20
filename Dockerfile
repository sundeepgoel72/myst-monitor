FROM python:3.12-slim

WORKDIR /app

LABEL org.opencontainers.image.title="MystMon"
LABEL org.opencontainers.image.description="Read-only monitoring service for MYST nodes."
LABEL org.opencontainers.image.source="https://github.com/sundeepgoel72/myst-monitor"
LABEL org.opencontainers.image.url="https://github.com/sundeepgoel72/myst-monitor"
LABEL org.opencontainers.image.documentation="https://github.com/sundeepgoel72/myst-monitor/blob/main/README.md"
LABEL org.opencontainers.image.licenses="MIT"

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
