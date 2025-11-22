"""
Notification Manager
--------------------
Manages Telegram notifications for simulation results.
"""
import os
import asyncio
from typing import Optional
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_USER_IDS = os.getenv('ADMIN_USER_IDS', '')
if not ADMIN_USER_IDS:
    ADMIN_USER_IDS = os.getenv('TELEGRAM_ADMIN_ID', '')


class NotificationManager:
    """Manages sending notifications via Telegram."""
    
    def __init__(self, bot_token: Optional[str] = None, admin_ids: Optional[str] = None):
        self.bot_token = bot_token or TELEGRAM_BOT_TOKEN
        self.admin_ids = admin_ids or ADMIN_USER_IDS
    
    async def send_telegram_report(self, report_text: str):
        """Sends the report to the admin user via Telegram."""
        if not self.bot_token or not self.admin_ids:
            print("⚠️ Telegram credentials missing.")
            return

        try:
            bot = Bot(token=self.bot_token)
            admin_id = int(self.admin_ids.split(',')[0].strip())
            
            chunk_size = 4000
            for i in range(0, len(report_text), chunk_size):
                chunk = report_text[i:i + chunk_size]
                # Use Markdown parse mode for better mobile formatting
                try:
                    await bot.send_message(
                        chat_id=admin_id, 
                        text=chunk, 
                        parse_mode='Markdown'
                    )
                except Exception:
                    # Fallback to plain text if Markdown parsing fails
                    await bot.send_message(chat_id=admin_id, text=chunk)
            print(f"✅ Report sent to admin ID: {admin_id}")
        except Exception as e:
            print(f"❌ Failed to send Telegram message: {e}")
    
    def send_report(self, report_text: str):
        """Synchronous wrapper for sending Telegram report."""
        asyncio.run(self.send_telegram_report(report_text))

