from __future__ import annotations

from typing import Any

__all__ = ["collect_myst_nodes_async", "collect_mystnodes_portal", "collect_prometheus", "collect_snmp"]


def __getattr__(name: str) -> Any:
    if name == "collect_myst_nodes_async":
        from mystmon.collectors.myst import collect_myst_nodes_async

        return collect_myst_nodes_async
    if name == "collect_mystnodes_portal":
        from mystmon.collectors.mystnodes import collect_mystnodes_portal

        return collect_mystnodes_portal
    if name == "collect_prometheus":
        from mystmon.collectors.prometheus import collect_prometheus

        return collect_prometheus
    if name == "collect_snmp":
        from mystmon.collectors.snmp import collect_snmp

        return collect_snmp
    raise AttributeError(name)
