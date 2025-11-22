"""
Simulation Module
-----------------
Modular simulation engine for TrendBot historical backtesting.
"""
from .models import Event
from .portfolio import Portfolio
from .position_manager import PositionSlot, calculate_liquidation_price, get_position_slot
from .simulation_engine import SimulationEngine
from .optimization_engine import OptimizationEngine

__all__ = [
    'Event',
    'Portfolio',
    'PositionSlot',
    'calculate_liquidation_price',
    'get_position_slot',
    'SimulationEngine',
    'OptimizationEngine'
]

