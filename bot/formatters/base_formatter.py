"""
BaseFormatter: Basic formatting utilities.
Markdown escape and timestamp formatting functions.
"""
import os
import time
from typing import Optional, List
from datetime import datetime, timezone
from utils.logger import LoggerManager


class BaseFormatter:
    """Provides basic formatting functions."""
    
    def __init__(self):
        self.logger = LoggerManager().get_logger('BaseFormatter')
    
    @staticmethod
    def escape_markdown_v2(text: str) -> str:
        """
        Escapes special characters for Telegram MarkdownV2.
        
        Characters that MUST be escaped in MarkdownV2 (only these):
        _ * [ ] ( ) ~ ` 
        
        Note: Other characters (+, -, =, |, {, }, ., !, >, #) should not be 
        escaped in normal text, only required in specific contexts.
        
        Args:
            text: Text to escape
            
        Returns:
            Escaped text
        """
        if not text:
            return text
        
        # Characters that MUST be escaped in MarkdownV2
        # Only these characters should be escaped
        # Note: () parentheses are only used in link format, should not be escaped in normal text
        special_chars = ['_', '*', '[', ']', '~', '`']
        
        # Escape each special character
        escaped = text
        for char in special_chars:
            escaped = escaped.replace(char, f'\\{char}')
        
        return escaped

    @staticmethod
    def escape_markdown_v2_chars(
        text: str,
        special_chars: Optional[List[str]] = None
    ) -> str:
        """
        Escapes specified characters in MarkdownV2 format.
        
        Args:
            text: Text to process
            special_chars: List of special characters to escape
            
        Returns:
            Escaped text
        """
        if not text:
            return text
        
        chars = special_chars or [
            '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|',
            '{', '}', '.', '!'
        ]
        
        escaped = text
        for char in chars:
            escaped = escaped.replace(char, f'\\{char}')
        return escaped
    
    @staticmethod
    def escape_markdown_v2_smart(text: str, preserve_code_blocks: bool = True) -> str:
        """
        Smart Markdown escape: Preserves characters inside code blocks and bold/italic.
        
        For Telegram's MarkdownV2 format:
        - *bold* -> preserved (single asterisk) - NOT ESCAPED
        - _italic_ -> preserved - NOT ESCAPED
        - `code` -> preserved - NOT ESCAPED
        
        Args:
            text: Text to escape
            preserve_code_blocks: If True, does not escape characters inside code blocks
            
        Returns:
            Escaped text
        """
        if not text:
            return text
        
        import re
        
        if not preserve_code_blocks:
            return BaseFormatter.escape_markdown_v2_selective(text)
        
        # Code block pattern: `...` (surrounded by backticks)
        parts = []
        last_end = 0
        
        # Find all code blocks (surrounded by backticks)
        pattern = r'`([^`]*)`'
        matches = list(re.finditer(pattern, text))
        
        for match in matches:
            # Escape the part before the code block (PRESERVING bold/italic)
            before = text[last_end:match.start()]
            before_escaped = BaseFormatter.escape_markdown_v2_selective(before)
            parts.append(before_escaped)
            
            # Leave code block content as is (DO NOT ESCAPE!)
            # Special characters (dot, brackets etc.) inside code block should not be escaped
            code_content = match.group(1)
            # Do not escape code block content at all - Telegram does not parse inside code blocks anyway
            parts.append(f'`{code_content}`')
            
            last_end = match.end()
        
        # Escape the remaining part (PRESERVING bold/italic)
        if last_end < len(text):
            remaining = text[last_end:]
            # Remaining part might contain code blocks too, check again
            remaining_escaped = BaseFormatter.escape_markdown_v2_selective(remaining)
            parts.append(remaining_escaped)
        
        return ''.join(parts)
    
    @staticmethod
    def escape_markdown_v2_selective(text: str) -> str:
        """
        Selective Markdown escape: Preserves Bold (*) and italic (_) formats,
        escapes other special characters.
        
        In Telegram's MarkdownV2 format:
        - *bold* -> preserved (single asterisk)
        - _italic_ -> preserved
        - Other special characters are escaped
        
        Args:
            text: Text to escape
            
        Returns:
            Escaped text
        """
        if not text:
            return text
        
        import re
        import uuid
        
        # Preserve bold and italic patterns
        # *text* -> preserved (single asterisk for MarkdownV2)
        # _text_ -> preserved
        
        # First mark bold and italic patterns
        # Then escape other special characters
        # Finally restore bold/italic markers
        
        # Temporary placeholders - must be unique
        placeholders = {}
        
        # Bold pattern: *text* (single asterisk for MarkdownV2)
        def bold_replacer(match):
            """Replaces bold pattern with placeholder for markdown escaping."""
            unique_id = str(uuid.uuid4())[:8]
            placeholder = f"__BOLD_{unique_id}__"
            content = match.group(1)
            escaped_content = BaseFormatter.escape_markdown_v2_chars(content)
            placeholders[placeholder] = f"*{escaped_content}*"
            return placeholder
        
        # Italic pattern: _text_ (but not inside *)
        def italic_replacer(match):
            """Replaces italic pattern with placeholder for markdown escaping."""
            unique_id = str(uuid.uuid4())[:8]
            placeholder = f"__ITALIC_{unique_id}__"
            content = match.group(1)
            escaped_content = BaseFormatter.escape_markdown_v2_chars(content)
            placeholders[placeholder] = f"_{escaped_content}_"
            return placeholder
        
        # Preserve bold (*text* - single asterisk, MarkdownV2)
        # Simple pattern: starts with * and ends with * (but not **)
        text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', bold_replacer, text)
        
        # Preserve italic (_text_ - underscore)
        text = re.sub(r'(?<!_)_([^_\s]+(?:\s+[^_\s]+)*)_(?!_)', italic_replacer, text)
        
        # Escape other special characters (except bold/italic)
        # According to Telegram MarkdownV2 documentation:
        # "In all other places characters '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!' must be escaped"
        # NOTE: Backtick (`) should not be escaped because _escape_markdown_v2_smart function
        # already preserves code blocks. If we escape here, code block pattern breaks.
        # Characters inside bold/italic patterns are not escaped because they are converted to placeholders
        # 
        # IMPORTANT: Must FULLY comply with Telegram documentation!
        # All special characters including parentheses must be escaped
        # Characters inside bold/italic are preserved thanks to placeholder mechanism
        text = BaseFormatter.escape_markdown_v2_chars(text)
        
        # Restore placeholders (in reverse order - last added first)
        for placeholder, original in reversed(list(placeholders.items())):
            text = text.replace(placeholder, original)
        
        return text
    
    def format_timestamp(self, timestamp: int) -> str:
        """
        Formats Unix timestamp to Turkey time (UTC+3).
        Uses TZ environment variable if present, otherwise defaults to Europe/Istanbul.
        
        Args:
            timestamp: Unix timestamp (seconds, UTC)
            
        Returns:
            Formatted date/time string (Turkey time - UTC+3)
        """
        try:
            # Convert Unix timestamp to UTC datetime
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            
            # TZ environment variable check (for flexibility)
            tz_name = os.getenv('TZ')
            if not tz_name:
                # Default timezone: Turkey time (UTC+3)
                tz_name = 'Europe/Istanbul'
            
            try:
                from zoneinfo import ZoneInfo
                local_dt = dt.astimezone(ZoneInfo(tz_name))
            except ImportError:
                # If zoneinfo module is missing (Python < 3.9), use UTC
                local_dt = dt
            except Exception:
                # If ZoneInfo fails, use UTC
                local_dt = dt
            
            formatted = local_dt.strftime('%d/%m/%Y %H:%M:%S')
            try:
                self.logger.debug(f"format_timestamp: ts={timestamp} -> {formatted} (timezone: {tz_name})")
            except Exception:
                pass
            return formatted
        except Exception as e:
            # Last resort: simple datetime format (based on system time)
            try:
                return datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y %H:%M:%S')
            except Exception:
                return "Date unavailable"
    
    def format_timestamp_with_seconds(self, timestamp: Optional[int]) -> str:
        """Formats optional timestamp."""
        if timestamp is None:
            return "-"
        return self.format_timestamp(timestamp)
    
    def format_time_elapsed(self, start_timestamp: Optional[int], end_timestamp: Optional[int]) -> str:
        """
        Returns the time elapsed between two timestamps in human readable format.
        
        Args:
            start_timestamp: Start timestamp (seconds)
            end_timestamp: End timestamp (seconds, if None uses current time)
            
        Returns:
            Human readable time difference (e.g., "2 hours 11 minutes", "1 day 3 hours", "45 minutes")
        """
        try:
            if start_timestamp is None:
                return "-"
            
            if end_timestamp is None:
                end_timestamp = int(time.time())
            
            elapsed_seconds = end_timestamp - start_timestamp
            
            if elapsed_seconds < 0:
                return "-"
            
            # Calculate days, hours, minutes
            days = elapsed_seconds // 86400
            hours = (elapsed_seconds % 86400) // 3600
            minutes = (elapsed_seconds % 3600) // 60
            
            # Format
            parts = []
            if days > 0:
                parts.append(f"{days} days" if days != 1 else f"{days} day")
            if hours > 0:
                parts.append(f"{hours} hours" if hours != 1 else f"{hours} hour")
            if minutes > 0:
                parts.append(f"{minutes} minutes" if minutes != 1 else f"{minutes} minute")
            
            # If nothing (very short duration)
            if not parts:
                if elapsed_seconds > 0:
                    return "less than 1 minute"
                return "0 minutes"
            
            return " ".join(parts)
            
        except Exception:
            return "-"

    def format_price_with_timestamp(self, price: float, timestamp: Optional[int] = None) -> str:
        """
        Formats price with date/time information.
        
        Args:
            price: Price
            timestamp: Unix timestamp (optional)
            
        Returns:
            Formatted price string
        """
        if price is None:
            return "💰 Price unavailable"
        
        price_str = f"💰 ${price:,.4f}"
        
        if timestamp:
            time_str = self.format_timestamp(timestamp)
            price_str += f" ({time_str})"
        
        try:
            self.logger.debug(f"format_price_with_timestamp: price={price}, ts={timestamp} -> {price_str}")
        except Exception:
            pass
        return price_str
    
    # Emoji and string mapping constants
    DIRECTION_EMOJI = {
        'LONG': '📈',
        'SHORT': '📉',
        'NEUTRAL': '➡️'
    }
    
    DIRECTION_TR = {
        'LONG': 'LONG (Buy)',
        'SHORT': 'SHORT (Sell)',
        'NEUTRAL': 'NEUTRAL'
    }

    DIRECTION_TITLE = {
        'LONG': 'LONG',
        'SHORT': 'SHORT',
        'NEUTRAL': 'NEUTRAL'
    }

    DIRECTION_FORECAST = {
        'LONG': 'Bullish',
        'SHORT': 'Bearish',
        'NEUTRAL': 'Neutral'
    }
