"""
TelegramBotManager: Telegram bot yönetim sınıfı.
Bot başlatma, komut routing ve hata yönetimi.
"""
import asyncio
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Optional
from telegram import Update
from telegram.error import TimedOut, RetryAfter
from telegram.ext import Application, ContextTypes, CallbackQueryHandler
from utils.logger import LoggerManager
from bot.command_handler import CommandHandler


class TelegramBotManager:
    """Telegram bot'u yönetir."""
    
    def __init__(self, token: str, command_handler: CommandHandler, reminder_manager=None):
        """
        TelegramBotManager'ı başlatır.
        
        Args:
            token: Telegram bot token
            command_handler: Komut işleyici
            reminder_manager: Forecast reminder manager (opsiyonel)
        """
        self.token = token
        self.cmd_handler = command_handler
        self.reminder_manager = reminder_manager
        self.logger = LoggerManager().get_logger('TelegramBot')
        self.application = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Command handlers'ı initialize et
        self._initialize_command_handlers()

        # Lifecycle notification helpers
        self._channel_id = None
        self._forecast_cache = None
    
    def _initialize_command_handlers(self) -> None:
        """Command handler'larını initialize eder (yalnızca callback için placeholder)."""
        self.logger.debug("Initializing command handlers (noop - only callback active)")
    
    async def error_handler(
        self, update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Global hata handler.
        
        Args:
            update: Telegram update
            context: Bot context
        """
        self.logger.error(
            f"Bot hatası: {context.error}", 
            exc_info=context.error
        )
        
        try:
            if isinstance(update, Update) and update.message:
                await update.message.reply_text(
                    "❌ Bir hata oluştu. Lütfen daha sonra tekrar deneyin."
                )
        except Exception as e:
            self.logger.error(f"Error handler'da hata: {e}", exc_info=True)
    
    def setup_handlers(self) -> None:
        """Bot handler'larını yapılandırır."""
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
                        "✅ Bot başlatıldı\n"
                        f"🧠 Cache: size={stats['size']}, oldest={stats['oldest_age_sec']}s, newest={stats['newest_age_sec']}s"
                    )
                    await app.bot.send_message(chat_id=self._channel_id, text=msg)
                    self.logger.info("Kanal mesajı gönderildi (post_init)")
            except Exception as e:
                self.logger.error(f"post_init kanal mesajı hatası: {e}")

        async def _on_post_shutdown(app: Application) -> None:
            try:
                if self._channel_id:
                    stats = {'size': 0, 'oldest_age_sec': None, 'newest_age_sec': None}
                    if self._forecast_cache:
                        stats = self._forecast_cache.get_cache_stats()
                    msg = (
                        "🛑 Bot kapatıldı\n"
                        f"🧠 Cache: size={stats['size']}, oldest={stats['oldest_age_sec']}s, newest={stats['newest_age_sec']}s"
                    )
                    await app.bot.send_message(chat_id=self._channel_id, text=msg)
                    self.logger.info("Kanal mesajı gönderildi (post_shutdown)")
            except Exception as e:
                # Bot kapatılırken HTTP bağlantısı zaten kapatılmış olabilir - bu normal
                if "HTTPXRequest" in str(e) or "not initialized" in str(e):
                    self.logger.debug(f"Post-shutdown mesajı gönderilemedi (bot zaten kapatılmış): {e}")
                else:
                    self.logger.error(f"post_shutdown kanal mesajı hatası: {e}")
            finally:
                self._loop = None

        # PTB v20+: post_init/post_shutdown callback'ları assign edilmelidir
        self.application.post_init = _on_post_init
        self.application.post_shutdown = _on_post_shutdown
    
    async def send_message_to_channel(
        self, channel_id: str, message: str, reply_markup=None
    ) -> Optional[int]:
        """
        Kanala mesaj gönderir.
        
        Args:
            channel_id: Telegram kanal ID
            message: Gönderilecek mesaj
            reply_markup: Inline keyboard markup (opsiyonel)
            
        Returns:
            Telegram message_id veya None
        """
        try:
            kwargs = {
                'chat_id': channel_id,
                'text': message,
                'parse_mode': 'MarkdownV2'  # MarkdownV2 formatını kullan
            }
            if reply_markup:
                kwargs['reply_markup'] = reply_markup
                
            sent_message = await self.application.bot.send_message(**kwargs)
            message_id = sent_message.message_id
            self.logger.info(f"Kanal mesajı gönderildi - Message ID: {message_id}")
            return message_id
        except Exception as e:
            error_msg = str(e).lower()
            # Markdown parse hatası kontrolü
            if "can't parse entities" in error_msg or "bad request" in error_msg:
                self.logger.warning(
                    f"Markdown parse hatası, mesaj plain text olarak gönderilecek: {str(e)}"
                )
                # Plain text olarak tekrar dene
                try:
                    kwargs['parse_mode'] = None  # Parse mode'u kaldır
                    sent_message = await self.application.bot.send_message(**kwargs)
                    message_id = sent_message.message_id
                    self.logger.info(f"Kanal mesajı plain text olarak gönderildi - Message ID: {message_id}")
                    return message_id
                except Exception as retry_error:
                    self.logger.error(
                        f"Plain text kanal mesajı gönderme hatası: {str(retry_error)}",
                        exc_info=True
                    )
                    return None
            else:
                self.logger.error(
                    f"Kanal mesajı gönderilemedi: {str(e)}",
                    exc_info=True
                )
                return None

    def send_channel_message(self, channel_id: str, message: str, reply_markup=None) -> Optional[int]:
        """
        Kanala mesaj gönderir (sync wrapper).
        
        Args:
            channel_id: Telegram kanal ID
            message: Gönderilecek mesaj
            reply_markup: Inline keyboard markup (opsiyonel)
            
        Returns:
            Telegram message_id veya None
        """
        try:
            if not self.application:
                self.logger.error("Bot application henüz initialize edilmemiş (channel)")
                return None
            result = self._run_on_bot_loop(
                self.send_message_to_channel(channel_id, message, reply_markup)
            )
            return result
        except Exception as e:
            self.logger.error(f"Channel mesajı gönderilemedi (sync): {str(e)}", exc_info=True)
            return None
    
    async def edit_message_to_channel(
        self, channel_id: str, message_id: int, message: str, reply_markup=None
    ) -> tuple[bool, bool]:
        """
        Kanal mesajını düzenler.
        
        Args:
            channel_id: Telegram kanal ID
            message_id: Düzenlenecek mesaj ID
            message: Yeni mesaj içeriği
            reply_markup: Inline keyboard markup (opsiyonel, None ise mevcut keyboard korunur)
            
        Returns:
            (success: bool, message_not_found: bool)
            - success: True ise başarılı
            - message_not_found: True ise mesaj bulunamadı (silinmiş)
        """
        try:
            # Eğer reply_markup None ise, mevcut mesajdan keyboard'u al
            if reply_markup is None:
                try:
                    current_message = await self.application.bot.get_chat(chat_id=channel_id)
                    # get_chat ile mesaj alınamaz, get_message kullanmalıyız
                    # Ama channel için get_message yok, bu yüzden None bırakıyoruz
                    # Telegram otomatik olarak mevcut keyboard'u korur
                except Exception:
                    pass
            
            kwargs = {
                'chat_id': channel_id,
                'message_id': message_id,
                'text': message,
                'parse_mode': 'MarkdownV2'  # MarkdownV2 formatını kullan
            }
            # reply_markup None ise, Telegram otomatik olarak mevcut keyboard'u korur
            # Explicit olarak None göndermek yerine, parametreyi hiç göndermeyiz
            if reply_markup is not None:
                kwargs['reply_markup'] = reply_markup
                
            try:
                await self.application.bot.edit_message_text(**kwargs)
                self.logger.info(f"Kanal mesajı güncellendi - Message ID: {message_id}")
                return (True, False)
            except Exception as e:
                # "Message is not modified" hatası normaldir (içerik değişmediyse)
                if "Message is not modified" in str(e):
                    self.logger.debug(f"Mesaj içeriği aynı, güncelleme atlandı: {message_id}")
                    return (True, False)  # Başarılı say
                raise e  # Diğer hataları yukarı fırlat (parse error handling için)
        except Exception as parse_error:
            error_msg = str(parse_error).lower()
            # Markdown parse hatası kontrolü
            if "can't parse entities" in error_msg or "bad request" in error_msg:
                self.logger.warning(
                    f"Markdown parse hatası, mesaj plain text olarak güncellenecek: {str(parse_error)}"
                )
                # Plain text olarak tekrar dene
                try:
                    kwargs['parse_mode'] = None  # Parse mode'u kaldır
                    await self.application.bot.edit_message_text(**kwargs)
                    self.logger.info(f"Kanal mesajı plain text olarak güncellendi - Message ID: {message_id}")
                    return (True, False)
                except Exception as retry_error:
                    self.logger.error(
                        f"Plain text kanal mesajı güncelleme hatası: {str(retry_error)}",
                        exc_info=True
                    )
                    return (False, False)
            # RetryAfter hatası için ayrı işlem
            if isinstance(parse_error, RetryAfter):
                raise  # RetryAfter'ı yukarı fırlat
            # Diğer hatalar için normal işlem
            raise
        except RetryAfter as e:
            # Flood control: Telegram'ın belirttiği süreyi bekle ve tekrar dene
            retry_after = e.retry_after
            self.logger.warning(
                f"Telegram flood control: {retry_after} saniye bekleniyor - Message ID: {message_id}"
            )
            await asyncio.sleep(retry_after)
            try:
                kwargs = {
                    'chat_id': channel_id,
                    'message_id': message_id,
                    'text': message,
                    'parse_mode': 'MarkdownV2'  # MarkdownV2 formatını kullan
                }
                if reply_markup is not None:
                    kwargs['reply_markup'] = reply_markup
                    
                await self.application.bot.edit_message_text(**kwargs)
                self.logger.info(f"Kanal mesajı güncellendi (retry sonrası) - Message ID: {message_id}")
                return (True, False)
            except Exception as retry_error:
                error_msg = str(retry_error).lower()
                # Markdown parse hatası kontrolü
                if "can't parse entities" in error_msg or "bad request" in error_msg:
                    try:
                        kwargs['parse_mode'] = None
                        await self.application.bot.edit_message_text(**kwargs)
                        self.logger.info(f"Kanal mesajı plain text olarak güncellendi (retry sonrası) - Message ID: {message_id}")
                        return (True, False)
                    except Exception:
                        pass  # Fall through to message_not_found check
                is_message_not_found = (
                    "message to edit not found" in error_msg or
                    "message not found" in error_msg
                )
                if is_message_not_found:
                    self.logger.warning(
                        f"Telegram mesajı bulunamadı (retry sonrası): Message ID: {message_id}"
                    )
                    return (False, True)
                else:
                    self.logger.error(
                        f"Kanal mesajı güncellenemedi (retry sonrası): {str(retry_error)}",
                        exc_info=True
                    )
                    return (False, False)
        except TimedOut:
            # Timeout: 2 saniye bekle ve 1 kez daha dene
            self.logger.warning(
                f"Telegram timeout - 2 saniye beklenip tekrar denenecek - Message ID: {message_id}"
            )
            await asyncio.sleep(2)
            try:
                kwargs = {
                    'chat_id': channel_id,
                    'message_id': message_id,
                    'text': message,
                    'parse_mode': 'MarkdownV2'  # MarkdownV2 formatını kullan
                }
                if reply_markup is not None:
                    kwargs['reply_markup'] = reply_markup
                    
                await self.application.bot.edit_message_text(**kwargs)
                self.logger.info(f"Kanal mesajı güncellendi (timeout retry sonrası) - Message ID: {message_id}")
                return (True, False)
            except Exception as retry_error:
                error_msg = str(retry_error).lower()
                # Markdown parse hatası kontrolü
                if "can't parse entities" in error_msg or "bad request" in error_msg:
                    try:
                        kwargs['parse_mode'] = None
                        await self.application.bot.edit_message_text(**kwargs)
                        self.logger.info(f"Kanal mesajı plain text olarak güncellendi (timeout retry sonrası) - Message ID: {message_id}")
                        return (True, False)
                    except Exception:
                        pass  # Fall through to message_not_found check
                is_message_not_found = (
                    "message to edit not found" in error_msg or
                    "message not found" in error_msg
                )
                if is_message_not_found:
                    self.logger.warning(
                        f"Telegram mesajı bulunamadı (timeout retry sonrası): Message ID: {message_id}"
                    )
                    return (False, True)
                else:
                    # Timeout retry sonrası hala başarısız, ama mesaj silinmiş sayma
                    # Çünkü gerçek sorun ağ olabilir
                    self.logger.error(
                        f"Kanal mesajı güncellenemedi (timeout retry sonrası): {str(retry_error)}",
                        exc_info=True
                    )
                    return (False, False)
        except Exception as e:
            error_message = str(e).lower()
            # "Message to edit not found" hatasını kontrol et
            is_message_not_found = (
                "message to edit not found" in error_message or
                "message not found" in error_message
            )
            
            if is_message_not_found:
                self.logger.warning(
                    f"Telegram mesajı bulunamadı (silinmiş olabilir): Message ID: {message_id}"
                )
            else:
                self.logger.error(
                    f"Kanal mesajı güncellenemedi: {str(e)}",
                    exc_info=True
                )
            return (False, is_message_not_found)
    
    def edit_channel_message(
        self, channel_id: str, message_id: int, message: str, reply_markup=None
    ) -> tuple[bool, bool]:
        """
        Kanal mesajını düzenler (sync wrapper).
        
        Args:
            channel_id: Telegram kanal ID
            message_id: Düzenlenecek mesaj ID
            message: Yeni mesaj içeriği
            reply_markup: Inline keyboard markup (opsiyonel, None ise mevcut keyboard korunur)
            
        Returns:
            (success: bool, message_not_found: bool)
            - success: True ise başarılı
            - message_not_found: True ise mesaj bulunamadı (silinmiş)
        """
        try:
            if not self.application:
                self.logger.error("Bot application henüz initialize edilmemiş (edit channel)")
                return (False, False)
            result = self._run_on_bot_loop(
                self.edit_message_to_channel(channel_id, message_id, message, reply_markup)
            )
            if isinstance(result, tuple) and len(result) == 2:
                return result
            # Eski format için fallback
            return (bool(result), False)
        except Exception as e:
            self.logger.error(f"Channel mesajı düzenlenemedi (sync): {str(e)}", exc_info=True)
            return (False, False)
    
    def send_message(
        self, chat_id: int, text: str, reply_to_message_id: int = None
    ) -> None:
        """
        Kullanıcıya mesaj gönderir (sync wrapper).
        
        Args:
            chat_id: Chat ID
            text: Gönderilecek mesaj
            reply_to_message_id: Reply edilecek mesaj ID'si (opsiyonel)
        """
        try:
            if not self.application:
                self.logger.error("Bot application henüz initialize edilmemiş")
                return
            self._run_on_bot_loop(
                self._send_message_async(chat_id, text, reply_to_message_id),
                return_result=False
            )
        except Exception as e:
            self.logger.error(
                f"Mesaj gönderilemedi: {str(e)}",
                exc_info=True
            )
    
    async def _send_message_async(
        self, chat_id: int, text: str, reply_to_message_id: int = None
    ) -> None:
        """
        Async mesaj gönderme fonksiyonu.
        
        Args:
            chat_id: Chat ID
            text: Gönderilecek mesaj
            reply_to_message_id: Reply edilecek mesaj ID'si (opsiyonel)
        """
        try:
            kwargs = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'MarkdownV2'  # MarkdownV2 formatını kullan
            }
            if reply_to_message_id:
                kwargs['reply_to_message_id'] = reply_to_message_id
            self.logger.debug(f"send_message kwargs: {kwargs | {'text': f'<{len(text)} chars>'}}")
                
            await self.application.bot.send_message(**kwargs)
            self.logger.info(f"Mesaj gönderildi - Chat: {chat_id}")
        except Exception as e:
            error_msg = str(e).lower()
            # Markdown parse hatası kontrolü
            if "can't parse entities" in error_msg or "bad request" in error_msg:
                self.logger.warning(
                    f"Markdown parse hatası, mesaj plain text olarak gönderilecek: {str(e)}"
                )
                # Plain text olarak tekrar dene
                try:
                    kwargs['parse_mode'] = None  # Parse mode'u kaldır
                    await self.application.bot.send_message(**kwargs)
                    self.logger.info(f"Mesaj plain text olarak gönderildi - Chat: {chat_id}")
                except Exception as retry_error:
                    self.logger.error(
                        f"Plain text mesaj gönderme hatası: {str(retry_error)}",
                        exc_info=True
                    )
            else:
                self.logger.error(
                    f"Async mesaj gönderme hatası: {str(e)}",
                    exc_info=True
                )
    
    def _run_on_bot_loop(self, coro, return_result: bool = True):
        """Bot'un event loop'u üzerinde güvenli şekilde coroutine çalıştırır."""
        if not self._loop or not self._loop.is_running():
            self.logger.error("Telegram bot event loop'u hazır değil veya çalışmıyor")
            return None

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        if not return_result:
            return future

        try:
            return future.result()
        except FuturesTimeoutError:
            self.logger.error("Telegram bot loop çağrısı zaman aşımına uğradı")
            return None
        except Exception as exc:
            self.logger.error(
                f"Telegram bot loop çağrısı başarısız: {exc}",
                exc_info=True
            )
            return None

    def initialize(self) -> None:
        """Bot'u initialize eder."""
        self.application = Application.builder().token(self.token).build()
        self.setup_handlers()
        self.logger.info("Telegram bot initialize edildi")

    def configure_lifecycle_notifications(self, channel_id: str, forecast_cache) -> None:
        """Kanal ID ve cache referansı vererek lifecycle bildirimlerini etkinleştirir."""
        self._channel_id = channel_id
        self._forecast_cache = forecast_cache
    
    def set_signal_tracker(self, signal_tracker) -> None:
        """SignalTracker instance'ını set eder (callback handler için)."""
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
            
            # callback_data parse et: "update_signal:{signal_id}"
            callback_data = query.data
            if not callback_data or not callback_data.startswith("update_signal:"):
                self.logger.warning(f"Geçersiz callback_data: {callback_data}")
                await query.answer("❌ Geçersiz istek", show_alert=True)
                return
            
            signal_id = callback_data.replace("update_signal:", "")
            if not signal_id:
                self.logger.warning("Sinyal ID bulunamadı")
                await query.answer("❌ Sinyal ID bulunamadı", show_alert=True)
                return
            
            self.logger.info(f"Signal update callback: {signal_id}")
            
            # SignalTracker instance'ına erişim sağla
            signal_tracker = getattr(self, '_signal_tracker', None)
            if not signal_tracker:
                self.logger.error("SignalTracker instance'ına erişilemedi")
                await query.answer("❌ Hata: SignalTracker bulunamadı", show_alert=True)
                return
            
            # ÖNEMLİ: Callback query'ye HEMEN yanıt ver (Telegram timeout'u önlemek için)
            # Telegram'ın callback query timeout'u çok kısa, bu yüzden önce yanıt veriyoruz
            try:
                await query.answer("⏳ Güncelleniyor...")
            except Exception as e:
                # "Query is too old" hatası normaldir (restart sonrası eski butonlara basılırsa)
                # Bu hatayı logla ama işlemi durdurma (update devam etsin)
                if "Query is too old" in str(e):
                    self.logger.warning(f"Callback query zaman aşımı (normal): {str(e)}")
                else:
                    self.logger.warning(f"Callback query yanıt hatası: {str(e)}")
            
            # Sinyali veritabanından al
            signal = signal_tracker.repository.get_signal(signal_id)
            if not signal:
                self.logger.warning(f"Sinyal bulunamadı: {signal_id}")
                # Query'ye zaten yanıt verdik, sadece log
                return
            
            # Mesajı güncelle (sync metod, thread'de çalıştır - non-blocking)
            # update_message_for_signal sync bir metod, bu yüzden thread'de çalıştırmalıyız
            import threading
            def update_signal():
                try:
                    signal_tracker.update_message_for_signal(signal)
                    self.logger.info(f"Signal update tamamlandı: {signal_id}")
                except Exception as e:
                    self.logger.error(f"Signal update hatası: {str(e)}", exc_info=True)
            
            # Thread'de çalıştır (non-blocking, daemon thread)
            thread = threading.Thread(target=update_signal, daemon=True)
            thread.start()
            # join() yapmıyoruz, arka planda çalışsın - callback query'ye zaten yanıt verdik
            
        except Exception as e:
            self.logger.error(
                f"Signal update callback hatası: {str(e)}",
                exc_info=True
            )
            if query:
                try:
                    await query.answer("❌ Güncelleme hatası", show_alert=True)
                except Exception:
                    pass
    
    def run(self) -> None:
        """Bot'u başlatır (blocking)."""
        if not self.application:
            self.initialize()
        
        self.logger.info("Telegram bot başlatılıyor...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
