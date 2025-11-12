"""
RetryHandler: API çağrıları için exponential backoff retry mekanizması.
"""
import time
from typing import Callable, Any, Type, Tuple
from functools import wraps


class RetryHandler:
    """API çağrıları için retry mekanizması sağlar."""
    
    def __init__(self, max_attempts: int = 5, 
                 backoff_base: int = 2,
                 initial_delay: int = 1):
        """
        RetryHandler'ı başlatır.
        
        Args:
            max_attempts: Maksimum deneme sayısı
            backoff_base: Exponential backoff base değeri
            initial_delay: İlk deneme arası bekleme süresi (saniye)
        """
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base
        self.initial_delay = initial_delay
    
    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        Fonksiyonu retry mekanizması ile çalıştırır.
        
        Args:
            func: Çalıştırılacak fonksiyon
            *args: Fonksiyon argümanları
            **kwargs: Fonksiyon keyword argümanları
            
        Returns:
            Fonksiyonun dönüş değeri
            
        Raises:
            Son denemede oluşan exception
        """
        last_exception = None
        
        for attempt in range(1, self.max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if attempt == self.max_attempts:
                    raise last_exception
                
                delay = self._calculate_delay(attempt)
                time.sleep(delay)
        
        raise last_exception
    
    def _calculate_delay(self, attempt: int) -> float:
        """
        Exponential backoff delay hesaplar.
        
        Args:
            attempt: Mevcut deneme sayısı
            
        Returns:
            Bekleme süresi (saniye)
        """
        return self.initial_delay * (self.backoff_base ** (attempt - 1))
    
    @staticmethod
    def with_retry(max_attempts: int = 5, 
                   backoff_base: int = 2,
                   initial_delay: int = 1,
                   exceptions: Tuple[Type[Exception], ...] = (Exception,)):
        """
        Decorator olarak retry mekanizması ekler.
        
        Args:
            max_attempts: Maksimum deneme sayısı
            backoff_base: Exponential backoff base
            initial_delay: İlk delay
            exceptions: Yakalanacak exception türleri
            
        Returns:
            Decorated fonksiyon
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                last_exception = None
                
                for attempt in range(1, max_attempts + 1):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        
                        if attempt == max_attempts:
                            raise last_exception
                        
                        delay = initial_delay * (backoff_base ** (attempt - 1))
                        time.sleep(delay)
                
                raise last_exception
            
            return wrapper
        return decorator

