"""
LoggerManager: Merkezi log yönetim sistemi.
Async logging + Rotating/TimedRotating file handler ile hem dosyaya hem console'a log yazan yapı.
Kategorize edilmiş log dosyaları: signal_scanner.log, signal_tracker.log, trendbot.log
"""
import logging
import os
import queue
import threading
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler, QueueHandler, QueueListener
from typing import Optional, List


class LoggerNameFilter(logging.Filter):
    """Logger name'lerine göre filtreleme yapar."""
    
    def __init__(self, allowed_names: list):
        """
        Args:
            allowed_names: İzin verilen logger name'leri (veya prefix'leri)
        """
        super().__init__()
        self.allowed_names = allowed_names
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Logger name'i kontrol eder."""
        logger_name = record.name
        # Tam eşleşme veya prefix kontrolü
        for allowed in self.allowed_names:
            if logger_name == allowed or logger_name.startswith(allowed + '.'):
                return True
        return False


class ExcludeLoggerNameFilter(logging.Filter):
    """Belirli logger name'lerini hariç tutar (exclude filter)."""
    
    def __init__(self, excluded_names: list):
        """
        Args:
            excluded_names: Hariç tutulacak logger name'leri (veya prefix'leri)
        """
        super().__init__()
        self.excluded_names = excluded_names
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Logger name'i kontrol eder - excluded name'ler False döner."""
        logger_name = record.name
        # Excluded name'lerden biriyle eşleşirse False döndür (hariç tut)
        for excluded in self.excluded_names:
            if logger_name == excluded or logger_name.startswith(excluded + '.'):
                return False
        return True


class LoggerManager:
    """Uygulama genelinde log yönetimi sağlar."""
    
    _instance: Optional['LoggerManager'] = None
    _initialized: bool = False
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern implementasyonu."""
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
        LoggerManager'ı başlatır.
        
        Args:
            log_dir: Log dosyalarının kaydedileceği dizin
            max_bytes: Her log dosyasının maksimum boyutu (default: .env'den okunur veya 1MB)
            backup_count: Saklanacak backup log sayısı (default: .env'den okunur veya 5)
            async_enabled: Async logging aktif mi? (default: .env'den okunur veya True)
            rotation_type: Rotation tipi: 'size', 'time', 'both' (default: .env'den okunur veya 'both')
            rotation_when: Zaman bazlı rotation: 'midnight', 'H', 'D', 'W' (default: .env'den okunur veya 'midnight')
            rotation_interval: Zaman bazlı rotation interval (default: .env'den okunur veya 1)
        """
        if self._initialized:
            return
        
        # .env'den log ayarlarını oku
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
        
        # Async logging ayarı
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
        
        # Time rotation ayarları
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
        
        # Async logging için queue ve listener
        self._log_queue = None
        self._queue_listener = None
        
        self._setup_log_directory()
        # Önce tüm handler'ları topla, sonra logger'ı kur
        all_real_handlers = []
        self._setup_logger(all_real_handlers)
        self._setup_categorized_loggers(all_real_handlers)
        # Async logging için QueueListener'ı tüm handler'larla oluştur
        if self.async_enabled and self._log_queue:
            if self._queue_listener:
                self._queue_listener.stop()
            self._queue_listener = QueueListener(self._log_queue, *all_real_handlers, respect_handler_level=True)
            self._queue_listener.start()
        self._initialized = True
    
    def _setup_log_directory(self) -> None:
        """Log dizinini oluşturur."""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
    def _create_file_handlers(self, log_file: str, level: int) -> List[logging.Handler]:
        """
        Dosya handler'ları oluşturur (rotation type'a göre).
        
        Args:
            log_file: Log dosya yolu
            level: Log seviyesi
            
        Returns:
            Handler instance'ları listesi (boş olabilir)
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
                # "both" modunda time rotation için farklı dosya kullan (duplicate önlemek için)
                # "time" modunda aynı dosyayı kullan
                if self.rotation_type == 'both':
                    # Time rotation için ayrı dosya: trendbot.log -> trendbot_time.log
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
        
        # Eğer handler yoksa, fallback handler oluştur
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
        Ana logger'ı yapılandırır.
        
        Args:
            real_handlers: Handler'ların ekleneceği liste (async için)
        """
        self.logger = logging.getLogger('TrendBot')
        
        # DEBUG env variable kontrolü (öncelikli)
        # DEBUG=1 → LOG_LEVEL=DEBUG, DEBUG=0 → LOG_LEVEL=INFO
        debug_env = os.getenv('DEBUG', '0').strip()
        if debug_env == '1':
            level = logging.DEBUG
        else:
            # LOG_LEVEL env ile override edilebilir (DEBUG, INFO, WARNING, ERROR)
            level_name = os.getenv('LOG_LEVEL', 'INFO').upper()
            level = getattr(logging, level_name, logging.INFO)
        
        self.logger.setLevel(level)
        
        # Önceki handler'ları temizle
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # Format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # File Handler(s) - rotation type'a göre birden fazla olabilir
        log_file = os.path.join(self.log_dir, 'trendbot.log')
        file_handlers = self._create_file_handlers(log_file, level)
        # trendbot.log handler'ına exclude filter ekle (kategorize edilmiş logları hariç tut)
        # Böylece duplicate loglar önlenir
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
        
        # Console Handler (her zaman senkron)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        real_handlers.append(console_handler)
        
        # Async logging aktifse QueueHandler kullan
        if self.async_enabled:
            # Queue oluştur
            self._log_queue = queue.Queue(-1)  # Unlimited queue
            
            # QueueHandler oluştur (logger'a eklenir)
            queue_handler = QueueHandler(self._log_queue)
            queue_handler.setLevel(level)
            self.logger.addHandler(queue_handler)
            # QueueListener daha sonra tüm handler'larla oluşturulacak
        else:
            # Senkron: handler'ları direkt ekle
            for handler in real_handlers:
                self.logger.addHandler(handler)
    
    def _setup_categorized_loggers(self, real_handlers: List[logging.Handler]) -> None:
        """
        Kategorize edilmiş logger'ları yapılandırır.
        
        Args:
            real_handlers: Handler'ların ekleneceği liste (async için)
        """
        # Log seviyesi
        debug_env = os.getenv('DEBUG', '0').strip()
        if debug_env == '1':
            level = logging.DEBUG
        else:
            level_name = os.getenv('LOG_LEVEL', 'INFO').upper()
            level = getattr(logging, level_name, logging.INFO)
        
        # Ana logger'ı al (tüm loglar buraya gider)
        root_logger = logging.getLogger('TrendBot')
        
        # 1. Signal Scanner Logger (Sinyal tarama ve üretme)
        scanner_file = os.path.join(self.log_dir, 'signal_scanner.log')
        scanner_handlers = self._create_file_handlers(scanner_file, level)
        # Sadece sinyal tarama ile ilgili logger'ları filtrele
        scanner_filter = LoggerNameFilter([
            'TrendBot.SignalScannerManager',
            'TrendBot.SignalGenerator',
            'TrendBot.SignalRanker',
            'TrendBot.RangingStrategyAnalyzer',
            'TrendBot.AdaptiveThresholdManager',
            'TrendBot.TechnicalIndicatorCalculator',
            'TrendBot.VolumeAnalyzer',
            'TrendBot.MarketAnalyzer',
            'TrendBot.LiquidationSafetyFilter'  # Liquidation risk analizi de buraya
        ])
        for handler in scanner_handlers:
            handler.addFilter(scanner_filter)
            real_handlers.append(handler)
        
        # 2. Signal Tracker Logger (TP/SL takip)
        tracker_file = os.path.join(self.log_dir, 'signal_tracker.log')
        tracker_handlers = self._create_file_handlers(tracker_file, level)
        # Sadece TP/SL takip ile ilgili logger'ları filtrele
        tracker_filter = LoggerNameFilter(['TrendBot.SignalTracker'])
        for handler in tracker_handlers:
            handler.addFilter(tracker_filter)
            real_handlers.append(handler)
        
        # Senkron modda handler'ları direkt ekle
        if not self.async_enabled:
            for handler in real_handlers:
                root_logger.addHandler(handler)
    
    def get_logger(self, name: Optional[str] = None) -> logging.Logger:
        """
        Logger instance döndürür.
        
        Args:
            name: Logger adı (opsiyonel)
            
        Returns:
            Logger instance
        """
        if name:
            return logging.getLogger(f'TrendBot.{name}')
        return self.logger
    
    def shutdown(self) -> None:
        """Logger'ı kapatır ve kaynakları temizler."""
        if self._queue_listener:
            self._queue_listener.stop()
            self._queue_listener = None
        
        # Tüm handler'ları kapat
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
    
    def info(self, message: str) -> None:
        """Info seviyesinde log kaydı."""
        self.logger.info(message)
    
    def warning(self, message: str) -> None:
        """Warning seviyesinde log kaydı."""
        self.logger.warning(message)
    
    def error(self, message: str, exc_info: bool = False) -> None:
        """Error seviyesinde log kaydı."""
        self.logger.error(message, exc_info=exc_info)
    
    def debug(self, message: str) -> None:
        """Debug seviyesinde log kaydı."""
        self.logger.debug(message)
    
    def critical(self, message: str, exc_info: bool = False) -> None:
        """Critical seviyesinde log kaydı."""
        self.logger.critical(message, exc_info=exc_info)

