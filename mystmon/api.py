"""FastAPI application for MystMon.

Provides the web API interface for MystMon including:
- REST endpoints for current data and historical snapshots
- Prometheus metrics export
- Configuration inspection
- Collection triggering
- Health checking

The API serves both programmatic clients and the web UI, providing a
centralized interface for all MystMon functionality.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from mystmon.config import MystMonConfig
from mystmon.history import CollectionRecord

logger = logging.getLogger(__name__)

# Global variables for app state
app_store = None
app_scheduler = None
app_history = None
app_config = None


def create_app(config: MystMonConfig) -> FastAPI:
    """Create the FastAPI application.
    
    Initializes the FastAPI application with all routes and middleware.
    Sets up static file serving for the web UI.
    
    Args:
        config: MystMon configuration
        
    Returns:
        Configured FastAPI application
    """
    global app_config
    app_config = config
    
    app = FastAPI(
        title="MystMon API",
        description="Dockerized Prometheus and SNMP monitoring bridge for Mysterium nodes",
        version="0.75.0-beta.3",
    )
    
    # Mount static files
    try:
        app.mount("/static", StaticFiles(directory="mystmon/static"), name="static")
    except Exception:
        logger.warning("Static files directory not found, skipping mount")
    
    # Include routes
    _add_routes(app)
    
    return app


def _add_routes(app: FastAPI) -> None:
    """Add routes to the FastAPI application.
    
    Registers all API endpoints with the FastAPI application.
    
    Args:
        app: FastAPI application to add routes to
    """
    
    @app.get("/api/v1/snapshot")
    async def get_snapshot() -> Dict[str, Any]:
        """Get the latest snapshot of node data.
        
        Returns the most recent complete snapshot of all monitored nodes
        including Docker container status, TequilAPI data, and portal information.
        
        Returns:
            Latest snapshot data
        """
        if not app_store:
            raise HTTPException(status_code=503, detail="Service not initialized")
        
        # This would typically gather data from the store
        # For now, return a placeholder
        return {
            "collected_at": datetime.now().isoformat(),
            "nodes": [],
            "collection_counts": {},
            "mystnodes": None
        }
    
    @app.post("/api/v1/collect")
    async def trigger_collection(background_tasks: BackgroundTasks) -> Dict[str, str]:
        """Trigger an immediate collection cycle.
        
        Starts a new collection cycle in the background, gathering fresh
        data from all configured sources.
        
        Args:
            background_tasks: FastAPI background tasks for async execution
            
        Returns:
            Confirmation message
        """
        if not app_scheduler:
            raise HTTPException(status_code=503, detail="Scheduler not available")
        
        background_tasks.add_task(app_scheduler.collect_once)
        return {"message": "Collection started"}
    
    @app.get("/api/v1/history/collections")
    async def get_collections(limit: int = 50) -> List[CollectionRecord]:
        """Get recent collection history.
        
        Retrieves historical collection snapshots for trend analysis
        and reporting.
        
        Args:
            limit: Maximum number of collections to return
            
        Returns:
            List of recent collections
        """
        if not app_history:
            raise HTTPException(status_code=503, detail="History not available")
        
        return app_history.get_recent_collections(limit)
    
    @app.get("/api/v1/history/collection/{collection_id}")
    async def get_collection(collection_id: int) -> Dict[str, Any]:
        """Get a specific collection by ID.
        
        Retrieves a single historical collection snapshot by its database ID.
        
        Args:
            collection_id: ID of the collection to retrieve
            
        Returns:
            Collection data
        """
        if not app_history:
            raise HTTPException(status_code=503, detail="History not available")
        
        collection = app_history.get_collection_by_id(collection_id)
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")
        
        return {
            "id": collection.id,
            "collected_at": collection.collected_at.isoformat(),
            "node_count": collection.node_count,
            "prometheus_count": collection.prometheus_count,
            "snmp_count": collection.snmp_count,
            "portal_nodes_count": collection.portal_nodes_count,
            "data": collection.raw_data
        }
    
    @app.get("/api/v1/config")
    async def get_config() -> Dict[str, Any]:
        """Get the current configuration.
        
        Returns a safe representation of the current MystMon configuration
        excluding sensitive fields like passwords.
        
        Returns:
            Current configuration
        """
        if not app_config:
            raise HTTPException(status_code=503, detail="Config not available")
        
        # Return a safe representation of the config
        return {
            "service": {
                "name": app_config.service.name,
                "poll_interval_seconds": app_config.service.poll_interval_seconds,
                "request_timeout_seconds": app_config.service.request_timeout_seconds,
                "log_window_seconds": app_config.service.log_window_seconds,
            },
            "prometheus": {
                "enabled": app_config.prometheus.enabled,
                "targets": [{"name": t.name, "url": t.url} for t in app_config.prometheus.targets]
            },
            "snmp": {
                "enabled": app_config.snmp.enabled,
                "default_community": app_config.snmp.default_community,
                "targets": [{"name": t.name, "host": t.host} for t in app_config.snmp.targets]
            },
            "myst": {
                "enabled": app_config.myst.enabled,
                "local_host": app_config.myst.local_host,
                "api_probe_enabled": app_config.myst.api_probe_enabled,
                "api_default_port": app_config.myst.api_default_port,
            },
            "mystnodes_accounts": [
                {
                    "account": account.account,
                    "enabled": account.enabled,
                }
                for account in app_config.mystnodes_accounts or []
            ],
            "history": {
                "enabled": app_config.history.enabled,
                "db_path": app_config.history.db_path,
            },
            "telegram": {
                "enabled": app_config.telegram.enabled,
            },
            "ui": {
                "enabled": app_config.ui.enabled,
                "path": app_config.ui.path,
            }
        }
    
    @app.get("/api/v1/status")
    async def get_status() -> Dict[str, Any]:
        """Get the current service status.
        
        Returns basic service status information including uptime and version.
        
        Returns:
            Service status information
        """
        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "version": "0.75.0-beta.3",
        }
    
    @app.get("/", response_class=HTMLResponse)
    async def root() -> str:
        """Root endpoint serving a simple HTML page.
        
        Provides a basic landing page with links to key resources.
        
        Returns:
            HTML content
        """
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>MystMon</title>
        </head>
        <body>
            <h1>MystMon</h1>
            <p>Dockerized Prometheus and SNMP monitoring bridge for Mysterium nodes</p>
            <p><a href="/ui">Web UI</a> | <a href="/docs">API Documentation</a></p>
        </body>
        </html>
        """
    
    @app.get("/ui", response_class=HTMLResponse)
    async def ui() -> str:
        """UI endpoint.
        
        Serves the main web UI dashboard page.
        
        Returns:
            UI HTML content
        """
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>MystMon Dashboard</title>
            <link rel="stylesheet" href="/static/css/dashboard.css">
        </head>
        <body>
            <div id="app">
                <h1>MystMon Dashboard</h1>
                <div id="dashboard">
                    <p>Loading dashboard...</p>
                </div>
            </div>
            <script src="/static/js/dashboard.js"></script>
        </body>
        </html>
        """


def build_snapshot(nodes: List[Dict[str, Any]], collection_counts: Dict[str, int], mystnodes_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a snapshot of the current state.
    
    Creates a complete snapshot of the MystMon state including node data,
    collection counts, and portal information for storage or export.
    
    Args:
        nodes: List of node data
        collection_counts: Counts of collected items
        mystnodes_data: MystNodes portal data
        
    Returns:
        Snapshot dictionary
    """
    return {
        "collected_at": datetime.now().isoformat(),
        "nodes": nodes,
        "collection_counts": collection_counts,
        "mystnodes": mystnodes_data
    }
