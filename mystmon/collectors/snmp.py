from __future__ import annotations

import logging

from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
)

from mystmon.config import SnmpTarget
from mystmon.storage import Reading

LOGGER = logging.getLogger(__name__)


async def collect_snmp(
    target: SnmpTarget,
    default_community: str,
    timeout_seconds: int,
) -> list[Reading]:
    community = target.community or default_community
    object_types = [ObjectType(ObjectIdentity(oid)) for oid in target.oids.values()]
    try:
        transport = await UdpTransportTarget.create(
            (target.host, target.port),
            timeout=timeout_seconds,
            retries=1,
        )
        error_indication, error_status, error_index, var_binds = await get_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            transport,
            ContextData(),
            *object_types,
        )
    except Exception as exc:
        LOGGER.exception(
            "SNMP collection failed target=%s host=%s port=%s reason=transport_error error=%s",
            target.name,
            target.host,
            target.port,
            exc,
        )
        raise

    if error_indication:
        LOGGER.error(
            "SNMP collection failed target=%s host=%s port=%s reason=error_indication error=%s",
            target.name,
            target.host,
            target.port,
            error_indication,
        )
        raise RuntimeError(str(error_indication))
    if error_status:
        failed_oid = error_index and var_binds[int(error_index) - 1][0] or "unknown"
        LOGGER.error(
            "SNMP collection failed target=%s host=%s port=%s reason=error_status error=%s failed_oid=%s",
            target.name,
            target.host,
            target.port,
            error_status.prettyPrint(),
            failed_oid,
        )
        raise RuntimeError(f"{error_status.prettyPrint()} at {failed_oid}")

    metric_names = list(target.oids.keys())
    readings: list[Reading] = []
    for index, (_, value) in enumerate(var_binds):
        raw_value = value.prettyPrint()
        readings.append(
            Reading(
                source_type="snmp",
                source_name=target.name,
                metric=metric_names[index],
                value=_coerce_snmp_value(raw_value),
                labels={"host": target.host, "oid": target.oids[metric_names[index]]},
            )
        )
    return readings


def _coerce_snmp_value(value: str) -> float | str:
    try:
        return float(value)
    except ValueError:
        return value
