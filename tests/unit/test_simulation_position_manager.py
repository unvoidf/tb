"""
Unit Tests for Simulation Position Manager
------------------------------------------
Tests for PositionSlot and position management.
"""
import pytest
from tools.simulation.position_manager import (
    PositionSlot, 
    calculate_liquidation_price,
    get_position_slot
)


class TestPositionSlot:
    """Test suite for PositionSlot class."""
    
    def test_position_slot_initialization(self):
        """Test position slot initialization."""
        slot = PositionSlot(direction='LONG')
        
        assert slot.direction == 'LONG'
        assert slot.total_quantity == 0.0
        assert slot.margin == 0.0
        assert not slot.is_active()
    
    def test_preview_after_add(self):
        """Test preview after adding position."""
        slot = PositionSlot(direction='LONG')
        mmr = 0.004
        
        qty, avg, margin, liq = slot.preview_after_add(
            quantity=1.0,
            entry_price=50000.0,
            margin_added=1000.0,
            mmr=mmr
        )
        
        assert qty == 1.0
        assert avg == 50000.0
        assert margin == 1000.0
        assert liq > 0  # Liquidation price should be calculated
    
    def test_apply_add(self):
        """Test applying position add."""
        slot = PositionSlot(direction='LONG')
        mmr = 0.004
        
        slot.apply_add(
            quantity=1.0,
            entry_price=50000.0,
            margin_added=1000.0,
            mmr=mmr
        )
        
        assert slot.total_quantity == 1.0
        assert slot.avg_entry_price == 50000.0
        assert slot.margin == 1000.0
        assert slot.is_active()
        assert slot.liquidation_price > 0
    
    def test_apply_add_aggregation(self):
        """Test position aggregation on multiple adds."""
        slot = PositionSlot(direction='LONG')
        mmr = 0.004
        
        # First add
        slot.apply_add(
            quantity=1.0,
            entry_price=50000.0,
            margin_added=1000.0,
            mmr=mmr
        )
        
        # Second add at different price
        slot.apply_add(
            quantity=1.0,
            entry_price=51000.0,
            margin_added=1020.0,
            mmr=mmr
        )
        
        # Average should be between two prices
        assert slot.total_quantity == 2.0
        assert 50000.0 < slot.avg_entry_price < 51000.0
        assert slot.margin == 2020.0
        assert slot.avg_entry_price == 50500.0  # Simple average
    
    def test_apply_reduce(self):
        """Test reducing position."""
        slot = PositionSlot(direction='LONG')
        mmr = 0.004
        
        # Add position first
        slot.apply_add(
            quantity=2.0,
            entry_price=50000.0,
            margin_added=2000.0,
            mmr=mmr
        )
        
        assert slot.total_quantity == 2.0
        
        # Reduce position
        slot.apply_reduce(
            quantity=1.0,
            margin_released=1000.0,
            mmr=mmr
        )
        
        assert slot.total_quantity == 1.0
        assert slot.margin == 1000.0
        assert slot.is_active()
    
    def test_apply_reduce_to_zero(self):
        """Test reducing position to zero."""
        slot = PositionSlot(direction='LONG')
        mmr = 0.004
        
        # Add position
        slot.apply_add(
            quantity=1.0,
            entry_price=50000.0,
            margin_added=1000.0,
            mmr=mmr
        )
        
        # Reduce all
        slot.apply_reduce(
            quantity=1.0,
            margin_released=1000.0,
            mmr=mmr
        )
        
        assert slot.total_quantity == 0.0
        assert slot.margin == 0.0
        assert not slot.is_active()
    
    def test_reset(self):
        """Test position slot reset."""
        slot = PositionSlot(direction='LONG')
        mmr = 0.004
        
        # Add position
        slot.apply_add(
            quantity=1.0,
            entry_price=50000.0,
            margin_added=1000.0,
            mmr=mmr
        )
        
        slot.reset()
        
        assert slot.total_quantity == 0.0
        assert slot.margin == 0.0
        assert slot.avg_entry_price == 0.0
        assert not slot.is_active()


class TestCalculateLiquidationPrice:
    """Test suite for liquidation price calculation."""
    
    def test_long_liquidation_price(self):
        """Test liquidation price calculation for LONG."""
        direction = 'LONG'
        entry_price = 50000.0
        quantity = 1.0
        margin = 1000.0
        mmr = 0.004
        
        liq_price = calculate_liquidation_price(
            direction, entry_price, quantity, margin, mmr
        )
        
        # For LONG, liquidation should be below entry price
        assert liq_price > 0
        assert liq_price < entry_price
    
    def test_short_liquidation_price(self):
        """Test liquidation price calculation for SHORT."""
        direction = 'SHORT'
        entry_price = 50000.0
        quantity = 1.0
        margin = 1000.0
        mmr = 0.004
        
        liq_price = calculate_liquidation_price(
            direction, entry_price, quantity, margin, mmr
        )
        
        # For SHORT, liquidation should be above entry price
        assert liq_price > 0
        assert liq_price > entry_price
    
    def test_zero_quantity(self):
        """Test liquidation price with zero quantity."""
        liq_price = calculate_liquidation_price(
            'LONG', 50000.0, 0.0, 1000.0, 0.004
        )
        
        assert liq_price == 0.0
    
    def test_zero_price(self):
        """Test liquidation price with zero price."""
        liq_price = calculate_liquidation_price(
            'LONG', 0.0, 1.0, 1000.0, 0.004
        )
        
        assert liq_price == 0.0


class TestGetPositionSlot:
    """Test suite for get_position_slot function."""
    
    def test_get_new_slot(self):
        """Test getting a new position slot."""
        position_book = {}
        
        slot = get_position_slot(position_book, 'BTC/USDT', 'LONG')
        
        assert slot.direction == 'LONG'
        assert 'BTC/USDT' in position_book
        assert 'LONG' in position_book['BTC/USDT']
        assert 'SHORT' in position_book['BTC/USDT']
    
    def test_get_existing_slot(self):
        """Test getting existing position slot."""
        position_book = {}
        
        slot1 = get_position_slot(position_book, 'BTC/USDT', 'LONG')
        slot1.apply_add(1.0, 50000.0, 1000.0, 0.004)
        
        slot2 = get_position_slot(position_book, 'BTC/USDT', 'LONG')
        
        # Should be the same slot
        assert slot1 is slot2
        assert slot2.total_quantity == 1.0
    
    def test_separate_long_short_slots(self):
        """Test that LONG and SHORT slots are separate."""
        position_book = {}
        
        long_slot = get_position_slot(position_book, 'BTC/USDT', 'LONG')
        short_slot = get_position_slot(position_book, 'BTC/USDT', 'SHORT')
        
        assert long_slot is not short_slot
        assert long_slot.direction == 'LONG'
        assert short_slot.direction == 'SHORT'

