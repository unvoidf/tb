"""
SignalTrackerScheduler: TP/SL kontrolünü periyodik olarak çalıştıran scheduler.
Her 1 dakikada bir aktif sinyalleri kontrol eder.
"""
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from scheduler.components.signal_tracker import SignalTracker
from utils.logger import LoggerManager


class SignalTrackerScheduler:
    """TP/SL kontrolü için scheduler."""
    
    def __init__(self, signal_tracker: SignalTracker, interval_minutes: int = 1):
        """
        SignalTrackerScheduler'ı başlatır.
        
        Args:
            signal_tracker: SignalTracker instance
            interval_minutes: Kontrol interval'i (dakika, default: 1)
        """
        self.tracker = signal_tracker
        self.interval_minutes = interval_minutes
        self.scheduler = BackgroundScheduler()
        self.logger = LoggerManager().get_logger('SignalTrackerScheduler')
        self.is_running = False
    
    def start(self) -> None:
        """Scheduler'ı başlatır."""
        try:
            if self.is_running:
                self.logger.warning("Signal tracker scheduler zaten çalışıyor")
                return
            
            self.scheduler.add_job(
                self._check_signals,
                trigger=IntervalTrigger(minutes=self.interval_minutes),
                id='signal_tracker_check',
                name='Sinyal TP/SL Kontrolü',
                replace_existing=True,
                max_instances=1,  # Aynı anda sadece 1 instance (rate limit koruması)
                coalesce=True,  # Kaçırılan job'ları birleştir
                misfire_grace_time=30  # 30 saniye içinde kaçırılan job'ları çalıştır
            )
            self.scheduler.start()
            self.is_running = True
            self.logger.info(f"SignalTrackerScheduler başlatıldı ({self.interval_minutes} dakika interval)")
        except Exception as e:
            self.logger.error(f"SignalTrackerScheduler başlatma hatası: {str(e)}", exc_info=True)
            raise
    
    def stop(self) -> None:
        """Scheduler'ı durdurur."""
        try:
            if not self.is_running:
                self.logger.warning("Signal tracker scheduler zaten durmuş")
                return
            
            if self.scheduler.running:
                self.scheduler.shutdown()
            
            self.is_running = False
            self.logger.info("SignalTrackerScheduler durduruldu")
        except Exception as e:
            self.logger.error(f"SignalTrackerScheduler durdurma hatası: {str(e)}", exc_info=True)
    
    def _check_signals(self) -> None:
        """Aktif sinyalleri kontrol eder (scheduler callback)."""
        start_time = time.time()
        try:
            self.logger.debug("TP/SL kontrolü başlatıldı")
            self.tracker.check_all_active_signals()
            elapsed = time.time() - start_time
            self.logger.debug(f"TP/SL kontrolü tamamlandı (süre: {elapsed:.2f} saniye)")
            
            # Eğer kontrol interval'in %80'inden uzun sürerse uyarı ver
            warning_threshold = (self.interval_minutes * 60) * 0.8
            if elapsed > warning_threshold:
                self.logger.warning(
                    f"TP/SL kontrolü {elapsed:.2f} saniye sürdü ({self.interval_minutes} dakika interval'in "
                    f"%{int((elapsed / (self.interval_minutes * 60)) * 100)}'i, job atlanabilir). "
                    f"Aktif sinyal sayısını kontrol edin."
                )
        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error(
                f"TP/SL kontrolü hatası (süre: {elapsed:.2f} saniye): {str(e)}",
                exc_info=True
            )

