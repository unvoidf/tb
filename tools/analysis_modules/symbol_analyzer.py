"""
Symbol Analyzer
---------------
Analyzes performance by symbol to identify best/worst performers.
"""
from typing import Dict, List
from dataclasses import dataclass
from collections import defaultdict
from .signal_analyzer import SignalStats, SignalOutcome


@dataclass
class SymbolPerformance:
    """Performance metrics for a single symbol."""
    symbol: str
    signal_count: int
    win_rate: float
    avg_r_multiple: float
    avg_confidence: float
    tp1_rate: float
    tp2_rate: float
    sl_rate: float
    long_count: int
    short_count: int


class SymbolAnalyzer:
    """Analyzes signal performance by symbol."""
    
    def __init__(self, signal_stats: List[SignalStats]):
        """
        Initialize symbol analyzer.
        
        Args:
            signal_stats: List of analyzed signals
        """
        self.signal_stats = signal_stats
        self.symbol_performance: List[SymbolPerformance] = []
    
    def analyze(self) -> List[SymbolPerformance]:
        """
        Analyzes performance by symbol.
        
        Returns:
            List of symbol performance metrics
        """
        # Group signals by symbol
        symbol_groups = defaultdict(list)
        for sig in self.signal_stats:
            symbol_groups[sig.symbol].append(sig)
        
        # Calculate metrics for each symbol
        results = []
        for symbol, signals in symbol_groups.items():
            perf = self._calculate_symbol_performance(symbol, signals)
            results.append(perf)
        
        # Sort by R-multiple (best performers first)
        results.sort(key=lambda x: x.avg_r_multiple, reverse=True)
        
        self.symbol_performance = results
        return results
    
    def _calculate_symbol_performance(
        self, 
        symbol: str, 
        signals: List[SignalStats]
    ) -> SymbolPerformance:
        """Calculates performance metrics for a symbol."""
        total = len(signals)
        
        # Filter closed signals
        closed = [s for s in signals if s.outcome != SignalOutcome.OPEN]
        closed_count = len(closed)
        
        # Win/loss counts
        wins = sum(1 for s in closed 
                  if s.outcome in [SignalOutcome.TP1_ONLY, 
                                  SignalOutcome.TP2_REACHED, 
                                  SignalOutcome.TP3_REACHED])
        
        losses = sum(1 for s in closed 
                   if s.outcome == SignalOutcome.SL_HIT)
        
        # Rates
        win_rate = (wins / closed_count * 100) if closed_count > 0 else 0.0
        sl_rate = (losses / closed_count * 100) if closed_count > 0 else 0.0
        
        # TP rates
        tp1_count = sum(1 for s in signals 
                       if s.outcome in [SignalOutcome.TP1_ONLY, 
                                       SignalOutcome.TP2_REACHED, 
                                       SignalOutcome.TP3_REACHED])
        tp2_count = sum(1 for s in signals 
                       if s.outcome in [SignalOutcome.TP2_REACHED, 
                                       SignalOutcome.TP3_REACHED])
        
        tp1_rate = (tp1_count / total * 100) if total > 0 else 0.0
        tp2_rate = (tp2_count / total * 100) if total > 0 else 0.0
        
        # R-multiples
        r_multiples = [s.r_multiple for s in signals if s.r_multiple is not None]
        avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else 0.0
        
        # Confidence
        avg_conf = sum(s.confidence for s in signals) / total
        
        # Direction counts
        long_count = sum(1 for s in signals if s.direction == 'LONG')
        short_count = sum(1 for s in signals if s.direction == 'SHORT')
        
        return SymbolPerformance(
            symbol=symbol,
            signal_count=total,
            win_rate=round(win_rate, 2),
            avg_r_multiple=round(avg_r, 3),
            avg_confidence=round(avg_conf, 3),
            tp1_rate=round(tp1_rate, 2),
            tp2_rate=round(tp2_rate, 2),
            sl_rate=round(sl_rate, 2),
            long_count=long_count,
            short_count=short_count
        )
    
    def get_top_performers(self, n: int = 10) -> List[SymbolPerformance]:
        """Returns top N performing symbols by R-multiple."""
        return self.symbol_performance[:n]
    
    def get_worst_performers(self, n: int = 10) -> List[SymbolPerformance]:
        """Returns worst N performing symbols by R-multiple."""
        return self.symbol_performance[-n:][::-1]
    
    def get_symbols_with_min_signals(self, min_signals: int = 5) -> List[SymbolPerformance]:
        """Returns symbols with at least min_signals for statistical significance."""
        return [p for p in self.symbol_performance if p.signal_count >= min_signals]
