"""
TelegramBotManager: Telegram bot management class.
Bot initialization, command routing and error management.
"""
import asyncio
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Optional
from telegram import Update
from telegram.error import TimedOut, RetryAfter
from telegram.ext import Application, ContextTypes, CallbackQueryHandler
from utils.logger import LoggerManager
from utils.logger import LoggerManager


class TelegramBotManager:
    """Manages Telegram bot."""
    
    def __init__(self, token: str, reminder_manager=None):
        """
        Initializes TelegramBotManager.
        
        Args:
            token: Telegram bot token
            reminder_manager: Forecast reminder manager (optional)
        """
        self.token = token
        self.reminder_manager = reminder_manager
        self.logger = LoggerManager().get_logger('TelegramBot')
        self.application = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Lifecycle notification helpers
        self._channel_id = None
        self._forecast_cache = None
    
    async def error_handler(
        self, update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Global error handler.
        
        Args:
            update: Telegram update
            context: Bot context
        """
        self.logger.error(
            f"Bot error: {context.error}", 
            exc_info=context.error
        )
        
        try:
            if isinstance(update, Update) and update.message:
                await update.message.reply_text(
                    "❌ An error occurred. Please try again later."
                )
        except Exception as e:
            self.logger.error(f"Error in error handler: {e}", exc_info=True)
    
    def setup_handlers(self) -> None:
        """Configures bot handlers."""
        self.logger.debug("Setting up Telegram handlers")
        # Callback query handler for signal updates
        self.application.add_handler(
            CallbackQueryHandler(self.handle_signal_update_callback, pattern="^update_signal:")
        )
        
        # Error handler
        self.application.add_error_handler(self.error_handler)

        # Lifecycle callbacks (post_init/post_shutdown)
        # Channel and cache will be configured by configure_lifecycle_notifications
        async def _on_post_init(app: Application) -> None:
            try:
                self._loop = asyncio.get_running_loop()
                if self._channel_id:
                    stats = {'size': 0, 'oldest_age_sec': None, 'newest_age_sec': None}
                    if self._forecast_cache:
                        stats = self._forecast_cache.get_cache_stats()
                    msg = (
                        "✅ Bot started\n"
                        f"🧠 Cache: size={stats['size']}, oldest={stats['oldest_age_sec']}s, newest={stats['newest_age_sec']}s"
                    )
                    await app.bot.send_message(chat_id=self._channel_id, text=msg)
                    self.logger.info("Channel message sent (post_init)")
            except Exception as e:
                self.logger.error(f"post_init channel message error: {e}")

        async def _on_post_shutdown(app: Application) -> None:
            try:
                if self._channel_id:
                    stats = {'size': 0, 'oldest_age_sec': None, 'newest_age_sec': None}
                    if self._forecast_cache:
                        stats = self._forecast_cache.get_cache_stats()
                    msg = (
                        "🛑 Bot stopped\n"
                        f"🧠 Cache: size={stats['size']}, oldest={stats['oldest_age_sec']}s, newest={stats['newest_age_sec']}s"
                    )
                    await app.bot.send_message(chat_id=self._channel_id, text=msg)
                    self.logger.info("Channel message sent (post_shutdown)")
            except Exception as e:
                # HTTP connection might be closed when bot is shutting down - this is normal
                if "HTTPXRequest" in str(e) or "not initialized" in str(e):
                    self.logger.debug(f"Post-shutdown message could not be sent (bot already closed): {e}")
                else:
                    self.logger.error(f"post_shutdown channel message error: {e}")
            finally:
                self._loop = None

        # PTB v20+: post_init/post_shutdown callbacks must be assigned
        self.application.post_init = _on_post_init
        self.application.post_shutdown = _on_post_shutdown
    
    async def send_message_to_channel(
        self, channel_id: str, message: str, reply_markup=None
    ) -> Optional[int]:
        """
        Sends message to channel.
        
        Args:
            channel_id: Telegram channel ID
            message: Message to send
            reply_markup: Inline keyboard markup (optional)
            
        Returns:
            Telegram message_id or None
        """
        try:
            kwargs = {
                'chat_id': channel_id,
                'text': message,
                'parse_mode': 'MarkdownV2'  # Use MarkdownV2 format
            }
            if reply_markup:
                kwargs['reply_markup'] = reply_markup
                
            sent_message = await self.application.bot.send_message(**kwargs)
            message_id = sent_message.message_id
            self.logger.info(f"Channel message sent - Message ID: {message_id}")
            return message_id
        except Exception as e:
            error_msg = str(e).lower()
            # Markdown parse error check
            if "can't parse entities" in error_msg or "bad request" in error_msg:
                self.logger.warning(
                    f"Markdown parse hatası, mesaj plain text olarak gönderilecek: {str(e)}"
                )
                # Plain text olarak tekrar dene
                try:
                    kwargs['parse_mode'] = None  # Remove parse mode
                    sent_message = await self.application.bot.send_message(**kwargs)
                    message_id = sent_message.message_id
                    self.logger.info(f"Channel message sent as plain text - Message ID: {message_id}")
                    return message_id
                except Exception as retry_error:
                    self.logger.error(
                        f"Plain text channel message sending error: {str(retry_error)}",
                        exc_info=True
                    )
                    return None
            else:
                self.logger.error(
                    f"Channel message could not be sent: {str(e)}",
                    exc_info=True
                )
                return None

    def send_channel_message(self, channel_id: str, message: str, reply_markup=None) -> Optional[int]:
        """
        Sends message to channel (sync wrapper).
        
        Args:
            channel_id: Telegram channel ID
            message: Message to send
            reply_markup: Inline keyboard markup (optional)
            
        Returns:
            Telegram message_id or None
        """
        try:
            if not self.application:
                self.logger.error("Bot application not initialized yet (channel)")
                return None
            result = self._run_on_bot_loop(
                self.send_message_to_channel(channel_id, message, reply_markup)
            )
            return result
        except Exception as e:
            self.logger.error(f"Channel message could not be sent (sync): {str(e)}", exc_info=True)
            return None
    
    async def edit_message_to_channel(
        self, channel_id: str, message_id: int, message: str, reply_markup=None
    ) -> tuple[bool, bool]:
        """
        Edits channel message.
        
        Args:
            channel_id: Telegram channel ID
            message_id: Message ID to edit
            message: New message content
            reply_markup: Inline keyboard markup (optional, if None keeps current keyboard)
            
        Returns:
            (success: bool, message_not_found: bool)
            - success: True if successful
            - message_not_found: True if message not found (deleted)
        """
        try:
            # If reply_markup is None, get keyboard from current message
            if reply_markup is None:
                try:
                    current_message = await self.application.bot.get_chat(chat_id=channel_id)
                    # Cannot get message with get_chat, must use get_message
                    # But get_message is not available for channel, so we leave it None
                    # Telegram automatically preserves current keyboard
                except Exception:
                    pass
            
            kwargs = {
                'chat_id': channel_id,
                'message_id': message_id,
                'text': message,
                'parse_mode': 'MarkdownV2'  # Use MarkdownV2 format
            }
            # If reply_markup is None, Telegram automatically preserves current keyboard
            # Instead of sending explicit None, we don't send the parameter at all
            if reply_markup is not None:
                kwargs['reply_markup'] = reply_markup
                
            try:
                await self.application.bot.edit_message_text(**kwargs)
                self.logger.info(f"Channel message updated - Message ID: {message_id}")
                return (True, False)
            except Exception as e:
                # "Message is not modified" error is normal (if content didn't change)
                if "Message is not modified" in str(e):
                    self.logger.debug(f"Message content same, update skipped: {message_id}")
                    return (True, False)  # Count as success
                raise e  # Raise other errors (for parse error handling)
        except Exception as parse_error:
            error_msg = str(parse_error).lower()
            # Markdown parse error check
            if "can't parse entities" in error_msg or "bad request" in error_msg:
                self.logger.warning(
                    f"Markdown parse error, message will be updated as plain text: {str(parse_error)}"
                )
                # Retry as plain text
                try:
                    kwargs['parse_mode'] = None  # Remove parse mode
                    await self.application.bot.edit_message_text(**kwargs)
                    self.logger.info(f"Channel message updated as plain text - Message ID: {message_id}")
                    return (True, False)
                except Exception as retry_error:
                    self.logger.error(
                        f"Plain text channel message update error: {str(retry_error)}",
                        exc_info=True
                    )
                    return (False, False)
            # Separate handling for RetryAfter error
            if isinstance(parse_error, RetryAfter):
                raise  # Raise RetryAfter
            # Normal handling for other errors
            raise
        except RetryAfter as e:
            # Flood control: Wait for Telegram's specified time and retry
            retry_after = e.retry_after
            self.logger.warning(
                f"Telegram flood control: Waiting {retry_after} seconds - Message ID: {message_id}"
            )
            await asyncio.sleep(retry_after)
            try:
                kwargs = {
                    'chat_id': channel_id,
                    'message_id': message_id,
                    'text': message,
                    'parse_mode': 'MarkdownV2'  # Use MarkdownV2 format
                }
                if reply_markup is not None:
                    kwargs['reply_markup'] = reply_markup
                    
                await self.application.bot.edit_message_text(**kwargs)
                self.logger.info(f"Channel message updated (after retry) - Message ID: {message_id}")
                return (True, False)
            except Exception as retry_error:
                error_msg = str(retry_error).lower()
                # Markdown parse error check
                if "can't parse entities" in error_msg or "bad request" in error_msg:
                    try:
                        kwargs['parse_mode'] = None
                        await self.application.bot.edit_message_text(**kwargs)
                        self.logger.info(f"Channel message updated as plain text (after retry) - Message ID: {message_id}")
                        return (True, False)
                    except Exception:
                        pass  # Fall through to message_not_found check
                is_message_not_found = (
                    "message to edit not found" in error_msg or
                    "message not found" in error_msg
                )
                if is_message_not_found:
                    self.logger.warning(
                        f"Telegram message not found (after retry): Message ID: {message_id}"
                    )
                    return (False, True)
                else:
                    self.logger.error(
                        f"Channel message could not be updated (after retry): {str(retry_error)}",
                        exc_info=True
                    )
                    return (False, False)
        except TimedOut:
            # Timeout: Wait 2 seconds and retry once
            self.logger.warning(
                f"Telegram timeout - waiting 2 seconds and retrying - Message ID: {message_id}"
            )
            await asyncio.sleep(2)
            try:
                kwargs = {
                    'chat_id': channel_id,
                    'message_id': message_id,
                    'text': message,
                    'parse_mode': 'MarkdownV2'  # Use MarkdownV2 format
                }
                if reply_markup is not None:
                    kwargs['reply_markup'] = reply_markup
                    
                await self.application.bot.edit_message_text(**kwargs)
                self.logger.info(f"Channel message updated (after timeout retry) - Message ID: {message_id}")
                return (True, False)
            except Exception as retry_error:
                error_msg = str(retry_error).lower()
                # Markdown parse error check
                if "can't parse entities" in error_msg or "bad request" in error_msg:
                    try:
                        kwargs['parse_mode'] = None
                        await self.application.bot.edit_message_text(**kwargs)
                        self.logger.info(f"Channel message updated as plain text (after timeout retry) - Message ID: {message_id}")
                        return (True, False)
                    except Exception:
                        pass  # Fall through to message_not_found check
                is_message_not_found = (
                    "message to edit not found" in error_msg or
                    "message not found" in error_msg
                )
                if is_message_not_found:
                    self.logger.warning(
                        f"Telegram message not found (after timeout retry): Message ID: {message_id}"
                    )
                    return (False, True)
                else:
                    # Still failed after timeout retry, but don't count as deleted
                    # Because real issue might be network
                    self.logger.error(
                        f"Channel message could not be updated (after timeout retry): {str(retry_error)}",
                        exc_info=True
                    )
                    return (False, False)
        except Exception as e:
            error_message = str(e).lower()
            # Check "Message to edit not found" error
            is_message_not_found = (
                "message to edit not found" in error_message or
                "message not found" in error_message
            )
            
            if is_message_not_found:
                self.logger.warning(
                    f"Telegram message not found (might be deleted): Message ID: {message_id}"
                )
            else:
                self.logger.error(
                    f"Channel message could not be updated: {str(e)}",
                    exc_info=True
                )
            return (False, is_message_not_found)
    
    def edit_channel_message(
        self, channel_id: str, message_id: int, message: str, reply_markup=None
    ) -> tuple[bool, bool]:
        """
        Edits channel message (sync wrapper).
        
        Args:
            channel_id: Telegram channel ID
            message_id: Message ID to edit
            message: New message content
            reply_markup: Inline keyboard markup (optional, if None keeps current keyboard)
            
        Returns:
            (success: bool, message_not_found: bool)
            - success: True if successful
            - message_not_found: True if message not found (deleted)
        """
        try:
            if not self.application:
                self.logger.error("Bot application not initialized yet (edit channel)")
                return (False, False)
            result = self._run_on_bot_loop(
                self.edit_message_to_channel(channel_id, message_id, message, reply_markup)
            )
            if isinstance(result, tuple) and len(result) == 2:
                return result
            # Fallback for old format
            return (bool(result), False)
        except Exception as e:
            self.logger.error(f"Channel message could not be edited (sync): {str(e)}", exc_info=True)
            return (False, False)
    
    async def check_message_exists_async(
        self, channel_id: str, message_id: int, reply_markup=None
    ) -> tuple[bool, bool]:
        """
        Checks if a message exists without modifying its text.
        
        Uses editMessageReplyMarkup to update only the inline keyboard,
        which allows checking message existence without requiring message text.
        
        Args:
            channel_id: Telegram channel ID
            message_id: Message ID to check
            reply_markup: Inline keyboard markup (optional, uses current if None)
            
        Returns:
            (exists: bool, message_not_found: bool)
            - exists: True if message exists
            - message_not_found: True if message not found (deleted)
        """
        try:
            # Use editMessageReplyMarkup - doesn't require message text
            await self.application.bot.edit_message_reply_markup(
                chat_id=channel_id,
                message_id=message_id,
                reply_markup=reply_markup
            )
            self.logger.debug(f"Message exists check passed - Message ID: {message_id}")
            return (True, False)
        except Exception as e:
            error_message = str(e).lower()
            # Check "Message to edit not found" error
            is_message_not_found = (
                "message to edit not found" in error_message or
                "message not found" in error_message
            )
            
            # "Message is not modified" is also a success - means message exists
            if "message is not modified" in error_message:
                self.logger.debug(f"Message exists (not modified) - Message ID: {message_id}")
                return (True, False)
            
            if is_message_not_found:
                self.logger.debug(f"Message not found - Message ID: {message_id}")
                return (False, True)
            else:
                self.logger.warning(
                    f"Message existence check error: {str(e)} - Message ID: {message_id}"
                )
                # Unknown error - assume message might exist (don't delete)
                return (False, False)
    
    def check_message_exists(
        self, channel_id: str, message_id: int, reply_markup=None
    ) -> tuple[bool, bool]:
        """
        Checks if a message exists (sync wrapper).
        
        Args:
            channel_id: Telegram channel ID
            message_id: Message ID to check
            reply_markup: Inline keyboard markup (optional)
            
        Returns:
            (exists: bool, message_not_found: bool)
        """
        try:
            if not self.application:
                self.logger.error("Bot application not initialized yet (check message)")
                return (False, False)
            result = self._run_on_bot_loop(
                self.check_message_exists_async(channel_id, message_id, reply_markup)
            )
            if isinstance(result, tuple) and len(result) == 2:
                return result
            return (False, False)
        except Exception as e:
            self.logger.error(f"Message existence check failed (sync): {str(e)}", exc_info=True)
            return (False, False)
    
    def send_message(
        self, chat_id: int, text: str, reply_to_message_id: int = None
    ) -> None:
        """
        Sends message to user (sync wrapper).
        
        Args:
            chat_id: Chat ID
            text: Message to send
            reply_to_message_id: Message ID to reply to (optional)
        """
        try:
            if not self.application:
                self.logger.error("Bot application not initialized yet")
                return
            self._run_on_bot_loop(
                self._send_message_async(chat_id, text, reply_to_message_id),
                return_result=False
            )
        except Exception as e:
            self.logger.error(
                f"Message could not be sent: {str(e)}",
                exc_info=True
            )
    
    async def _send_message_async(
        self, chat_id: int, text: str, reply_to_message_id: int = None
    ) -> None:
        """
        Async message sending function.
        
        Args:
            chat_id: Chat ID
            text: Message to send
            reply_to_message_id: Message ID to reply to (optional)
        """
        try:
            kwargs = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'MarkdownV2'  # Use MarkdownV2 format
            }
            if reply_to_message_id:
                kwargs['reply_to_message_id'] = reply_to_message_id
            self.logger.debug(f"send_message kwargs: {kwargs | {'text': f'<{len(text)} chars>'}}")
                
            await self.application.bot.send_message(**kwargs)
            self.logger.info(f"Message sent - Chat: {chat_id}")
        except Exception as e:
            error_msg = str(e).lower()
            # Markdown parse error check
            if "can't parse entities" in error_msg or "bad request" in error_msg:
                self.logger.warning(
                    f"Markdown parse hatası, mesaj plain text olarak gönderilecek: {str(e)}"
                )
                # Plain text olarak tekrar dene
                try:
                    kwargs['parse_mode'] = None  # Remove parse mode
                    await self.application.bot.send_message(**kwargs)
                    self.logger.info(f"Message sent as plain text - Chat: {chat_id}")
                except Exception as retry_error:
                    self.logger.error(
                        f"Plain text message sending error: {str(retry_error)}",
                        exc_info=True
                    )
            else:
                self.logger.error(
                    f"Async message sending error: {str(e)}",
                    exc_info=True
                )
    
    def _run_on_bot_loop(self, coro, return_result: bool = True):
        """Runs coroutine safely on bot's event loop."""
        if not self._loop or not self._loop.is_running():
            self.logger.error("Telegram bot event loop is not ready or not running")
            return None

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        if not return_result:
            return future

        try:
            return future.result()
        except FuturesTimeoutError:
            self.logger.error("Telegram bot loop call timed out")
            return None
        except Exception as exc:
            self.logger.error(
                f"Telegram bot loop call failed: {exc}",
                exc_info=True
            )
            return None

    def initialize(self) -> None:
        """Initializes the bot."""
        self.application = Application.builder().token(self.token).build()
        self.setup_handlers()
        self.logger.info("Telegram bot initialized")

    def configure_lifecycle_notifications(self, channel_id: str, forecast_cache) -> None:
        """Enables lifecycle notifications by providing channel ID and cache reference."""
        self._channel_id = channel_id
        self._forecast_cache = forecast_cache
    
    def set_signal_tracker(self, signal_tracker) -> None:
        """Sets SignalTracker instance (for callback handler)."""
        self._signal_tracker = signal_tracker
    
    async def handle_signal_update_callback(self, update, context) -> None:
        """
        Signal update callback query handler.
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        query = None
        try:
            query = update.callback_query
            if not query:
                return
            
            # Parse callback_data: "update_signal:{signal_id}"
            callback_data = query.data
            if not callback_data or not callback_data.startswith("update_signal:"):
                self.logger.warning(f"Invalid callback_data: {callback_data}")
                await query.answer("❌ Invalid request", show_alert=True)
                return
            
            signal_id = callback_data.replace("update_signal:", "")
            if not signal_id:
                self.logger.warning("Signal ID not found")
                await query.answer("❌ Signal ID not found", show_alert=True)
                return
            
            self.logger.info(f"Signal update callback: {signal_id}")
            
            # Access SignalTracker instance
            signal_tracker = getattr(self, '_signal_tracker', None)
            if not signal_tracker:
                self.logger.error("Could not access SignalTracker instance")
                await query.answer("❌ Error: SignalTracker not found", show_alert=True)
                return
            
            # IMPORTANT: Answer callback query IMMEDIATELY (to prevent Telegram timeout)
            # Telegram's callback query timeout is very short, so we answer first
            try:
                await query.answer("⏳ Updating...")
            except Exception as e:
                # "Query is too old" error is normal (if old buttons are clicked after restart)
                # Log this error but don't stop execution (continue update)
                if "Query is too old" in str(e):
                    self.logger.warning(f"Callback query timeout (normal): {str(e)}")
                else:
                    self.logger.warning(f"Callback query answer error: {str(e)}")
            
            # Get signal from database
            signal = signal_tracker.repository.get_signal(signal_id)
            if not signal:
                self.logger.warning(f"Signal not found: {signal_id}")
                # We already answered the query, just log
                return
            
            # Update message (sync method, run in thread - non-blocking)
            # update_message_for_signal is a sync method, so we must run it in a thread
            import threading
            def update_signal():
                try:
                    signal_tracker.update_message_for_signal(signal)
                    self.logger.info(f"Signal update completed: {signal_id}")
                except Exception as e:
                    self.logger.error(f"Signal update error: {str(e)}", exc_info=True)
            
            # Run in thread (non-blocking, daemon thread)
            thread = threading.Thread(target=update_signal, daemon=True)
            thread.start()
            # We don't join(), let it run in background - we already answered the callback query
            
        except Exception as e:
            self.logger.error(
                f"Signal update callback error: {str(e)}",
                exc_info=True
            )
            if query:
                try:
                    await query.answer("❌ Update error", show_alert=True)
                except Exception:
                    pass
    
    def run(self) -> None:
        """Starts the bot (blocking)."""
        if not self.application:
            self.initialize()
        
        self.logger.info("Starting Telegram bot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
