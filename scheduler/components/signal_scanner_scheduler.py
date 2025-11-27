"""
SignalScannerScheduler: Signal scanning scheduler.
Triggers SignalScannerManager every 5 minutes.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from typing import Optional
from utils.logger import LoggerManager
from scheduler.components.signal_scanner_manager import SignalScannerManager


class SignalScannerScheduler:
    """Signal scanning scheduler."""
    
    def __init__(self, scanner_manager: SignalScannerManager):
        """
        Initializes SignalScannerScheduler.
        
        Args:
            scanner_manager: Signal scanner manager instance
        """
        self.scanner_manager = scanner_manager
        self.scheduler = BackgroundScheduler()
        self.logger = LoggerManager().get_logger('SignalScannerScheduler')
        self.is_running = False
    
    def start(self) -> None:
        """Starts the scheduler."""
        try:
            if self.is_running:
                self.logger.warning("Signal scanner scheduler is already running")
                return
            
            # Scan signals every 5 minutes
            self.scheduler.add_job(
                self._scan_signals,
                trigger=IntervalTrigger(minutes=5),
                id='signal_scanner_scan',
                name='Signal Scanning',
                replace_existing=True
            )
            
            # Cleanup cache every hour
            self.scheduler.add_job(
                self._cleanup_cache,
                trigger=IntervalTrigger(hours=1),
                id='signal_scanner_cleanup',
                name='Cache Cleanup',
                replace_existing=True
            )
            
            self.scheduler.start()
            self.is_running = True
            
            self.logger.info("Signal scanner scheduler started - Scanning every 5 minutes")
            
        except Exception as e:
            self.logger.error(f"Signal scanner scheduler startup error: {str(e)}", exc_info=True)
            raise
    
    def stop(self) -> None:
        """Stops the scheduler."""
        try:
            if not self.is_running:
                self.logger.warning("Signal scanner scheduler is already stopped")
                return
            
            if self.scheduler.running:
                self.scheduler.shutdown()
            
            self.is_running = False
            self.logger.info("Signal scanner scheduler stopped")
            
        except Exception as e:
            self.logger.error(f"Signal scanner scheduler shutdown error: {str(e)}", exc_info=True)
    
    def _scan_signals(self) -> None:
        """Runs the signal scanning job."""
        try:
            self.logger.debug("Signal scanning job started")
            self.scanner_manager.scan_for_signals()
        except Exception as e:
            self.logger.error(f"Signal scanning job error: {str(e)}", exc_info=True)
    
    def _cleanup_cache(self) -> None:
        """Runs the cache cleanup job."""
        try:
            self.logger.debug("Cache cleanup job started")
            self.scanner_manager.cleanup_old_cache()
        except Exception as e:
            self.logger.error(f"Cache cleanup job error: {str(e)}", exc_info=True)
    
    def get_status(self) -> dict:
        """Returns scheduler status."""
        cache_stats = self.scanner_manager.get_cache_stats()
        
        return {
            'is_running': self.is_running,
            'scheduler_running': self.scheduler.running if self.scheduler else False,
            'cache_stats': cache_stats,
            'scan_interval_minutes': 5,
            'cleanup_interval_hours': 1
        }
    
    def force_scan(self) -> None:
        """Manually triggers signal scanning."""
        try:
            self.logger.info("Manual signal scanning triggered")
            self.scanner_manager.scan_for_signals()
        except Exception as e:
            self.logger.error(f"Manual signal scanning error: {str(e)}", exc_info=True)
