#!/usr/bin/env python3
"""
Long/Short Oranı Kontrolü
--------------------------
Veritabanındaki tüm sinyallerin (reddedilenler dahil) long/short oranını hesaplar.
"""
import sqlite3
import sys
from pathlib import Path

# Add project root to path
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

DB_PATH = "data/signals.db"


def main():
    """Veritabanındaki tüm sinyallerin long/short oranını hesaplar."""
    if not Path(DB_PATH).exists():
        print(f"❌ Veritabanı bulunamadı: {DB_PATH}")
        sys.exit(1)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tüm sinyallerin direction'a göre sayısını al
    cursor.execute("""
        SELECT direction, COUNT(*) as count 
        FROM signals 
        GROUP BY direction
    """)
    
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        print("❌ Veritabanında sinyal bulunamadı.")
        return
    
    # Toplam sinyal sayısı
    total = sum(count for _, count in results)
    
    # Long ve Short sayılarını bul
    long_count = 0
    short_count = 0
    
    for direction, count in results:
        if direction.upper() == 'LONG':
            long_count = count
        elif direction.upper() == 'SHORT':
            short_count = count
    
    # Sonuçları göster
    print("=" * 60)
    print("📊 LONG/SHORT ORANI (Tüm Sinyaller - Reddedilenler Dahil)")
    print("=" * 60)
    print(f"\n💰 LONG:  {long_count:>6} sinyal ({long_count/total*100:>6.2f}%)")
    print(f"📉 SHORT: {short_count:>6} sinyal ({short_count/total*100:>6.2f}%)")
    print(f"\n📈 TOPLAM: {total:>6} sinyal")
    
    if total > 0:
        ratio = long_count / short_count if short_count > 0 else float('inf')
        print(f"\n🔢 LONG/SHORT Oranı: {ratio:.2f}:1")
        if ratio > 1:
            print(f"   → LONG sinyaller {ratio:.2f}x daha fazla")
        elif ratio < 1:
            print(f"   → SHORT sinyaller {1/ratio:.2f}x daha fazla")
        else:
            print(f"   → LONG ve SHORT eşit")
    
    print("=" * 60)


if __name__ == "__main__":
    main()

