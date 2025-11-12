"""
LoggerManager: Merkezi log yönetim sistemi.
Rotating file handler ile hem dosyaya hem console'a log yazan yapı.
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional


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
                 max_bytes: int = 1 * 1024 * 1024,  # 1MB
                 backup_count: int = 5):
        """
        LoggerManager'ı başlatır.
        
        Args:
            log_dir: Log dosyalarının kaydedileceği dizin
            max_bytes: Her log dosyasının maksimum boyutu (1MB)
            backup_count: Saklanacak backup log sayısı
        """
        if self._initialized:
            return
            
        self.log_dir = log_dir
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        
        self._setup_log_directory()
        self._setup_logger()
        self._initialized = True
    
    def _setup_log_directory(self) -> None:
        """Log dizinini oluşturur."""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
    def _setup_logger(self) -> None:
        """Ana logger'ı yapılandırır."""
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
        
        # File Handler (Rotating)
        log_file = os.path.join(self.log_dir, 'trendbot.log')
        try:
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=self.max_bytes,
                backupCount=self.backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        except Exception:
            # Test veya kısıtlı ortamlarda dosyaya yazılamazsa yalnızca console kullan
            pass
        
        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        
        # Handler'ları ekle
        self.logger.addHandler(console_handler)
    
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

