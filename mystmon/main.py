from __future__ import annotations

import logging
import os
from pathlib import Path

import uvicorn


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
    log_level = os.getenv("MYSTMON_LOG_LEVEL", "INFO").upper()
    log_format = "%(asctime)s %(levelname)s %(name)s %(message)s"

    data_dir = Path(os.getenv("MYSTMON_DATA_DIR", "/data/mystmon"))
    log_file = data_dir / "mystmon.log"

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )
    host = os.getenv("MYSTMON_HOST", "0.0.0.0")
    port = int(os.getenv("MYSTMON_PORT", "8072"))
    print("Hey there! Starting MystMon...")
    uvicorn.run("mystmon.api:create_app", host=host, port=port, factory=True)


if __name__ == "__main__":
    main()
