"""
Time Analyzer
-------------
Analyzes time-based patterns in signal performance.
"""
from typing import Dict, List
from datetime import datetime
from collections import defaultdict
from .signal_analyzer import SignalStats, SignalOutcome


class TimeAnalyzer:
    """Analyzes time-based patterns."""
    
    def __init__(self, signal_stats: List[SignalStats]):
        """Initialize time analyzer."""
        self.signal_stats = signal_stats
    
    def analyze(self) -> Dict:
        """Performs time-based analysis."""
        return {
            'hourly': self._analyze_by_hour(),
            'daily': self._analyze_by_day_of_week(),
            'hold_times': self._analyze_hold_times()
        }
    
    def _analyze_by_hour(self) -> Dict:
        """Analyzes performance by hour of day."""
        hourly_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'total': 0})
        
        for sig in self.signal_stats:
            if sig.outcome == SignalOutcome.OPEN:
                continue
            
            hour = datetime.fromtimestamp(sig.created_at).hour
            hourly_stats[hour]['total'] += 1
            
            if sig.outcome in [SignalOutcome.TP1_ONLY, SignalOutcome.TP2_REACHED]:
                hourly_stats[hour]['wins'] += 1
            elif sig.outcome == SignalOutcome.SL_HIT:
                hourly_stats[hour]['losses'] += 1
        
        results = {}
        for hour, stats in hourly_stats.items():
            win_rate = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0.0
            results[hour] = {
                'total': stats['total'],
                'win_rate': round(win_rate, 2)
            }
        
        # Find best and worst hours
        sorted_hours = sorted(results.items(), key=lambda x: x[1]['win_rate'], reverse=True)
        best_hours = sorted_hours[:3] if len(sorted_hours) >= 3 else sorted_hours
        worst_hours = sorted_hours[-3:][::-1] if len(sorted_hours) >= 3 else []
        
        return {
            'hourly_stats': results,
            'best_hours': [(h, s['win_rate']) for h, s in best_hours],
            'worst_hours': [(h, s['win_rate']) for h, s in worst_hours]
        }
    
    def _analyze_by_day_of_week(self) -> Dict:
        """Analyzes performance by day of week."""
        daily_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'total': 0})
        
        for sig in self.signal_stats:
            if sig.outcome == SignalOutcome.OPEN:
                continue
            
            day = datetime.fromtimestamp(sig.created_at).strftime('%A')
            daily_stats[day]['total'] += 1
            
            if sig.outcome in [SignalOutcome.TP1_ONLY, SignalOutcome.TP2_REACHED]:
                daily_stats[day]['wins'] += 1
            elif sig.outcome == SignalOutcome.SL_HIT:
                daily_stats[day]['losses'] += 1
        
        results = {}
        for day, stats in daily_stats.items():
            win_rate = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0.0
            results[day] = {
                'total': stats['total'],
                'win_rate': round(win_rate, 2)
            }
        
        return results
    
    def _analyze_hold_times(self) -> Dict:
        """Analyzes hold time distributions."""
        tp_times = [s.hold_time_hours for s in self.signal_stats 
                   if s.hold_time_hours and s.outcome in [SignalOutcome.TP1_ONLY, SignalOutcome.TP2_REACHED]]
        sl_times = [s.hold_time_hours for s in self.signal_stats 
                   if s.hold_time_hours and s.outcome == SignalOutcome.SL_HIT]
        
        return {
            'avg_tp_time': round(sum(tp_times) / len(tp_times), 2) if tp_times else 0.0,
            'avg_sl_time': round(sum(sl_times) / len(sl_times), 2) if sl_times else 0.0,
            'min_tp_time': round(min(tp_times), 2) if tp_times else 0.0,
            'max_tp_time': round(max(tp_times), 2) if tp_times else 0.0,
            'min_sl_time': round(min(sl_times), 2) if sl_times else 0.0,
            'max_sl_time': round(max(sl_times), 2) if sl_times else 0.0
        }
