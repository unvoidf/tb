"""
PositionCalculator unit tests - R-based distances için.
"""
import pytest
from unittest.mock import Mock
from strategy.position_calculator import PositionCalculator


@pytest.fixture
def calculator():
    """PositionCalculator instance."""
    mock_fib = Mock()
    return PositionCalculator(mock_fib)


def test_calculate_r_distances_long(calculator):
    """LONG pozisyon için R-based distances."""
    # Arrange
    signal_price = 100.0
    direction = 'LONG'
    tp_levels = {'tp1': 105.0, 'tp2': 110.0}
    sl_price = 96.0
    
    # Act
    r_distances = calculator.calculate_r_distances(
        signal_price, direction, tp_levels, sl_price
    )
    
    # Assert
    # SL2 risk = 100 - 96 = 4
    # TP1 = (105-100)/4 = 1.25R
    # TP2 = (110-100)/4 = 2.5R
    assert abs(r_distances['tp1_r'] - 1.25) < 0.01
    assert abs(r_distances['tp2_r'] - 2.5) < 0.01
    assert abs(r_distances['sl_r'] - (-1.0)) < 0.01


def test_calculate_r_distances_short(calculator):
    """SHORT pozisyon için R-based distances."""
    # Arrange
    signal_price = 100.0
    direction = 'SHORT'
    tp_levels = {'tp1': 95.0, 'tp2': 90.0}
    sl_price = 104.0
    
    # Act
    r_distances = calculator.calculate_r_distances(
        signal_price, direction, tp_levels, sl_price
    )
    
    # Assert
    # SL2 risk = 104 - 100 = 4
    # TP1 = (100-95)/4 = 1.25R
    # TP2 = (100-90)/4 = 2.5R
    assert abs(r_distances['tp1_r'] - 1.25) < 0.01
    assert abs(r_distances['tp2_r'] - 2.5) < 0.01
    assert abs(r_distances['sl_r'] - (-1.0)) < 0.01

