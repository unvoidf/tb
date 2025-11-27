#!/usr/bin/env python3
"""
Signal Performance Analysis Tool

This tool analyzes signal performance from archived parquet files,
correlating results with market conditions.
"""

import pandas as pd
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import json

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class SignalPerformanceAnalyzer:
    """Analyzes signal performance based on market conditions"""
    
    def __init__(self, signals_path: str, snapshots_path: str):
        """
        Initialize the analyzer with data paths
        
        Args:
            signals_path: Path to signals parquet file
            snapshots_path: Path to snapshots parquet file
        """
        self.signals_df = pd.read_parquet(signals_path)
        self.snapshots_df = pd.read_parquet(snapshots_path)
        
        # Convert string columns to appropriate types
        self._convert_data_types()
        
    def _convert_data_types(self):
        """Convert string columns to appropriate numeric/boolean types"""
        # Numeric columns
        numeric_cols = [
            'signal_price', 'confidence', 'atr', 'tp1_price', 'tp2_price',
            'sl_price', 'mfe_price', 'mae_price', 'final_price',
            'tp1_distance_r', 'tp2_distance_r', 'sl_distance_r',
            'optimal_entry_price', 'conservative_entry_price'
        ]
        
        for col in numeric_cols:
            if col in self.signals_df.columns:
                self.signals_df[col] = pd.to_numeric(self.signals_df[col], errors='coerce')
        
        # Boolean columns
        bool_cols = [
            'tp1_hit', 'tp2_hit', 'sl_hit', 'message_deleted',
            'optimal_entry_hit', 'conservative_entry_hit'
        ]
        
        for col in bool_cols:
            if col in self.signals_df.columns:
                self.signals_df[col] = self.signals_df[col].map({'True': True, 'False': False, True: True, False: False})
        
        # Timestamp columns
        timestamp_cols = [
            'created_at', 'tp1_hit_at', 'tp2_hit_at', 'sl_hit_at',
            'mfe_at', 'mae_at', 'optimal_entry_hit_at', 'conservative_entry_hit_at'
        ]
        
        for col in timestamp_cols:
            if col in self.signals_df.columns:
                self.signals_df[col] = pd.to_numeric(self.signals_df[col], errors='coerce')
                
    def get_basic_stats(self) -> Dict[str, Any]:
        """Get basic statistics about the signals"""
        stats = {
            'total_signals': len(self.signals_df),
            'timeframe': self.signals_df['timeframe'].unique().tolist(),
            'symbols': self.signals_df['symbol'].unique().tolist(),
            'directions': self.signals_df['direction'].value_counts().to_dict(),
            'avg_confidence': float(self.signals_df['confidence'].mean())
        }
        return stats
    
    def analyze_outcomes(self) -> Dict[str, Any]:
        """Analyze signal outcomes (TP/SL hits)"""
        outcomes = {
            'tp1_hit_count': int(self.signals_df['tp1_hit'].sum()),
            'tp2_hit_count': int(self.signals_df['tp2_hit'].sum()),
            'sl_hit_count': int(self.signals_df['sl_hit'].sum()),
            'tp1_hit_rate': float(self.signals_df['tp1_hit'].mean() * 100),
            'tp2_hit_rate': float(self.signals_df['tp2_hit'].mean() * 100),
            'sl_hit_rate': float(self.signals_df['sl_hit'].mean() * 100),
        }
        
        # Calculate win rate (TP hit before SL)
        wins = self.signals_df[
            (self.signals_df['tp1_hit'] == True) | 
            (self.signals_df['tp2_hit'] == True)
        ]
        losses = self.signals_df[self.signals_df['sl_hit'] == True]
        
        outcomes['wins'] = len(wins)
        outcomes['losses'] = len(losses)
        outcomes['win_rate'] = float((len(wins) / len(self.signals_df)) * 100) if len(self.signals_df) > 0 else 0
        
        return outcomes
    
    def analyze_by_direction(self) -> Dict[str, Dict[str, Any]]:
        """Analyze performance by signal direction (LONG/SHORT)"""
        results = {}
        
        for direction in self.signals_df['direction'].unique():
            df_dir = self.signals_df[self.signals_df['direction'] == direction]
            
            results[direction] = {
                'count': len(df_dir),
                'avg_confidence': float(df_dir['confidence'].mean()),
                'tp1_hit_rate': float(df_dir['tp1_hit'].mean() * 100),
                'tp2_hit_rate': float(df_dir['tp2_hit'].mean() * 100),
                'sl_hit_rate': float(df_dir['sl_hit'].mean() * 100),
                'win_rate': float((
                    (df_dir['tp1_hit'] | df_dir['tp2_hit']).sum() / len(df_dir)
                ) * 100) if len(df_dir) > 0 else 0
            }
        
        return results
    
    def analyze_by_symbol(self) -> pd.DataFrame:
        """Analyze performance by symbol"""
        symbol_stats = []
        
        for symbol in self.signals_df['symbol'].unique():
            df_sym = self.signals_df[self.signals_df['symbol'] == symbol]
            
            symbol_stats.append({
                'symbol': symbol,
                'count': len(df_sym),
                'direction': df_sym['direction'].iloc[0] if len(df_sym) > 0 else '',
                'avg_confidence': float(df_sym['confidence'].mean()),
                'tp1_hit': df_sym['tp1_hit'].sum(),
                'tp2_hit': df_sym['tp2_hit'].sum(),
                'sl_hit': df_sym['sl_hit'].sum(),
                'win_rate': float((
                    (df_sym['tp1_hit'] | df_sym['tp2_hit']).sum() / len(df_sym)
                ) * 100) if len(df_sym) > 0 else 0
            })
        
        return pd.DataFrame(symbol_stats).sort_values('win_rate', ascending=False)
    
    def analyze_market_context(self) -> Dict[str, Any]:
        """Analyze market context for signals"""
        market_contexts = []
        
        for _, row in self.signals_df.iterrows():
            if pd.notna(row.get('market_context')):
                try:
                    ctx = json.loads(row['market_context']) if isinstance(row['market_context'], str) else row['market_context']
                    market_contexts.append(ctx)
                except (json.JSONDecodeError, TypeError) as e:
                    pass
        
        if not market_contexts:
            return {'message': 'No market context data available'}
        
        # Extract common market condition metrics
        return {
            'total_with_context': len(market_contexts),
            'sample_context': market_contexts[0] if market_contexts else None
        }
    
    def analyze_timing(self) -> Dict[str, Any]:
        """Analyze timing of hits (how long until TP/SL hit)"""
        timing = {}
        
        # Calculate time to TP1
        tp1_signals = self.signals_df[self.signals_df['tp1_hit'] == True].copy()
        if len(tp1_signals) > 0:
            tp1_signals['time_to_tp1'] = tp1_signals['tp1_hit_at'] - tp1_signals['created_at']
            timing['avg_time_to_tp1_seconds'] = float(tp1_signals['time_to_tp1'].mean())
            timing['avg_time_to_tp1_hours'] = float(tp1_signals['time_to_tp1'].mean() / 3600)
        
        # Calculate time to TP2
        tp2_signals = self.signals_df[self.signals_df['tp2_hit'] == True].copy()
        if len(tp2_signals) > 0:
            tp2_signals['time_to_tp2'] = tp2_signals['tp2_hit_at'] - tp2_signals['created_at']
            timing['avg_time_to_tp2_seconds'] = float(tp2_signals['time_to_tp2'].mean())
            timing['avg_time_to_tp2_hours'] = float(tp2_signals['time_to_tp2'].mean() / 3600)
        
        # Calculate time to SL
        sl_signals = self.signals_df[self.signals_df['sl_hit'] == True].copy()
        if len(sl_signals) > 0:
            sl_signals['time_to_sl'] = sl_signals['sl_hit_at'] - sl_signals['created_at']
            timing['avg_time_to_sl_seconds'] = float(sl_signals['time_to_sl'].mean())
            timing['avg_time_to_sl_hours'] = float(sl_signals['time_to_sl'].mean() / 3600)
        
        return timing
    
    def generate_report(self) -> str:
        """Generate comprehensive analysis report"""
        report = []
        report.append("=" * 80)
        report.append("SIGNAL PERFORMANCE ANALYSIS REPORT")
        report.append("=" * 80)
        report.append("")
        
        # Basic Stats
        report.append("📊 BASIC STATISTICS")
        report.append("-" * 80)
        basic_stats = self.get_basic_stats()
        report.append(f"Total Signals:     {basic_stats['total_signals']}")
        report.append(f"Timeframes:        {', '.join(basic_stats['timeframe'])}")
        report.append(f"Avg Confidence:    {basic_stats['avg_confidence']:.2f}%")
        report.append(f"Unique Symbols:    {len(basic_stats['symbols'])}")
        report.append(f"Direction Split:   {basic_stats['directions']}")
        report.append("")
        
        # Outcomes
        report.append("🎯 SIGNAL OUTCOMES")
        report.append("-" * 80)
        outcomes = self.analyze_outcomes()
        report.append(f"Wins:              {outcomes['wins']} signals")
        report.append(f"Losses:            {outcomes['losses']} signals")
        report.append(f"Win Rate:          {outcomes['win_rate']:.2f}%")
        report.append("")
        report.append(f"TP1 Hits:          {outcomes['tp1_hit_count']} ({outcomes['tp1_hit_rate']:.2f}%)")
        report.append(f"TP2 Hits:          {outcomes['tp2_hit_count']} ({outcomes['tp2_hit_rate']:.2f}%)")
        report.append(f"SL Hits:           {outcomes['sl_hit_count']} ({outcomes['sl_hit_rate']:.2f}%)")
        report.append("")
        
        # By Direction
        report.append("📈 PERFORMANCE BY DIRECTION")
        report.append("-" * 80)
        by_direction = self.analyze_by_direction()
        for direction, stats in by_direction.items():
            report.append(f"{direction}:")
            report.append(f"  Count:           {stats['count']}")
            report.append(f"  Avg Confidence:  {stats['avg_confidence']:.2f}%")
            report.append(f"  Win Rate:        {stats['win_rate']:.2f}%")
            report.append(f"  TP1 Rate:        {stats['tp1_hit_rate']:.2f}%")
            report.append(f"  TP2 Rate:        {stats['tp2_hit_rate']:.2f}%")
            report.append(f"  SL Rate:         {stats['sl_hit_rate']:.2f}%")
            report.append("")
        
        # By Symbol
        report.append("💹 PERFORMANCE BY SYMBOL")
        report.append("-" * 80)
        by_symbol = self.analyze_by_symbol()
        for _, row in by_symbol.iterrows():
            report.append(f"{row['symbol']} ({row['direction']}):")
            report.append(f"  Confidence:      {row['avg_confidence']:.2f}%")
            report.append(f"  Win Rate:        {row['win_rate']:.2f}%")
            report.append(f"  TP1/TP2/SL:      {int(row['tp1_hit'])}/{int(row['tp2_hit'])}/{int(row['sl_hit'])}")
            report.append("")
        
        # Timing
        report.append("⏱️  TIMING ANALYSIS")
        report.append("-" * 80)
        timing = self.analyze_timing()
        if 'avg_time_to_tp1_hours' in timing:
            report.append(f"Avg Time to TP1:   {timing['avg_time_to_tp1_hours']:.2f} hours")
        if 'avg_time_to_tp2_hours' in timing:
            report.append(f"Avg Time to TP2:   {timing['avg_time_to_tp2_hours']:.2f} hours")
        if 'avg_time_to_sl_hours' in timing:
            report.append(f"Avg Time to SL:    {timing['avg_time_to_sl_hours']:.2f} hours")
        report.append("")
        
        # Market Context
        report.append("🌍 MARKET CONTEXT")
        report.append("-" * 80)
        market_ctx = self.analyze_market_context()
        if 'sample_context' in market_ctx and market_ctx['sample_context']:
            report.append(f"Signals with Context: {market_ctx['total_with_context']}")
            report.append(f"Sample Context Keys:  {list(market_ctx['sample_context'].keys())}")
        else:
            report.append(market_ctx.get('message', 'No market context available'))
        report.append("")
        
        report.append("=" * 80)
        
        return "\n".join(report)


def main():
    """Main execution function"""
    # Default paths
    signals_path = PROJECT_ROOT / "data" / "archive" / "signals" / "2025-11.parquet"
    snapshots_path = PROJECT_ROOT / "data" / "archive" / "snapshots" / "2025-11.parquet"
    
    # Check if files exist
    if not signals_path.exists():
        print(f"❌ Signals file not found: {signals_path}")
        return
    
    if not snapshots_path.exists():
        print(f"❌ Snapshots file not found: {snapshots_path}")
        return
    
    # Create analyzer and generate report
    analyzer = SignalPerformanceAnalyzer(str(signals_path), str(snapshots_path))
    report = analyzer.generate_report()
    
    print(report)
    
    # Optionally save to file
    output_path = PROJECT_ROOT / "data" / "performance_report.txt"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n📄 Report saved to: {output_path}")


if __name__ == "__main__":
    main()
