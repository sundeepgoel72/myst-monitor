from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("MYSTMON_HOST", "0.0.0.0")
    port = int(os.getenv("MYSTMON_PORT", "8072"))
    uvicorn.run("mystmon.api:create_app", host=host, port=port, factory=True)


if __name__ == "__main__":
    main()

