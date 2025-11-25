"""
Direction Analyzer
------------------
Analyzes performance differences between LONG and SHORT signals.
"""
from typing import Dict, List
from dataclasses import dataclass
from .signal_analyzer import SignalStats, SignalOutcome


@dataclass
class DirectionPerformance:
    """Performance metrics for a direction (LONG/SHORT)."""
    direction: str
    signal_count: int
    win_rate: float
    avg_r_multiple: float
    avg_confidence: float
    tp1_rate: float
    tp2_rate: float
    sl_rate: float
    avg_hold_time_hours: float


class DirectionAnalyzer:
    """Analyzes LONG vs SHORT performance."""
    
    def __init__(self, signal_stats: List[SignalStats]):
        """Initialize direction analyzer."""
        self.signal_stats = signal_stats
        self.long_perf: Optional[DirectionPerformance] = None
        self.short_perf: Optional[DirectionPerformance] = None
    
    def analyze(self) -> Dict:
        """Analyzes LONG vs SHORT performance."""
        long_signals = [s for s in self.signal_stats if s.direction == 'LONG']
        short_signals = [s for s in self.signal_stats if s.direction == 'SHORT']
        
        self.long_perf = self._calculate_direction_performance('LONG', long_signals)
        self.short_perf = self._calculate_direction_performance('SHORT', short_signals)
        
        return {
            'long': self.long_perf,
            'short': self.short_perf,
            'bias': self._calculate_bias()
        }
    
    def _calculate_direction_performance(
        self, 
        direction: str, 
        signals: List[SignalStats]
    ) -> DirectionPerformance:
        """Calculates performance for a direction."""
        if not signals:
            return DirectionPerformance(
                direction=direction, signal_count=0, win_rate=0.0,
                avg_r_multiple=0.0, avg_confidence=0.0, tp1_rate=0.0,
                tp2_rate=0.0, sl_rate=0.0, avg_hold_time_hours=0.0
            )
        
        total = len(signals)
        closed = [s for s in signals if s.outcome != SignalOutcome.OPEN]
        closed_count = len(closed)
        
        wins = sum(1 for s in closed 
                  if s.outcome in [SignalOutcome.TP1_ONLY, SignalOutcome.TP2_REACHED, SignalOutcome.TP3_REACHED])
        losses = sum(1 for s in closed 
                    if s.outcome == SignalOutcome.SL_HIT)
        
        win_rate = (wins / closed_count * 100) if closed_count > 0 else 0.0
        sl_rate = (losses / closed_count * 100) if closed_count > 0 else 0.0
        
        tp1_count = sum(1 for s in signals 
                       if s.outcome in [SignalOutcome.TP1_ONLY, SignalOutcome.TP2_REACHED, SignalOutcome.TP3_REACHED])
        tp2_count = sum(1 for s in signals 
                       if s.outcome in [SignalOutcome.TP2_REACHED, SignalOutcome.TP3_REACHED])
        
        tp1_rate = (tp1_count / total * 100) if total > 0 else 0.0
        tp2_rate = (tp2_count / total * 100) if total > 0 else 0.0
        
        r_multiples = [s.r_multiple for s in signals if s.r_multiple is not None]
        avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else 0.0
        
        avg_conf = sum(s.confidence for s in signals) / total
        
        hold_times = [s.hold_time_hours for s in signals if s.hold_time_hours is not None]
        avg_hold = sum(hold_times) / len(hold_times) if hold_times else 0.0
        
        return DirectionPerformance(
            direction=direction,
            signal_count=total,
            win_rate=round(win_rate, 2),
            avg_r_multiple=round(avg_r, 3),
            avg_confidence=round(avg_conf, 3),
            tp1_rate=round(tp1_rate, 2),
            tp2_rate=round(tp2_rate, 2),
            sl_rate=round(sl_rate, 2),
            avg_hold_time_hours=round(avg_hold, 2)
        )
    
    def _calculate_bias(self) -> Dict:
        """Calculates if system has directional bias."""
        total = self.long_perf.signal_count + self.short_perf.signal_count
        if total == 0:
            return {'bias': 'NONE', 'ratio': '0:0'}
        
        long_pct = (self.long_perf.signal_count / total) * 100
        short_pct = (self.short_perf.signal_count / total) * 100
        
        bias = 'BALANCED'
        if long_pct > 70:
            bias = 'LONG'
        elif short_pct > 70:
            bias = 'SHORT'
        
        return {
            'bias': bias,
            'long_percentage': round(long_pct, 1),
            'short_percentage': round(short_pct, 1),
            'ratio': f"{self.long_perf.signal_count}:{self.short_perf.signal_count}"
        }
