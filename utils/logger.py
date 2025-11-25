"""
LoggerManager: Central log management system.
Hourly date-based logging: logs/YYYY-MM-DD/category_HH.log
Categorized log files: signal_scanner, signal_tracker, trendbot
"""
import logging
import os
import queue
import threading
from datetime import datetime
from logging import FileHandler
from logging.handlers import QueueHandler, QueueListener
from typing import Optional, List


class LoggerNameFilter(logging.Filter):
    """Filters based on logger names."""
    
    def __init__(self, allowed_names: list):
        """
        Args:
            allowed_names: Allowed logger names (or prefixes)
        """
        super().__init__()
        self.allowed_names = allowed_names
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Checks the logger name."""
        logger_name = record.name
        # Exact match or prefix check
        for allowed in self.allowed_names:
            if logger_name == allowed or logger_name.startswith(allowed + '.'):
                return True
        return False


class ExcludeLoggerNameFilter(logging.Filter):
    """Excludes specific logger names (exclude filter)."""
    
    def __init__(self, excluded_names: list):
        """
        Args:
            excluded_names: Logger names to exclude (or prefixes)
        """
        super().__init__()
        self.excluded_names = excluded_names
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Checks the logger name - excluded names return False."""
        logger_name = record.name
        # If matches one of the excluded names, return False (exclude)
        for excluded in self.excluded_names:
            if logger_name == excluded or logger_name.startswith(excluded + '.'):
                return False
        return True


class HourlyFileHandler(FileHandler):
    """
    Custom file handler that creates a new log file every hour.
    File structure: logs/YYYY-MM-DD/category_HH.log
    """
    
    def __init__(self, log_dir: str, category: str, level: int = logging.NOTSET):
        """
        Args:
            log_dir: Base log directory (e.g., 'logs')
            category: Log category name (e.g., 'signal_scanner', 'signal_tracker', 'trendbot')
            level: Log level
        """
        self.log_dir = log_dir
        self.category = category
        self.current_date = None
        self.current_hour = None
        self._lock = threading.Lock()
        
        # Initialize with current date/hour
        self._update_file_path()
        
        # Create directory if needed
        os.makedirs(os.path.dirname(self.baseFilename), exist_ok=True)
        
        super().__init__(self.baseFilename, mode='a', encoding='utf-8', delay=False)
        self.setLevel(level)
    
    def _update_file_path(self) -> None:
        """Updates the file path based on current date and hour."""
        now = datetime.now()
        date_str = now.strftime('%Y-%m-%d')
        hour = now.hour
        
        # Only update if date or hour changed
        if self.current_date != date_str or self.current_hour != hour:
            self.current_date = date_str
            self.current_hour = hour
            
            # Create date-based directory
            date_dir = os.path.join(self.log_dir, date_str)
            os.makedirs(date_dir, exist_ok=True)
            
            # File name: category_HH.log (e.g., signal_scanner_14.log)
            filename = f"{self.category}_{hour:02d}.log"
            self.baseFilename = os.path.join(date_dir, filename)
    
    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record, creating new file if hour changed."""
        with self._lock:
            # Check if we need to switch to a new file
            now = datetime.now()
            date_str = now.strftime('%Y-%m-%d')
            hour = now.hour
            
            if self.current_date != date_str or self.current_hour != hour:
                # Hour changed, close current file and open new one
                if self.stream:
                    self.stream.close()
                    self.stream = None
                
                self._update_file_path()
                
                # Open new file
                if self.delay:
                    self.stream = None
                else:
                    self.stream = self._open()
        
        # Call parent emit
        super().emit(record)


class LoggerManager:
    """Provides application-wide log management."""
    
    _instance: Optional['LoggerManager'] = None
    _initialized: bool = False
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern implementation."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, log_dir: str = 'logs', 
                 async_enabled: Optional[bool] = None):
        """
        Initializes LoggerManager with hourly date-based logging.
        
        Args:
            log_dir: Base directory where log files will be saved (default: 'logs')
            async_enabled: Is async logging enabled? (default: read from .env or True)
        """
        if self._initialized:
            return
        
        # Read log settings from .env
        self.log_dir = log_dir or os.getenv('LOG_DIR', 'logs')
        
        # Async logging setting
        if async_enabled is None:
            async_str = os.getenv('LOG_ASYNC_ENABLED', 'true').lower()
            self.async_enabled = async_str in ('true', '1', 'yes')
        else:
            self.async_enabled = async_enabled
        
        # Queue and listener for async logging
        self._log_queue = None
        self._queue_listener = None
        
        self._setup_log_directory()
        # Collect all handlers first, then setup logger
        all_real_handlers = []
        self._setup_logger(all_real_handlers)
        self._setup_categorized_loggers(all_real_handlers)
        # Create QueueListener with all handlers for async logging
        if self.async_enabled and self._log_queue:
            if self._queue_listener:
                self._queue_listener.stop()
            self._queue_listener = QueueListener(self._log_queue, *all_real_handlers, respect_handler_level=True)
            self._queue_listener.start()
        self._initialized = True
    
    def _setup_log_directory(self) -> None:
        """Creates the log directory."""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
    def _create_hourly_handler(self, category: str, level: int) -> Optional[logging.Handler]:
        """
        Creates hourly file handler for a category.
        
        Args:
            category: Log category name (e.g., 'signal_scanner', 'signal_tracker', 'trendbot')
            level: Log level
            
        Returns:
            Handler instance or None
        """
        try:
            handler = HourlyFileHandler(self.log_dir, category, level)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            return handler
        except Exception:
            return None
    
    def _setup_logger(self, real_handlers: List[logging.Handler]) -> None:
        """
        Configures the main logger.
        
        Args:
            real_handlers: List to add handlers to (for async)
        """
        self.logger = logging.getLogger('TrendBot')
        
        # DEBUG env variable check (priority)
        # DEBUG=1 → LOG_LEVEL=DEBUG, DEBUG=0 → LOG_LEVEL=INFO
        debug_env = os.getenv('DEBUG', '0').strip()
        if debug_env == '1':
            level = logging.DEBUG
        else:
            # Can be overridden with LOG_LEVEL env (DEBUG, INFO, WARNING, ERROR)
            level_name = os.getenv('LOG_LEVEL', 'INFO').upper()
            level = getattr(logging, level_name, logging.INFO)
        
        self.logger.setLevel(level)
        
        # Clear previous handlers
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # Format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # File Handler for trendbot category (general logs)
        trendbot_handler = self._create_hourly_handler('trendbot', level)
        if trendbot_handler:
            # Add exclude filter to trendbot handler (exclude categorized logs)
            # This prevents duplicate logs
            exclude_filter = ExcludeLoggerNameFilter([
                'TrendBot.SignalScannerManager',
                'TrendBot.SignalGenerator',
                'TrendBot.SignalRanker',
                'TrendBot.RangingStrategyAnalyzer',
                'TrendBot.AdaptiveThresholdManager',
                'TrendBot.TechnicalIndicatorCalculator',
                'TrendBot.VolumeAnalyzer',
                'TrendBot.MarketAnalyzer',
                'TrendBot.LiquidationSafetyFilter',
                'TrendBot.SignalTracker'
            ])
            trendbot_handler.addFilter(exclude_filter)
            real_handlers.append(trendbot_handler)
        
        # Console Handler (always synchronous)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        real_handlers.append(console_handler)
        
        # Use QueueHandler if async logging is enabled
        if self.async_enabled:
            # Create Queue
            self._log_queue = queue.Queue(-1)  # Unlimited queue
            
            # Create QueueHandler (added to logger)
            queue_handler = QueueHandler(self._log_queue)
            queue_handler.setLevel(level)
            self.logger.addHandler(queue_handler)
            # QueueListener will be created later with all handlers
        else:
            # Synchronous: add handlers directly
            for handler in real_handlers:
                self.logger.addHandler(handler)
    
    def _setup_categorized_loggers(self, real_handlers: List[logging.Handler]) -> None:
        """
        Configures categorized loggers with hourly date-based files.
        
        Args:
            real_handlers: List to add handlers to (for async)
        """
        # Log level
        debug_env = os.getenv('DEBUG', '0').strip()
        if debug_env == '1':
            level = logging.DEBUG
        else:
            level_name = os.getenv('LOG_LEVEL', 'INFO').upper()
            level = getattr(logging, level_name, logging.INFO)
        
        # Get root logger (all logs go here)
        root_logger = logging.getLogger('TrendBot')
        
        # 1. Signal Scanner Logger (Signal scanning and generation)
        scanner_handler = self._create_hourly_handler('signal_scanner', level)
        if scanner_handler:
            # Filter only signal scanning related loggers
            scanner_filter = LoggerNameFilter([
                'TrendBot.SignalScannerManager',
                'TrendBot.SignalGenerator',
                'TrendBot.SignalRanker',
                'TrendBot.RangingStrategyAnalyzer',
                'TrendBot.AdaptiveThresholdManager',
                'TrendBot.TechnicalIndicatorCalculator',
                'TrendBot.VolumeAnalyzer',
                'TrendBot.MarketAnalyzer',
                'TrendBot.LiquidationSafetyFilter'  # Liquidation risk analysis here too
            ])
            scanner_handler.addFilter(scanner_filter)
            real_handlers.append(scanner_handler)
        
        # 2. Signal Tracker Logger (TP/SL tracking)
        tracker_handler = self._create_hourly_handler('signal_tracker', level)
        if tracker_handler:
            # Filter only TP/SL tracking related loggers
            tracker_filter = LoggerNameFilter(['TrendBot.SignalTracker'])
            tracker_handler.addFilter(tracker_filter)
            real_handlers.append(tracker_handler)
        
        # In synchronous mode, add handlers directly
        if not self.async_enabled:
            for handler in real_handlers:
                root_logger.addHandler(handler)
    
    def get_logger(self, name: Optional[str] = None) -> logging.Logger:
        """
        Returns logger instance.
        
        Args:
            name: Logger name (optional)
            
        Returns:
            Logger instance
        """
        if name:
            return logging.getLogger(f'TrendBot.{name}')
        return self.logger
    
    def shutdown(self) -> None:
        """Closes the logger and cleans up resources."""
        if self._queue_listener:
            self._queue_listener.stop()
            self._queue_listener = None
        
        # Close all handlers
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
    
    def info(self, message: str) -> None:
        """Log record at Info level."""
        self.logger.info(message)
    
    def warning(self, message: str) -> None:
        """Log record at Warning level."""
        self.logger.warning(message)
    
    def error(self, message: str, exc_info: bool = False) -> None:
        """Log record at Error level."""
        self.logger.error(message, exc_info=exc_info)
    
    def debug(self, message: str) -> None:
        """Log record at Debug level."""
        self.logger.debug(message)
    
    def critical(self, message: str, exc_info: bool = False) -> None:
        """Log record at Critical level."""
        self.logger.critical(message, exc_info=exc_info)
