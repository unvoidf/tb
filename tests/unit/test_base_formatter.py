"""
Unit tests for BaseFormatter.
"""
import pytest
from bot.formatters.base_formatter import BaseFormatter


class TestBaseFormatter:
    """BaseFormatter test sınıfı."""
    
    @pytest.fixture
    def formatter(self):
        """BaseFormatter fixture."""
        return BaseFormatter()
    
    def test_escape_markdown_v2(self, formatter):
        """Markdown escape testi."""
        # Temel escape
        text = "Test_text*with[special]chars"
        escaped = formatter.escape_markdown_v2(text)
        
        assert '\\' in escaped  # Escape karakteri var
        assert '_' not in escaped or '\\_' in escaped
        assert '*' not in escaped or '\\*' in escaped
    
    def test_format_timestamp(self, formatter):
        """Timestamp formatlama testi."""
        timestamp = 1700000000  # Örnek timestamp
        
        formatted = formatter.format_timestamp(timestamp)
        
        assert formatted is not None
        assert isinstance(formatted, str)
        assert len(formatted) > 0
        # Format: DD/MM/YYYY HH:MM:SS
        assert '/' in formatted
        assert ':' in formatted
    
    def test_format_time_elapsed(self, formatter):
        """Geçen süre formatlama testi."""
        start = 1700000000
        end = 1700003600  # 1 saat sonra
        
        elapsed = formatter.format_time_elapsed(start, end)
        
        assert elapsed is not None
        assert 'saat' in elapsed or 'dakika' in elapsed
    
    def test_direction_constants(self, formatter):
        """Yön constant'ları testi."""
        assert 'LONG' in formatter.DIRECTION_EMOJI
        assert 'SHORT' in formatter.DIRECTION_EMOJI
        assert 'NEUTRAL' in formatter.DIRECTION_EMOJI
        
        assert formatter.DIRECTION_EMOJI['LONG'] == '📈'
        assert formatter.DIRECTION_EMOJI['SHORT'] == '📉'

