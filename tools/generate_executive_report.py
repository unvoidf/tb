#!/usr/bin/env python3
"""
Executive Trading Signal Performance Report Generator

Generates comprehensive, non-technical reports for financial experts
to evaluate trading signal system performance.

Usage:
    python3 tools/generate_executive_report.py
    
Output:
    reports/executive_report_YYYYMMDD_HHMMSS.md
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Any
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class ExecutiveReportGenerator:
    """Generates executive-level trading performance reports"""
    
    def __init__(self, archive_path: Path):
        """
        Initialize report generator
        
        Args:
            archive_path: Path to data/archive directory
        """
        self.archive_path = archive_path
        self.signals_data = []
        self.snapshots_data = []
        self.report_lines = []
        
    def load_all_parquet_files(self):
        """Load all parquet files from archive directory"""
        signals_dir = self.archive_path / "signals"
        snapshots_dir = self.archive_path / "snapshots"
        
        # Load signals
        if signals_dir.exists():
            for parquet_file in signals_dir.glob("*.parquet"):
                df = pd.read_parquet(parquet_file)
                self.signals_data.append({
                    'file': parquet_file.name,
                    'data': df
                })
        
        # Load snapshots
        if snapshots_dir.exists():
            for parquet_file in snapshots_dir.glob("*.parquet"):
                df = pd.read_parquet(parquet_file)
                self.snapshots_data.append({
                    'file': parquet_file.name,
                    'data': df
                })
    
    def prepare_signals_dataframe(self) -> pd.DataFrame:
        """Combine and prepare all signals data"""
        if not self.signals_data:
            return pd.DataFrame()
        
        # Combine all signals
        all_dfs = [item['data'] for item in self.signals_data]
        df = pd.concat(all_dfs, ignore_index=True)
        
        # Convert boolean columns (stored as '0'/'1' strings)
        bool_cols = ['tp1_hit', 'tp2_hit', 'sl_hit', 'message_deleted',
                     'optimal_entry_hit', 'conservative_entry_hit']
        for col in bool_cols:
            if col in df.columns:
                df[col] = df[col].map({'0': False, '1': True, 0: False, 1: True, 
                                       'False': False, 'True': True})
        
        # Convert numeric columns
        numeric_cols = ['signal_price', 'confidence', 'atr', 'tp1_price', 'tp2_price',
                       'sl_price', 'mfe_price', 'mae_price', 'final_price',
                       'tp1_distance_r', 'tp2_distance_r', 'sl_distance_r']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Convert timestamps
        timestamp_cols = ['created_at', 'tp1_hit_at', 'tp2_hit_at', 'sl_hit_at',
                         'mfe_at', 'mae_at']
        for col in timestamp_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    
    def calculate_metrics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate key performance metrics"""
        total_signals = len(df)
        
        if total_signals == 0:
            return {}
        
        # Outcome counts
        tp1_hits = df['tp1_hit'].sum()
        tp2_hits = df['tp2_hit'].sum()
        sl_hits = df['sl_hit'].sum()
        active = total_signals - tp1_hits - sl_hits
        
        # Win/Loss rates
        win_rate = (tp1_hits / total_signals * 100) if total_signals > 0 else 0
        loss_rate = (sl_hits / total_signals * 100) if total_signals > 0 else 0
        
        # Direction split
        direction_counts = df['direction'].value_counts().to_dict()
        
        # Confidence stats
        avg_confidence = df['confidence'].mean()
        
        # Timing analysis
        timing = {}
        winners = df[df['tp1_hit'] == True]
        losers = df[df['sl_hit'] == True]
        
        if len(winners) > 0:
            time_to_tp1 = (winners['tp1_hit_at'] - winners['created_at']) / 3600
            timing['avg_hours_to_win'] = time_to_tp1.mean()
            timing['median_hours_to_win'] = time_to_tp1.median()
        
        if len(losers) > 0:
            time_to_sl = (losers['sl_hit_at'] - losers['created_at']) / 3600
            timing['avg_hours_to_loss'] = time_to_sl.mean()
            timing['median_hours_to_loss'] = time_to_sl.median()
        
        # Market context analysis
        market_analysis = self.analyze_market_context(df)
        
        return {
            'total_signals': total_signals,
            'tp1_hits': int(tp1_hits),
            'tp2_hits': int(tp2_hits),
            'sl_hits': int(sl_hits),
            'active': int(active),
            'win_rate': win_rate,
            'loss_rate': loss_rate,
            'direction_counts': direction_counts,
            'avg_confidence': avg_confidence,
            'timing': timing,
            'market_analysis': market_analysis,
            'winners_df': winners,
            'losers_df': losers
        }
    
    def analyze_market_context(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze market conditions for winners vs losers"""
        contexts = []
        
        for _, row in df.iterrows():
            if pd.notna(row.get('market_context')):
                try:
                    ctx = json.loads(row['market_context']) if isinstance(row['market_context'], str) else row['market_context']
                    ctx['outcome'] = 'win' if row['tp1_hit'] else ('loss' if row['sl_hit'] else 'active')
                    ctx['symbol'] = row['symbol']
                    contexts.append(ctx)
                except (json.JSONDecodeError, TypeError, KeyError) as e:
                    # Skip malformed context data
                    pass
        
        if not contexts:
            return {}
        
        ctx_df = pd.DataFrame(contexts)
        
        # Separate winners and losers
        winners = ctx_df[ctx_df['outcome'] == 'win']
        losers = ctx_df[ctx_df['outcome'] == 'loss']
        
        analysis = {}
        
        if len(winners) > 0:
            analysis['winners'] = {
                'regime': winners['regime'].value_counts().to_dict() if 'regime' in winners.columns else {},
                'ema_trend': winners['ema_trend'].value_counts().to_dict() if 'ema_trend' in winners.columns else {},
                'avg_adx': pd.to_numeric(winners['adx_strength'], errors='coerce').mean() if 'adx_strength' in winners.columns else None,
                'avg_volatility': pd.to_numeric(winners['volatility_percentile'], errors='coerce').mean() if 'volatility_percentile' in winners.columns else None,
                'avg_24h_change': pd.to_numeric(winners['price_change_24h_pct'], errors='coerce').mean() if 'price_change_24h_pct' in winners.columns else None,
            }
        
        if len(losers) > 0:
            analysis['losers'] = {
                'regime': losers['regime'].value_counts().to_dict() if 'regime' in losers.columns else {},
                'ema_trend': losers['ema_trend'].value_counts().to_dict() if 'ema_trend' in losers.columns else {},
                'avg_adx': pd.to_numeric(losers['adx_strength'], errors='coerce').mean() if 'adx_strength' in losers.columns else None,
                'avg_volatility': pd.to_numeric(losers['volatility_percentile'], errors='coerce').mean() if 'volatility_percentile' in losers.columns else None,
                'avg_24h_change': pd.to_numeric(losers['price_change_24h_pct'], errors='coerce').mean() if 'price_change_24h_pct' in losers.columns else None,
            }
        
        return analysis
    
    def generate_report(self) -> str:
        """Generate complete executive report in markdown format"""
        self.load_all_parquet_files()
        df = self.prepare_signals_dataframe()
        
        if df.empty:
            return "# Executive Report\n\nNo signal data found in archive."
        
        metrics = self.calculate_metrics(df)
        
        # Generate report sections
        self.report_lines = []
        self._add_header(metrics)
        self._add_executive_summary(metrics, df)
        self._add_performance_metrics(metrics)
        self._add_market_conditions_analysis(metrics)
        self._add_winners_losers_breakdown(metrics, df)
        self._add_risk_analysis(metrics, df)
        self._add_timing_analysis(metrics)
        self._add_recommendations(metrics)
        self._add_code_level_insights(metrics, df)
        self._add_footer()
        
        return '\n'.join(self.report_lines)
    
    def _add_header(self, metrics: Dict):
        """Add report header"""
        now = datetime.now()
        self.report_lines.extend([
            "# AI Code Optimization Report",
            "",
            "> **Purpose**: Analyze trading bot performance data to guide GitHub code modifications",
            "> **Audience**: AI analyzing TrendBot codebase for optimization",
            "> **Repository**: https://github.com/[your-repo]/trendbot",
            "",
            f"**Generated**: {now.strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**Dataset**: {metrics.get('total_signals', 0)} signals from archive  ",
            "",
            "---",
            ""
        ])
    
    def _add_executive_summary(self, metrics: Dict, df: pd.DataFrame):
        """Add AI-focused executive summary"""
        win_rate = metrics['win_rate']
        loss_rate = metrics['loss_rate']
        total = metrics['total_signals']
        
        self.report_lines.extend([
            "## Performance Metrics",
            "",
            "```json",
            "{",
            f'  "total_signals": {total},',
            f'  "win_rate": {win_rate:.2f},',
            f'  "loss_rate": {loss_rate:.2f},',
            f'  "tp1_hits": {metrics["tp1_hits"]},',
            f'  "sl_hits": {metrics["sl_hits"]},',
            f'  "active": {metrics["active"]},',
            f'  "direction_split": {json.dumps(metrics["direction_counts"])},',
            f'  "avg_confidence": {metrics["avg_confidence"]:.4f}',
            "}",
            "```",
            "",
            "## Critical Issues",
            ""
        ])
        
        # List critical issues for AI to investigate
        issues = []
        if win_rate < 40:
            issues.append(f"- **CRITICAL**: Win rate {win_rate:.1f}% below minimum threshold (40%)")
        if loss_rate > 60:
            issues.append(f"- **CRITICAL**: Loss rate {loss_rate:.1f}% exceeds maximum threshold (60%)")
        
        # Market context issues
        market_analysis = metrics.get('market_analysis', {})
        losers = market_analysis.get('losers', {})
        winners = market_analysis.get('winners', {})
        
        if losers.get('avg_24h_change') and winners.get('avg_24h_change'):
            diff = abs(winners['avg_24h_change'] - losers['avg_24h_change'])
            if diff > 5:
                issues.append(f"- **PATTERN**: 24h price change divergence: winners {winners['avg_24h_change']:.2f}% vs losers {losers['avg_24h_change']:.2f}%")
        
        if not issues:
            issues.append("- No critical issues detected")
        
        self.report_lines.extend(issues)
        self.report_lines.extend(["", "---", ""])
    
    def _add_performance_metrics(self, metrics: Dict):
        """Add detailed performance metrics"""
        self.report_lines.extend([
            "## 📈 Performance Breakdown",
            "",
            "### Signal Outcomes",
            ""
        ])
        
        total = metrics['total_signals']
        tp1 = metrics['tp1_hits']
        tp2 = metrics['tp2_hits']
        sl = metrics['sl_hits']
        active = metrics['active']
        
        # Outcome distribution
        self.report_lines.extend([
            "| Outcome | Count | Percentage | Visualization |",
            "|---------|-------|------------|---------------|",
            f"| ✅ Take Profit 1 Hit | {tp1} | {tp1/total*100:.1f}% | {'█' * int(tp1/total*20)} |",
            f"| ✅ Take Profit 2 Hit | {tp2} | {tp2/total*100:.1f}% | {'█' * int(tp2/total*20)} |",
            f"| ❌ Stop Loss Hit | {sl} | {sl/total*100:.1f}% | {'█' * int(sl/total*20)} |",
            f"| ⏳ Active (Pending) | {active} | {active/total*100:.1f}% | {'█' * int(active/total*20)} |",
            "",
        ])
        
        # Direction analysis
        self.report_lines.extend([
            "### Position Direction Split",
            ""
        ])
        
        for direction, count in metrics['direction_counts'].items():
            pct = count / total * 100
            self.report_lines.append(f"- **{direction}**: {count} signals ({pct:.1f}%)")
        
        self.report_lines.extend(["", "---", ""])
    
    def _add_market_conditions_analysis(self, metrics: Dict):
        """Add market data correlation analysis for AI"""
        market_analysis = metrics.get('market_analysis', {})
        
        if not market_analysis:
            return
        
        self.report_lines.extend([
            "## Data Correlation Analysis",
            "",
            "### Winner vs Loser Characteristics",
            ""
        ])
        
        winners = market_analysis.get('winners', {})
        losers = market_analysis.get('losers', {})
        
        # JSON format for AI parsing
        self.report_lines.extend([
            "```json",
            "{",
            '  "winners": {',
        ])
        
        if winners:
            self.report_lines.extend([
                f'    "regime": {json.dumps(winners.get("regime", {}))},',
                f'    "ema_trend": {json.dumps(winners.get("ema_trend", {}))},',
                f'    "avg_adx": {winners.get("avg_adx", 0):.2f},',
                f'    "avg_volatility_percentile": {winners.get("avg_volatility", 0):.2f},',
                f'    "avg_24h_price_change": {winners.get("avg_24h_change", 0):.2f}',
            ])
        
        self.report_lines.extend([
            '  },',
            '  "losers": {',
        ])
        
        if losers:
            self.report_lines.extend([
                f'    "regime": {json.dumps(losers.get("regime", {}))},',
                f'    "ema_trend": {json.dumps(losers.get("ema_trend", {}))},',
                f'    "avg_adx": {losers.get("avg_adx", 0):.2f},',
                f'    "avg_volatility_percentile": {losers.get("avg_volatility", 0):.2f},',
                f'    "avg_24h_price_change": {losers.get("avg_24h_change", 0):.2f}',
            ])
        
        self.report_lines.extend([
            '  }',
            "}",
            "```",
            "",
            "### Key Divergences",
            ""
        ])
        
        # Calculate and highlight significant divergences
        if winners and losers:
            divergences = []
            
            # 24h change
            w_chg = winners.get('avg_24h_change')
            l_chg = losers.get('avg_24h_change')
            if w_chg is not None and l_chg is not None:
                diff = abs(w_chg - l_chg)
                if diff > 5:
                    divergences.append(f"- **24h_price_change**: {diff:.2f}% gap (winners: {w_chg:.2f}%, losers: {l_chg:.2f}%)")
            
            # ADX
            w_adx = winners.get('avg_adx')
            l_adx = losers.get('avg_adx')
            if w_adx and l_adx:
                diff = abs(w_adx - l_adx)
                if diff > 5:
                    divergences.append(f"- **adx_strength**: {diff:.2f} gap (winners: {w_adx:.2f}, losers: {l_adx:.2f})")
            
            # Volatility
            w_vol = winners.get('avg_volatility')
            l_vol = losers.get('avg_volatility')
            if w_vol and l_vol:
                diff = abs(w_vol - l_vol)
                if diff > 10:
                    divergences.append(f"- **volatility**: {diff:.2f} percentile gap (winners: {w_vol:.2f}, losers: {l_vol:.2f})")
            
            if divergences:
                self.report_lines.extend(divergences)
            else:
                self.report_lines.append("- No significant statistical divergences detected")
        
        self.report_lines.extend(["", "---", ""])
    
    def _add_winners_losers_breakdown(self, metrics: Dict, df: pd.DataFrame):
        """Add detailed breakdown of winners and losers"""
        winners = metrics.get('winners_df')
        losers = metrics.get('losers_df')
        
        self.report_lines.extend([
            "## 🎯 Signal Details",
            ""
        ])
        
        # Winners section
        if len(winners) > 0:
            self.report_lines.extend([
                "### ✅ Winning Signals",
                "",
                "| Symbol | Direction | Confidence | Entry Price | Market Regime | 24h Change |",
                "|--------|-----------|------------|-------------|---------------|------------|"
            ])
            
            for _, row in winners.iterrows():
                ctx = {}
                if pd.notna(row.get('market_context')):
                    try:
                        ctx = json.loads(row['market_context']) if isinstance(row['market_context'], str) else row['market_context']
                    except (json.JSONDecodeError, TypeError) as e:
                        pass
                
                regime = ctx.get('regime', 'N/A')
                chg_24h = ctx.get('price_change_24h_pct', 'N/A')
                chg_str = f"{chg_24h:.2f}%" if isinstance(chg_24h, (int, float)) else chg_24h
                
                self.report_lines.append(
                    f"| {row['symbol']} | {row['direction']} | {row['confidence']:.2f}% | "
                    f"${row['signal_price']:.4f} | {regime} | {chg_str} |"
                )
            
            self.report_lines.extend(["", ""])
        
        # Losers section
        if len(losers) > 0:
            self.report_lines.extend([
                "### ❌ Losing Signals",
                "",
                "| Symbol | Direction | Confidence | Entry Price | Market Regime | 24h Change | Max Favorable |",
                "|--------|-----------|------------|-------------|---------------|------------|---------------|"
            ])
            
            for _, row in losers.iterrows():
                ctx = {}
                if pd.notna(row.get('market_context')):
                    try:
                        ctx = json.loads(row['market_context']) if isinstance(row['market_context'], str) else row['market_context']
                    except (json.JSONDecodeError, TypeError) as e:
                        pass
                
                regime = ctx.get('regime', 'N/A')
                chg_24h = ctx.get('price_change_24h_pct', 'N/A')
                chg_str = f"{chg_24h:.2f}%" if isinstance(chg_24h, (int, float)) else chg_24h
                
                # Calculate MFE
                mfe_r = 'N/A'
                if pd.notna(row['mfe_price']) and pd.notna(row['signal_price']) and pd.notna(row['sl_price']):
                    if row['direction'] == 'SHORT':
                        mfe_r = (row['signal_price'] - row['mfe_price']) / (row['sl_price'] - row['signal_price'])
                    else:
                        mfe_r = (row['mfe_price'] - row['signal_price']) / (row['signal_price'] - row['sl_price'])
                    mfe_r = f"{mfe_r:.2f}R"
                
                self.report_lines.append(
                    f"| {row['symbol']} | {row['direction']} | {row['confidence']:.2f}% | "
                    f"${row['signal_price']:.4f} | {regime} | {chg_str} | {mfe_r} |"
                )
            
            self.report_lines.extend(["", ""])
        
        self.report_lines.extend(["---", ""])
    
    def _add_risk_analysis(self, metrics: Dict, df: pd.DataFrame):
        """Add risk analysis section"""
        self.report_lines.extend([
            "## ⚠️ Risk Assessment",
            "",
        ])
        
        win_rate = metrics['win_rate']
        loss_rate = metrics['loss_rate']
        
        # Risk level determination
        if win_rate >= 60:
            risk_level = "🟢 LOW RISK"
            risk_desc = "System demonstrates consistent profitability with acceptable risk parameters."
        elif win_rate >= 40:
            risk_level = "🟡 MODERATE RISK"
            risk_desc = "System shows potential but requires close monitoring and possible optimization."
        else:
            risk_level = "🔴 HIGH RISK"
            risk_desc = "System performance is below acceptable thresholds. Immediate review required before continuing operations."
        
        self.report_lines.extend([
            f"**Risk Level**: {risk_level}",
            "",
            risk_desc,
            "",
            "### Risk Factors",
            ""
        ])
        
        # Identify risk factors
        risks = []
        
        if loss_rate > 60:
            risks.append("- 🚨 **High Loss Rate**: Over 60% of signals hit stop loss")
        
        if metrics['active'] > metrics['total_signals'] * 0.3:
            risks.append(f"- ⚠️ **High Open Position Ratio**: {metrics['active']} active positions ({metrics['active']/metrics['total_signals']*100:.1f}%)")
        
        # Check market context
        market_analysis = metrics.get('market_analysis', {})
        losers = market_analysis.get('losers', {})
        if losers and losers.get('avg_24h_change'):
            if losers['avg_24h_change'] > 0 and 'SHORT' in metrics['direction_counts']:
                risks.append(f"- 🚨 **Counter-Trend Trading**: Shorting in rising markets (avg +{losers['avg_24h_change']:.2f}% price change)")
        
        if not risks:
            risks.append("- ✅ No major risk factors identified")
        
        self.report_lines.extend(risks)
        self.report_lines.extend(["", "---", ""])
    
    def _add_timing_analysis(self, metrics: Dict):
        """Add timing analysis section"""
        timing = metrics.get('timing', {})
        
        if not timing:
            return
        
        self.report_lines.extend([
            "## ⏱️ Timing Analysis",
            "",
            "Average time from signal generation to outcome:",
            "",
            "| Outcome | Average Time | Median Time |",
            "|---------|--------------|-------------|"
        ])
        
        if 'avg_hours_to_win' in timing:
            avg_hrs = timing['avg_hours_to_win']
            med_hrs = timing.get('median_hours_to_win', avg_hrs)
            self.report_lines.append(f"| ✅ Winning Trades | {avg_hrs:.1f} hours | {med_hrs:.1f} hours |")
        
        if 'avg_hours_to_loss' in timing:
            avg_hrs = timing['avg_hours_to_loss']
            med_hrs = timing.get('median_hours_to_loss', avg_hrs)
            self.report_lines.append(f"| ❌ Losing Trades | {avg_hrs:.1f} hours | {med_hrs:.1f} hours |")
        
        self.report_lines.extend(["", "---", ""])
    
    def _add_recommendations(self, metrics: Dict):
        """Add strategic recommendations"""
        win_rate = metrics['win_rate']
        market_analysis = metrics.get('market_analysis', {})
        
        self.report_lines.extend([
            "## 💡 Strategic Recommendations",
            ""
        ])
        
        recommendations = []
        
        # Performance-based recommendations
        if win_rate < 40:
            recommendations.extend([
                "### 🔴 Critical Actions Required",
                "",
                "1. **Suspend Live Trading**: Win rate below 40% threshold",
                "2. **Conduct Full System Review**: Analyze signal generation parameters",
                "3. **Implement Stricter Filters**: Add momentum and price change validation",
                "4. **Backtest Thoroughly**: Test new parameters on historical data",
                ""
            ])
        elif win_rate < 60:
            recommendations.extend([
                "### 🟡 Optimization Opportunities",
                "",
                "1. **Fine-tune Entry Criteria**: Improve signal quality through tighter filters",
                "2. **Monitor Market Conditions**: Track performance across different regimes",
                "3. **Consider Position Sizing**: Implement dynamic position sizing based on confidence",
                ""
            ])
        
        # Market-specific recommendations
        losers_analysis = market_analysis.get('losers', {})
        winners_analysis = market_analysis.get('winners', {})
        
        if losers_analysis and winners_analysis:
            loser_24h = losers_analysis.get('avg_24h_change')
            winner_24h = winners_analysis.get('avg_24h_change')
            
            if loser_24h is not None and winner_24h is not None:
                if abs(winner_24h - loser_24h) > 5:
                    recommendations.extend([
                        "### 📊 Market Context Insights",
                        "",
                        f"- **Winning signals** had average 24h change of **{winner_24h:.2f}%**",
                        f"- **Losing signals** had average 24h change of **{loser_24h:.2f}%**",
                        f"- **Recommendation**: Implement 24h price change filter (threshold: {winner_24h:.1f}%)",
                        ""
                    ])
        
        # General best practices
        recommendations.extend([
            "### ✅ Best Practices",
            "",
            "1. **Continuous Monitoring**: Review performance metrics weekly",
            "2. **Market Regime Awareness**: Adjust strategy based on market conditions",
            "3. **Risk Management**: Never risk more than 1-2% per signal",
            "4. **Documentation**: Keep detailed logs of all signals and outcomes",
            "5. **Regular Backtesting**: Validate strategy changes on historical data",
            ""
        ])
        
        self.report_lines.extend(recommendations)
        self.report_lines.extend(["---", ""])
    
    def _add_code_level_insights(self, metrics: Dict, df: pd.DataFrame):
        """Add code investigation map for AI"""
        win_rate = metrics['win_rate']
        market_analysis = metrics.get('market_analysis', {})
        losers_analysis = market_analysis.get('losers', {})
        winners_analysis = market_analysis.get('winners', {})
        
        self.report_lines.extend([
            "## Code Investigation Map",
            "",
            "### Signal Generation Pipeline",
            "",
            "```",
            "scheduler/components/signal_scanner_manager.py",
            "├─ _should_generate_signal()        # Signal validation logic",
            "├─ _validate_signal_quality()       # Quality checks",
            "└─ scan_and_generate_signal()       # Main scan loop",
            "",
            "analysis/generators/signal_generator.py",
            "├─ generate_signal()                # Core signal generation",
            "├─ _combine_timeframe_signals()     # Multi-timeframe logic",
            "└─ _calculate_confidence()          # Confidence scoring",
            "",
            "analysis/generators/market_analyzer.py",
            "├─ analyze_market_context()         # Market regime detection",
            "├─ detect_market_regime()           # Regime classification",
            "└─ calculate_volatility_percentile()# Volatility metrics",
            "",
            "analysis/adaptive_thresholds.py",
            "└─ adjust_signal_confidence()       # Dynamic threshold adjustment",
            "```",
            "",
            "### Investigation Priority (based on data)",
            ""
        ])
        
        # Add investigation priorities based on actual data
        if win_rate < 40:
            self.report_lines.extend([
                "#### 🔴 HIGH PRIORITY",
                ""
            ])
            
            # 24h change issue
            loser_24h = losers_analysis.get('avg_24h_change', 0)
            winner_24h = winners_analysis.get('avg_24h_change', -10)
            
            if abs(winner_24h - loser_24h) > 5:
                self.report_lines.extend([
                    "**1. Signal Validation - Momentum Direction Check**",
                    "- **File**: `scheduler/components/signal_scanner_manager.py`",
                    "- **Function**: `_should_generate_signal()` or `_validate_signal_quality()`",
                    "- **Issue**: SHORT signals accepted with positive 24h price change",
                    f"- **Data**: Losers avg {loser_24h:.2f}%, Winners avg {winner_24h:.2f}%",
                    "- **Investigation**: Check if momentum direction is validated before signal acceptance",
                    "- **Look for**: Filters checking `price_change_24h_pct` from `market_context`",
                    ""
                ])
            
            # ADX issue
            loser_adx = losers_analysis.get('avg_adx', 0)
            winner_adx = winners_analysis.get('avg_adx', 0)
            
            if loser_adx > winner_adx + 5:
                self.report_lines.extend([
                    "**2. ADX Threshold Configuration**",
                    "- **File**: `analysis/adaptive_thresholds.py` or config files",
                    "- **Function**: ADX filtering logic",
                    "- **Issue**: Higher ADX correlates withlosers (counter-intuitive)",
                    f"- **Data**: Losers avg ADX {loser_adx:.2f}, Winners avg {winner_adx:.2f}",
                    "- **Investigation**: Review ADX minimum threshold and how it's applied",
                    "- **Check**: Is ADX being used as filter or just metadata?",
                    ""
                ])
            
            # Failure patterns
            losers = metrics.get('losers_df')
            if len(losers) > 0:
                counter_trend = 0
                for _, row in losers.iterrows():
                    try:
                        ctx = json.loads(row.get('market_context', '{}')) if pd.notna(row.get('market_context')) else {}
                        if ctx.get('price_change_24h_pct', 0) > 0 and row['direction'] == 'SHORT':
                            counter_trend += 1
                    except (json.JSONDecodeError, TypeError, KeyError) as e:
                        pass
                
                if counter_trend > 0:
                    self.report_lines.extend([
                        "**3. Counter-Trend Trading Pattern**",
                        f"- **Frequency**: {counter_trend}/{len(losers)} losing signals ({counter_trend/len(losers)*100:.0f}%)",
                        "- **Pattern**: SHORT positions opened during upward price movement",
                        "- **Files to check**:",
                        "  - `signal_scanner_manager.py` - validation logic",
                        "  - `market_analyzer.py` - how regime is determined vs actual price movement",
                        "- **Questions**:",
                        "  - Why is `trending_down` regime assigned despite positive 24h change?",
                        "  - Is there a lag between regime detection and current price action?",
                        ""
                    ])
        
        # Configuration files
        self.report_lines.extend([
            "#### ⚙️ MEDIUM PRIORITY - Configuration Review",
            "",
            "**Config Files**:",
            "- `.env` - Environment variables and thresholds",
            "- `config/config_manager.py` - Configuration loader",
            "- `env.example` - Default values documentation",
            "",
            "**Key Parameters to Review**:",
            "```",
            "CONFIDENCE_THRESHOLD_SHORT=0.69      # Current SHORT threshold",
            "CONFIDENCE_THRESHOLD_LONG=0.90       # Current LONG threshold",
            "ADX_PERIOD=14                         # ADX calculation period",
            "MIN_ATR_PERCENT=2.0                   # Minimum ATR filter",
            "```",
            "",
            "---",
            ""
        ])
        
        # Testing and validation
        self.report_lines.extend([
            "### Validation Workflow",
            "",
            "**After making changes:**",
            "",
            "```bash",
            "# 1. Unit tests",
            "pytest tests/integration/test_signal_generation.py -v",
            "",
            "# 2. Backtest with modified code",
            "python3 tools/simulate.py --start-date 2024-11-01 --end-date 2024-11-26",
            "",
            "# 3. Generate new performance report",
            "python3 tools/generate_executive_report.py",
            "",
            "# 4. Compare metrics",
            "# Target: win_rate > 60%, loss_rate < 40%",
            "```",
            "",
            "---",
            ""
        ])
        
        # Summary for AI
        self.report_lines.extend([
            "## AI Analysis Prompt Suggestion",
            "",
            "```",
            "Analyze the TrendBot codebase focusing on:",
            "",
            "1. Signal validation in signal_scanner_manager.py:",
            "   - Why are SHORT signals with positive 24h price change accepted?",
            "   - What validation filters are currently implemented?",
            "",
            "2. Market regime detection in market_analyzer.py:",
            f"   - Why 'trending_down' assigned when 24h change is +{abs(losers_analysis.get('avg_24h_change', 0)):.2f}%?",
            "   - Is there a discrepancy between regime labels and actual price movement?",
            "",
            "3. Configuration optimization:",
            "   - Suggest optimal threshold values based on performance data",
            f"   - Current win rate: {win_rate:.2f}%, target: >60%",
            "",
            "Provide specific code changes with file paths and function names.",
            "```",
            "",
            "---",
            ""
        ])
    
    def _add_footer(self):
        """Add report footer"""
        self.report_lines.extend([
            "---",
            "",
            "## 📝 Report Notes",
            "",
            "- **Data Source**: Archive parquet files from `data/archive/` directory",
            "- **Metrics**: All percentages and statistics calculated from historical signal data",
            "- **Recommendations**: Based on statistical analysis and trading best practices",
            "",
            "*This report is auto-generated for strategic decision-making purposes.*",
            ""
        ])
    
    def save_report(self, report_content: str) -> Path:
        """Save report to file"""
        # Create reports directory
        reports_dir = PROJECT_ROOT / "reports"
        reports_dir.mkdir(exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"executive_report_{timestamp}.md"
        filepath = reports_dir / filename
        
        # Write report
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        return filepath


def main():
    """Main execution function"""
    archive_path = PROJECT_ROOT / "data" / "archive"
    
    if not archive_path.exists():
        print(f"❌ Archive directory not found: {archive_path}")
        return
    
    print("📊 Generating Executive Report...")
    print(f"📁 Source: {archive_path}")
    print()
    
    # Generate report
    generator = ExecutiveReportGenerator(archive_path)
    report_content = generator.generate_report()
    
    # Save report
    filepath = generator.save_report(report_content)
    
    print("✅ Report generated successfully!")
    print(f"📄 Location: {filepath}")
    print()
    print("─" * 80)
    print()
    print(report_content)
    print()
    print("─" * 80)
    print()
    print(f"💡 Report saved to: {filepath}")


if __name__ == "__main__":
    main()

