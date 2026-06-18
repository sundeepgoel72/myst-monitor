"""Telegram notification support for MystMon.

Provides functionality to send notifications and reports via Telegram bot API.
Supports daily reports with node status summaries and alert notifications
for node issues or collection failures.

The notifier integrates with the configuration system to get bot credentials
and report settings, and can be triggered manually or on a schedule.
"""

import asyncio
import logging
import os
from datetime import datetime, time
from typing import Any

import httpx

from mystmon.config import MystMonConfig

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends notifications via Telegram.
    
    Handles sending daily reports and alert notifications via Telegram bot API.
    Integrates with MystMon configuration for credentials and settings.
    """
    
    def __init__(self, config: MystMonConfig) -> None:
        """Initialize the Telegram notifier.
        
        Args:
            config: MystMon configuration containing Telegram settings
        """
        self.config = config
        # Fix: Resolve environment variables instead of storing variable names
        self.bot_token = os.getenv(config.telegram.bot_token_env) if config.telegram.bot_token_env else None
        self.chat_id = os.getenv(config.telegram.chat_id_env) if config.telegram.chat_id_env else None
        self.enabled = config.telegram.enabled and self.bot_token and self.chat_id
    
    async def send_report(self) -> None:
        """Send a daily report via Telegram.
        
        Generates and sends a daily status report containing node summaries
        and key metrics to the configured Telegram chat.
        """
        if not self.enabled:
            return
            
        try:
            message = self._generate_report_message()
            await self._send_message(message)
            logger.info("Telegram report sent successfully")
        except Exception as e:
            logger.error("Failed to send Telegram report: %s", e)
    
    def _generate_report_message(self) -> str:
        """Generate the report message content.
        
        Creates a formatted message with node status summaries and key metrics.
        
        Returns:
            Formatted report message
        """
        # This would typically gather data from the store/history
        # For now, return a placeholder message
        now = datetime.now()
        return f"📊 MystMon Daily Report - {now.strftime('%Y-%m-%d %H:%M')}\n\nReport content would go here."
    
    async def _send_message(self, message: str) -> None:
        """Send a message via Telegram API.
        
        Sends a message to the configured Telegram chat using the bot API.
        
        Args:
            message: Message to send
        """
        if not self.bot_token or not self.chat_id:
            raise ValueError("Bot token or chat ID not configured")
            
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "disable_notification": self.config.telegram.disable_notification,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()


def next_report_delay(config: Any) -> float:
    """Calculate the delay until the next report time.
    
    Determines how long to wait until the next scheduled report based on
    the configured report time and current time.
    
    Args:
        config: Telegram configuration containing report time settings
        
    Returns:
        Delay in seconds until next report time
    """
    if not config or not config.enabled:
        return 3600  # 1 hour default
        
    try:
        # Parse report time
        report_time = config.report_time_local or "09:00"
        hour, minute = map(int, report_time.split(":"))
        
        # Get current time
        now = datetime.now()
        report_datetime = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If report time has passed today, schedule for tomorrow
        if report_datetime <= now:
            report_datetime = report_datetime.replace(day=report_datetime.day + 1)
            
        # Calculate delay
        delay = (report_datetime - now).total_seconds()
        return max(delay, 60)  # Minimum 1 minute delay
    except Exception as e:
        logger.warning("Failed to calculate report delay, using default: %s", e)
        return 3600  # 1 hour default
```

mystmon/snapshot.py
