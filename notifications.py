import asyncio
import logging
import time
from typing import Dict, Optional
from aiogram import Bot
from admin import ADMIN_IDS

logger = logging.getLogger(__name__)

class NotificationManager:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.last_alerts: Dict[str, float] = {} # key: timestamp
        self.alert_history: Dict[str, float] = {} # message_hash: timestamp (for deduplication)
        self.rate_limit_window = 60 # seconds
        self.dedup_window = 300 # seconds

    async def send_alert(self, level: str, message: str, key: Optional[str] = None):
        """
        Send an alert to all admins.
        level: 'INFO', 'WARNING', 'CRITICAL'
        key: Unique key for rate limiting (e.g., 'high_cpu', 'user_violation_123')
        """
        # 1. Deduplication
        msg_hash = hash(message)
        current_time = time.time()
        
        if msg_hash in self.alert_history:
            if current_time - self.alert_history[msg_hash] < self.dedup_window:
                logger.info(f"Suppressed duplicate alert: {message}")
                return
        self.alert_history[msg_hash] = current_time

        # 2. Rate Limiting (if key provided)
        if key:
            if key in self.last_alerts:
                if current_time - self.last_alerts[key] < self.rate_limit_window:
                    logger.info(f"Rate limited alert: {key}")
                    return
            self.last_alerts[key] = current_time

        # 3. Format Message
        emoji = {
            'INFO': 'ℹ️',
            'WARNING': '⚠️',
            'CRITICAL': '🚨'
        }.get(level, '📢')
        
        formatted_msg = f"{emoji} *ADMIN ALERT: {level}*\n\n{message}"

        # 4. Send to Admins
        for admin_id in ADMIN_IDS:
            try:
                await self.bot.send_message(admin_id, formatted_msg, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Failed to send alert to {admin_id}: {e}")

# Global instance will be initialized in bot.py
notify: Optional[NotificationManager] = None
