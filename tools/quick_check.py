#!/usr/bin/env python3
"""Quick check of signal outcomes from parquet file"""

import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
signals_path = PROJECT_ROOT / "data" / "archive" / "signals" / "2025-11.parquet"

df = pd.read_parquet(signals_path)

# Convert to boolean properly
df['tp1_hit'] = df['tp1_hit'].map({'True': True, 'False': False, True: True, False: False, 'true': True, 'false': False})
df['tp2_hit'] = df['tp2_hit'].map({'True': True, 'False': False, True: True, False: False, 'true': True, 'false': False})
df['sl_hit'] = df['sl_hit'].map({'True': True, 'False': False, True: True, False: False, 'true': True, 'false': False})

print("=" * 80)
print("GÜNCEL SİNYAL DURUMU")
print("=" * 80)
print(f"\nToplam Sinyal: {len(df)}")
print(f"TP1 Hit: {df['tp1_hit'].sum()}")
print(f"TP2 Hit: {df['tp2_hit'].sum()}")
print(f"SL Hit: {df['sl_hit'].sum()}")
print(f"Aktif: {len(df) - df['tp1_hit'].sum() - df['sl_hit'].sum()}")

print(f"\nWin Rate: {(df['tp1_hit'].sum() / len(df) * 100):.1f}%")
print(f"Loss Rate: {(df['sl_hit'].sum() / len(df) * 100):.1f}%")

print("\n" + "=" * 80)
print("DETAYLI SINYAL DURUMU")
print("=" * 80)

for idx, row in df.iterrows():
    status = "🟢 TP1 HIT" if row['tp1_hit'] else ("🔴 SL HIT" if row['sl_hit'] else "⚪ AKTİF")
    print(f"{row['symbol']:15s} {status:15s} Confidence: {row['confidence']}")

print("\n" + "=" * 80)
