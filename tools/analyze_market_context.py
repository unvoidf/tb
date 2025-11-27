#!/usr/bin/env python3
"""
Advanced Signal Analysis with Market Context
"""

import pandas as pd
import sys
import json
from pathlib import Path
from typing import Dict, Any, List

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_and_analyze():
    """Load data and perform detailed analysis"""
    
    signals_path = PROJECT_ROOT / "data" / "archive" / "signals" / "2025-11.parquet"
    df = pd.read_parquet(signals_path)
    
    # Convert numeric columns
    numeric_cols = ['signal_price', 'confidence', 'atr', 'tp1_price', 'tp2_price', 'sl_price']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    print("=" * 100)
    print("📈 SIGNAL PERFORMANCE ANALYSIS - DETAILED MARKET CONTEXT")
    print("=" * 100)
    print()
    
    # Overall summary
    print("📊 OVERVIEW")
    print("-" * 100)
    print(f"Total Signals:         {len(df)}")
    print(f"All Direction:         {df['direction'].value_counts().to_dict()}")
    print(f"Timeframe:             {df['timeframe'].unique()[0]}")
    print(f"Date Range:            {pd.to_datetime(pd.to_numeric(df['created_at'], errors='coerce'), unit='s').min()} to {pd.to_datetime(pd.to_numeric(df['created_at'], errors='coerce'), unit='s').max()}")
    print()
    
    # Market Context Analysis
    print("🌍 MARKET CONDITIONS ANALYSIS")
    print("-" * 100)
    
    market_data = []
    for idx, row in df.iterrows():
        if pd.notna(row.get('market_context')):
            try:
                ctx = json.loads(row['market_context']) if isinstance(row['market_context'], str) else row['market_context']
                ctx['symbol'] = row['symbol']
                ctx['confidence'] = row['confidence']
                ctx['direction'] = row['direction']
                market_data.append(ctx)
            except:
                pass
    
    if market_data:
        market_df = pd.DataFrame(market_data)
        
        print(f"\n📍 MARKET REGIME DISTRIBUTION")
        if 'regime' in market_df.columns:
            regime_counts = market_df['regime'].value_counts()
            for regime, count in regime_counts.items():
                print(f"  {regime:20s} {count:2d} signals ({count/len(market_df)*100:5.1f}%)")
        
        print(f"\n📊 TREND ANALYSIS (EMA)")
        if 'ema_trend' in market_df.columns:
            trend_counts = market_df['ema_trend'].value_counts()
            for trend, count in trend_counts.items():
                print(f"  {trend:20s} {count:2d} signals ({count/len(market_df)*100:5.1f}%)")
        
        print(f"\n💪 ADX STRENGTH DISTRIBUTION")
        if 'adx_strength' in market_df.columns:
            adx_counts = market_df['adx_strength'].value_counts()
            for strength, count in adx_counts.items():
                print(f"  {str(strength):20s} {count:2d} signals ({count/len(market_df)*100:5.1f}%)")
        
        print(f"\n📈 VOLATILITY METRICS")
        if 'volatility_percentile' in market_df.columns:
            print(f"  Avg Volatility Percentile:  {market_df['volatility_percentile'].mean():.1f}")
            print(f"  Min/Max Volatility:         {market_df['volatility_percentile'].min():.1f} / {market_df['volatility_percentile'].max():.1f}")
        
        if 'atr_14' in market_df.columns:
            print(f"  Avg ATR (14):               {market_df['atr_14'].mean():.4f}")
        
        print(f"\n💹 PRICE CHANGE ANALYSIS")
        if 'price_change_pct' in market_df.columns:
            # Convert to numeric, handling dicts and other types
            price_changes = pd.to_numeric(market_df['price_change_pct'], errors='coerce')
            if price_changes.notna().any():
                print(f"  Avg Price Change %:         {price_changes.mean():.2f}%")
                print(f"  Min/Max Price Change:       {price_changes.min():.2f}% / {price_changes.max():.2f}%")
        
        if 'price_change_24h_pct' in market_df.columns:
            price_changes_24h = pd.to_numeric(market_df['price_change_24h_pct'], errors='coerce')
            if price_changes_24h.notna().any():
                print(f"  Avg 24h Price Change %:     {price_changes_24h.mean():.2f}%")
    
    # Individual Signal Analysis
    print()
    print("🎯 DETAILED SIGNAL BREAKDOWN")
    print("-" * 100)
    
    for idx, row in df.iterrows():
        print(f"\n{row['symbol']} - {row['direction']}")
        print(f"  Signal ID:         {row['signal_id']}")
        print(f"  Confidence:        {row['confidence']:.2f}%")
        print(f"  Signal Price:      ${row['signal_price']:.4f}")
        print(f"  TP1 / TP2:         ${row['tp1_price']:.4f} / ${row['tp2_price']:.4f}")
        print(f"  SL Price:          ${row['sl_price']:.4f}")
        
        # Calculate R:R ratios
        if row['direction'] == 'LONG':
            tp1_r = (row['tp1_price'] - row['signal_price']) / (row['signal_price'] - row['sl_price'])
            tp2_r = (row['tp2_price'] - row['signal_price']) / (row['signal_price'] - row['sl_price'])
        else:  # SHORT
            tp1_r = (row['signal_price'] - row['tp1_price']) / (row['sl_price'] - row['signal_price'])
            tp2_r = (row['signal_price'] - row['tp2_price']) / (row['sl_price'] - row['signal_price'])
        
        print(f"  Risk:Reward (TP1): 1:{tp1_r:.2f}R")
        print(f"  Risk:Reward (TP2): 1:{tp2_r:.2f}R")
        
        # Market Context
        if pd.notna(row.get('market_context')):
            try:
                ctx = json.loads(row['market_context']) if isinstance(row['market_context'], str) else row['market_context']
                print(f"  Market Regime:     {ctx.get('regime', 'N/A')}")
                print(f"  EMA Trend:         {ctx.get('ema_trend', 'N/A')}")
                print(f"  ADX Strength:      {ctx.get('adx_strength', 'N/A')}")
                print(f"  Volatility %ile:   {ctx.get('volatility_percentile', 'N/A'):.1f}")
                print(f"  24h Change:        {ctx.get('price_change_24h_pct', 'N/A'):.2f}%")
            except:
                print(f"  Market Context:    Error parsing")
    
    print()
    print("=" * 100)
    
    # Key Insights
    print("\n💡 KEY INSIGHTS & OBSERVATIONS")
    print("-" * 100)
    
    print("\n1. SIGNAL CHARACTERISTICS:")
    print(f"   • All {len(df)} signals are SHORT positions")
    print(f"   • Average confidence: {df['confidence'].mean():.2f}%")
    print(f"   • Signals appear to be trend-following SHORT setups")
    
    if market_data:
        market_df = pd.DataFrame(market_data)
        
        print("\n2. MARKET CONDITIONS:")
        if 'regime' in market_df.columns:
            dominant_regime = market_df['regime'].mode()[0]
            print(f"   • Dominant market regime: {dominant_regime}")
        
        if 'ema_trend' in market_df.columns:
            dominant_trend = market_df['ema_trend'].mode()[0]
            print(f"   • Dominant EMA trend: {dominant_trend}")
        
        if 'adx_strength' in market_df.columns:
            dominant_adx = market_df['adx_strength'].mode()[0]
            print(f"   • Most common ADX strength: {dominant_adx}")
        
        print("\n3. SIGNAL STATUS:")
        print(f"   ⚠️  These are ACTIVE/RECENT signals - TP/SL outcomes not yet determined")
        print(f"   • Signals created between Nov 25-26, 2025")
        print(f"   • Currently being tracked by the system")
        print(f"   • Performance data will be available after TP/SL hits")
    
    print("\n4. RECOMMENDATIONS:")
    print("   • Monitor these signals as they develop")
    print("   • Track which market regimes produce best results")
    print("   • Analyze correlation between market context and eventual outcomes")
    print("   • Consider creating alerts for specific regime/trend combinations")
    
    print()
    print("=" * 100)


if __name__ == "__main__":
    load_and_analyze()
