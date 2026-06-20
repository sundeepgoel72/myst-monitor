from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn

from mystmon.config import load_config


class LocalTimezoneFormatter(logging.Formatter):
    def __init__(self, fmt: str, timezone_name: str) -> None:
        super().__init__(fmt=fmt)
        self._timezone = ZoneInfo(timezone_name)

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = self.converter(record.created, self._timezone)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(timespec="milliseconds")

    @staticmethod
    def converter(timestamp: float, timezone: ZoneInfo) -> datetime:
        return datetime.fromtimestamp(timestamp, tz=timezone)


def main() -> None:
    """
    Run the MystMon application.

    This function sets up logging, reads configuration from environment
    variables, and starts the Uvicorn server for the FastAPI application.

    Logging:
    - Logs are sent to both the console and a file (`mystmon.log`).
    - The log file is stored in the data directory.

    Configuration (Environment Variables):
    - MYSTMON_LOG_LEVEL: Log level (e.g., INFO, DEBUG). Default: INFO.
    - MYSTMON_DATA_DIR: Directory to store data and logs. Default: /data/mystmon.
    - MYSTMON_HOST: Host to bind the web server to. Default: 0.0.0.0.
    - MYSTMON_PORT: Port for the web server. Default: 8072.
    """
    config = load_config()
    log_level = os.getenv("MYSTMON_LOG_LEVEL", "INFO").upper()
    log_format = "%(asctime)s %(levelname)s %(name)s %(message)s"

    data_dir = Path(os.getenv("MYSTMON_DATA_DIR", config.service.data_dir))
    data_dir.mkdir(parents=True, exist_ok=True)
    log_file = data_dir / "mystmon.log"
    formatter = LocalTimezoneFormatter(log_format, config.service.timezone)
    file_handler = logging.FileHandler(log_file)
    stream_handler = logging.StreamHandler()
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    logging.basicConfig(
        level=log_level,
        handlers=[file_handler, stream_handler],
        force=True,
    )
    host = os.getenv("MYSTMON_HOST", "0.0.0.0")
    port = int(os.getenv("MYSTMON_PORT", "8072"))
    print("Hey there! Starting MystMon...")
    uvicorn.run("mystmon.api:create_app", host=host, port=port, factory=True)


if __name__ == "__main__":
    main()
