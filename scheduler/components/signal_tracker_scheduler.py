"""
SignalTrackerScheduler: Scheduler that periodically runs TP/SL checks.
Checks active signals every 1 minute.
"""
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from scheduler.components.signal_tracker import SignalTracker
from utils.logger import LoggerManager


class SignalTrackerScheduler:
    """Scheduler for TP/SL checks."""
    
    def __init__(self, signal_tracker: SignalTracker, interval_minutes: int = 1):
        """
        Initializes SignalTrackerScheduler.
        
        Args:
            signal_tracker: SignalTracker instance
            interval_minutes: Check interval (minutes, default: 1)
        """
        self.tracker = signal_tracker
        self.interval_minutes = interval_minutes
        self.scheduler = BackgroundScheduler()
        self.logger = LoggerManager().get_logger('SignalTrackerScheduler')
        self.is_running = False
    
    def start(self) -> None:
        """Starts the scheduler."""
        try:
            if self.is_running:
                self.logger.warning("Signal tracker scheduler is already running")
                return
            
            self.scheduler.add_job(
                self._check_signals,
                trigger=IntervalTrigger(minutes=self.interval_minutes),
                id='signal_tracker_check',
                name='Signal TP/SL Check',
                replace_existing=True,
                max_instances=1,  # Only 1 instance at a time (rate limit protection)
                coalesce=True,  # Coalesce missed jobs
                misfire_grace_time=30  # Run missed jobs within 30 seconds
            )
            self.scheduler.start()
            self.is_running = True
            self.logger.info(f"SignalTrackerScheduler started ({self.interval_minutes} minute interval)")
        except Exception as e:
            self.logger.error(f"SignalTrackerScheduler start error: {str(e)}", exc_info=True)
            raise
    
    def stop(self) -> None:
        """Stops the scheduler."""
        try:
            if not self.is_running:
                self.logger.warning("Signal tracker scheduler is already stopped")
                return
            
            if self.scheduler.running:
                self.scheduler.shutdown()
            
            self.is_running = False
            self.logger.info("SignalTrackerScheduler stopped")
        except Exception as e:
            self.logger.error(f"SignalTrackerScheduler stop error: {str(e)}", exc_info=True)
    
    def _check_signals(self) -> None:
        """Checks active signals (scheduler callback)."""
        start_time = time.time()
        try:
            self.logger.debug("TP/SL check started")
            self.tracker.check_all_active_signals()
            elapsed = time.time() - start_time
            self.logger.debug(f"TP/SL check completed (duration: {elapsed:.2f} seconds)")
            
            # Warn if check takes longer than 80% of interval
            warning_threshold = (self.interval_minutes * 60) * 0.8
            if elapsed > warning_threshold:
                self.logger.warning(
                    f"TP/SL check took {elapsed:.2f} seconds ({int((elapsed / (self.interval_minutes * 60)) * 100)}% of "
                    f"{self.interval_minutes} minute interval, job might be skipped). "
                    f"Check active signal count."
                )
        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error(
                f"TP/SL check error (duration: {elapsed:.2f} seconds): {str(e)}",
                exc_info=True
            )

