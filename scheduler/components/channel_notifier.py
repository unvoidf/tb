"""
ChannelNotifier: Channel message sending component.
Sends hourly analysis results to the channel.
"""
from typing import List, Dict
import asyncio
import nest_asyncio
from utils.logger import LoggerManager
from bot.telegram_bot_manager import TelegramBotManager
from bot.message_formatter import MessageFormatter
from config.config_manager import ConfigManager


class ChannelNotifier:
    """Channel message sending component."""
    
    def __init__(self, bot_manager: TelegramBotManager, formatter: MessageFormatter, market_data):
        """
        Initializes ChannelNotifier.
        
        Args:
            bot_manager: Telegram bot manager
            formatter: Mesaj formatter
            market_data: Market data manager
        """
        self.bot_mgr = bot_manager
        self.formatter = formatter
        self.market_data = market_data
        self.logger = LoggerManager().get_logger('ChannelNotifier')
        self.config = ConfigManager()
    
    def send_hourly_analysis(self, top_signals: List[Dict], channel_id: str) -> bool:
        """
        Sends hourly analysis results to the channel.
        
        Args:
            top_signals: List of top signals
            channel_id: Telegram channel ID
            
        Returns:
            Is sending successful
        """
        try:
            # Format message
            message = self._format_hourly_message(top_signals)
            
            # Send message
            self._send_channel_message_sync(message, channel_id)
            
            self.logger.info(
                f"Hourly analysis completed - {len(top_signals)} signals sent"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Channel message could not be sent: {str(e)}")
            # Notify admins
            self._notify_admins_about_error(e, top_signals)
            return False
    
    def _format_hourly_message(self, top_signals: List[Dict]) -> str:
        """
        Formats hourly message.
        
        Args:
            top_signals: List of top signals
            
        Returns:
            Formatted message
        """
        from datetime import datetime
        
        header = (
            "⏰ HOURLY MARKET ANALYSIS\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        )
        
        summary = self.formatter.format_trend_summary_with_prices(top_signals, self.market_data)
        
        footer = (
            "\n💡 For detailed analysis: /analyze [COIN]\n"
            "Example: /analyze BTC"
        )
        
        return header + summary + footer
    
    def _send_channel_message_sync(self, message: str, channel_id: str) -> None:
        """
        Sends channel message from sync context.
        
        Args:
            message: Message to send
            channel_id: Channel ID
        """
        nest_asyncio.apply()
        
        asyncio.run(
            self.bot_mgr.send_message_to_channel(
                channel_id,
                message
            )
        )
    
    def _notify_admins_about_error(self, error: Exception, top_signals: List[Dict]) -> None:
        """
        Sends notification to admins when channel message fails.
        
        Args:
            error: Error occurred
            top_signals: Signals attempted to send
        """
        try:
            error_notification = (
                "⚠️ CHANNEL MESSAGE FAILED\n\n"
                f"Error: {str(error)}\n\n"
                "Possible Causes:\n"
                "• Bot not added as admin to channel\n"
                "• Incorrect Channel ID\n"
                "• Bot lacks message sending permission\n\n"
                "Solution:\n"
                "1. Add bot as admin to channel\n"
                "2. Grant 'Post Messages' permission\n"
                "3. Check Channel ID (.env file)\n\n"
                f"📊 Number of Signals Attempted: {len(top_signals)}"
            )
            
            # Send to admin users
            admin_users = self.config.admin_user_ids
            
            if not admin_users:
                self.logger.warning(
                    "Admin user ID not defined - "
                    "Add ADMIN_USER_IDS to .env"
                )
                return
            
            for user_id in admin_users:
                try:
                    nest_asyncio.apply()
                    
                    asyncio.run(
                        self.bot_mgr.application.bot.send_message(
                            chat_id=user_id,
                            text=error_notification
                        )
                    )
                    
                    self.logger.info(f"Error notification sent: User {user_id}")
                except Exception as notify_error:
                    self.logger.error(
                        f"Could not send notification to User {user_id}: {str(notify_error)}"
                    )
        except Exception as e:
            self.logger.error(f"Error during admin notification: {str(e)}", exc_info=True)
