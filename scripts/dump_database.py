#!/usr/bin/env python3
"""
Veritabanı dump scripti.
Tüm sinyal verilerini txt dosyasına aktarır.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path


def format_timestamp(ts: int) -> str:
    """Unix timestamp'i okunabilir formata çevirir."""
    if ts is None:
        return "N/A"
    try:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return str(ts)


def dump_database(db_path: str = "data/signals.db", output_path: str = "signals_dump.txt"):
    """
    Veritabanındaki tüm verileri txt dosyasına aktarır.
    
    Args:
        db_path: Veritabanı dosya yolu
        output_path: Çıktı dosyası yolu
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("TRENDBOT SİNYAL VERİTABANI DUMP\n")
            f.write(f"Oluşturulma Tarihi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            # SIGNALS tablosu
            f.write("\n" + "=" * 80 + "\n")
            f.write("SIGNALS TABLOSU\n")
            f.write("=" * 80 + "\n\n")
            
            cursor.execute("SELECT COUNT(*) as count FROM signals")
            total_signals = cursor.fetchone()['count']
            f.write(f"Toplam Sinyal Sayısı: {total_signals}\n\n")
            
            cursor.execute("""
                SELECT * FROM signals 
                ORDER BY created_at DESC
            """)
            
            signals = cursor.fetchall()
            
            for idx, signal in enumerate(signals, 1):
                f.write(f"\n--- Sinyal #{idx} ---\n")
                f.write(f"Signal ID: {signal['signal_id']}\n")
                f.write(f"Symbol: {signal['symbol']}\n")
                f.write(f"Direction: {signal['direction']}\n")
                f.write(f"Signal Price: ${signal['signal_price']:.4f}\n")
                f.write(f"Confidence: {signal['confidence']*100:.2f}%\n")
                f.write(f"ATR: {signal['atr'] if signal['atr'] else 'N/A'}\n")
                f.write(f"Timeframe: {signal['timeframe'] or 'N/A'}\n")
                f.write(f"Created At: {format_timestamp(signal['created_at'])}\n")
                
                f.write(f"\nTake Profit Seviyeleri:\n")
                tp1_str = f"${signal['tp1_price']:.4f}" if signal['tp1_price'] else 'N/A'
                f.write(f"  TP1: {tp1_str}\n")
                f.write(f"    Hit: {'Evet' if signal['tp1_hit'] else 'Hayır'}\n")
                if signal['tp1_hit_at']:
                    f.write(f"    Hit At: {format_timestamp(signal['tp1_hit_at'])}\n")
                
                tp2_str = f"${signal['tp2_price']:.4f}" if signal['tp2_price'] else 'N/A'
                f.write(f"  TP2: {tp2_str}\n")
                f.write(f"    Hit: {'Evet' if signal['tp2_hit'] else 'Hayır'}\n")
                if signal['tp2_hit_at']:
                    f.write(f"    Hit At: {format_timestamp(signal['tp2_hit_at'])}\n")
                
                tp3_str = f"${signal['tp3_price']:.4f}" if signal['tp3_price'] else 'N/A'
                f.write(f"  TP3: {tp3_str}\n")
                f.write(f"    Hit: {'Evet' if signal['tp3_hit'] else 'Hayır'}\n")
                if signal['tp3_hit_at']:
                    f.write(f"    Hit At: {format_timestamp(signal['tp3_hit_at'])}\n")
                
                f.write(f"\nStop Loss Seviyeleri:\n")
                sl1_str = f"${signal['sl1_price']:.4f}" if signal['sl1_price'] else 'N/A'
                f.write(f"  SL1: {sl1_str}\n")
                f.write(f"    Hit: {'Evet' if signal['sl1_hit'] else 'Hayır'}\n")
                if signal['sl1_hit_at']:
                    f.write(f"    Hit At: {format_timestamp(signal['sl1_hit_at'])}\n")
                
                sl1_5_str = f"${signal['sl1_5_price']:.4f}" if signal['sl1_5_price'] else 'N/A'
                f.write(f"  SL1.5: {sl1_5_str}\n")
                f.write(f"    Hit: {'Evet' if signal['sl1_5_hit'] else 'Hayır'}\n")
                if signal['sl1_5_hit_at']:
                    f.write(f"    Hit At: {format_timestamp(signal['sl1_5_hit_at'])}\n")
                
                sl2_str = f"${signal['sl2_price']:.4f}" if signal['sl2_price'] else 'N/A'
                f.write(f"  SL2: {sl2_str}\n")
                f.write(f"    Hit: {'Evet' if signal['sl2_hit'] else 'Hayır'}\n")
                if signal['sl2_hit_at']:
                    f.write(f"    Hit At: {format_timestamp(signal['sl2_hit_at'])}\n")
                
                # R-based distances
                if 'tp1_distance_r' in signal.keys() and signal['tp1_distance_r']:
                    f.write(f"\nR-based Distances:\n")
                    f.write(f"  TP1 Distance: {signal['tp1_distance_r']:.2f}R\n")
                    if 'tp2_distance_r' in signal.keys() and signal['tp2_distance_r']:
                        f.write(f"  TP2 Distance: {signal['tp2_distance_r']:.2f}R\n")
                    if 'tp3_distance_r' in signal.keys() and signal['tp3_distance_r']:
                        f.write(f"  TP3 Distance: {signal['tp3_distance_r']:.2f}R\n")
                    if 'sl1_distance_r' in signal.keys() and signal['sl1_distance_r']:
                        f.write(f"  SL1 Distance: {signal['sl1_distance_r']:.2f}R\n")
                    if 'sl2_distance_r' in signal.keys() and signal['sl2_distance_r']:
                        f.write(f"  SL2 Distance: {signal['sl2_distance_r']:.2f}R\n")
                
                # Alternative entry prices
                if 'optimal_entry_price' in signal.keys() and signal['optimal_entry_price']:
                    f.write(f"\nAlternative Entry Prices:\n")
                    f.write(f"  Optimal Entry: ${signal['optimal_entry_price']:.4f}\n")
                    opt_hit = signal['optimal_entry_hit'] if 'optimal_entry_hit' in signal.keys() else 0
                    f.write(f"    Hit: {'Evet' if opt_hit else 'Hayır'}\n")
                    if 'optimal_entry_hit_at' in signal.keys() and signal['optimal_entry_hit_at']:
                        f.write(f"    Hit At: {format_timestamp(signal['optimal_entry_hit_at'])}\n")
                
                if 'conservative_entry_price' in signal.keys() and signal['conservative_entry_price']:
                    f.write(f"  Conservative Entry: ${signal['conservative_entry_price']:.4f}\n")
                    cons_hit = signal['conservative_entry_hit'] if 'conservative_entry_hit' in signal.keys() else 0
                    f.write(f"    Hit: {'Evet' if cons_hit else 'Hayır'}\n")
                    if 'conservative_entry_hit_at' in signal.keys() and signal['conservative_entry_hit_at']:
                        f.write(f"    Hit At: {format_timestamp(signal['conservative_entry_hit_at'])}\n")
                
                # MFE/MAE tracking
                if 'mfe_price' in signal.keys() and signal['mfe_price']:
                    f.write(f"\nMFE/MAE Tracking:\n")
                    f.write(f"  MFE Price: ${signal['mfe_price']:.4f}\n")
                    if 'mfe_at' in signal.keys() and signal['mfe_at']:
                        f.write(f"    MFE At: {format_timestamp(signal['mfe_at'])}\n")
                    if 'mae_price' in signal.keys() and signal['mae_price']:
                        f.write(f"  MAE Price: ${signal['mae_price']:.4f}\n")
                    if 'mae_at' in signal.keys() and signal['mae_at']:
                        f.write(f"    MAE At: {format_timestamp(signal['mae_at'])}\n")
                    if 'final_price' in signal.keys() and signal['final_price']:
                        f.write(f"  Final Price: ${signal['final_price']:.4f}\n")
                    if 'final_outcome' in signal.keys() and signal['final_outcome']:
                        f.write(f"  Final Outcome: {signal['final_outcome']}\n")
                
                # Telegram bilgileri
                f.write(f"\nTelegram:\n")
                f.write(f"  Message ID: {signal['telegram_message_id']}\n")
                f.write(f"  Channel ID: {signal['telegram_channel_id']}\n")
                msg_del = signal['message_deleted'] if 'message_deleted' in signal.keys() else 0
                f.write(f"  Message Deleted: {'Evet' if msg_del else 'Hayır'}\n")
                
                # JSON verileri
                if 'signal_data' in signal.keys() and signal['signal_data']:
                    try:
                        signal_data = json.loads(signal['signal_data'])
                        f.write(f"\nSignal Data (JSON):\n")
                        f.write(json.dumps(signal_data, indent=2, ensure_ascii=False) + "\n")
                    except Exception:
                        f.write(f"\nSignal Data: {signal['signal_data']}\n")
                
                if 'entry_levels' in signal.keys() and signal['entry_levels']:
                    try:
                        entry_levels = json.loads(signal['entry_levels'])
                        f.write(f"\nEntry Levels (JSON):\n")
                        f.write(json.dumps(entry_levels, indent=2, ensure_ascii=False) + "\n")
                    except Exception:
                        f.write(f"\nEntry Levels: {signal['entry_levels']}\n")
                
                if 'signal_score_breakdown' in signal.keys() and signal['signal_score_breakdown']:
                    try:
                        score_breakdown = json.loads(signal['signal_score_breakdown'])
                        f.write(f"\nScore Breakdown (JSON):\n")
                        f.write(json.dumps(score_breakdown, indent=2, ensure_ascii=False) + "\n")
                    except Exception:
                        f.write(f"\nScore Breakdown: {signal['signal_score_breakdown']}\n")
                
                if 'market_context' in signal.keys() and signal['market_context']:
                    try:
                        market_context = json.loads(signal['market_context'])
                        f.write(f"\nMarket Context (JSON):\n")
                        f.write(json.dumps(market_context, indent=2, ensure_ascii=False) + "\n")
                    except Exception:
                        f.write(f"\nMarket Context: {signal['market_context']}\n")
                
                f.write("\n" + "-" * 80 + "\n")
            
            # SIGNAL_PRICE_SNAPSHOTS tablosu
            f.write("\n\n" + "=" * 80 + "\n")
            f.write("SIGNAL_PRICE_SNAPSHOTS TABLOSU\n")
            f.write("=" * 80 + "\n\n")
            
            cursor.execute("SELECT COUNT(*) as count FROM signal_price_snapshots")
            total_snapshots = cursor.fetchone()['count']
            f.write(f"Toplam Snapshot Sayısı: {total_snapshots}\n\n")
            
            cursor.execute("""
                SELECT * FROM signal_price_snapshots 
                ORDER BY timestamp DESC
            """)
            
            snapshots = cursor.fetchall()
            for idx, snapshot in enumerate(snapshots, 1):
                f.write(f"\nSnapshot #{idx}:\n")
                f.write(f"  ID: {snapshot['id']}\n")
                f.write(f"  Signal ID: {snapshot['signal_id']}\n")
                f.write(f"  Timestamp: {format_timestamp(snapshot['timestamp'])}\n")
                f.write(f"  Price: ${snapshot['price']:.4f}\n")
                f.write(f"  Source: {snapshot['source'] or 'N/A'}\n")
            
            # REJECTED_SIGNALS tablosu
            f.write("\n\n" + "=" * 80 + "\n")
            f.write("REJECTED_SIGNALS TABLOSU\n")
            f.write("=" * 80 + "\n\n")
            
            cursor.execute("SELECT COUNT(*) as count FROM rejected_signals")
            total_rejected = cursor.fetchone()['count']
            f.write(f"Toplam Reddedilen Sinyal Sayısı: {total_rejected}\n\n")
            
            cursor.execute("""
                SELECT * FROM rejected_signals 
                ORDER BY created_at DESC
            """)
            
            rejected = cursor.fetchall()
            for idx, rej in enumerate(rejected, 1):
                f.write(f"\nReddedilen Sinyal #{idx}:\n")
                f.write(f"  ID: {rej['id']}\n")
                f.write(f"  Symbol: {rej['symbol']}\n")
                f.write(f"  Direction: {rej['direction']}\n")
                f.write(f"  Confidence: {rej['confidence']*100:.2f}%\n")
                f.write(f"  Signal Price: ${rej['signal_price']:.4f}\n")
                f.write(f"  Created At: {format_timestamp(rej['created_at'])}\n")
                f.write(f"  Rejection Reason: {rej['rejection_reason']}\n")
                
                if 'score_breakdown' in rej.keys() and rej['score_breakdown']:
                    try:
                        score_breakdown = json.loads(rej['score_breakdown'])
                        f.write(f"\n  Score Breakdown (JSON):\n")
                        f.write("  " + json.dumps(score_breakdown, indent=2, ensure_ascii=False).replace("\n", "\n  ") + "\n")
                    except Exception:
                        f.write(f"  Score Breakdown: {rej['score_breakdown']}\n")
                
                if 'market_context' in rej.keys() and rej['market_context']:
                    try:
                        market_context = json.loads(rej['market_context'])
                        f.write(f"\n  Market Context (JSON):\n")
                        f.write("  " + json.dumps(market_context, indent=2, ensure_ascii=False).replace("\n", "\n  ") + "\n")
                    except Exception:
                        f.write(f"  Market Context: {rej['market_context']}\n")
            
            # SIGNAL_METRICS_SUMMARY tablosu
            f.write("\n\n" + "=" * 80 + "\n")
            f.write("SIGNAL_METRICS_SUMMARY TABLOSU\n")
            f.write("=" * 80 + "\n\n")
            
            cursor.execute("SELECT COUNT(*) as count FROM signal_metrics_summary")
            total_summaries = cursor.fetchone()['count']
            f.write(f"Toplam Özet Sayısı: {total_summaries}\n\n")
            
            cursor.execute("""
                SELECT * FROM signal_metrics_summary 
                ORDER BY period_start DESC
            """)
            
            summaries = cursor.fetchall()
            for idx, summary in enumerate(summaries, 1):
                f.write(f"\nÖzet #{idx}:\n")
                f.write(f"  ID: {summary['id']}\n")
                f.write(f"  Period Start: {format_timestamp(summary['period_start'])}\n")
                f.write(f"  Period End: {format_timestamp(summary['period_end'])}\n")
                f.write(f"  Total Signals: {summary['total_signals'] or 'N/A'}\n")
                f.write(f"  Long Signals: {summary['long_signals'] or 'N/A'}\n")
                f.write(f"  Short Signals: {summary['short_signals'] or 'N/A'}\n")
                f.write(f"  Neutral Filtered: {summary['neutral_filtered'] or 'N/A'}\n")
                avg_conf = f"{summary['avg_confidence']*100:.2f}%" if summary['avg_confidence'] else 'N/A'
                f.write(f"  Avg Confidence: {avg_conf}\n")
                
                tp1_rate = f"{summary['tp1_hit_rate']*100:.2f}%" if summary['tp1_hit_rate'] else 'N/A'
                f.write(f"  TP1 Hit Rate: {tp1_rate}\n")
                
                tp2_rate = f"{summary['tp2_hit_rate']*100:.2f}%" if summary['tp2_hit_rate'] else 'N/A'
                f.write(f"  TP2 Hit Rate: {tp2_rate}\n")
                
                tp3_rate = f"{summary['tp3_hit_rate']*100:.2f}%" if summary['tp3_hit_rate'] else 'N/A'
                f.write(f"  TP3 Hit Rate: {tp3_rate}\n")
                
                sl1_rate = f"{summary['sl1_hit_rate']*100:.2f}%" if summary['sl1_hit_rate'] else 'N/A'
                f.write(f"  SL1 Hit Rate: {sl1_rate}\n")
                
                sl2_rate = f"{summary['sl2_hit_rate']*100:.2f}%" if summary['sl2_hit_rate'] else 'N/A'
                f.write(f"  SL2 Hit Rate: {sl2_rate}\n")
                
                avg_mfe = f"{summary['avg_mfe_percent']*100:.2f}%" if summary['avg_mfe_percent'] else 'N/A'
                f.write(f"  Avg MFE: {avg_mfe}\n")
                
                avg_mae = f"{summary['avg_mae_percent']*100:.2f}%" if summary['avg_mae_percent'] else 'N/A'
                f.write(f"  Avg MAE: {avg_mae}\n")
                
                avg_time = f"{summary['avg_time_to_first_target_hours']:.2f} hours" if summary['avg_time_to_first_target_hours'] else 'N/A'
                f.write(f"  Avg Time to First Target: {avg_time}\n")
                f.write(f"  Market Regime: {summary['market_regime'] or 'N/A'}\n")
            
            f.write("\n\n" + "=" * 80 + "\n")
            f.write("DUMP TAMAMLANDI\n")
            f.write("=" * 80 + "\n")
        
        conn.close()
        print(f"✅ Veritabanı dump'ı başarıyla oluşturuldu: {output_path}")
        print(f"   Toplam {total_signals} sinyal, {total_snapshots} snapshot, {total_rejected} reddedilen sinyal, {total_summaries} özet kaydedildi.")
        
    except Exception as e:
        print(f"❌ Hata: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    dump_database()

