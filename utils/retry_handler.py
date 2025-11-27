"""
RetryHandler: Exponential backoff retry mechanism for API calls.
"""
import time
from typing import Callable, Any, Type, Tuple
from functools import wraps


class RetryHandler:
    """Provides retry mechanism for API calls."""
    
    def __init__(self, max_attempts: int = 5, 
                 backoff_base: int = 2,
                 initial_delay: int = 1):
        """
        Initializes RetryHandler.
        
        Args:
            max_attempts: Maximum number of attempts
            backoff_base: Exponential backoff base value
            initial_delay: Wait time before first retry (seconds)
        """
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base
        self.initial_delay = initial_delay
    
    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        Executes the function with retry mechanism.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function return value
            
        Raises:
            Exception occurred in the last attempt
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
        Calculates exponential backoff delay.
        
        Args:
            attempt: Current attempt number
            
        Returns:
            Wait time (seconds)
        """
        return self.initial_delay * (self.backoff_base ** (attempt - 1))
    
    @staticmethod
    def with_retry(max_attempts: int = 5, 
                   backoff_base: int = 2,
                   initial_delay: int = 1,
                   exceptions: Tuple[Type[Exception], ...] = (Exception,)):
        """
        Adds retry mechanism as a decorator.
        
        Args:
            max_attempts: Maximum number of attempts
            backoff_base: Exponential backoff base
            initial_delay: Initial delay
            exceptions: Exception types to catch
            
        Returns:
            Decorated function
        """
        def decorator(func: Callable) -> Callable:
            """Decorator that adds retry logic to the function."""
            @wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                """Wrapper function that executes the function with retries."""
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
