"""
LoggerManager: Central log management system.
Structure that writes logs to both file and console with Async logging + Rotating/TimedRotating file handler.
Categorized log files: signal_scanner.log, signal_tracker.log, trendbot.log
"""
import logging
import os
import queue
import threading
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler, QueueHandler, QueueListener
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
                 max_bytes: Optional[int] = None,
                 backup_count: Optional[int] = None,
                 async_enabled: Optional[bool] = None,
                 rotation_type: Optional[str] = None,
                 rotation_when: Optional[str] = None,
                 rotation_interval: Optional[int] = None):
        """
        Initializes LoggerManager.
        
        Args:
            log_dir: Directory where log files will be saved
            max_bytes: Maximum size of each log file (default: read from .env or 1MB)
            backup_count: Number of backup logs to keep (default: read from .env or 5)
            async_enabled: Is async logging enabled? (default: read from .env or True)
            rotation_type: Rotation type: 'size', 'time', 'both' (default: read from .env or 'both')
            rotation_when: Time-based rotation: 'midnight', 'H', 'D', 'W' (default: read from .env or 'midnight')
            rotation_interval: Time-based rotation interval (default: read from .env or 1)
        """
        if self._initialized:
            return
        
        # Read log settings from .env
        self.log_dir = log_dir or os.getenv('LOG_DIR', 'logs')
        
        if max_bytes is None:
            try:
                max_bytes_str = os.getenv('LOG_MAX_BYTES')
                self.max_bytes = int(max_bytes_str) if max_bytes_str else (1 * 1024 * 1024)  # 1MB default
            except (ValueError, TypeError):
                self.max_bytes = 1 * 1024 * 1024  # 1MB default
        else:
            self.max_bytes = max_bytes
        
        if backup_count is None:
            try:
                backup_count_str = os.getenv('LOG_BACKUP_COUNT')
                self.backup_count = int(backup_count_str) if backup_count_str else 5
            except (ValueError, TypeError):
                self.backup_count = 5
        else:
            self.backup_count = backup_count
        
        # Async logging setting
        if async_enabled is None:
            async_str = os.getenv('LOG_ASYNC_ENABLED', 'true').lower()
            self.async_enabled = async_str in ('true', '1', 'yes')
        else:
            self.async_enabled = async_enabled
        
        # Rotation type: 'size', 'time', 'both'
        if rotation_type is None:
            self.rotation_type = os.getenv('LOG_ROTATION_TYPE', 'both').lower()
            if self.rotation_type not in ('size', 'time', 'both'):
                self.rotation_type = 'both'
        else:
            self.rotation_type = rotation_type
        
        # Time rotation settings
        if rotation_when is None:
            self.rotation_when = os.getenv('LOG_ROTATION_WHEN', 'midnight').lower()
        else:
            self.rotation_when = rotation_when
        
        if rotation_interval is None:
            try:
                interval_str = os.getenv('LOG_ROTATION_INTERVAL', '1')
                self.rotation_interval = int(interval_str)
            except (ValueError, TypeError):
                self.rotation_interval = 1
        else:
            self.rotation_interval = rotation_interval
        
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
    
    def _create_file_handlers(self, log_file: str, level: int) -> List[logging.Handler]:
        """
        Creates file handlers (based on rotation type).
        
        Args:
            log_file: Log file path
            level: Log level
            
        Returns:
            List of Handler instances (can be empty)
        """
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        handlers = []
        
        # Size-based rotation (RotatingFileHandler)
        if self.rotation_type in ('size', 'both'):
            try:
                size_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=self.max_bytes,
                    backupCount=self.backup_count,
                    encoding='utf-8'
                )
                size_handler.setLevel(level)
                size_handler.setFormatter(formatter)
                handlers.append(size_handler)
            except Exception:
                pass
        
        # Time-based rotation (TimedRotatingFileHandler)
        if self.rotation_type in ('time', 'both'):
            try:
                # Use different file for time rotation in "both" mode (to prevent duplicates)
                # Use same file in "time" mode
                if self.rotation_type == 'both':
                    # Separate file for time rotation: trendbot.log -> trendbot_time.log
                    time_log_file = log_file.replace('.log', '_time.log')
                else:
                    time_log_file = log_file
                
                time_handler = TimedRotatingFileHandler(
                    time_log_file,
                    when=self.rotation_when,
                    interval=self.rotation_interval,
                    backupCount=self.backup_count,
                    encoding='utf-8'
                )
                time_handler.setLevel(level)
                time_handler.setFormatter(formatter)
                handlers.append(time_handler)
            except Exception:
                pass
        
        # If no handler, create fallback handler
        if not handlers:
            try:
                fallback_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=self.max_bytes,
                    backupCount=self.backup_count,
                    encoding='utf-8'
                )
                fallback_handler.setLevel(level)
                fallback_handler.setFormatter(formatter)
                handlers.append(fallback_handler)
            except Exception:
                pass
        
        return handlers
    
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
        
        # File Handler(s) - can be multiple based on rotation type
        log_file = os.path.join(self.log_dir, 'trendbot.log')
        file_handlers = self._create_file_handlers(log_file, level)
        # Add exclude filter to trendbot.log handler (exclude categorized logs)
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
        for handler in file_handlers:
            handler.addFilter(exclude_filter)
        real_handlers.extend(file_handlers)
        
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
        Configures categorized loggers.
        
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
        scanner_file = os.path.join(self.log_dir, 'signal_scanner.log')
        scanner_handlers = self._create_file_handlers(scanner_file, level)
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
        for handler in scanner_handlers:
            handler.addFilter(scanner_filter)
            real_handlers.append(handler)
        
        # 2. Signal Tracker Logger (TP/SL tracking)
        tracker_file = os.path.join(self.log_dir, 'signal_tracker.log')
        tracker_handlers = self._create_file_handlers(tracker_file, level)
        # Filter only TP/SL tracking related loggers
        tracker_filter = LoggerNameFilter(['TrendBot.SignalTracker'])
        for handler in tracker_handlers:
            handler.addFilter(tracker_filter)
            real_handlers.append(handler)
        
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
