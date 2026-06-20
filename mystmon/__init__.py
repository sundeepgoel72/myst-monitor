"""MystMon - Dockerized Prometheus and SNMP monitoring bridge for Mysterium nodes.

This package provides monitoring capabilities for Mysterium nodes including:
- Docker container discovery (local and remote)
- TequilAPI endpoint monitoring
- Prometheus metrics export
- SNMP extend script generation
- Web UI dashboard
- Historical data storage
- Telegram notifications

The main components are:
- mystmon.main: Entry point and application setup
- mystmon.api: FastAPI web interface
- mystmon.scheduler: Collection scheduling and coordination
- mystmon.storage: In-memory metric storage
- mystmon.history: Persistent historical data storage
- mystmon.telegram: Notification system
- mystmon.collectors: Data collection implementations
- mystmon.config: Configuration management
"""
__version__ = "0.1"
__author__ = "Sundeep Goel"
