#!/usr/bin/env python3
"""
Signal Analysis Tool
--------------------
Comprehensive analysis tool for TrendBot trading signals.
Analyzes performance, identifies patterns, and provides optimization insights.

Usage:
    python tools/analyze_signals.py --mode all
    python tools/analyze_signals.py --mode confidence
    python tools/analyze_signals.py --mode symbols --top-n 5
    python tools/analyze_signals.py --mode all --export json
"""
import sys
from pathlib import Path
from argparse import ArgumentParser, Namespace

# Add project root to path
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

import sqlite3
from typing import List, Dict
from analysis_modules import (
    SignalAnalyzer,
    SymbolAnalyzer,
    DirectionAnalyzer,
    ConfidenceAnalyzer,
    TimeAnalyzer,
    RejectedAnalyzer,
    EntryAnalyzer,
    ReportGenerator
)


class SignalAnalysisTool:
    """Main analysis tool orchestrator."""
    
    def __init__(self, db_path: str = "data/signals.db"):
        """Initialize analysis tool."""
        self.db_path = db_path
        self.signals = []
        self.report_gen = ReportGenerator()
    
    def load_signals(self) -> None:
        """Loads all signals from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM signals ORDER BY created_at ASC")
            rows = cursor.fetchall()
            conn.close()
            
            self.signals = [dict(row) for row in rows]
            
            if not self.signals:
                print("⚠️  No signals found in database!")
                sys.exit(1)
            
            print(f"✅ Loaded {len(self.signals)} signals from database\n")
            
        except Exception as e:
            print(f"❌ Error loading signals: {str(e)}")
            sys.exit(1)
    
    def run_overview_analysis(self) -> None:
        """Runs overall performance analysis."""
        analyzer = SignalAnalyzer(self.signals)
        metrics = analyzer.analyze()
        
        self.report_gen.print_overview_report(metrics)
    
    def run_symbol_analysis(self, top_n: int = 10) -> None:
        """Runs symbol-based analysis."""
        # First run signal analyzer
        signal_analyzer = SignalAnalyzer(self.signals)
        signal_analyzer.analyze()
        
        # Then run symbol analyzer
        symbol_analyzer = SymbolAnalyzer(signal_analyzer.signal_stats)
        symbol_analyzer.analyze()
        
        top = symbol_analyzer.get_top_performers(top_n)
        worst = symbol_analyzer.get_worst_performers(top_n)
        
        self.report_gen.print_symbol_report(top, worst)
    
    def run_direction_analysis(self) -> None:
        """Runs LONG vs SHORT analysis."""
        signal_analyzer = SignalAnalyzer(self.signals)
        signal_analyzer.analyze()
        
        direction_analyzer = DirectionAnalyzer(signal_analyzer.signal_stats)
        results = direction_analyzer.analyze()
        
        self.report_gen.print_direction_report(
            results['long'],
            results['short'],
            results['bias']
        )
    
    def run_confidence_analysis(self) -> None:
        """Runs confidence correlation analysis."""
        signal_analyzer = SignalAnalyzer(self.signals)
        signal_analyzer.analyze()
        
        confidence_analyzer = ConfidenceAnalyzer(signal_analyzer.signal_stats)
        results = confidence_analyzer.analyze()
        
        self.report_gen.print_confidence_report(
            results['confidence_bands'],
            results['correlation'],
            results['optimal_threshold']
        )
        
        # Print false positive patterns
        self.report_gen.print_false_positive_patterns(
            results['false_positive_patterns']
        )
    
    def run_time_analysis(self) -> None:
        """Runs time-based pattern analysis."""
        signal_analyzer = SignalAnalyzer(self.signals)
        signal_analyzer.analyze()
        
        time_analyzer = TimeAnalyzer(signal_analyzer.signal_stats)
        results = time_analyzer.analyze()
        
        print("\n⏰ TIME PATTERN ANALYSIS")
        print(f"\nBest Hours: {results['hourly']['best_hours']}")
        print(f"Worst Hours: {results['hourly']['worst_hours']}")
        print(f"\nAvg Time to TP: {results['hold_times']['avg_tp_time']}h")
        print(f"Avg Time to SL: {results['hold_times']['avg_sl_time']}h")
    
    def run_rejected_analysis(self) -> None:
        """Runs rejected signals analysis."""
        rejected_analyzer = RejectedAnalyzer(self.db_path)
        results = rejected_analyzer.analyze()
        
        print("\n🚫 REJECTED SIGNALS ANALYSIS")
        print(f"\nTotal Rejected: {results['total_rejected']}")
        print(f"Avg Confidence: {results['avg_confidence']}")
        
        if results['top_reasons']:
            print("\nTop Rejection Reasons:")
            for reason in results['top_reasons'][:5]:
                print(f"  • {reason['reason']}: {reason['count']} ({reason['percentage']}%)")
    
    def run_entry_analysis(self) -> None:
        """Runs entry pattern analysis (CRITICAL for false positives)."""
        signal_analyzer = SignalAnalyzer(self.signals)
        signal_analyzer.analyze()
        
        entry_analyzer = EntryAnalyzer(signal_analyzer.signal_stats, self.db_path)
        results = entry_analyzer.analyze()
        
        self.report_gen.print_entry_patterns(
            results['risk_patterns'],
            results['filter_recommendations']
        )
    
    def run_all_analyses(self) -> None:
        """Runs all analyses."""
        self.run_overview_analysis()
        self.run_symbol_analysis()
        self.run_direction_analysis()
        self.run_confidence_analysis()
        self.run_time_analysis()
        self.run_rejected_analysis()
        self.run_entry_analysis()


def _parse_arguments() -> Namespace:
    """Parse command line arguments."""
    parser = ArgumentParser(description='TrendBot Signal Analysis Tool')
    
    parser.add_argument(
        '--db',
        default='data/signals.db',
        help='Database path (default: data/signals.db)'
    )
    
    parser.add_argument(
        '--mode',
        choices=['overview', 'symbols', 'direction', 'confidence', 'time', 'rejected', 'entry', 'all'],
        default='all',
        help='Analysis mode (default: all)'
    )
    
    parser.add_argument(
        '--top-n',
        type=int,
        default=10,
        help='Number of top results to show (default: 10)'
    )
    
    parser.add_argument(
        '--export',
        choices=['json', 'csv'],
        help='Export format (optional)'
    )
    
    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    args = _parse_arguments()
    
    # Initialize tool
    tool = SignalAnalysisTool(args.db)
    
    # Load signals
    tool.load_signals()
    
    # Run analysis based on mode
    if args.mode == 'overview':
        tool.run_overview_analysis()
    elif args.mode == 'symbols':
        tool.run_symbol_analysis(args.top_n)
    elif args.mode == 'direction':
        tool.run_direction_analysis()
    elif args.mode == 'confidence':
        tool.run_confidence_analysis()
    elif args.mode == 'time':
        tool.run_time_analysis()
    elif args.mode == 'rejected':
        tool.run_rejected_analysis()
    elif args.mode == 'entry':
        tool.run_entry_analysis()
    elif args.mode == 'all':
        tool.run_all_analyses()
    
    print("\n")


if __name__ == "__main__":
    main()
