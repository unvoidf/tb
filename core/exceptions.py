"""
Custom Exceptions: TrendBot özel exception sınıfları.
Hata yönetimi için hiyerarşik exception yapısı.
"""


class TrendBotException(Exception):
    """TrendBot base exception sınıfı."""
    
    def __init__(self, message: str, error_code: str = None):
        """
        TrendBotException'ı başlatır.
        
        Args:
            message: Hata mesajı
            error_code: Hata kodu
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class AnalysisException(TrendBotException):
    """Teknik analiz hataları."""
    
    def __init__(self, message: str, symbol: str = None):
        """
        AnalysisException'ı başlatır.
        
        Args:
            message: Hata mesajı
            symbol: Analiz edilen sembol
        """
        super().__init__(message, "ANALYSIS_ERROR")
        self.symbol = symbol


class DataException(TrendBotException):
    """Veri çekme hataları."""
    
    def __init__(self, message: str, source: str = None):
        """
        DataException'ı başlatır.
        
        Args:
            message: Hata mesajı
            source: Veri kaynağı
        """
        super().__init__(message, "DATA_ERROR")
        self.source = source


class BotException(TrendBotException):
    """Telegram bot hataları."""
    
    def __init__(self, message: str, user_id: int = None):
        """
        BotException'ı başlatır.
        
        Args:
            message: Hata mesajı
            user_id: Kullanıcı ID
        """
        super().__init__(message, "BOT_ERROR")
        self.user_id = user_id


class SchedulerException(TrendBotException):
    """Scheduler hataları."""
    
    def __init__(self, message: str, job_id: str = None):
        """
        SchedulerException'ı başlatır.
        
        Args:
            message: Hata mesajı
            job_id: Job ID
        """
        super().__init__(message, "SCHEDULER_ERROR")
        self.job_id = job_id


class ConfigurationException(TrendBotException):
    """Konfigürasyon hataları."""
    
    def __init__(self, message: str, config_key: str = None):
        """
        ConfigurationException'ı başlatır.
        
        Args:
            message: Hata mesajı
            config_key: Konfigürasyon anahtarı
        """
        super().__init__(message, "CONFIG_ERROR")
        self.config_key = config_key


class ValidationException(TrendBotException):
    """Veri doğrulama hataları."""
    
    def __init__(self, message: str, field: str = None):
        """
        ValidationException'ı başlatır.
        
        Args:
            message: Hata mesajı
            field: Doğrulanan alan
        """
        super().__init__(message, "VALIDATION_ERROR")
        self.field = field


class NetworkException(TrendBotException):
    """Ağ bağlantı hataları."""
    
    def __init__(self, message: str, url: str = None):
        """
        NetworkException'ı başlatır.
        
        Args:
            message: Hata mesajı
            url: Bağlantı URL'i
        """
        super().__init__(message, "NETWORK_ERROR")
        self.url = url


class RateLimitException(TrendBotException):
    """Rate limit hataları."""
    
    def __init__(self, message: str, retry_after: int = None):
        """
        RateLimitException'ı başlatır.
        
        Args:
            message: Hata mesajı
            retry_after: Tekrar deneme süresi (saniye)
        """
        super().__init__(message, "RATE_LIMIT_ERROR")
        self.retry_after = retry_after
