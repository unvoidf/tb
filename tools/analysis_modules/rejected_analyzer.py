"""
Rejected Signals Analyzer
--------------------------
Analyzes rejected signals to identify optimization opportunities.
"""
import sqlite3
import json
from typing import Dict, List, Optional
from collections import Counter


class RejectedAnalyzer:
    """Analyzes rejected signals for insights."""
    
    def __init__(self, db_path: str = "data/signals.db"):
        """Initialize rejected signals analyzer."""
        self.db_path = db_path
    
    def analyze(self) -> Dict:
        """Analyzes rejected signals."""
        rejected = self._load_rejected_signals()
        
        if not rejected:
            return {
                'total_rejected': 0,
                'top_reasons': [],
                'rejected_vs_accepted': 0,
                'avg_confidence': 0.0
            }
        
        return {
            'total_rejected': len(rejected),
            'top_reasons': self._analyze_rejection_reasons(rejected),
            'symbol_distribution': self._analyze_rejected_symbols(rejected),
            'direction_distribution': self._analyze_rejected_directions(rejected),
            'avg_confidence': round(sum(r['confidence'] for r in rejected) / len(rejected), 3),
            'confidence_distribution': self._analyze_rejected_confidence(rejected)
        }
    
    def _load_rejected_signals(self) -> List[Dict]:
        """Loads rejected signals from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM rejected_signals ORDER BY created_at DESC")
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception:
            return []
    
    def _analyze_rejection_reasons(self, rejected: List[Dict]) -> List[Dict]:
        """Analyzes most common rejection reasons."""
        reasons = [r['rejection_reason'] for r in rejected if r.get('rejection_reason')]
        reason_counts = Counter(reasons)
        
        total = len(rejected)
        top_reasons = []
        for reason, count in reason_counts.most_common(10):
            top_reasons.append({
                'reason': reason,
                'count': count,
                'percentage': round((count / total) * 100, 2)
            })
        
        return top_reasons
    
    def _analyze_rejected_symbols(self, rejected: List[Dict]) -> Dict:
        """Analyzes rejected symbol distribution."""
        symbols = [r['symbol'] for r in rejected if r.get('symbol')]
        symbol_counts = Counter(symbols)
        
        return {
            'total_symbols': len(symbol_counts),
            'top_rejected': [
                {'symbol': sym, 'count': count} 
                for sym, count in symbol_counts.most_common(10)
            ]
        }
    
    def _analyze_rejected_directions(self, rejected: List[Dict]) -> Dict:
        """Analyzes rejected direction distribution."""
        directions = [r['direction'] for r in rejected if r.get('direction')]
        dir_counts = Counter(directions)
        
        total = len(directions)
        return {
            'LONG': dir_counts.get('LONG', 0),
            'SHORT': dir_counts.get('SHORT', 0),
            'long_percentage': round((dir_counts.get('LONG', 0) / total) * 100, 2) if total > 0 else 0.0,
            'short_percentage': round((dir_counts.get('SHORT', 0) / total) * 100, 2) if total > 0 else 0.0
        }
    
    def _analyze_rejected_confidence(self, rejected: List[Dict]) -> Dict:
        """Analyzes confidence distribution of rejected signals."""
        confidences = sorted([r['confidence'] for r in rejected if r.get('confidence')])
        
        if not confidences:
            return {}
        
        n = len(confidences)
        return {
            'min': round(min(confidences), 3),
            'max': round(max(confidences), 3),
            'median': round(confidences[n // 2], 3),
            'high_confidence_rejected': sum(1 for c in confidences if c >= 0.80)
        }
