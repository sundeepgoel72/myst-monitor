"""System metrics collector for retrieving host-level metrics.

This module provides functionality to collect system-level metrics including
CPU usage, memory usage, disk usage, and network statistics. It uses the psutil
library to gather these metrics efficiently.

The collector supports monitoring the local host where MystMon is running.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from mystmon.storage import Reading

LOGGER = logging.getLogger(__name__)


async def collect_system(timeout_seconds: int) -> List[Reading]:
    """Collect system metrics from the local host.
    
    Args:
        timeout_seconds: Request timeout in seconds (not used for system metrics)
        
    Returns:
        List of readings with system metrics
    """
    if not PSUTIL_AVAILABLE:
        LOGGER.debug("psutil not available, skipping system metrics collection")
        return []
    
    try:
        readings: List[Reading] = []
        timestamp = datetime.now()
        
        # Collect CPU metrics
        cpu_readings = _collect_cpu_metrics(timestamp)
        readings.extend(cpu_readings)
        
        # Collect memory metrics
        memory_readings = _collect_memory_metrics(timestamp)
        readings.extend(memory_readings)
        
        # Collect disk metrics
        disk_readings = _collect_disk_metrics(timestamp)
        readings.extend(disk_readings)
        
        # Collect network metrics
        network_readings = _collect_network_metrics(timestamp)
        readings.extend(network_readings)
        
        # Collect system info
        system_readings = _collect_system_info(timestamp)
        readings.extend(system_readings)
        
        return readings
    except Exception as exc:
        LOGGER.warning("System metrics collection failed reason=%s", exc)
        return []


def _collect_cpu_metrics(timestamp: datetime) -> List[Reading]:
    """Collect CPU usage metrics.
    
    Args:
        timestamp: Collection timestamp
        
    Returns:
        List of CPU metric readings
    """
    readings: List[Reading] = []
    
    try:
        # Overall CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="cpu_percent",
            value=cpu_percent,
            labels={},
            timestamp=timestamp,
        ))
        
        # Per-CPU usage
        cpu_percents = psutil.cpu_percent(interval=1, percpu=True)
        for i, percent in enumerate(cpu_percents):
            readings.append(Reading(
                source_type="system",
                source_name="localhost",
                metric_name=f"cpu_{i}_percent",
                value=percent,
                labels={"cpu": str(i)},
                timestamp=timestamp,
            ))
        
        # CPU frequency
        cpu_freq = psutil.cpu_freq()
        if cpu_freq:
            readings.append(Reading(
                source_type="system",
                source_name="localhost",
                metric_name="cpu_frequency_current",
                value=cpu_freq.current,
                labels={},
                timestamp=timestamp,
            ))
            if cpu_freq.min:
                readings.append(Reading(
                    source_type="system",
                    source_name="localhost",
                    metric_name="cpu_frequency_min",
                    value=cpu_freq.min,
                    labels={},
                    timestamp=timestamp,
                ))
            if cpu_freq.max:
                readings.append(Reading(
                    source_type="system",
                    source_name="localhost",
                    metric_name="cpu_frequency_max",
                    value=cpu_freq.max,
                    labels={},
                    timestamp=timestamp,
                ))
        
        # CPU load averages
        load_avg = psutil.getloadavg()
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="load_average_1min",
            value=load_avg[0],
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="load_average_5min",
            value=load_avg[1],
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="load_average_15min",
            value=load_avg[2],
            labels={},
            timestamp=timestamp,
        ))
    except Exception as exc:
        LOGGER.warning("CPU metrics collection failed reason=%s", exc)
    
    return readings


def _collect_memory_metrics(timestamp: datetime) -> List[Reading]:
    """Collect memory usage metrics.
    
    Args:
        timestamp: Collection timestamp
        
    Returns:
        List of memory metric readings
    """
    readings: List[Reading] = []
    
    try:
        # Virtual memory
        virtual_mem = psutil.virtual_memory()
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="memory_virtual_total_bytes",
            value=float(virtual_mem.total),
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="memory_virtual_available_bytes",
            value=float(virtual_mem.available),
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="memory_virtual_percent",
            value=virtual_mem.percent,
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="memory_virtual_used_bytes",
            value=float(virtual_mem.used),
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="memory_virtual_free_bytes",
            value=float(virtual_mem.free),
            labels={},
            timestamp=timestamp,
        ))
        
        # Swap memory
        swap_mem = psutil.swap_memory()
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="memory_swap_total_bytes",
            value=float(swap_mem.total),
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="memory_swap_used_bytes",
            value=float(swap_mem.used),
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="memory_swap_free_bytes",
            value=float(swap_mem.free),
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="memory_swap_percent",
            value=swap_mem.percent,
            labels={},
            timestamp=timestamp,
        ))
    except Exception as exc:
        LOGGER.warning("Memory metrics collection failed reason=%s", exc)
    
    return readings


def _collect_disk_metrics(timestamp: datetime) -> List[Reading]:
    """Collect disk usage metrics.
    
    Args:
        timestamp: Collection timestamp
        
    Returns:
        List of disk metric readings
    """
    readings: List[Reading] = []
    
    try:
        # Disk usage for all partitions
        disk_partitions = psutil.disk_partitions()
        for partition in disk_partitions:
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                labels = {"device": partition.device, "mountpoint": partition.mountpoint}
                
                readings.append(Reading(
                    source_type="system",
                    source_name="localhost",
                    metric_name="disk_total_bytes",
                    value=float(usage.total),
                    labels=labels,
                    timestamp=timestamp,
                ))
                readings.append(Reading(
                    source_type="system",
                    source_name="localhost",
                    metric_name="disk_used_bytes",
                    value=float(usage.used),
                    labels=labels,
                    timestamp=timestamp,
                ))
                readings.append(Reading(
                    source_type="system",
                    source_name="localhost",
                    metric_name="disk_free_bytes",
                    value=float(usage.free),
                    labels=labels,
                    timestamp=timestamp,
                ))
                readings.append(Reading(
                    source_type="system",
                    source_name="localhost",
                    metric_name="disk_percent",
                    value=usage.percent,
                    labels=labels,
                    timestamp=timestamp,
                ))
            except Exception:
                # Skip partitions that can't be accessed
                continue
        
        # Disk I/O statistics
        disk_io = psutil.disk_io_counters()
        if disk_io:
            readings.append(Reading(
                source_type="system",
                source_name="localhost",
                metric_name="disk_io_read_bytes",
                value=float(disk_io.read_bytes),
                labels={},
                timestamp=timestamp,
            ))
            readings.append(Reading(
                source_type="system",
                source_name="localhost",
                metric_name="disk_io_write_bytes",
                value=float(disk_io.write_bytes),
                labels={},
                timestamp=timestamp,
            ))
            readings.append(Reading(
                source_type="system",
                source_name="localhost",
                metric_name="disk_io_read_count",
                value=float(disk_io.read_count),
                labels={},
                timestamp=timestamp,
            ))
            readings.append(Reading(
                source_type="system",
                source_name="localhost",
                metric_name="disk_io_write_count",
                value=float(disk_io.write_count),
                labels={},
                timestamp=timestamp,
            ))
    except Exception as exc:
        LOGGER.warning("Disk metrics collection failed reason=%s", exc)
    
    return readings


def _collect_network_metrics(timestamp: datetime) -> List[Reading]:
    """Collect network usage metrics.
    
    Args:
        timestamp: Collection timestamp
        
    Returns:
        List of network metric readings
    """
    readings: List[Reading] = []
    
    try:
        # Network I/O statistics
        net_io = psutil.net_io_counters()
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="network_io_bytes_sent",
            value=float(net_io.bytes_sent),
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="network_io_bytes_recv",
            value=float(net_io.bytes_recv),
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="network_io_packets_sent",
            value=float(net_io.packets_sent),
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="network_io_packets_recv",
            value=float(net_io.packets_recv),
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="network_io_errin",
            value=float(net_io.errin),
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="network_io_errout",
            value=float(net_io.errout),
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="network_io_dropin",
            value=float(net_io.dropin),
            labels={},
            timestamp=timestamp,
        ))
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="network_io_dropout",
            value=float(net_io.dropout),
            labels={},
            timestamp=timestamp,
        ))
        
        # Per-interface network statistics
        net_if_stats = psutil.net_if_stats()
        net_if_addrs = psutil.net_if_addrs()
        
        for interface, stats in net_if_stats.items():
            labels = {"interface": interface}
            readings.append(Reading(
                source_type="system",
                source_name="localhost",
                metric_name="network_interface_speed",
                value=float(stats.speed),
                labels=labels,
                timestamp=timestamp,
            ))
            readings.append(Reading(
                source_type="system",
                source_name="localhost",
                metric_name="network_interface_mtu",
                value=float(stats.mtu),
                labels=labels,
                timestamp=timestamp,
            ))
            
            # Check if interface has IP address
            if interface in net_if_addrs:
                has_ip = any(addr.family == psutil.AF_INET for addr in net_if_addrs[interface])
                readings.append(Reading(
                    source_type="system",
                    source_name="localhost",
                    metric_name="network_interface_has_ip",
                    value=1.0 if has_ip else 0.0,
                    labels=labels,
                    timestamp=timestamp,
                ))
    except Exception as exc:
        LOGGER.warning("Network metrics collection failed reason=%s", exc)
    
    return readings


def _collect_system_info(timestamp: datetime) -> List[Reading]:
    """Collect system information metrics.
    
    Args:
        timestamp: Collection timestamp
        
    Returns:
        List of system info readings
    """
    readings: List[Reading] = []
    
    try:
        # Boot time
        boot_time = psutil.boot_time()
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="system_boot_time",
            value=boot_time,
            labels={},
            timestamp=timestamp,
        ))
        
        # Number of processes
        process_count = len(psutil.pids())
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="system_process_count",
            value=float(process_count),
            labels={},
            timestamp=timestamp,
        ))
        
        # Number of users
        user_count = len(psutil.users())
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="system_user_count",
            value=float(user_count),
            labels={},
            timestamp=timestamp,
        ))
        
        # System uptime
        uptime = timestamp.timestamp() - boot_time
        readings.append(Reading(
            source_type="system",
            source_name="localhost",
            metric_name="system_uptime_seconds",
            value=uptime,
            labels={},
            timestamp=timestamp,
        ))
    except Exception as exc:
        LOGGER.warning("System info collection failed reason=%s", exc)
    
    return readings
