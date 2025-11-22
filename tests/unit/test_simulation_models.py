"""
Unit Tests for Simulation Models
---------------------------------
Tests for Event dataclass and other models.
"""
import pytest
from tools.simulation.models import Event


class TestEvent:
    """Test suite for Event dataclass."""
    
    def test_event_initialization(self):
        """Test event initialization."""
        signal = {'signal_id': 'TEST123', 'symbol': 'BTC/USDT', 'direction': 'LONG'}
        details = {'exit_price': 50000.0}
        
        event = Event(
            timestamp=1000000000,
            type='ENTRY',
            signal=signal,
            details=details
        )
        
        assert event.timestamp == 1000000000
        assert event.type == 'ENTRY'
        assert event.signal == signal
        assert event.details == details
    
    def test_event_comparison(self):
        """Test event comparison for sorting."""
        event1 = Event(
            timestamp=1000000000,
            type='ENTRY',
            signal={},
            details={}
        )
        
        event2 = Event(
            timestamp=1000000100,
            type='EXIT_TP',
            signal={},
            details={}
        )
        
        assert event1 < event2
        assert not (event2 < event1)
    
    def test_event_sorting(self):
        """Test event sorting by timestamp."""
        events = [
            Event(timestamp=1000000200, type='ENTRY', signal={}, details={}),
            Event(timestamp=1000000000, type='ENTRY', signal={}, details={}),
            Event(timestamp=1000000100, type='EXIT_TP', signal={}, details={}),
        ]
        
        sorted_events = sorted(events)
        
        assert sorted_events[0].timestamp == 1000000000
        assert sorted_events[1].timestamp == 1000000100
        assert sorted_events[2].timestamp == 1000000200

