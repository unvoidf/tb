"""
Simulation Models
-----------------
Data models for simulation events.
"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class Event:
    """Represents a simulation event (Entry, Exit TP, Exit SL)."""
    timestamp: int
    type: str  # 'ENTRY', 'EXIT_TP', 'EXIT_SL'
    signal: Dict[str, Any]
    details: Dict[str, Any]  # Extra info like price, reason

    def __lt__(self, other):
        return self.timestamp < other.timestamp

