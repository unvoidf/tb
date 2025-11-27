#!/usr/bin/env python3
"""
Post-Mortem Analysis: Why Did 7/9 Signals Hit Stop Loss?
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
signals_path = PROJECT_ROOT / "data" / "archive" / "signals" / "2025-11.parquet"

df = pd.read_parquet(signals_path)

# Convert string '0'/'1' to boolean
df['tp1_hit'] = df['tp1_hit'].map({'0': False, '1': True, 0: False, 1: True})
df['tp2_hit'] = df['tp2_hit'].map({'0': False, '1': True, 0: False, 1: True})
df['sl_hit'] = df['sl_hit'].map({'0': False, '1': True, 0: False, 1: True})

# Convert numeric columns
numeric_cols = ['signal_price', 'confidence', 'atr', 'tp1_price', 'tp2_price', 'sl_price', 
                'mfe_price', 'mae_price', 'final_price']
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')

# Convert timestamps
timestamp_cols = ['created_at', 'tp1_hit_at', 'sl_hit_at', 'mfe_at', 'mae_at']
for col in timestamp_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')

print("=" * 100)
print("🔴 POST-MORTEM ANALYSIS: NEDEN 7/9 SİNYAL STOP LOSS'A TAKILDI?")
print("=" * 100)
print()

# Overall Stats
tp1_count = df['tp1_hit'].sum()
sl_count = df['sl_hit'].sum()
active_count = len(df) - tp1_count - sl_count

print("📊 GENEL SONUÇLAR")
print("-" * 100)
print(f"✅ TP1 Hit:        {tp1_count}/9 ({tp1_count/len(df)*100:.1f}%)")
print(f"❌ SL Hit:         {sl_count}/9 ({sl_count/len(df)*100:.1f}%)")
print(f"⏳ Aktif:          {active_count}/9 ({active_count/len(df)*100:.1f}%)")
print(f"📉 Loss Rate:      {sl_count/len(df)*100:.1f}%")
print()

# Winners vs Losers
winners = df[df['tp1_hit'] == True]
losers = df[df['sl_hit'] == True]
active = df[(df['tp1_hit'] == False) & (df['sl_hit'] == False)]

print("🎯 KAZANAN SİNYAL")
print("-" * 100)
if len(winners) > 0:
    for _, row in winners.iterrows():
        ctx = json.loads(row['market_context']) if pd.notna(row.get('market_context')) else {}
        print(f"✅ {row['symbol']}")
        print(f"   Confidence:       {row['confidence']:.2f}%")
        print(f"   Signal Price:     ${row['signal_price']:.4f}")
        print(f"   Market Regime:    {ctx.get('regime', 'N/A')}")
        print(f"   EMA Trend:        {ctx.get('ema_trend', 'N/A')}")
        print(f"   ADX Strength:     {ctx.get('adx_strength', 'N/A')}")
        print(f"   Volatility %ile:  {ctx.get('volatility_percentile', 'N/A')}")
        print(f"   24h Change:       {ctx.get('price_change_24h_pct', 'N/A')}%")
        
        # Timing
        if pd.notna(row['tp1_hit_at']) and pd.notna(row['created_at']):
            time_to_tp = (row['tp1_hit_at'] - row['created_at']) / 3600
            print(f"   Time to TP1:      {time_to_tp:.1f} saat")
        print()

print("❌ KAYBEDEN SİNYALLER")
print("-" * 100)
if len(losers) > 0:
    for _, row in losers.iterrows():
        ctx = json.loads(row['market_context']) if pd.notna(row.get('market_context')) else {}
        print(f"❌ {row['symbol']}")
        print(f"   Confidence:       {row['confidence']:.2f}%")
        print(f"   Signal Price:     ${row['signal_price']:.4f}")
        print(f"   Market Regime:    {ctx.get('regime', 'N/A')}")
        print(f"   EMA Trend:        {ctx.get('ema_trend', 'N/A')}")
        print(f"   ADX Strength:     {ctx.get('adx_strength', 'N/A'):.2f}" if isinstance(ctx.get('adx_strength'), (int, float)) else f"   ADX Strength:     {ctx.get('adx_strength', 'N/A')}")
        print(f"   Volatility %ile:  {ctx.get('volatility_percentile', 'N/A'):.1f}" if isinstance(ctx.get('volatility_percentile'), (int, float)) else f"   Volatility %ile:  {ctx.get('volatility_percentile', 'N/A')}")
        print(f"   24h Change:       {ctx.get('price_change_24h_pct', 'N/A'):.2f}%" if isinstance(ctx.get('price_change_24h_pct'), (int, float)) else f"   24h Change:       {ctx.get('price_change_24h_pct', 'N/A')}")
        
        # Timing
        if pd.notna(row['sl_hit_at']) and pd.notna(row['created_at']):
            time_to_sl = (row['sl_hit_at'] - row['created_at']) / 3600
            print(f"   Time to SL:       {time_to_sl:.1f} saat")
        
        # MFE/MAE Analysis
        if pd.notna(row['mfe_price']):
            if row['direction'] == 'SHORT':
                mfe_r = (row['signal_price'] - row['mfe_price']) / (row['sl_price'] - row['signal_price'])
            else:
                mfe_r = (row['mfe_price'] - row['signal_price']) / (row['signal_price'] - row['sl_price'])
            print(f"   Max Favorable:    {mfe_r:.2f}R (price: ${row['mfe_price']:.4f})")
        
        print()

print("\n🔍 KARŞILAŞTIRMALI ANALİZ: KAZANAN vs KAYBEDEN")
print("-" * 100)

if len(winners) > 0 and len(losers) > 0:
    # Extract market context
    winner_contexts = []
    loser_contexts = []
    
    for _, row in winners.iterrows():
        if pd.notna(row.get('market_context')):
            ctx = json.loads(row['market_context']) if isinstance(row['market_context'], str) else row['market_context']
            winner_contexts.append(ctx)
    
    for _, row in losers.iterrows():
        if pd.notna(row.get('market_context')):
            ctx = json.loads(row['market_context']) if isinstance(row['market_context'], str) else row['market_context']
            loser_contexts.append(ctx)
    
    if winner_contexts and loser_contexts:
        winner_df = pd.DataFrame(winner_contexts)
        loser_df = pd.DataFrame(loser_contexts)
        
        print("\n📊 Market Regime Dağılımı")
        print(f"   Kazanan:  {winner_df['regime'].value_counts().to_dict()}")
        print(f"   Kaybeden: {loser_df['regime'].value_counts().to_dict()}")
        
        print("\n📈 EMA Trend Dağılımı")
        print(f"   Kazanan:  {winner_df['ema_trend'].value_counts().to_dict()}")
        print(f"   Kaybeden: {loser_df['ema_trend'].value_counts().to_dict()}")
        
        print("\n💪 ADX Ortalaması")
        winner_adx = pd.to_numeric(winner_df['adx_strength'], errors='coerce')
        loser_adx = pd.to_numeric(loser_df['adx_strength'], errors='coerce')
        print(f"   Kazanan:  {winner_adx.mean():.2f}")
        print(f"   Kaybeden: {loser_adx.mean():.2f}")
        
        print("\n📉 Volatility Percentile Ortalaması")
        winner_vol = pd.to_numeric(winner_df['volatility_percentile'], errors='coerce')
        loser_vol = pd.to_numeric(loser_df['volatility_percentile'], errors='coerce')
        print(f"   Kazanan:  {winner_vol.mean():.1f}")
        print(f"   Kaybeden: {loser_vol.mean():.1f}")
        
        print("\n💹 24h Price Change Ortalaması")
        winner_chg = pd.to_numeric(winner_df['price_change_24h_pct'], errors='coerce')
        loser_chg = pd.to_numeric(loser_df['price_change_24h_pct'], errors='coerce')
        print(f"   Kazanan:  {winner_chg.mean():.2f}%")
        print(f"   Kaybeden: {loser_chg.mean():.2f}%")

print("\n\n🧠 핵심 İÇGÖRÜLER & ÖNERİLER")
print("-" * 100)

print("\n1. ❌ SORUN:")
print(f"   • 7/9 sinyal SL'ye takıldı ({sl_count/len(df)*100:.0f}% loss rate)")
print(f"   • Sadece 1 sinyal TP1'e ulaştı ({tp1_count/len(df)*100:.0f}% win rate)")
print(f"   • Bu performans KABUL EDİLEMEZ - strateji revize gerektirir")

print("\n2. 🔎 MUHTEMEL SEBEPLER:")

# Check if market reversed
losers_trending_down = sum(1 for _, row in losers.iterrows() 
                           if json.loads(row['market_context']).get('regime') == 'trending_down')

print(f"   • {losers_trending_down}/7 kaybeden sinyal 'trending_down' regime'inde")
print(f"   • Tüm sinyaller SHORT pozisyon - muhtemelen piyasa tersine döndü")
print(f"   • SHORT sinyalleri için piyasa koşulları uygun değildi")

# Check volatility of losers
if len(losers) > 0:
    loser_contexts = [json.loads(row['market_context']) for _, row in losers.iterrows() if pd.notna(row.get('market_context'))]
    if loser_contexts:
        loser_vol_avg = pd.DataFrame(loser_contexts)['volatility_percentile'].mean()
        print(f"   • Kaybeden sinyallerin avg volatility: {loser_vol_avg:.1f} (düşük/orta volatilite)")

print("\n3. 💡 ÖNERİLER:")
print("   ✓ Trend filtresi güçlendirilmeli")
print("   ✓ SHORT sinyaller için daha katı market koşulu kriterleri")
print("   ✓ ADX threshold yükseltilmeli (>35-40)")
print("   ✓ Volatility minimum seviyesi belirle")
print("   ✓ 24h change negative olmalı SHORT için")
print("   ✓ Stop loss mesafesi gözden geçirilmeli (çok dar olabilir)")
print("   ✓ Piyasa momentum göstergeleri eklenmeli")

print("\n4. 🎯 AKSİYON İTEMLERI:")
print("   □ Strateji parametrelerini revize et")
print("   □ Backtest yap güncellenmiş parametrelerle")
print("   □ Paper trading ile doğrula")
print("   □ Live'a geçmeden önce en az %60 win rate hedefle")

print("\n" + "=" * 100)
