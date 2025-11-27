"""
Entry Analyzer
--------------
Analyzes entry timing and addresses the CRITICAL question:
"How can we prevent high-confidence signals that hit SL first?"

This module provides advanced pattern detection to identify signals
that should be filtered out despite having high confidence scores.
"""
import sqlite3
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from .signal_analyzer import SignalStats, SignalOutcome


@dataclass
class EntryPattern:
    """Entry-related pattern that predicts SL hits."""
    pattern_name: str
    description: str
    signals_affected: int
    sl_hit_rate: float  # % of signals with this pattern that hit SL
    suggested_filter: str


class EntryAnalyzer:
    """Analyzes entry timing and patterns to prevent false positives."""
    
    def __init__(
        self, 
        signal_stats: List[SignalStats], 
        db_path: str = "data/signals.db"
    ):
        """Initialize entry analyzer."""
        self.signal_stats = signal_stats
        self.db_path = db_path
        self.risk_patterns: List[EntryPattern] = []
    
    def analyze(self) -> Dict:
        """
        Analyzes entry patterns to identify red flags.
        
        Returns:
            Analysis results with actionable filters
        """
        # Load full signal data for advanced analysis
        full_signals = self._load_full_signal_data()
        
        # Identify risk patterns
        self.risk_patterns = self._identify_risk_patterns(full_signals)
        
        # Analyze alternative entries
        entry_analysis = self._analyze_alternative_entries(full_signals)
        
        # Generate filtering recommendations
        recommendations = self._generate_filter_recommendations()
        
        return {
            'risk_patterns': self.risk_patterns,
            'entry_analysis': entry_analysis,
            'filter_recommendations': recommendations
        }
    
    def _load_full_signal_data(self) -> List[Dict]:
        """Loads complete signal data from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM signals")
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception:
            return []
    
    def _identify_risk_patterns(
        self, 
        full_signals: List[Dict]
    ) -> List[EntryPattern]:
        """
        Identifies patterns that correlate with SL hits.
        This is the CORE function for answering the user's question.
        """
        patterns = []
        
        # Pattern 1: MAE exceeds certain threshold before TP
        mae_pattern = self._analyze_mae_pattern(full_signals)
        if mae_pattern:
            patterns.append(mae_pattern)
        
        # Pattern 2: Confidence-ATR mismatch
        atr_pattern = self._analyze_atr_confidence_mismatch(full_signals)
        if atr_pattern:
            patterns.append(atr_pattern)
        
        # Pattern 3: Rapid SL hits (< 1 hour)
        rapid_sl_pattern = self._analyze_rapid_sl_hits(full_signals)
        if rapid_sl_pattern:
            patterns.append(rapid_sl_pattern)
        
        # Pattern 4: Signal log frequency (repeated signals in same direction)
        signal_log_pattern = self._analyze_signal_repetition(full_signals)
        if signal_log_pattern:
            patterns.append(signal_log_pattern)
        
        return patterns
    
    def _analyze_mae_pattern(self, signals: List[Dict]) -> Optional[EntryPattern]:
        """
        Analyzes Maximum Adverse Excursion patterns.
        If MAE is too large before TP, it's a red flag.
        """
        high_conf_signals = [
            s for s in signals 
            if s.get('confidence', 0) >= 0.80 
            and s.get('mae_price') 
            and s.get('signal_price')
        ]
        
        if not high_conf_signals:
            return None
        
        # Calculate MAE percentage for each
        sl_hits_with_large_mae = []
        for sig in high_conf_signals:
            direction = sig.get('direction', '').upper()
            entry = sig['signal_price']
            mae = sig['mae_price']
            
            # Calculate MAE %
            if direction == 'LONG':
                mae_pct = ((mae - entry) / entry) * 100
            else:
                mae_pct = ((entry - mae) / entry) * 100
            
            # If MAE is < -2% (went significantly against us)
            if mae_pct < -2.0:
                # Check if it eventually hit SL
                sl_hit = sig.get('sl_hit')
                if sl_hit:
                    sl_hits_with_large_mae.append(sig)
        
        if not sl_hits_with_large_mae:
            return None
        
        sl_rate = (len(sl_hits_with_large_mae) / len(high_conf_signals)) * 100
        
        if sl_rate > 30:  # If >30% of high-conf signals with large MAE hit SL
            return EntryPattern(
                pattern_name="Large MAE Before Target",
                description=f"Signals with >2% adverse movement often hit SL ({len(sl_hits_with_large_mae)} signals)",
                signals_affected=len(sl_hits_with_large_mae),
                sl_hit_rate=round(sl_rate, 2),
                suggested_filter="Add early exit rule: If MAE exceeds 2% within first hour, close or reduce position"
            )
        
        return None
    
    def _analyze_atr_confidence_mismatch(
        self, 
        signals: List[Dict]
    ) -> Optional[EntryPattern]:
        """
        Checks if high confidence with low ATR leads to SL.
        Low ATR might indicate ranging market (risky for trend signals).
        """
        high_conf_low_atr = [
            s for s in signals
            if s.get('confidence', 0) >= 0.85
            and s.get('atr')
            and s.get('signal_price')
            and (s['atr'] / s['signal_price']) < 0.02  # ATR < 2% of price
        ]
        
        if len(high_conf_low_atr) < 5:  # Need statistical significance
            return None
        
        sl_hits = sum(1 for s in high_conf_low_atr 
                     if s.get('sl_hit'))
        
        sl_rate = (sl_hits / len(high_conf_low_atr)) * 100
        
        if sl_rate > 50:  # If >50% fail
            return EntryPattern(
                pattern_name="High Confidence + Low ATR",
                description=f"Low volatility (ATR <2%) with high confidence is deceptive ({sl_hits}/{len(high_conf_low_atr)} failed)",
                signals_affected=sl_hits,
                sl_hit_rate=round(sl_rate, 2),
                suggested_filter="Require ATR > 2% of price OR add volatility confirmation filter"
            )
        
        return None
    
    def _analyze_rapid_sl_hits(
        self, 
        signals: List[Dict]
    ) -> Optional[EntryPattern]:
        """
        Identifies signals that hit SL very quickly (<1 hour).
        These might be false breakouts or bad entries.
        """
        high_conf_signals = [
            s for s in signals
            if s.get('confidence', 0) >= 0.80
            and s.get('created_at')
        ]
        
        rapid_sl_signals = []
        for sig in high_conf_signals:
            # Check if SL was hit
            sl_hit_time = sig.get('sl_hit_at')
            
            if sl_hit_time and sig.get('created_at'):
                time_to_sl_hours = (sl_hit_time - sig['created_at']) / 3600
                
                if time_to_sl_hours < 1.0:  # SL hit in less than 1 hour
                    rapid_sl_signals.append(sig)
        
        if len(rapid_sl_signals) < 3:
            return None
        
        return EntryPattern(
            pattern_name="Rapid SL Hits (<1 hour)",
            description=f"{len(rapid_sl_signals)} high-confidence signals hit SL within 1 hour",
            signals_affected=len(rapid_sl_signals),
            sl_hit_rate=100.0,  # All of these are SL hits by definition
            suggested_filter="Add price action confirmation: Wait 15-30 minutes after signal before entry to avoid false breakouts"
        )
    
    def _analyze_signal_repetition(
        self, 
        signals: List[Dict]
    ) -> Optional[EntryPattern]:
        """
        Checks if repeated signals in same direction (via signal_log) correlate with SL.
        Sometimes system keeps generating signals against a strong counter-trend.
        """
        import json
        
        signals_with_log = [
            s for s in signals
            if s.get('signal_log')
            and s.get('confidence', 0) >= 0.80
        ]
        
        repeated_signals_sl = []
        for sig in signals_with_log:
            try:
                log_data = json.loads(sig['signal_log']) if isinstance(sig['signal_log'], str) else sig['signal_log']
                
                if isinstance(log_data, list) and len(log_data) >= 2:  # At least 2 logged events
                    # Check if this signal hit SL
                    if sig.get('sl_hit'):
                        repeated_signals_sl.append(sig)
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                continue
        
        if len(repeated_signals_sl) < 3:
            return None
        
        sl_rate = (len(repeated_signals_sl) / len(signals_with_log)) * 100 if signals_with_log else 0.0
        
        if sl_rate > 40:
            return EntryPattern(
                pattern_name="Repeated Signal Failures",
                description=f"Signals with multiple re-triggers often fail ({len(repeated_signals_sl)} signals)",
                signals_affected=len(repeated_signals_sl),
                sl_hit_rate=round(sl_rate, 2),
                suggested_filter="If signal re-triggers multiple times (signal_log >2 entries), skip or reduce confidence"
            )
        
        return None
    
    def _analyze_alternative_entries(self, signals: List[Dict]) -> Dict:
        """Analyzes if alternative entries would have been better."""
        optimal_filled = sum(1 for s in signals if s.get('optimal_entry_hit'))
        conservative_filled = sum(1 for s in signals if s.get('conservative_entry_hit'))
        signal_price_entries = len(signals)
        
        return {
            'signal_price_entries': signal_price_entries,
            'optimal_entry_hit_count': optimal_filled,
            'conservative_entry_hit_count': conservative_filled,
            'optimal_fill_rate': round((optimal_filled / signal_price_entries) * 100, 2) if signal_price_entries > 0 else 0.0,
            'conservative_fill_rate': round((conservative_filled / signal_price_entries) * 100, 2) if signal_price_entries > 0 else 0.0
        }
    
    def _generate_filter_recommendations(self) -> List[Dict]:
        """
        Generates actionable filtering recommendations.
        This directly answers: "What can we do to prevent high-conf SL signals?"
        """
        recommendations = []
        
        # High-confidence threshold
        high_conf_sl = [
            s for s in self.signal_stats
            if s.confidence >= 0.85
                and s.outcome == SignalOutcome.SL_HIT
        ]
        
        if high_conf_sl:
            recommendations.append({
                'priority': 'HIGH',
                'title': 'High Confidence is NOT Enough',
                'details': f"{len(high_conf_sl)} signals with 85%+ confidence still hit SL",
                'action': 'Add secondary filters: ATR threshold, volume confirmation, trend alignment'
            })
        
        # Add pattern-based recommendations
        for pattern in self.risk_patterns:
            recommendations.append({
                'priority': 'HIGH' if pattern.sl_hit_rate > 60 else 'MEDIUM',
                'title': pattern.pattern_name,
                'details': pattern.description,
                'action': pattern.suggested_filter
            })
        
        # If no patterns found but still have SL hits
        if not self.risk_patterns and high_conf_sl:
            recommendations.append({
                'priority': 'MEDIUM',
                'title': 'Need More Data Points',
                'details': 'Not enough signals to detect clear patterns yet',
                'action': 'Continue collecting data. Consider adding: MFE/MAE tracking, market regime classification'
            })
        
        return recommendations
