"""
MessageHelper: Telegram message sending and editing helpers.
Markdown formatting, error handling, retry logic.
"""
from utils.logger import LoggerManager


class MessageHelper:
    """Helper class for Telegram message operations."""
    
    def __init__(self):
        self.logger = LoggerManager().get_logger('MessageHelper')
    
    def validate_message_length(self, message: str, max_length: int = 4096) -> bool:
        """
        Checks message length.
        
        Args:
            message: Message
            max_length: Maximum length (Telegram limit: 4096)
            
        Returns:
            True if valid
        """
        return len(message) <= max_length
    
    def truncate_message(self, message: str, max_length: int = 4096) -> str:
        """
        Truncates the message.
        
        Args:
            message: Message
            max_length: Maximum length
            
        Returns:
            Truncated message
        """
        if len(message) <= max_length:
            return message
        
        truncated = message[:max_length-50] + "\n\n...(message truncated)"
        return truncated
    
    def should_retry_on_error(self, error_message: str) -> bool:
        """
        Determines whether to retry based on the error message.
        
        Args:
            error_message: Error message
            
        Returns:
            True if retry should be attempted
        """
        retry_errors = [
            'timeout',
            'network error',
            'connection',
            'temporary'
        ]
        
        error_lower = error_message.lower()
        return any(err in error_lower for err in retry_errors)
