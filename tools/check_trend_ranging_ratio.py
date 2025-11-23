#!/usr/bin/env python3
"""
Trend Following / Ranging Oranı Kontrolü
----------------------------------------
Veritabanındaki tüm sinyallerin (reddedilenler dahil) trend following/ranging oranını hesaplar.
"""
import sqlite3
import json
import sys
from pathlib import Path
from typing import Dict, Any

# Add project root to path
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

DB_PATH = "data/signals.db"


def parse_signal_data(signal_data_str: str) -> Dict[str, Any]:
    """Parse signal_data JSON string.
    
    Args:
        signal_data_str: JSON string from database
        
    Returns:
        Parsed dictionary or empty dict
    """
    if not signal_data_str:
        return {}
    try:
        return json.loads(signal_data_str)
    except (json.JSONDecodeError, TypeError):
        return {}


def main():
    """Veritabanındaki tüm sinyallerin trend/ranging oranını hesaplar."""
    if not Path(DB_PATH).exists():
        print(f"❌ Veritabanı bulunamadı: {DB_PATH}")
        sys.exit(1)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tüm sinyalleri al
    cursor.execute("SELECT signal_data FROM signals")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("❌ Veritabanında sinyal bulunamadı.")
        return
    
    # Strategy type'ları say (ana sinyal seviyesi)
    trend_count = 0
    ranging_count = 0
    unknown_count = 0
    
    # Timeframe seviyesinde de sayalım (detaylı analiz için)
    trend_tf_count = 0
    ranging_tf_count = 0
    
    for row in rows:
        signal_data_str = row[0] if row[0] else None
        signal_data = parse_signal_data(signal_data_str)
        
        # Ana sinyal seviyesindeki strategy_type'ı kontrol et
        strategy_type = signal_data.get('strategy_type', '').lower() if signal_data else ''
        
        # Timeframe seviyesindeki strategy_type'ları da say
        if signal_data:
            timeframe_signals = signal_data.get('timeframe_signals', {})
            for tf_signal in timeframe_signals.values():
                if isinstance(tf_signal, dict):
                    tf_strategy = tf_signal.get('strategy_type', '').lower()
                    # Custom targets içinde mean_reversion kontrolü
                    tf_custom_targets = tf_signal.get('custom_targets', {})
                    if isinstance(tf_custom_targets, dict):
                        for target_info in tf_custom_targets.values():
                            if isinstance(target_info, dict):
                                target_type = target_info.get('type', '').lower()
                                if target_type == 'mean_reversion':
                                    ranging_tf_count += 1
                                    break
                    if tf_strategy == 'trend':
                        trend_tf_count += 1
                    elif tf_strategy == 'ranging' or tf_strategy == 'mean_reversion':
                        ranging_tf_count += 1
        
        # Mean reversion da kontrol et (custom_targets içinde type olabilir)
        mean_reversion_found = False
        if signal_data:
            custom_targets = signal_data.get('custom_targets', {})
            if isinstance(custom_targets, dict):
                for target_info in custom_targets.values():
                    if isinstance(target_info, dict):
                        target_type = target_info.get('type', '').lower()
                        if target_type == 'mean_reversion':
                            mean_reversion_found = True
                            break
        
        if strategy_type == 'trend':
            trend_count += 1
        elif strategy_type == 'ranging' or mean_reversion_found:
            ranging_count += 1
        elif strategy_type == 'mean_reversion':
            ranging_count += 1  # Mean reversion da ranging kategorisinde
        else:
            unknown_count += 1
    
    total = len(rows)
    
    # Sonuçları göster
    print("=" * 60)
    print("📊 TREND FOLLOWING / RANGING ORANI (Tüm Sinyaller)")
    print("=" * 60)
    print("\n🎯 ANA SİNYAL SEVİYESİ:")
    print(f"📈 TREND FOLLOWING: {trend_count:>6} sinyal ({trend_count/total*100:>6.2f}%)")
    print(f"🔄 RANGING:         {ranging_count:>6} sinyal ({ranging_count/total*100:>6.2f}%)")
    if unknown_count > 0:
        print(f"❓ BİLİNMEYEN:      {unknown_count:>6} sinyal ({unknown_count/total*100:>6.2f}%)")
    print(f"\n📈 TOPLAM:         {total:>6} sinyal")
    
    # Timeframe seviyesi istatistikleri
    tf_total = trend_tf_count + ranging_tf_count
    if tf_total > 0:
        print("\n" + "-" * 60)
        print("📊 TIMEFRAME SEVİYESİ (Detaylı Analiz):")
        print(f"📈 TREND:          {trend_tf_count:>6} timeframe ({trend_tf_count/tf_total*100:>6.2f}%)")
        print(f"🔄 RANGING:        {ranging_tf_count:>6} timeframe ({ranging_tf_count/tf_total*100:>6.2f}%)")
        print(f"📈 TOPLAM:         {tf_total:>6} timeframe")
    
    if total > 0:
        valid_total = trend_count + ranging_count
        if valid_total > 0:
            ratio = trend_count / ranging_count if ranging_count > 0 else float('inf')
            print(f"\n🔢 TREND/RANGING Oranı (Ana Sinyal): {ratio:.2f}:1")
            if ratio > 1:
                print(f"   → TREND sinyaller {ratio:.2f}x daha fazla")
            elif ratio < 1:
                print(f"   → RANGING sinyaller {1/ratio:.2f}x daha fazla")
            else:
                print(f"   → TREND ve RANGING eşit")
        else:
            print(f"\n⚠️  Hiç trend veya ranging sinyali bulunamadı.")
    
    print("=" * 60)


if __name__ == "__main__":
    main()

