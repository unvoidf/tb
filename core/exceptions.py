"""
Custom Exceptions: TrendBot custom exception classes.
Hierarchical exception structure for error handling.
"""


class TrendBotException(Exception):
    """TrendBot base exception class."""
    
    def __init__(self, message: str, error_code: str = None):
        """
        Initializes TrendBotException.
        
        Args:
            message: Error message
            error_code: Error code
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class AnalysisException(TrendBotException):
    """Technical analysis errors."""
    
    def __init__(self, message: str, symbol: str = None):
        """
        Initializes AnalysisException.
        
        Args:
            message: Error message
            symbol: Analyzed symbol
        """
        super().__init__(message, "ANALYSIS_ERROR")
        self.symbol = symbol


class DataException(TrendBotException):
    """Data fetching errors."""
    
    def __init__(self, message: str, source: str = None):
        """
        Initializes DataException.
        
        Args:
            message: Error message
            source: Data source
        """
        super().__init__(message, "DATA_ERROR")
        self.source = source


class BotException(TrendBotException):
    """Telegram bot errors."""
    
    def __init__(self, message: str, user_id: int = None):
        """
        Initializes BotException.
        
        Args:
            message: Error message
            user_id: User ID
        """
        super().__init__(message, "BOT_ERROR")
        self.user_id = user_id


class SchedulerException(TrendBotException):
    """Scheduler errors."""
    
    def __init__(self, message: str, job_id: str = None):
        """
        Initializes SchedulerException.
        
        Args:
            message: Error message
            job_id: Job ID
        """
        super().__init__(message, "SCHEDULER_ERROR")
        self.job_id = job_id


class ConfigurationException(TrendBotException):
    """Configuration errors."""
    
    def __init__(self, message: str, config_key: str = None):
        """
        Initializes ConfigurationException.
        
        Args:
            message: Error message
            config_key: Configuration key
        """
        super().__init__(message, "CONFIG_ERROR")
        self.config_key = config_key


class ValidationException(TrendBotException):
    """Data validation errors."""
    
    def __init__(self, message: str, field: str = None):
        """
        Initializes ValidationException.
        
        Args:
            message: Error message
            field: Validated field
        """
        super().__init__(message, "VALIDATION_ERROR")
        self.field = field


class NetworkException(TrendBotException):
    """Network connection errors."""
    
    def __init__(self, message: str, url: str = None):
        """
        Initializes NetworkException.
        
        Args:
            message: Error message
            url: Connection URL
        """
        super().__init__(message, "NETWORK_ERROR")
        self.url = url


class RateLimitException(TrendBotException):
    """Rate limit errors."""
    
    def __init__(self, message: str, retry_after: int = None):
        """
        Initializes RateLimitException.
        
        Args:
            message: Error message
            retry_after: Retry duration (seconds)
        """
        super().__init__(message, "RATE_LIMIT_ERROR")
        self.retry_after = retry_after
