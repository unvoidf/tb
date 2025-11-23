#!/usr/bin/env python3
"""
Mean Reversion Sinyali Kontrolü
--------------------------------
Veritabanındaki tüm sinyallerde mean reversion stratejisi olup olmadığını kontrol eder.
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
    """Veritabanındaki mean reversion sinyallerini kontrol eder."""
    if not Path(DB_PATH).exists():
        print(f"❌ Veritabanı bulunamadı: {DB_PATH}")
        sys.exit(1)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tüm sinyalleri al
    cursor.execute("SELECT signal_id, signal_data FROM signals")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("❌ Veritabanında sinyal bulunamadı.")
        return
    
    # Mean reversion sinyallerini bul
    mean_reversion_signals = []
    mean_reversion_tf_count = 0
    mean_reversion_custom_targets_count = 0
    
    for row in rows:
        signal_id = row[0]
        signal_data_str = row[1] if row[1] else None
        signal_data = parse_signal_data(signal_data_str)
        
        has_mean_reversion = False
        found_in = []
        
        # Ana sinyal seviyesinde strategy_type kontrolü
        strategy_type = signal_data.get('strategy_type', '').lower() if signal_data else ''
        if strategy_type == 'mean_reversion':
            has_mean_reversion = True
            found_in.append('strategy_type')
        
        # Custom targets içinde mean_reversion kontrolü
        if signal_data:
            custom_targets = signal_data.get('custom_targets', {})
            if isinstance(custom_targets, dict):
                for target_name, target_info in custom_targets.items():
                    if isinstance(target_info, dict):
                        target_type = target_info.get('type', '').lower()
                        if target_type == 'mean_reversion':
                            has_mean_reversion = True
                            mean_reversion_custom_targets_count += 1
                            found_in.append(f'custom_targets.{target_name}')
            
            # Timeframe seviyesinde de kontrol et
            timeframe_signals = signal_data.get('timeframe_signals', {})
            for tf_name, tf_signal in timeframe_signals.items():
                if isinstance(tf_signal, dict):
                    tf_strategy = tf_signal.get('strategy_type', '').lower()
                    if tf_strategy == 'mean_reversion':
                        has_mean_reversion = True
                        mean_reversion_tf_count += 1
                        found_in.append(f'timeframe.{tf_name}.strategy_type')
                    
                    # Timeframe custom targets kontrolü
                    tf_custom_targets = tf_signal.get('custom_targets', {})
                    if isinstance(tf_custom_targets, dict):
                        for target_name, target_info in tf_custom_targets.items():
                            if isinstance(target_info, dict):
                                target_type = target_info.get('type', '').lower()
                                if target_type == 'mean_reversion':
                                    has_mean_reversion = True
                                    mean_reversion_custom_targets_count += 1
                                    found_in.append(f'timeframe.{tf_name}.custom_targets.{target_name}')
        
        if has_mean_reversion:
            mean_reversion_signals.append((signal_id, found_in))
    
    total = len(rows)
    mean_rev_count = len(mean_reversion_signals)
    
    # Sonuçları göster
    print("=" * 60)
    print("📊 MEAN REVERSION SİNYALİ KONTROLÜ")
    print("=" * 60)
    print(f"\n🔄 MEAN REVERSION: {mean_rev_count:>6} sinyal ({mean_rev_count/total*100:>6.2f}%)")
    print(f"📈 TOPLAM:         {total:>6} sinyal")
    
    if mean_reversion_tf_count > 0:
        print(f"\n📊 Timeframe seviyesinde mean_reversion: {mean_reversion_tf_count} adet")
    
    if mean_rev_count > 0:
        print(f"\n✅ Mean reversion sinyalleri bulundu!")
        print(f"\n📊 Detaylı İstatistikler:")
        print(f"   - Custom targets içinde mean_reversion: {mean_reversion_custom_targets_count} adet")
        print(f"   - Timeframe seviyesinde mean_reversion: {mean_reversion_tf_count} adet")
        print(f"\n📋 İlk 10 Mean Reversion Sinyali:")
        for i, (signal_id, found_in) in enumerate(mean_reversion_signals[:10], 1):
            print(f"   {i}. {signal_id}")
            print(f"      Bulunduğu yerler: {', '.join(found_in)}")
        if len(mean_reversion_signals) > 10:
            print(f"   ... ve {len(mean_reversion_signals) - 10} tane daha")
    else:
        print(f"\n❌ Veritabanında mean reversion sinyali bulunamadı.")
        print(f"   (Ranging stratejisi 'ranging' olarak kaydediliyor olabilir)")
        print(f"   (Mean reversion custom_targets içinde 'type: mean_reversion' olarak saklanıyor olabilir)")
    
    print("=" * 60)


if __name__ == "__main__":
    main()

