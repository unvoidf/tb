"""
Main Application: TrendBot ana giriş noktası.
ApplicationFactory pattern ile tüm bileşenleri initialize eder.
"""
import signal
import sys
from core.application_factory import ApplicationFactory
from core.exceptions import TrendBotException
from utils.logger import LoggerManager


class TrendBot:
    """Ana uygulama sınıfı."""
    
    def __init__(self):
        """TrendBot'u başlatır."""
        self.components = None
        self.logger = None
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self) -> None:
        """Signal handler'ları ayarlar."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame) -> None:
        """
        Signal handler.
        
        Args:
            signum: Signal numarası
            frame: Frame objesi
        """
        if self.logger:
            self.logger.info(f"Signal {signum} alındı, uygulama kapatılıyor...")
        
        self.shutdown()
        sys.exit(0)
    
    def initialize(self) -> None:
        """Tüm bileşenleri initialize eder."""
        print("🚀 TrendBot başlatılıyor...")
        
        try:
            # ApplicationFactory ile bileşenleri oluştur
            factory = ApplicationFactory()
            self.components = factory.create_application()
            
            # Logger'ı al
            self.logger = self.components['logger']
            
            self.logger.info("=" * 50)
            self.logger.info("TrendBot başlatılıyor")
            self.logger.info("=" * 50)
            
            # Bot'u initialize et
            self.components['telegram_bot'].initialize()
            
            # Scheduler'ı başlat
            self.components['scheduler'].start()
            
            # Signal scanner scheduler'ı başlat
            self.components['signal_scanner_scheduler'].start()
            
            # Signal tracker scheduler'ı başlat
            self.components['signal_tracker_scheduler'].start()
            
            self.logger.info("Tüm bileşenler başarıyla initialize edildi")
            
        except Exception as e:
            error_msg = f"Uygulama başlatma hatası: {str(e)}"
            print(f"❌ {error_msg}")
            if self.logger:
                self.logger.error(error_msg, exc_info=True)
            raise TrendBotException(error_msg)
    
    def run(self) -> None:
        """Bot'u çalıştırır."""
        if not self.components:
            raise TrendBotException("Uygulama initialize edilmemiş")
        
        try:
            self.logger.info("TrendBot çalıştırılıyor...")
            self.components['telegram_bot'].run()
        except KeyboardInterrupt:
            self.logger.info("Kullanıcı tarafından durduruldu")
        except Exception as e:
            error_msg = f"Bot çalıştırma hatası: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            raise TrendBotException(error_msg)
        finally:
            self.shutdown()
    
    def shutdown(self) -> None:
        """Uygulamayı güvenli şekilde kapatır."""
        # Pre-shutdown kanal bildirimi (event loop kapanmadan önce)
        try:
            if self.components and 'config' in self.components:
                ch_id = self.components['config'].telegram_channel_id
                msg = "🛑 Bot kapatılıyor"
                self.logger.info(msg)
                # PTB kapanmış olabilir; doğrudan Telegram HTTP API ile gönder
                try:
                    import json as _json, urllib.request as _urlreq
                    token = self.components['config'].telegram_token
                    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
                    payload = _json.dumps({'chat_id': ch_id, 'text': msg}).encode('utf-8')
                    req = _urlreq.Request(api_url, data=payload, headers={'Content-Type': 'application/json'})
                    _urlreq.urlopen(req, timeout=5)
                    if self.logger:
                        self.logger.info("Kanal mesajı gönderildi (pre-shutdown, direct API)")
                except Exception as http_err:
                    if self.logger:
                        self.logger.error(f"Pre-shutdown direct API hatası: {http_err}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Pre-shutdown mesajı gönderilemedi: {str(e)}", exc_info=True)
        if self.components and 'scheduler' in self.components:
            try:
                self.components['scheduler'].stop()
                if self.logger:
                    self.logger.info("Scheduler durduruldu")
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Scheduler durdurma hatası: {str(e)}")
        
        if self.components and 'signal_scanner_scheduler' in self.components:
            try:
                self.components['signal_scanner_scheduler'].stop()
                if self.logger:
                    self.logger.info("Signal scanner scheduler durduruldu")
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Signal scanner scheduler durdurma hatası: {str(e)}")
        
        if self.components and 'signal_tracker_scheduler' in self.components:
            try:
                self.components['signal_tracker_scheduler'].stop()
                if self.logger:
                    self.logger.info("Signal tracker scheduler durduruldu")
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Signal tracker scheduler durdurma hatası: {str(e)}")
        
        if self.logger:
            self.logger.info("TrendBot kapatıldı")


def main():
    """Ana fonksiyon."""
    try:
        bot = TrendBot()
        bot.initialize()
        bot.run()
    except TrendBotException as e:
        print(f"❌ TrendBot Hatası: {e.message}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Beklenmeyen Hata: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
