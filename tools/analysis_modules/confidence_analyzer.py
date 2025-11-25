"""
Confidence Analyzer
-------------------
Analyzes correlation between confidence scores and signal outcomes.
CRITICAL: Identifies high-confidence signals that hit SL (false positives).
"""
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from .signal_analyzer import SignalStats, SignalOutcome


@dataclass
class ConfidenceBand:
    """Performance metrics for a confidence range."""
    min_confidence: float
    max_confidence: float
    signal_count: int
    win_rate: float
    avg_r_multiple: float
    tp_rate: float
    sl_rate: float
    false_positive_count: int  # High confidence but SL hit


@dataclass
class FalsePositivePattern:
    """Pattern detected in false positive signals."""
    pattern_name: str
    description: str
    affected_signals: int
    common_symbols: List[str]
    avg_confidence: float
    sl_hit_rate: float  # % of signals with this pattern that hit SL
    suggestion: str


class ConfidenceAnalyzer:
    """Analyzes confidence score correlation with outcomes."""
    
    def __init__(self, signal_stats: List[SignalStats]):
        """
        Initialize confidence analyzer.
        
        Args:
            signal_stats: List of analyzed signals
        """
        self.signal_stats = signal_stats
        self.confidence_bands: List[ConfidenceBand] = []
        self.false_positive_patterns: List[FalsePositivePattern] = []
    
    def analyze(self) -> Dict:
        """
        Performs confidence analysis.
        
        Returns:
            Analysis results dict
        """
        # Analyze by confidence bands
        self.confidence_bands = self._analyze_by_confidence_bands()
        
        # Identify false positive patterns
        self.false_positive_patterns = self._analyze_false_positives()
        
        # Calculate overall correlation
        correlation = self._calculate_correlation()
        
        return {
            'confidence_bands': self.confidence_bands,
            'false_positive_patterns': self.false_positive_patterns,
            'correlation': correlation,
            'optimal_threshold': self._find_optimal_threshold()
        }
    
    def _analyze_by_confidence_bands(self) -> List[ConfidenceBand]:
        """Analyzes performance across confidence bands."""
        bands = [
            (0.70, 0.75),
            (0.75, 0.80),
            (0.80, 0.85),
            (0.85, 0.90),
            (0.90, 0.95),
            (0.95, 1.0)
        ]
        
        results = []
        for min_conf, max_conf in bands:
            band_signals = [s for s in self.signal_stats 
                           if min_conf <= s.confidence < max_conf]
            
            if not band_signals:
                continue
            
            # Calculate metrics
            wins = sum(1 for s in band_signals 
                      if s.outcome in [SignalOutcome.TP1_ONLY, 
                                      SignalOutcome.TP2_REACHED])
            
            losses = sum(1 for s in band_signals 
                        if s.outcome == SignalOutcome.SL_HIT)
            
            closed = len([s for s in band_signals 
                         if s.outcome != SignalOutcome.OPEN])
            
            win_rate = (wins / closed * 100) if closed > 0 else 0.0
            sl_rate = (losses / closed * 100) if closed > 0 else 0.0
            
            # TP rate (any TP hit)
            tp_count = sum(1 for s in band_signals 
                          if s.outcome in [SignalOutcome.TP1_ONLY, 
                                          SignalOutcome.TP2_REACHED])
            tp_rate = (tp_count / len(band_signals) * 100) if band_signals else 0.0
            
            # Average R-multiple
            r_multiples = [s.r_multiple for s in band_signals 
                          if s.r_multiple is not None]
            avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else 0.0
            
            # False positives (high confidence but SL)
            false_positives = sum(1 for s in band_signals 
                                 if s.outcome == SignalOutcome.SL_HIT)
            
            results.append(ConfidenceBand(
                min_confidence=min_conf,
                max_confidence=max_conf,
                signal_count=len(band_signals),
                win_rate=round(win_rate, 2),
                avg_r_multiple=round(avg_r, 3),
                tp_rate=round(tp_rate, 2),
                sl_rate=round(sl_rate, 2),
                false_positive_count=false_positives
            ))
        
        return results
    
    def _analyze_false_positives(
        self, 
        min_confidence: float = 0.80
    ) -> List[FalsePositivePattern]:
        """
        Identifies patterns in high-confidence signals that hit SL.
        This is CRITICAL for system optimization.
        """
        # Get false positives
        false_positives = [s for s in self.signal_stats 
                          if s.confidence >= min_confidence 
                          and s.outcome == SignalOutcome.SL_HIT]
        
        if not false_positives:
            return []
        
        patterns = []
        
        # Pattern 1: Symbol-specific failures
        symbol_failures = self._analyze_symbol_failures(false_positives)
        if symbol_failures:
            patterns.append(symbol_failures)
        
        # Pattern 2: Direction-specific failures
        direction_pattern = self._analyze_direction_failures(false_positives)
        if direction_pattern:
            patterns.append(direction_pattern)
        
        # Pattern 3: Confidence range analysis
        extreme_confidence = self._analyze_extreme_confidence(false_positives)
        if extreme_confidence:
            patterns.append(extreme_confidence)
        
        return patterns
    
    def _analyze_symbol_failures(
        self, 
        false_positives: List[SignalStats]
    ) -> Optional[FalsePositivePattern]:
        """Identifies symbols with high false positive rate."""
        symbol_counts = {}
        for sig in false_positives:
            symbol_counts[sig.symbol] = symbol_counts.get(sig.symbol, 0) + 1
        
        # Find symbols with 2+ failures
        problem_symbols = [sym for sym, count in symbol_counts.items() if count >= 2]
        
        if not problem_symbols:
            return None
        
        total_affected = sum(symbol_counts[sym] for sym in problem_symbols)
        avg_conf = sum(s.confidence for s in false_positives 
                      if s.symbol in problem_symbols) / total_affected
        
        # Calculate SL hit rate for these symbols
        symbol_signals = [s for s in self.signal_stats if s.symbol in problem_symbols]
        symbol_sl_hits = sum(1 for s in symbol_signals 
                            if s.outcome == SignalOutcome.SL_HIT)
        sl_rate = (symbol_sl_hits / len(symbol_signals) * 100) if symbol_signals else 100.0
        
        return FalsePositivePattern(
            pattern_name="Symbol-Specific Failures",
            description=f"{len(problem_symbols)} symbols consistently fail despite high confidence",
            affected_signals=total_affected,
            common_symbols=sorted(problem_symbols, 
                                 key=lambda x: symbol_counts[x], 
                                 reverse=True)[:5],
            avg_confidence=round(avg_conf, 3),
            sl_hit_rate=round(sl_rate, 2),
            suggestion=f"Consider blacklisting or reducing confidence weight for: {', '.join(problem_symbols[:3])}"
        )
    
    def _analyze_direction_failures(
        self, 
        false_positives: List[SignalStats]
    ) -> Optional[FalsePositivePattern]:
        """Identifies if one direction has more false positives."""
        long_fps = [s for s in false_positives if s.direction == 'LONG']
        short_fps = [s for s in false_positives if s.direction == 'SHORT']
        
        # Check if significantly imbalanced
        total = len(false_positives)
        if not total:
            return None
        
        long_pct = (len(long_fps) / total) * 100
        short_pct = (len(short_fps) / total) * 100
        
        # If one direction is >70% of false positives
        if long_pct > 70:
            long_signals = [s for s in self.signal_stats if s.direction == 'LONG']
            long_sl = sum(1 for s in long_signals 
                         if s.outcome == SignalOutcome.SL_HIT)
            sl_rate = (long_sl / len(long_signals) * 100) if long_signals else 100.0
            
            return FalsePositivePattern(
                pattern_name="LONG Bias in False Positives",
                description=f"{long_pct:.1f}% of false positives are LONG signals",
                affected_signals=len(long_fps),
                common_symbols=list(set(s.symbol for s in long_fps[:10])),
                avg_confidence=round(sum(s.confidence for s in long_fps) / len(long_fps), 3),
                sl_hit_rate=round(sl_rate, 2),
                suggestion="LONG signals may need stricter filtering or lower confidence threshold"
            )
        elif short_pct > 70:
            short_signals = [s for s in self.signal_stats if s.direction == 'SHORT']
            short_sl = sum(1 for s in short_signals 
                          if s.outcome == SignalOutcome.SL_HIT)
            sl_rate = (short_sl / len(short_signals) * 100) if short_signals else 100.0
            
            return FalsePositivePattern(
                pattern_name="SHORT Bias in False Positives",
                description=f"{short_pct:.1f}% of false positives are SHORT signals",
                affected_signals=len(short_fps),
                common_symbols=list(set(s.symbol for s in short_fps[:10])),
                avg_confidence=round(sum(s.confidence for s in short_fps) / len(short_fps), 3),
                sl_hit_rate=round(sl_rate, 2),
                suggestion="SHORT signals may need stricter filtering or lower confidence threshold"
            )
        
        return None
    
    def _analyze_extreme_confidence(
        self, 
        false_positives: List[SignalStats]
    ) -> Optional[FalsePositivePattern]:
        """Analyzes if extreme confidence (>0.9) still fails."""
        extreme = [s for s in false_positives if s.confidence >= 0.90]
        
        if not extreme:
            return None
        
        sl_rate = 100.0  # All extreme confidence false positives are SL hits by definition
        
        return FalsePositivePattern(
            pattern_name="Extreme Confidence Failures",
            description=f"{len(extreme)} signals with 90%+ confidence still hit SL",
            affected_signals=len(extreme),
            common_symbols=list(set(s.symbol for s in extreme)),
            avg_confidence=round(sum(s.confidence for s in extreme) / len(extreme), 3),
            sl_hit_rate=sl_rate,
            suggestion="Even extreme confidence is not reliable. Additional filters needed (volume, trend strength, etc.)"
        )
    
    def _calculate_correlation(self) -> float:
        """
        Calculates Pearson correlation between confidence and success.
        Returns value between -1 and 1.
        """
        # Only use closed signals
        closed = [s for s in self.signal_stats if s.outcome != SignalOutcome.OPEN]
        
        if len(closed) < 2:
            return 0.0
        
        # Map outcomes to binary (1 = win, 0 = loss)
        outcomes = []
        confidences = []
        
        for sig in closed:
            if sig.outcome in [SignalOutcome.TP1_ONLY, 
                              SignalOutcome.TP2_REACHED]:
                outcomes.append(1)
            else:
                outcomes.append(0)
            confidences.append(sig.confidence)
        
        # Calculate Pearson correlation
        n = len(outcomes)
        sum_x = sum(confidences)
        sum_y = sum(outcomes)
        sum_xy = sum(c * o for c, o in zip(confidences, outcomes))
        sum_x2 = sum(c ** 2 for c in confidences)
        sum_y2 = sum(o ** 2 for o in outcomes)
        
        numerator = n * sum_xy - sum_x * sum_y
        denominator = ((n * sum_x2 - sum_x ** 2) * (n * sum_y2 - sum_y ** 2)) ** 0.5
        
        if denominator == 0:
            return 0.0
        
        correlation = numerator / denominator
        return round(correlation, 3)
    
    def _find_optimal_threshold(self) -> Dict:
        """Finds optimal confidence threshold to maximize expectancy."""
        thresholds = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
        best_threshold = 0.70
        best_expectancy = -999
        best_win_rate = 0
        
        results = []
        for threshold in thresholds:
            signals = [s for s in self.signal_stats 
                      if s.confidence >= threshold 
                      and s.outcome != SignalOutcome.OPEN]
            
            if not signals:
                continue
            
            wins = sum(1 for s in signals 
                      if s.outcome in [SignalOutcome.TP1_ONLY, 
                                      SignalOutcome.TP2_REACHED])
            
            win_rate = (wins / len(signals) * 100) if signals else 0.0
            
            r_multiples = [s.r_multiple for s in signals if s.r_multiple is not None]
            expectancy = sum(r_multiples) / len(r_multiples) if r_multiples else 0.0
            
            results.append({
                'threshold': threshold,
                'signal_count': len(signals),
                'win_rate': round(win_rate, 2),
                'expectancy': round(expectancy, 3)
            })
            
            if expectancy > best_expectancy:
                best_expectancy = expectancy
                best_threshold = threshold
                best_win_rate = win_rate
        
        return {
            'optimal_threshold': best_threshold,
            'expected_win_rate': round(best_win_rate, 2),
            'expected_r_multiple': round(best_expectancy, 3),
            'all_thresholds': results
        }
