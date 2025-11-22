"""
Unit Tests for Simulation Utils
--------------------------------
Tests for utility functions in simulation module.
"""
import pytest
from tools.simulation.utils import (
    format_timestamp,
    format_duration_str,
    interpret_results
)


class TestFormatTimestamp:
    """Test suite for format_timestamp function."""
    
    def test_format_timestamp(self):
        """Test timestamp formatting."""
        timestamp = 1000000000  # Unix timestamp
        
        result = format_timestamp(timestamp)
        
        assert isinstance(result, str)
        assert '/' in result  # Date separator
        assert ':' in result  # Time separator
    
    def test_format_timestamp_zero(self):
        """Test timestamp formatting with zero."""
        result = format_timestamp(0)
        
        assert isinstance(result, str)
        # Should not raise exception


class TestFormatDurationStr:
    """Test suite for format_duration_str function."""
    
    def test_format_duration_seconds(self):
        """Test duration formatting for seconds."""
        result = format_duration_str(90)
        
        assert isinstance(result, str)
        assert '0s' in result or '1s' in result
        assert 'dk' in result
    
    def test_format_duration_minutes(self):
        """Test duration formatting for minutes."""
        result = format_duration_str(3660)  # 1 hour 1 minute
        
        assert isinstance(result, str)
        assert 's' in result
        assert 'dk' in result
    
    def test_format_duration_hours(self):
        """Test duration formatting for hours."""
        result = format_duration_str(7200)  # 2 hours
        
        assert isinstance(result, str)
        assert 's' in result or 'dk' in result
    
    def test_format_duration_zero(self):
        """Test duration formatting with zero."""
        result = format_duration_str(0)
        
        assert isinstance(result, str)
        assert '0s' in result or 'dk' in result


class TestInterpretResults:
    """Test suite for interpret_results function."""
    
    def test_interpret_results_high_profit_factor(self):
        """Test interpretation with high profit factor."""
        metrics = {
            'profit_factor': 2.5,
            'max_drawdown': 10.0,
            'max_loss_streak': 3,
            'avg_duration_seconds': 3600,
            'liquidations': 0
        }
        
        insights = interpret_results(metrics)
        
        assert isinstance(insights, list)
        assert len(insights) > 0
        assert any('Mükemmel' in insight or 'mükemmel' in insight for insight in insights)
    
    def test_interpret_results_liquidations(self):
        """Test interpretation with liquidations."""
        metrics = {
            'profit_factor': 1.5,
            'max_drawdown': 15.0,
            'max_loss_streak': 2,
            'avg_duration_seconds': 1800,
            'liquidations': 3
        }
        
        insights = interpret_results(metrics)
        
        assert isinstance(insights, list)
        assert len(insights) > 0
        assert any('LİKİDASYON' in insight or 'likidite' in insight.lower() 
                   for insight in insights)
    
    def test_interpret_results_high_drawdown(self):
        """Test interpretation with high drawdown."""
        metrics = {
            'profit_factor': 1.2,
            'max_drawdown': 25.0,
            'max_loss_streak': 5,
            'avg_duration_seconds': 7200,
            'liquidations': 0
        }
        
        insights = interpret_results(metrics)
        
        assert isinstance(insights, list)
        assert len(insights) > 0
        assert any('YÜKSEK' in insight or 'yüksek' in insight.lower() 
                   for insight in insights)
    
    def test_interpret_results_loss_streak(self):
        """Test interpretation with high loss streak."""
        metrics = {
            'profit_factor': 1.1,
            'max_drawdown': 12.0,
            'max_loss_streak': 7,
            'avg_duration_seconds': 5400,
            'liquidations': 1
        }
        
        insights = interpret_results(metrics)
        
        assert isinstance(insights, list)
        assert len(insights) > 0
        assert any('Psikolojik' in insight or 'psikolojik' in insight.lower() 
                   for insight in insights)
    
    def test_interpret_results_scalper(self):
        """Test interpretation for scalper style."""
        metrics = {
            'profit_factor': 1.8,
            'max_drawdown': 8.0,
            'max_loss_streak': 2,
            'avg_duration_seconds': 1800,  # 30 minutes
            'liquidations': 0
        }
        
        insights = interpret_results(metrics)
        
        assert isinstance(insights, list)
        assert len(insights) > 0
        assert any('Scalper' in insight or 'scalper' in insight.lower() 
                   for insight in insights)
    
    def test_interpret_results_day_trader(self):
        """Test interpretation for day trader style."""
        metrics = {
            'profit_factor': 1.6,
            'max_drawdown': 10.0,
            'max_loss_streak': 3,
            'avg_duration_seconds': 21600,  # 6 hours
            'liquidations': 0
        }
        
        insights = interpret_results(metrics)
        
        assert isinstance(insights, list)
        assert len(insights) > 0
        assert any('Day Trader' in insight or 'day trader' in insight.lower() 
                   for insight in insights)
    
    def test_interpret_results_swing_trader(self):
        """Test interpretation for swing trader style."""
        metrics = {
            'profit_factor': 1.4,
            'max_drawdown': 15.0,
            'max_loss_streak': 4,
            'avg_duration_seconds': 172800,  # 2 days
            'liquidations': 0
        }
        
        insights = interpret_results(metrics)
        
        assert isinstance(insights, list)
        assert len(insights) > 0
        assert any('Swing Trader' in insight or 'swing trader' in insight.lower() 
                   for insight in insights)

