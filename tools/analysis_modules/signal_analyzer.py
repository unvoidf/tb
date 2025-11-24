"""
Signal Analyzer - Core Analysis Engine
---------------------------------------
Analyzes signal outcomes, calculates performance metrics, and provides insights.
"""
from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import time


class SignalOutcome(Enum):
    """Signal outcome classification."""
    TP3_REACHED = "TP3_REACHED"      # Hit TP3
    TP2_REACHED = "TP2_REACHED"      # Hit TP2 (but not TP3)
    TP1_ONLY = "TP1_ONLY"            # Hit TP1 only
    SL2_HIT = "SL2_HIT"              # Hit SL2 (liquidation)
    SL1_5_HIT = "SL1_5_HIT"          # Hit SL1.5
    SL1_HIT = "SL1_HIT"              # Hit SL1
    OPEN = "OPEN"                     # Still open (no TP/SL hit)
    EXPIRED_NO_HIT = "EXPIRED_NO_HIT"  # Expired without hitting anything


@dataclass
class SignalStats:
    """Statistics for a single signal."""
    signal_id: str
    symbol: str
    direction: str
    confidence: float
    outcome: SignalOutcome
    r_multiple: Optional[float]  # Profit/Loss in R
    hold_time_hours: Optional[float]
    created_at: int
    
    # Additional context
    mfe_percent: Optional[float] = None  # Maximum Favorable Excursion
    mae_percent: Optional[float] = None  # Maximum Adverse Excursion


@dataclass
class PerformanceMetrics:
    """Overall performance metrics."""
    total_signals: int
    
    # Outcome distribution
    tp3_count: int = 0
    tp2_count: int = 0
    tp1_count: int = 0
    sl1_count: int = 0
    sl1_5_count: int = 0
    sl2_count: int = 0
    open_count: int = 0
    expired_count: int = 0
    
    # Win rates
    win_rate: float = 0.0  # (TP1+TP2+TP3) / total_closed
    tp1_hit_rate: float = 0.0
    tp2_hit_rate: float = 0.0
    tp3_hit_rate: float = 0.0
    sl_hit_rate: float = 0.0
    
    # R-multiples
    avg_r_multiple: float = 0.0
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    expectancy: float = 0.0  # Expected R per trade
    
    # Time metrics
    avg_hold_time_hours: float = 0.0
    avg_time_to_tp_hours: float = 0.0
    avg_time_to_sl_hours: float = 0.0
    
    # MFE/MAE
    avg_mfe_percent: float = 0.0
    avg_mae_percent: float = 0.0


class SignalAnalyzer:
    """Main signal analysis engine."""
    
    def __init__(self, signals: List[Dict]):
        """
        Initialize analyzer with signals.
        
        Args:
            signals: List of signal dicts from database
        """
        self.signals = signals
        self.signal_stats: List[SignalStats] = []
        self.metrics: Optional[PerformanceMetrics] = None
    
    def analyze(self) -> PerformanceMetrics:
        """
        Performs comprehensive analysis.
        
        Returns:
            Performance metrics
        """
        # Classify each signal
        self.signal_stats = [self._classify_signal(sig) for sig in self.signals]
        
        # Calculate metrics
        self.metrics = self._calculate_metrics()
        
        return self.metrics
    
    def _classify_signal(self, signal: Dict) -> SignalStats:
        """
        Classifies signal outcome and calculates stats.
        
        Args:
            signal: Signal dict
            
        Returns:
            Signal statistics
        """
        # Determine outcome based on TP/SL hits
        outcome = self._determine_outcome(signal)
        
        # Calculate R-multiple
        r_multiple = self._calculate_r_multiple(signal, outcome)
        
        # Calculate hold time
        hold_time = self._calculate_hold_time(signal, outcome)
        
        # Calculate MFE/MAE percentages
        mfe_pct, mae_pct = self._calculate_mfe_mae_percent(signal)
        
        return SignalStats(
            signal_id=signal['signal_id'],
            symbol=signal['symbol'],
            direction=signal['direction'],
            confidence=signal['confidence'],
            outcome=outcome,
            r_multiple=r_multiple,
            hold_time_hours=hold_time,
            created_at=signal['created_at'],
            mfe_percent=mfe_pct,
            mae_percent=mae_pct
        )
    
    def _determine_outcome(self, signal: Dict) -> SignalOutcome:
        """Determines signal outcome based on TP/SL hits."""
        # Check SL hits first (most critical)
        if signal.get('sl2_hit'):
            return SignalOutcome.SL2_HIT
        if signal.get('sl1_5_hit'):
            return SignalOutcome.SL1_5_HIT
        if signal.get('sl1_hit'):
            return SignalOutcome.SL1_HIT
        
        # Check TP hits (in order of priority)
        if signal.get('tp3_hit'):
            return SignalOutcome.TP3_REACHED
        if signal.get('tp2_hit'):
            return SignalOutcome.TP2_REACHED
        if signal.get('tp1_hit'):
            return SignalOutcome.TP1_ONLY
        
        # Check if expired (older than 72 hours)
        age_hours = (time.time() - signal['created_at']) / 3600
        if age_hours > 72:
            return SignalOutcome.EXPIRED_NO_HIT
        
        return SignalOutcome.OPEN
    
    def _calculate_r_multiple(
        self, 
        signal: Dict, 
        outcome: SignalOutcome
    ) -> Optional[float]:
        """
        Calculates R-multiple (profit/loss in terms of risk).
        
        R-multiple = (Exit Price - Entry Price) / Risk
        Risk = Entry Price - SL2 Price
        """
        try:
            entry = signal.get('signal_price')
            sl2 = signal.get('sl2_price')
            
            if not entry or not sl2:
                return None
            
            # Calculate risk (always positive)
            direction = signal.get('direction', '').upper()
            if direction == 'LONG':
                risk = entry - sl2
            else:  # SHORT
                risk = sl2 - entry
            
            if risk <= 0:
                return None
            
            # Determine exit price based on outcome
            exit_price = self._get_exit_price(signal, outcome)
            if not exit_price:
                return None
            
            # Calculate profit/loss
            if direction == 'LONG':
                pnl = exit_price - entry
            else:  # SHORT
                pnl = entry - exit_price
            
            # R-multiple
            r_multiple = pnl / risk
            return round(r_multiple, 2)
            
        except (TypeError, ZeroDivisionError):
            return None
    
    def _get_exit_price(
        self, 
        signal: Dict, 
        outcome: SignalOutcome
    ) -> Optional[float]:
        """Gets exit price based on outcome."""
        if outcome == SignalOutcome.TP3_REACHED:
            return signal.get('tp3_price')
        elif outcome == SignalOutcome.TP2_REACHED:
            return signal.get('tp2_price')
        elif outcome == SignalOutcome.TP1_ONLY:
            return signal.get('tp1_price')
        elif outcome == SignalOutcome.SL1_HIT:
            return signal.get('sl1_price')
        elif outcome == SignalOutcome.SL1_5_HIT:
            return signal.get('sl1_5_price')
        elif outcome == SignalOutcome.SL2_HIT:
            return signal.get('sl2_price')
        
        return signal.get('final_price')  # For closed signals
    
    def _calculate_hold_time(
        self, 
        signal: Dict, 
        outcome: SignalOutcome
    ) -> Optional[float]:
        """Calculates hold time in hours."""
        created_at = signal.get('created_at')
        if not created_at:
            return None
        
        # Get exit timestamp based on outcome
        exit_time = None
        if outcome in [SignalOutcome.TP3_REACHED, SignalOutcome.TP2_REACHED]:
            exit_time = signal.get('tp2_hit_at') or signal.get('tp3_hit_at')
        elif outcome == SignalOutcome.TP1_ONLY:
            exit_time = signal.get('tp1_hit_at')
        elif outcome == SignalOutcome.SL2_HIT:
            exit_time = signal.get('sl2_hit_at')
        elif outcome == SignalOutcome.SL1_5_HIT:
            exit_time = signal.get('sl1_5_hit_at')
        elif outcome == SignalOutcome.SL1_HIT:
            exit_time = signal.get('sl1_hit_at')
        
        if not exit_time:
            return None
        
        hold_seconds = exit_time - created_at
        return round(hold_seconds / 3600, 2)
    
    def _calculate_mfe_mae_percent(
        self, 
        signal: Dict
    ) -> Tuple[Optional[float], Optional[float]]:
        """Calculates MFE and MAE as percentages of entry price."""
        entry = signal.get('signal_price')
        mfe_price = signal.get('mfe_price')
        mae_price = signal.get('mae_price')
        direction = signal.get('direction', '').upper()
        
        mfe_pct = None
        mae_pct = None
        
        if entry and mfe_price:
            if direction == 'LONG':
                mfe_pct = ((mfe_price - entry) / entry) * 100
            else:
                mfe_pct = ((entry - mfe_price) / entry) * 100
        
        if entry and mae_price:
            if direction == 'LONG':
                mae_pct = ((mae_price - entry) / entry) * 100
            else:
                mae_pct = ((entry - mae_price) / entry) * 100
        
        return (
            round(mfe_pct, 2) if mfe_pct else None,
            round(mae_pct, 2) if mae_pct else None
        )
    
    def _calculate_metrics(self) -> PerformanceMetrics:
        """Calculates overall performance metrics."""
        total = len(self.signal_stats)
        
        # Count outcomes
        tp3_count = sum(1 for s in self.signal_stats if s.outcome == SignalOutcome.TP3_REACHED)
        tp2_count = sum(1 for s in self.signal_stats if s.outcome == SignalOutcome.TP2_REACHED)
        tp1_count = sum(1 for s in self.signal_stats if s.outcome == SignalOutcome.TP1_ONLY)
        sl1_count = sum(1 for s in self.signal_stats if s.outcome == SignalOutcome.SL1_HIT)
        sl1_5_count = sum(1 for s in self.signal_stats if s.outcome == SignalOutcome.SL1_5_HIT)
        sl2_count = sum(1 for s in self.signal_stats if s.outcome == SignalOutcome.SL2_HIT)
        open_count = sum(1 for s in self.signal_stats if s.outcome == SignalOutcome.OPEN)
        expired_count = sum(1 for s in self.signal_stats if s.outcome == SignalOutcome.EXPIRED_NO_HIT)
        
        # Closed signals (exclude OPEN)
        closed_count = total - open_count
        wins = tp1_count + tp2_count + tp3_count
        losses = sl1_count + sl1_5_count + sl2_count
        
        # Win rates
        win_rate = (wins / closed_count * 100) if closed_count > 0 else 0.0
        tp1_hit_rate = (tp1_count / total * 100) if total > 0 else 0.0
        tp2_hit_rate = (tp2_count / total * 100) if total > 0 else 0.0
        tp3_hit_rate = (tp3_count / total * 100) if total > 0 else 0.0
        sl_hit_rate = (losses / closed_count * 100) if closed_count > 0 else 0.0
        
        # R-multiples
        r_multiples = [s.r_multiple for s in self.signal_stats if s.r_multiple is not None]
        win_r = [r for r in r_multiples if r > 0]
        loss_r = [r for r in r_multiples if r < 0]
        
        avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else 0.0
        avg_win_r = sum(win_r) / len(win_r) if win_r else 0.0
        avg_loss_r = sum(loss_r) / len(loss_r) if loss_r else 0.0
        expectancy = avg_r
        
        # Time metrics
        hold_times = [s.hold_time_hours for s in self.signal_stats if s.hold_time_hours is not None]
        avg_hold = sum(hold_times) / len(hold_times) if hold_times else 0.0
        
        tp_times = [s.hold_time_hours for s in self.signal_stats 
                    if s.hold_time_hours and s.outcome in [SignalOutcome.TP1_ONLY, SignalOutcome.TP2_REACHED, SignalOutcome.TP3_REACHED]]
        avg_tp_time = sum(tp_times) / len(tp_times) if tp_times else 0.0
        
        sl_times = [s.hold_time_hours for s in self.signal_stats 
                    if s.hold_time_hours and s.outcome in [SignalOutcome.SL1_HIT, SignalOutcome.SL1_5_HIT, SignalOutcome.SL2_HIT]]
        avg_sl_time = sum(sl_times) / len(sl_times) if sl_times else 0.0
        
        # MFE/MAE
        mfe_values = [s.mfe_percent for s in self.signal_stats if s.mfe_percent is not None]
        mae_values = [s.mae_percent for s in self.signal_stats if s.mae_percent is not None]
        avg_mfe = sum(mfe_values) / len(mfe_values) if mfe_values else 0.0
        avg_mae = sum(mae_values) / len(mae_values) if mae_values else 0.0
        
        return PerformanceMetrics(
            total_signals=total,
            tp3_count=tp3_count,
            tp2_count=tp2_count,
            tp1_count=tp1_count,
            sl1_count=sl1_count,
            sl1_5_count=sl1_5_count,
            sl2_count=sl2_count,
            open_count=open_count,
            expired_count=expired_count,
            win_rate=round(win_rate, 2),
            tp1_hit_rate=round(tp1_hit_rate, 2),
            tp2_hit_rate=round(tp2_hit_rate, 2),
            tp3_hit_rate=round(tp3_hit_rate, 2),
            sl_hit_rate=round(sl_hit_rate, 2),
            avg_r_multiple=round(avg_r, 3),
            avg_win_r=round(avg_win_r, 3),
            avg_loss_r=round(avg_loss_r, 3),
            expectancy=round(expectancy, 3),
            avg_hold_time_hours=round(avg_hold, 2),
            avg_time_to_tp_hours=round(avg_tp_time, 2),
            avg_time_to_sl_hours=round(avg_sl_time, 2),
            avg_mfe_percent=round(avg_mfe, 2),
            avg_mae_percent=round(avg_mae, 2)
        )
    
    def get_signals_by_outcome(self, outcome: SignalOutcome) -> List[SignalStats]:
        """Returns signals with specific outcome."""
        return [s for s in self.signal_stats if s.outcome == outcome]
    
    def get_high_confidence_sl_signals(self, min_confidence: float = 0.8) -> List[SignalStats]:
        """
        Returns high-confidence signals that hit SL.
        Critical for identifying false positives.
        """
        return [s for s in self.signal_stats 
                if s.confidence >= min_confidence 
                and s.outcome in [SignalOutcome.SL1_HIT, SignalOutcome.SL1_5_HIT, SignalOutcome.SL2_HIT]]
