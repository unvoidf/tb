#!/usr/bin/env python3
"""
Historical Simulator for TrendBot
---------------------------------
Replays past signals from signals.db to simulate portfolio performance.
Uses existing TP/SL hit data stored in the database.

Usage:
    python tools/simulate.py [--send-telegram]
"""
import sqlite3
import os
import sys
import asyncio
import argparse
from datetime import datetime
from typing import List, Dict, Optional
from dotenv import load_dotenv
from telegram import Bot
from telegram.constants import ParseMode

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

# Configuration
INITIAL_BALANCE = 10000.0  # USDT
RISK_PER_TRADE_PERCENT = 1.0  # %1 risk per trade
LEVERAGE = 5  # Default leverage if not specified
DB_PATH = "data/signals.db"
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_USER_IDS = os.getenv('ADMIN_USER_IDS', '')
if not ADMIN_USER_IDS:
    ADMIN_USER_IDS = os.getenv('TELEGRAM_ADMIN_ID', '')

class Portfolio:
    def __init__(self, balance: float):
        self.initial_balance = balance
        self.balance = balance
        self.equity = balance
        self.trades: List[Dict] = []
        self.wins = 0
        self.losses = 0
        self.open_trades = 0

    def add_trade(self, trade_result: Dict):
        self.trades.append(trade_result)
        self.balance += trade_result['pnl']
        self.equity = self.balance
        
        if trade_result['status'] == 'WIN':
            self.wins += 1
        elif trade_result['status'] == 'LOSS':
            self.losses += 1
        elif trade_result['status'] == 'OPEN':
            self.open_trades += 1

    def get_summary(self) -> Dict:
        total_trades = self.wins + self.losses
        win_rate = (self.wins / total_trades * 100) if total_trades > 0 else 0
        pnl_percent = ((self.balance - self.initial_balance) / self.initial_balance) * 100
        
        return {
            'initial_balance': self.initial_balance,
            'final_balance': self.balance,
            'pnl_amount': self.balance - self.initial_balance,
            'pnl_percent': pnl_percent,
            'total_trades': total_trades,
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': win_rate,
            'open_trades': self.open_trades
        }

def get_db_connection():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def format_timestamp(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime('%d/%m/%Y %H:%M:%S')

def format_duration(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours} saat {minutes} dakika"

async def send_telegram_report(report_text: str):
    """Sends the report to the admin user via Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN not found in .env")
        return

    if not ADMIN_USER_IDS:
        print("⚠️ ADMIN_USER_IDS not found in .env")
        return

    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        # Get the first admin ID (assuming single admin for now)
        admin_id = int(ADMIN_USER_IDS.split(',')[0].strip())
        
        # Split message if too long (Telegram limit is 4096 chars)
        chunk_size = 4000
        for i in range(0, len(report_text), chunk_size):
            chunk = report_text[i:i + chunk_size]
            await bot.send_message(chat_id=admin_id, text=chunk) # Removed ParseMode.MARKDOWN to avoid errors with special chars
            
        print(f"✅ Report sent to admin ID: {admin_id}")
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

def simulate(send_telegram: bool = False, summary_only: bool = False):
    report_buffer = []
    
    def log(message: str = "", detail: bool = True):
        if summary_only and detail:
            return
        print(message)
        report_buffer.append(message)

    log(f"🚀 Starting Historical Simulation")
    log(f"💰 Initial Balance: ${INITIAL_BALANCE:,.2f}")
    log(f"⚠️  Risk Per Trade: {RISK_PER_TRADE_PERCENT}%")
    log("-" * 60)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch all signals sorted by creation time
    cursor.execute("""
        SELECT * FROM signals 
        ORDER BY created_at ASC
    """)
    signals = cursor.fetchall()

    portfolio = Portfolio(INITIAL_BALANCE)
    active_trades = []  # List of currently open trades: [{'signal_id': str, 'margin_used': float, 'exit_time': int|None}]
    skipped_trades = 0  # Count of trades skipped due to insufficient margin

    for signal in signals:
        current_time = signal['created_at']
        
        # ZAMAN TÜNELİ: Bu zamana kadar açık olan işlemleri kontrol et
        # Kapalı olan işlemlerin margin'ini serbest bırak
        trades_to_close = []
        for active_trade in active_trades:
            # Eğer exit_time varsa ve geçtiyse, bu işlem kapandı
            if active_trade['exit_time'] and active_trade['exit_time'] <= current_time:
                trades_to_close.append(active_trade)
        
        # Kapalı işlemleri listeden çıkar (margin serbest kalır)
        for closed_trade in trades_to_close:
            active_trades.remove(closed_trade)
        
        # Şu anki kilitli margin'i hesapla (sadece açık işlemler)
        current_locked_margin = sum(t['margin_used'] for t in active_trades)
        available_balance = portfolio.balance - current_locked_margin
        
        # Yeni sinyalin durumunu belirle
        status = "OPEN"
        exit_price = 0.0
        exit_reason = "UNKNOWN"
        exit_time = 0
        
        if signal['tp1_hit']:
            status = "WIN"
            exit_price = signal['tp1_price']
            exit_reason = "TP1"
            exit_time = signal['tp1_hit_at'] or (signal['created_at'] + 3600)
        elif signal['sl1_hit'] or signal['sl1_5_hit'] or signal['sl2_hit']:
            status = "LOSS"
            if signal['sl1_hit']:
                exit_price = signal['sl1_price']
                exit_time = signal['sl1_hit_at']
            elif signal['sl1_5_hit']:
                exit_price = signal['sl1_5_price']
                exit_time = signal['sl1_5_hit_at']
            else:
                exit_price = signal['sl2_price']
                exit_time = signal['sl2_hit_at']
            
            exit_reason = "SL"
            if not exit_time: 
                exit_time = signal['created_at'] + 3600
        else:
            status = "OPEN"
        
        # Pozisyon büyüklüğü hesaplama (hem OPEN hem kapalı işlemler için aynı)
        risk_amount = portfolio.balance * (RISK_PER_TRADE_PERCENT / 100)
        entry_price = signal['signal_price']
        sl_price = signal['sl2_price'] or signal['sl1_price']  # Önce SL2'yi kontrol et
        
        if not sl_price:
            # Fallback: %5 varsayılan SL
            sl_price = entry_price * 0.95 if signal['direction'] == 'LONG' else entry_price * 1.05
             
        sl_distance_pct = abs(entry_price - sl_price) / entry_price
        if sl_distance_pct == 0: 
            sl_distance_pct = 0.01

        position_size_usd = risk_amount / sl_distance_pct
        # Leverage ile maksimum pozisyon büyüklüğü
        max_position = available_balance * LEVERAGE
        if position_size_usd > max_position:
            position_size_usd = max_position

        margin_used = position_size_usd / LEVERAGE
        
        # MARGIN KONTROLÜ: Yeterli margin var mı?
        if margin_used > available_balance:
            # Margin yetersiz - bu işlemi atla
            skipped_trades += 1
            log(f"\n⏭️  ATLANAN SİNYAL (Margin Yetersiz):")
            log(f"🟢 {signal['direction']} | {signal['symbol']}")
            log(f"🕐 {format_timestamp(signal['created_at'])}")
            log(f"💰 Gereken Margin: ${margin_used:,.2f}")
            log(f"💵 Kullanılabilir: ${available_balance:,.2f}")
            log(f"🔒 Kilitli Margin: ${current_locked_margin:,.2f} ({len(active_trades)} açık işlem)")
            continue
        
        # Margin yeterli - işlemi aç
        if status == "OPEN":
            # Açık işlem - margin kilitlenecek
            trade_result = {
                'symbol': signal['symbol'],
                'direction': signal['direction'],
                'status': status,
                'pnl': 0.0,
                'entry_price': entry_price,
                'exit_price': 0.0,
                'exit_reason': "OPEN",
                'margin_used': margin_used
            }
            portfolio.add_trade(trade_result)
            
            # Active trades'a ekle (exit_time yok, gerçekten açık)
            active_trades.append({
                'signal_id': signal['signal_id'],
                'margin_used': margin_used,
                'exit_time': None
            })
            
            log(f"\n📊 AÇILAN SİNYAL:")
            log(f"🟢 {signal['direction']} | {signal['symbol']}")
            log(f"🕐 {format_timestamp(signal['created_at'])}")
            log(f"🔔 Sinyal: ${entry_price:.6f}")
            log(f"💰 Margin Kullanıldı: ${margin_used:,.2f}")
            log(f"💵 Kalan Kullanılabilir: ${available_balance - margin_used:,.2f}")
            log(f"🔒 Toplam Kilitli Margin: ${current_locked_margin + margin_used:,.2f} ({len(active_trades)} açık işlem)")
            continue

        # Kapalı işlem (WIN/LOSS) - Bu işlem zaten kapandı, margin kontrolü yapmaya gerek yok
        # Çünkü bu işlem açıldığında margin kullanıldı ve exit_time'da serbest kaldı
        # Sadece PnL hesaplayıp portföyü güncelle
        
        # Calculate PnL
        price_change_pct = 0.0
        if signal['direction'] == 'LONG':
            price_change_pct = (exit_price - entry_price) / entry_price
        else:
            price_change_pct = (entry_price - exit_price) / entry_price
            
        trade_pnl = position_size_usd * price_change_pct
        
        trade_result = {
            'symbol': signal['symbol'],
            'direction': signal['direction'],
            'status': status,
            'pnl': trade_pnl,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'exit_reason': exit_reason,
            'margin_used': margin_used
        }
        portfolio.add_trade(trade_result)
        
        # Kapalı işlemler için active_trades'a ekle (exit_time ile)
        # Bu işlem, exit_time'a kadar margin'i kilitli tutacak
        # (Gelecekteki sinyaller için margin hesaplamasında kullanılacak)
        active_trades.append({
            'signal_id': signal['signal_id'],
            'margin_used': margin_used,
            'exit_time': exit_time
        })

        duration = exit_time - signal['created_at'] if exit_time else 0
        duration_str = format_duration(duration) if duration > 0 else "???"
        
        icon = "✅" if status == "WIN" else "❌"
        pnl_color = "+" if trade_pnl > 0 else ""
        
        log(f"\n{status} OLAN SİNYAL:")
        log(f"🟢 {signal['direction']} | {signal['symbol']}")
        log(f"🕐 {format_timestamp(signal['created_at'])}")
        log(f"🔔 Sinyal: ${entry_price:.6f}")
        log(f"🏁 Çıkış: ${exit_price:.6f} ({exit_reason})")
        log(f"{icon} PnL: {pnl_color}${trade_pnl:.2f} ({price_change_pct*100:.2f}%)")
        log(f"⏱ {duration_str}")
        log(f"💵 Bakiye: ${portfolio.balance:,.2f}")
    # Final Report
    summary = portfolio.get_summary()
    
    # Calculate EXACT locked margin for open trades
    total_margin_used = 0.0
    open_symbols = []
    
    for trade in portfolio.trades:
        if trade['status'] == 'OPEN':
            open_symbols.append(f"{trade['symbol']} ({trade['direction']})")
            # Margin = Position Size USD / Leverage
            # Position Size USD was calculated during entry: risk_amount / sl_distance_pct
            # But we didn't store it in trade_result. Let's recalculate or store it.
            # Since we don't have it stored, we can infer it from PnL if it wasn't 0, but PnL is 0 for open.
            # Better way: We need to store 'margin_used' in trade_result.
            if 'margin_used' in trade:
                total_margin_used += trade['margin_used']

    if summary_only:
        open_count = len(open_symbols)
        available = summary['final_balance'] - total_margin_used
        pnl_sign = "+" if summary['pnl_amount'] >= 0 else ""
        win_rate = summary['win_rate']
        
        # İlk sinyal tarihini al
        first_signal_date = ""
        if signals:
            first_signal_date = format_timestamp(signals[0]['created_at'])
        
        log("📊 TRADE SIMULATION (w/ --summary flag)", detail=False)
        log("", detail=False)  # Boş satır
        if first_signal_date:
            log(f"📅 Starting Date: {first_signal_date}", detail=False)
        log(f"💰 Starting Balance: ${INITIAL_BALANCE:,.2f} USD", detail=False)
        log("", detail=False)  # Boş satır
        
        # PnL için emoji seç (pozitifse yeşil, negatifse kırmızı)
        pnl_emoji = "🟢" if summary['pnl_amount'] >= 0 else "🔴"
        
        log(f"💰 Actual Balance: ${summary['final_balance']:,.2f}", detail=False)
        log(f"{pnl_emoji} PnL: {pnl_sign}${summary['pnl_amount']:,.2f} ({summary['pnl_percent']:.2f}%)", detail=False)
        log(f"🏆 Win Rate: {win_rate:.1f}%", detail=False)
        log("", detail=False)  # Boş satır
        log(f"🔒 Locked in Margin: ${total_margin_used:,.2f}", detail=False)
        log(f"💵 Free Balance: ${available:,.2f}", detail=False)
        log(f"✅ {summary['wins']} ❌ {summary['losses']} | ⏭️ {skipped_trades} | 🔓 {open_count}", detail=False)
    else:
        log("\n" + "="*30)
        log("📊 SİMÜLASYON RAPORU")
        log("="*30)
        log(f"Başlangıç Bakiyesi: ${summary['initial_balance']:,.2f}")
        log(f"Güncel Bakiye:      ${summary['final_balance']:,.2f}")
        log(f"Net Kâr/Zarar:      ${summary['pnl_amount']:,.2f} ({summary['pnl_percent']:.2f}%)")
        log("-" * 30)
        log(f"Toplam İşlem:       {summary['total_trades']}")
        log(f"✅ Kazanç (TP):     {summary['wins']}")
        log(f"❌ Kayıp (SL):      {summary['losses']}")
        log(f"⏭️  Atlanan:         {skipped_trades} (Margin yetersiz)")
        log(f"🏆 Win Rate:        {summary['win_rate']:.1f}%")
        log("-" * 30)
        
        if open_symbols:
            log(f"🔓 Açık Pozisyonlar ({len(open_symbols)}):")
            chunks = [open_symbols[i:i + 3] for i in range(0, len(open_symbols), 3)]
            for chunk in chunks:
                log(", ".join(chunk))
                
            available = summary['final_balance'] - total_margin_used
            log(f"\n💰 Tahmini Kullanılabilir Bakiye: ${available:,.2f}")
            log(f"(Kilitli Margin: ${total_margin_used:,.2f})")
        else:
            log("🔓 Açık Pozisyon Yok")
            log(f"💰 Kullanılabilir Bakiye: ${summary['final_balance']:,.2f}")
            
        log("="*30)

    conn.close()

    if send_telegram:
        full_report = "\n".join(report_buffer)
        asyncio.run(send_telegram_report(full_report))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TrendBot Historical Simulator')
    parser.add_argument('--send-telegram', action='store_true', help='Send report to Telegram Admin')
    parser.add_argument('--summary', action='store_true', help='Only output condensed summary report')
    args = parser.parse_args()
    
    simulate(send_telegram=args.send_telegram, summary_only=args.summary)
