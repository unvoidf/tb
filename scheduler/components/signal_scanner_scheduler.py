"""
SignalScannerScheduler: Sinyal tarama scheduler'ı.
Her 5 dakikada bir SignalScannerManager'ı tetikler.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from typing import Optional
from utils.logger import LoggerManager
from scheduler.components.signal_scanner_manager import SignalScannerManager


class SignalScannerScheduler:
    """Sinyal tarama scheduler'ı."""
    
    def __init__(self, scanner_manager: SignalScannerManager):
        """
        SignalScannerScheduler'ı başlatır.
        
        Args:
            scanner_manager: Signal scanner manager instance
        """
        self.scanner_manager = scanner_manager
        self.scheduler = BackgroundScheduler()
        self.logger = LoggerManager().get_logger('SignalScannerScheduler')
        self.is_running = False
    
    def start(self) -> None:
        """Scheduler'ı başlatır."""
        try:
            if self.is_running:
                self.logger.warning("Signal scanner scheduler zaten çalışıyor")
                return
            
            # Her 5 dakikada bir sinyal tarama
            self.scheduler.add_job(
                self._scan_signals,
                trigger=IntervalTrigger(minutes=5),
                id='signal_scanner_scan',
                name='Sinyal Tarama',
                replace_existing=True
            )
            
            # Her saat başı cache temizleme
            self.scheduler.add_job(
                self._cleanup_cache,
                trigger=IntervalTrigger(hours=1),
                id='signal_scanner_cleanup',
                name='Cache Temizleme',
                replace_existing=True
            )
            
            self.scheduler.start()
            self.is_running = True
            
            self.logger.info("Signal scanner scheduler başlatıldı - Her 5 dakikada tarama")
            
        except Exception as e:
            self.logger.error(f"Signal scanner scheduler başlatma hatası: {str(e)}", exc_info=True)
            raise
    
    def stop(self) -> None:
        """Scheduler'ı durdurur."""
        try:
            if not self.is_running:
                self.logger.warning("Signal scanner scheduler zaten durmuş")
                return
            
            if self.scheduler.running:
                self.scheduler.shutdown()
            
            self.is_running = False
            self.logger.info("Signal scanner scheduler durduruldu")
            
        except Exception as e:
            self.logger.error(f"Signal scanner scheduler durdurma hatası: {str(e)}", exc_info=True)
    
    def _scan_signals(self) -> None:
        """Sinyal tarama job'ını çalıştırır."""
        try:
            self.logger.debug("Sinyal tarama job başlatıldı")
            self.scanner_manager.scan_for_signals()
        except Exception as e:
            self.logger.error(f"Sinyal tarama job hatası: {str(e)}", exc_info=True)
    
    def _cleanup_cache(self) -> None:
        """Cache temizleme job'ını çalıştırır."""
        try:
            self.logger.debug("Cache temizleme job başlatıldı")
            self.scanner_manager.cleanup_old_cache()
        except Exception as e:
            self.logger.error(f"Cache temizleme job hatası: {str(e)}", exc_info=True)
    
    def get_status(self) -> dict:
        """Scheduler durumunu döndürür."""
        cache_stats = self.scanner_manager.get_cache_stats()
        
        return {
            'is_running': self.is_running,
            'scheduler_running': self.scheduler.running if self.scheduler else False,
            'cache_stats': cache_stats,
            'scan_interval_minutes': 5,
            'cleanup_interval_hours': 1
        }
    
    def force_scan(self) -> None:
        """Manuel olarak sinyal tarama tetikler."""
        try:
            self.logger.info("Manuel sinyal tarama tetiklendi")
            self.scanner_manager.scan_for_signals()
        except Exception as e:
            self.logger.error(f"Manuel sinyal tarama hatası: {str(e)}", exc_info=True)
