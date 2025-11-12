"""
ChannelNotifier: Kanal mesajı gönderen bileşen.
Saatlik analiz sonuçlarını kanala gönderir.
"""
from typing import List, Dict
import asyncio
import nest_asyncio
from utils.logger import LoggerManager
from bot.telegram_bot_manager import TelegramBotManager
from bot.message_formatter import MessageFormatter
from config.config_manager import ConfigManager


class ChannelNotifier:
    """Kanal mesajı gönderen bileşen."""
    
    def __init__(self, bot_manager: TelegramBotManager, formatter: MessageFormatter, market_data):
        """
        ChannelNotifier'ı başlatır.
        
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
        Saatlik analiz sonuçlarını kanala gönderir.
        
        Args:
            top_signals: Top sinyal listesi
            channel_id: Telegram kanal ID
            
        Returns:
            Gönderim başarılı mı
        """
        try:
            # Mesaj formatla
            message = self._format_hourly_message(top_signals)
            
            # Mesajı gönder
            self._send_channel_message_sync(message, channel_id)
            
            self.logger.info(
                f"Saatlik analiz tamamlandı - {len(top_signals)} sinyal gönderildi"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Kanal mesajı gönderilemedi: {str(e)}")
            # Admin'lere bildir
            self._notify_admins_about_error(e, top_signals)
            return False
    
    def _format_hourly_message(self, top_signals: List[Dict]) -> str:
        """
        Saatlik mesaj formatlar.
        
        Args:
            top_signals: Top sinyal listesi
            
        Returns:
            Formatlanmış mesaj
        """
        from datetime import datetime
        
        header = (
            "⏰ SAATLİK PİYASA ANALİZİ\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        )
        
        summary = self.formatter.format_trend_summary_with_prices(top_signals, self.market_data)
        
        footer = (
            "\n💡 Detaylı analiz için: /analiz [COIN]\n"
            "Örnek: /analiz BTC"
        )
        
        return header + summary + footer
    
    def _send_channel_message_sync(self, message: str, channel_id: str) -> None:
        """
        Kanal mesajını senkron context'ten gönderir.
        
        Args:
            message: Gönderilecek mesaj
            channel_id: Kanal ID
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
        Kanal mesajı başarısız olduğunda admin'lere bildirim gönderir.
        
        Args:
            error: Oluşan hata
            top_signals: Gönderilmeye çalışılan sinyaller
        """
        try:
            error_notification = (
                "⚠️ KANAL MESAJI GÖNDERİLEMEDİ\n\n"
                f"Hata: {str(error)}\n\n"
                "Olası Nedenler:\n"
                "• Bot kanala admin olarak eklenmemiş\n"
                "• Kanal ID yanlış\n"
                "• Bot'un mesaj gönderme yetkisi yok\n\n"
                "Çözüm:\n"
                "1. Botunuzu kanala admin olarak ekleyin\n"
                "2. 'Post Messages' yetkisini verin\n"
                "3. Kanal ID'yi kontrol edin (.env dosyası)\n\n"
                f"📊 Gönderilmeye Çalışılan Sinyal Sayısı: {len(top_signals)}"
            )
            
            # Admin kullanıcılara gönder
            admin_users = self.config.admin_user_ids
            
            if not admin_users:
                self.logger.warning(
                    "Admin user ID tanımlı değil - "
                    "ADMIN_USER_IDS .env'ye ekleyin"
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
                    
                    self.logger.info(f"Error bildirimi gönderildi: User {user_id}")
                except Exception as notify_error:
                    self.logger.error(
                        f"User {user_id}'ye bildirim gönderilemedi: {str(notify_error)}"
                    )
        except Exception as e:
            self.logger.error(f"Admin bildirimi sırasında hata: {str(e)}", exc_info=True)
