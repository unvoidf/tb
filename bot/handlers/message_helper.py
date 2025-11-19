"""
MessageHelper: Telegram mesaj gönderme ve düzenleme helper'ları.
Markdown formatting, error handling, retry logic.
"""
from utils.logger import LoggerManager


class MessageHelper:
    """Telegram mesaj işlemleri için helper sınıfı."""
    
    def __init__(self):
        self.logger = LoggerManager().get_logger('MessageHelper')
    
    def validate_message_length(self, message: str, max_length: int = 4096) -> bool:
        """
        Mesaj uzunluğunu kontrol eder.
        
        Args:
            message: Mesaj
            max_length: Maximum uzunluk (Telegram limiti: 4096)
            
        Returns:
            True ise geçerli
        """
        return len(message) <= max_length
    
    def truncate_message(self, message: str, max_length: int = 4096) -> str:
        """
        Mesajı kısaltır.
        
        Args:
            message: Mesaj
            max_length: Maximum uzunluk
            
        Returns:
            Kısaltılmış mesaj
        """
        if len(message) <= max_length:
            return message
        
        truncated = message[:max_length-50] + "\n\n...(mesaj kısaltıldı)"
        return truncated
    
    def should_retry_on_error(self, error_message: str) -> bool:
        """
        Hata mesajına göre retry yapılıp yapılmayacağını belirler.
        
        Args:
            error_message: Hata mesajı
            
        Returns:
            True ise retry yapılmalı
        """
        retry_errors = [
            'timeout',
            'network error',
            'connection',
            'temporary'
        ]
        
        error_lower = error_message.lower()
        return any(err in error_lower for err in retry_errors)

