from __future__ import annotations

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


async def collect_snmp(
    target: SnmpTarget,
    default_community: str,
    timeout_seconds: int,
) -> list[Reading]:
    community = target.community or default_community
    object_types = [ObjectType(ObjectIdentity(oid)) for oid in target.oids.values()]
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

    if error_indication:
        raise RuntimeError(str(error_indication))
    if error_status:
        failed_oid = error_index and var_binds[int(error_index) - 1][0] or "unknown"
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
