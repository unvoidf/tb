#!/usr/bin/env python3
"""
Log Analyzer Tool - Analyzes TrendBot logs for signal generation patterns

Usage:
    python tools/loganalyzer.py                    # Analyze all logs
    python tools/loganalyzer.py --last-hours 24    # Last 24 hours
    python tools/loganalyzer.py --verbose          # Detailed output
"""

import re
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import Dict, List, Optional, Tuple
import argparse


class LogAnalyzer:
    """Analyzes TrendBot logs for signal patterns and outcomes."""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.stats = {
            'scans': 0,
            'signals_generated': 0,
            'signals_rejected': 0,
            'rejection_reasons': Counter(),
            'accepted_signals': [],
            'rejected_signals': [],
            'scan_summaries': []
        }
        
        # Advanced Analytics
        self.market_pulse = {'LONG': 0, 'SHORT': 0, 'NEUTRAL': 0}
        self.near_misses = []  # Signals with score > threshold - 0.05
        self.indicator_stats = defaultdict(list)  # RSI, ADX, Vol stats per direction
        
        # Track last seen signal info per symbol to fill in gaps
        self.last_seen_signal = {}
        
    def parse_timestamp(self, line: str) -> Optional[datetime]:
        """Extract timestamp from log line."""
        match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        if match:
            try:
                return datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
            except ValueError as e:
                # Invalid datetime format
                return None
        return None
    
    def analyze_logs(self, last_hours: Optional[int] = None) -> Dict:
        """
        Analyze signal scanner logs.
        
        Args:
            last_hours: Only analyze logs from last N hours
            
        Returns:
            Statistics dictionary
        """
        scanner_log = self.log_dir / "signal_scanner.log"
        
        if not scanner_log.exists():
            print(f"❌ Log file not found: {scanner_log}")
            return self.stats
        
        cutoff_time = None
        if last_hours:
            cutoff_time = datetime.now() - timedelta(hours=last_hours)
        
        with open(scanner_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for i, line in enumerate(lines):
            # Check timestamp filter
            if cutoff_time:
                ts = self.parse_timestamp(line)
                if ts and ts < cutoff_time:
                    continue
            
            # Track signal context (look for "DYM/USDT sinyal: direction=LONG")
            # This helps fill in "UNKNOWN" for older logs
            context_match = re.search(r'([A-Z0-9]+/USDT) sinyal: direction=(LONG|SHORT|NEUTRAL)', line)
            if context_match:
                symbol = context_match.group(1)
                direction = context_match.group(2)
                # Also try to get score
                score_match = re.search(r'total_score=(\d+\.\d+)', line)
                score = float(score_match.group(1)) if score_match else 0.0
                
                self.last_seen_signal[symbol] = {
                    'direction': direction,
                    'score': score,
                    'timestamp': self.parse_timestamp(line)
                }
                
                # Market Pulse Update
                self.market_pulse[direction] += 1

            # Scan summary detection
            if 'TARAMA ÖZETİ' in line or '📊 SCAN SUMMARY' in line:
                self._parse_scan_summary(lines, i)
            
            # Signal generation (Summary count)
            elif 'Sinyal Üretildi' in line and '✅' in line:
                # This is handled in _parse_scan_summary, don't double count
                pass
            
            # Accepted Signal (Individual log)
            elif 'sinyal bildirimi gönderildi' in line:
                self.stats['signals_generated'] += 1
                self._extract_signal_info(line, accepted=True)
            
            # Rejection patterns
            elif 'rejected:' in line:
                self.stats['signals_rejected'] += 1
                self._extract_rejection_info(line)
            
            # Rejection Details (RSI, ADX, Vol extraction)
            elif 'rejection details:' in line:
                self._extract_indicator_stats(line)
            
            # Specific rejection reasons
            elif 'ATR too low' in line:
                self._extract_rejection_info(line, reason='low_atr')
            
            elif 'Düşük ATR' in line:
                # From scan summary
                pass
            
            # Direction-specific threshold logged
            elif 'Direction-Specific Thresholds' in line:
                pass  # Just acknowledgment
        
        return self.stats
    
    def _parse_scan_summary(self, lines: List[str], start_idx: int):
        """Parse scan summary section from logs."""
        self.stats['scans'] += 1
        summary = {'timestamp': self.parse_timestamp(lines[start_idx])}
        
        # Look ahead for summary details
        for i in range(start_idx, min(start_idx + 15, len(lines))):
            line = lines[i]
            
            # Generated signals
            if 'Sinyal Üretildi' in line or 'Generated' in line:
                match = re.search(r':?\s*(\d+)', line)
                if match:
                    summary['generated'] = int(match.group(1))
            
            # Rejection reasons
            if 'Risk/Reward' in line or 'R/R Yetersiz' in line:
                match = re.search(r':?\s*(\d+)', line)
                if match:
                    self.stats['rejection_reasons']['risk_reward'] += int(match.group(1))
            
            if 'Trend Uyumsuz' in line or 'Trend Mismatch' in line:
                match = re.search(r':?\s*(\d+)', line)
                if match:
                    self.stats['rejection_reasons']['trend_mismatch'] += int(match.group(1))
            
            if 'Confidence Yetersiz' in line or 'Düşük Güven' in line:
                match = re.search(r':?\s*(\d+)', line)
                if match:
                    self.stats['rejection_reasons']['low_confidence'] += int(match.group(1))
            
            if 'BTC' in line and ('Crash' in line or 'Filtresi' in line):
                match = re.search(r':?\s*(\d+)', line)
                if match:
                    self.stats['rejection_reasons']['btc_crash'] += int(match.group(1))
            
            if 'Düşük ATR' in line or 'LowATR' in line:
                match = re.search(r':?\s*(\d+)', line)
                if match:
                    self.stats['rejection_reasons']['low_atr'] += int(match.group(1))
            
            if 'Yüksek Volatilite' in line:
                match = re.search(r':?\s*(\d+)', line)
                if match:
                    self.stats['rejection_reasons']['high_volatility'] += int(match.group(1))
        
        self.stats['scan_summaries'].append(summary)
    
    def _extract_indicator_stats(self, line: str):
        """Extract RSI, ADX, Vol from rejection details log."""
        # Example: rejection details: base=0.660, rsi_bonus=+0.000, vol_bonus=+0.000, RSI=39.0/SHORT, ADX=38.4, vol=0.89x
        try:
            rsi_match = re.search(r'RSI=(\d+\.\d+)', line)
            adx_match = re.search(r'ADX=(\d+\.\d+)', line)
            vol_match = re.search(r'vol=(\d+\.\d+)x', line)
            
            if rsi_match: self.indicator_stats['RSI'].append(float(rsi_match.group(1)))
            if adx_match: self.indicator_stats['ADX'].append(float(adx_match.group(1)))
            if vol_match: self.indicator_stats['VOL'].append(float(vol_match.group(1)))
        except (ValueError, AttributeError) as e:
            # Failed to parse indicator values
            pass

    def _extract_signal_info(self, line: str, accepted: bool = True) -> Optional[Dict]:
        """Extract signal information from log line."""
        # Extract symbol
        symbol_match = re.search(r'([A-Z0-9]+/USDT)', line)
        if not symbol_match:
            symbol_match = re.search(r'([A-Z0-9]+)', line)
        
        symbol = symbol_match.group(1) if symbol_match else 'UNKNOWN'
        
        # Extract direction
        # Try explicit dir= format first (common in new logs)
        direction_match = re.search(r'dir=(LONG|SHORT|NEUTRAL)', line)
        if not direction_match:
            # Fallback to simple search
            direction_match = re.search(r'(LONG|SHORT)', line)
        
        direction = direction_match.group(1) if direction_match else 'UNKNOWN'
        
        # Extract confidence/score
        score_match = re.search(r'score=(\d+\.\d+)', line)
        if not score_match:
            score_match = re.search(r'confidence[=:]?\s*(\d+\.\d+)', line)
        
        score = float(score_match.group(1)) if score_match else 0.0
        
        # If direction is UNKNOWN (old log format), try to find it in context
        if direction == 'UNKNOWN' and symbol in self.last_seen_signal:
            # Check if context is recent (within 1 minute)
            ctx = self.last_seen_signal[symbol]
            current_ts = self.parse_timestamp(line)
            if current_ts and ctx['timestamp'] and abs((current_ts - ctx['timestamp']).total_seconds()) < 60:
                direction = ctx['direction']
                if score == 0.0:
                    score = ctx['score']
        
        signal_info = {
            'symbol': symbol,
            'direction': direction,
            'score': score,
            'timestamp': self.parse_timestamp(line)
        }
        
        if accepted:
            self.stats['accepted_signals'].append(signal_info)
        else:
            self.stats['rejected_signals'].append(signal_info)
            
        return signal_info
    
    def _extract_rejection_info(self, line: str, reason: str = None):
        """Extract rejection information."""
        if not reason:
            # Try to infer reason from line
            if 'atr_too_low' in line or 'ATR too low' in line:
                reason = 'low_atr'
            elif 'regime=' in line:
                # Direction-specific or regime mismatch
                if 'trending_down' in line and 'LONG' in line:
                    reason = 'trend_mismatch'
                elif 'trending_up' in line and 'SHORT' in line:
                    reason = 'trend_mismatch'
                else:
                    reason = 'low_confidence'
            else:
                reason = 'other'
        
        self.stats['rejection_reasons'][reason] += 1
        signal_info = self._extract_signal_info(line, accepted=False)
        
        # Check for Near Miss (Score > 0.85 for LONG, > 0.65 for SHORT)
        if signal_info:
            score = signal_info['score']
            direction = signal_info['direction']
            
            is_near_miss = False
            if direction == 'LONG' and score >= 0.85:
                is_near_miss = True
            elif direction == 'SHORT' and score >= 0.64: # Threshold is 0.69
                is_near_miss = True
            
            if is_near_miss:
                self.near_misses.append(signal_info)
    
    def print_report(self, verbose: bool = False):
        """Print analysis report."""
        print("\n" + "="*60)
        print("📊 TRENDBOT STRATEGY & LOG ANALYSIS")
        print("="*60)
        
        # Overview
        print(f"\n{'📈 OVERVIEW':<40}")
        print("-" * 60)
        print(f"  Total Scans:              {self.stats['scans']}")
        print(f"  Signals Generated:        {self.stats['signals_generated']} ✅")
        print(f"  Signals Rejected:         {self.stats['signals_rejected']} ❌")
        
        total_attempts = self.stats['signals_generated'] + self.stats['signals_rejected']
        if total_attempts > 0:
            acceptance_rate = (self.stats['signals_generated'] / total_attempts) * 100
            print(f"  Acceptance Rate:          {acceptance_rate:.1f}%")
            
        # Market Pulse
        total_pulse = sum(self.market_pulse.values())
        if total_pulse > 0:
            print(f"\n{'🌡️ MARKET PULSE (Analyzed Coins)':<40}")
            print("-" * 60)
            long_pct = (self.market_pulse['LONG'] / total_pulse) * 100
            short_pct = (self.market_pulse['SHORT'] / total_pulse) * 100
            neutral_pct = (self.market_pulse['NEUTRAL'] / total_pulse) * 100
            
            print(f"  LONG Bias:                {long_pct:.1f}%")
            print(f"  SHORT Bias:               {short_pct:.1f}%")
            print(f"  NEUTRAL:                  {neutral_pct:.1f}%")
            
            sentiment = "NEUTRAL"
            if long_pct > 60: sentiment = "BULLISH 🐂"
            elif short_pct > 60: sentiment = "BEARISH 🐻"
            print(f"  Overall Sentiment:        {sentiment}")

        # Rejection Reasons
        if self.stats['rejection_reasons']:
            print(f"\n{'❌ REJECTION ANALYSIS':<40}")
            print("-" * 60)
            
            reason_labels = {
                'low_confidence': '  • Low Confidence',
                'risk_reward': '  • Risk/Reward Insufficient',
                'trend_mismatch': '  • Trend Mismatch',
                'low_atr': '  • Low ATR (<2%)',
                'btc_crash': '  • BTC Crash Filter',
                'high_volatility': '  • High Volatility',
                'other': '  • Other'
            }
            
            total_rejections = sum(self.stats['rejection_reasons'].values())
            for reason, count in self.stats['rejection_reasons'].most_common():
                label = reason_labels.get(reason, f'  • {reason}')
                pct = (count / total_rejections * 100) if total_rejections > 0 else 0
                print(f"{label:<40} {count:>4} ({pct:>5.1f}%)")
        
        # Indicator Stats
        if self.indicator_stats:
            print(f"\n{'📉 REJECTION INDICATORS (Avg)':<40}")
            print("-" * 60)
            avg_rsi = sum(self.indicator_stats['RSI']) / len(self.indicator_stats['RSI']) if self.indicator_stats['RSI'] else 0
            avg_adx = sum(self.indicator_stats['ADX']) / len(self.indicator_stats['ADX']) if self.indicator_stats['ADX'] else 0
            avg_vol = sum(self.indicator_stats['VOL']) / len(self.indicator_stats['VOL']) if self.indicator_stats['VOL'] else 0
            
            print(f"  Avg RSI:                  {avg_rsi:.1f}")
            print(f"  Avg ADX:                  {avg_adx:.1f}")
            print(f"  Avg Vol Ratio:            {avg_vol:.2f}x")

        # Near Misses
        if self.near_misses:
            print(f"\n{'🎯 NEAR MISSES (Close to Threshold)':<40}")
            print("-" * 60)
            for sig in self.near_misses[-5:]:
                ts_str = sig['timestamp'].strftime('%H:%M') if sig['timestamp'] else 'N/A'
                print(f"  {ts_str} | {sig['symbol']:<12} {sig['direction']:<7} @ {sig['score']:.3f}")

        # Accepted Signals
        if self.stats['accepted_signals']:
            print(f"\n{'✅ ACCEPTED SIGNALS':<40}")
            print("-" * 60)
            
            # Group by direction
            long_signals = [s for s in self.stats['accepted_signals'] if s['direction'] == 'LONG']
            short_signals = [s for s in self.stats['accepted_signals'] if s['direction'] == 'SHORT']
            unknown_signals = [s for s in self.stats['accepted_signals'] if s['direction'] == 'UNKNOWN']
            
            print(f"  LONG Signals:             {len(long_signals)}")
            print(f"  SHORT Signals:            {len(short_signals)}")
            if unknown_signals:
                print(f"  UNKNOWN Direction:        {len(unknown_signals)}")
            
            if self.stats['accepted_signals']:
                print(f"\n  Recent Signals:")
                for sig in self.stats['accepted_signals'][-10:]:
                    ts_str = sig['timestamp'].strftime('%H:%M:%S') if sig['timestamp'] else 'N/A'
                    print(f"    {ts_str} | {sig['symbol']:<12} {sig['direction']:<7} @ {sig['score']:.3f}")
        
        # Rejected Signals Details
        if verbose and self.stats['rejected_signals']:
            print(f"\n{'❌ REJECTED SIGNALS (Last 10)':<40}")
            print("-" * 60)
            for sig in self.stats['rejected_signals'][-10:]:
                ts_str = sig['timestamp'].strftime('%H:%M:%S') if sig['timestamp'] else 'N/A'
                print(f"  {ts_str} | {sig['symbol']:<12} {sig['direction']:<5} @ {sig['score']:.3f}")
        
        # Scan History
        if verbose and self.stats['scan_summaries']:
            print(f"\n{'📊 SCAN HISTORY':<40}")
            print("-" * 60)
            for summary in self.stats['scan_summaries'][-5:]:
                ts_str = summary['timestamp'].strftime('%H:%M:%S') if summary.get('timestamp') else 'N/A'
                generated = summary.get('generated', 0)
                print(f"  {ts_str} | Generated: {generated}")
        
        print("\n" + "="*60)
        print("")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Analyze TrendBot logs for signal patterns'
    )
    parser.add_argument(
        '--log-dir',
        default='logs',
        help='Log directory path (default: logs)'
    )
    parser.add_argument(
        '--last-hours',
        type=int,
        help='Only analyze logs from last N hours'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed signal information'
    )
    
    args = parser.parse_args()
    
    analyzer = LogAnalyzer(log_dir=args.log_dir)
    analyzer.analyze_logs(last_hours=args.last_hours)
    analyzer.print_report(verbose=args.verbose)


if __name__ == '__main__':
    main()
