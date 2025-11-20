#!/usr/bin/env python3
"""
Historical Simulator for TrendBot (Event-Driven)
------------------------------------------------
Replays past signals from signals.db to simulate portfolio performance.
Uses a strict chronological event stream (Entry -> Exit) to manage margin and PnL.
Implements ISOLATED MARGIN logic with Liquidation checks.

Usage:
    python tools/simulate.py [--send-telegram] [--summary] [--risk 1.0] [--leverage 5] [--balance 10000] [--commission 0.075]
"""
import sqlite3
import os
import sys
import asyncio
import argparse
import copy
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from dotenv import load_dotenv
from telegram import Bot

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

# Default Configuration (can be overridden by CLI args)
DEFAULT_INITIAL_BALANCE = 10000.0
DEFAULT_RISK_PER_TRADE_PERCENT = 1.0
DEFAULT_LEVERAGE = 5
DEFAULT_COMMISSION_RATE = 0.075  # % per side (Binance default)
DEFAULT_MAINTENANCE_MARGIN_RATE = 0.004  # %0.4 (Binance default for small positions)
DB_PATH = "data/signals.db"
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_USER_IDS = os.getenv('ADMIN_USER_IDS', '')
if not ADMIN_USER_IDS:
    ADMIN_USER_IDS = os.getenv('TELEGRAM_ADMIN_ID', '')

@dataclass
class Event:
    timestamp: int
    type: str  # 'ENTRY', 'EXIT_TP', 'EXIT_SL'
    signal: Dict[str, Any]
    details: Dict[str, Any]  # Extra info like price, reason

    def __lt__(self, other):
        return self.timestamp < other.timestamp

class Portfolio:
    def __init__(self, balance: float, commission_rate: float):
        self.initial_balance = balance
        self.balance = balance # Total Balance (Free + Locked)
        self.free_balance = balance # Available for new trades
        self.peak_balance = balance
        self.max_drawdown_pct = 0.0
        self.equity = balance
        self.commission_rate = commission_rate
        self.trades: List[Dict] = []
        self.balance_history: List[float] = [balance]
        
        # Stats
        self.wins = 0
        self.losses = 0
        self.liquidations = 0
        self.gross_profit = 0.0
        self.gross_loss = 0.0
        self.total_commission_paid = 0.0
        
        # Streaks
        self.current_win_streak = 0
        self.current_loss_streak = 0
        self.max_win_streak = 0
        self.max_loss_streak = 0
        
        # Duration
        self.total_duration_seconds = 0
        
        # Directional Stats
        self.long_wins = 0
        self.long_losses = 0
        self.short_wins = 0
        self.short_losses = 0
        
        self.open_trades = 0
        self.locked_margin = 0.0

    def update_drawdown(self):
        if self.balance > self.peak_balance:
            self.peak_balance = self.balance
        
        drawdown = (self.peak_balance - self.balance) / self.peak_balance * 100
        if drawdown > self.max_drawdown_pct:
            self.max_drawdown_pct = drawdown

    def lock_margin(self, amount: float):
        """Locks margin for a new trade (Isolated Margin)."""
        self.free_balance -= amount
        self.locked_margin += amount

    def release_margin(self, amount: float, pnl: float):
        """Releases margin and adds PnL (Isolated Margin)."""
        self.locked_margin -= amount
        self.free_balance += amount + pnl
        self.balance = self.free_balance + self.locked_margin
        self.update_drawdown()
        self.balance_history.append(self.balance)
    
    def pay_commission(self, amount: float):
        """Deducts commission from balance."""
        self.free_balance -= amount
        self.balance = self.free_balance + self.locked_margin
        self.update_drawdown()

    def add_trade_result(self, trade_result: Dict):
        self.trades.append(trade_result)
        
        # Commission Calculation (Entry + Exit)
        position_size = trade_result['position_size']
        entry_comm = position_size * (self.commission_rate / 100)
        exit_comm = position_size * (self.commission_rate / 100)
        total_comm = entry_comm + exit_comm
        self.total_commission_paid += total_comm
        
        # Gross PnL (komisyonsuz)
        gross_pnl = trade_result['pnl']
        
        # Net PnL for statistics (gross_pnl - total_comm)
        net_pnl = gross_pnl - total_comm
        
        # Update Balances: First add gross PnL, then deduct commission
        margin_used = trade_result['margin_used']
        self.release_margin(margin_used, gross_pnl)  # Gross PnL ekleniyor
        self.pay_commission(total_comm)  # Komisyon bakiyeden düşülüyor
        
        direction = trade_result['direction']
        duration = trade_result['duration']
        self.total_duration_seconds += duration
        
        if trade_result['status'] == 'LIQUIDATED':
            self.liquidations += 1
            self.gross_loss += abs(net_pnl)
            self.losses += 1 # Count as loss too
            self.current_loss_streak += 1
            self.current_win_streak = 0
            if self.current_loss_streak > self.max_loss_streak:
                self.max_loss_streak = self.current_loss_streak
            if direction == 'LONG': self.long_losses += 1
            else: self.short_losses += 1

        elif net_pnl > 0:
            self.gross_profit += net_pnl
            self.wins += 1
            self.current_win_streak += 1
            self.current_loss_streak = 0
            if self.current_win_streak > self.max_win_streak:
                self.max_win_streak = self.current_win_streak
                
            if direction == 'LONG': self.long_wins += 1
            else: self.short_wins += 1
        else:
            self.gross_loss += abs(net_pnl)
            self.losses += 1
            self.current_loss_streak += 1
            self.current_win_streak = 0
            if self.current_loss_streak > self.max_loss_streak:
                self.max_loss_streak = self.current_loss_streak
                
            if direction == 'LONG': self.long_losses += 1
            else: self.short_losses += 1

    def get_summary(self) -> Dict:
        total_trades = self.wins + self.losses # Liquidations are included in losses
        win_rate = (self.wins / total_trades * 100) if total_trades > 0 else 0
        pnl_percent = ((self.balance - self.initial_balance) / self.initial_balance) * 100
        
        profit_factor = (self.gross_profit / self.gross_loss) if self.gross_loss > 0 else float('inf')
        
        avg_win = (self.gross_profit / self.wins) if self.wins > 0 else 0
        avg_loss = (self.gross_loss / self.losses) if self.losses > 0 else 0
        
        avg_duration = self.total_duration_seconds / total_trades if total_trades > 0 else 0
        
        long_total = self.long_wins + self.long_losses
        short_total = self.short_wins + self.short_losses
        long_win_rate = (self.long_wins / long_total * 100) if long_total > 0 else 0
        short_win_rate = (self.short_wins / short_total * 100) if short_total > 0 else 0

        return {
            'initial_balance': self.initial_balance,
            'final_balance': self.balance,
            'pnl_amount': self.balance - self.initial_balance,
            'pnl_percent': pnl_percent,
            'total_trades': total_trades,
            'wins': self.wins,
            'losses': self.losses,
            'liquidations': self.liquidations,
            'win_rate': win_rate,
            'open_trades': self.open_trades,
            'locked_margin': self.locked_margin,
            'free_balance': self.free_balance,
            'max_drawdown': self.max_drawdown_pct,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'total_commission': self.total_commission_paid,
            'max_win_streak': self.max_win_streak,
            'max_loss_streak': self.max_loss_streak,
            'avg_duration_seconds': avg_duration,
            'long_stats': {'total': long_total, 'wins': self.long_wins, 'win_rate': long_win_rate},
            'short_stats': {'total': short_total, 'wins': self.short_wins, 'win_rate': short_win_rate},
            'balance_history': self.balance_history
        }

def interpret_results(metrics: Dict) -> List[str]:
    """Generates human-readable insights based on simulation metrics."""
    insights = []
    
    # Liquidation Warning
    if metrics['liquidations'] > 0:
        insights.append(f"💀 **LİKİDASYON UYARISI:** {metrics['liquidations']} işlem likit oldu! Kaldıraç çok yüksek veya SL çok uzak.")

    # 1. Profitability & Efficiency
    pf = metrics['profit_factor']
    if pf > 2.0:
        insights.append(f"✅ **Mükemmel Verimlilik:** Profit Factor {pf:.2f} (Her 1$ kayba karşılık {pf:.2f}$ kazanç).")
    elif pf > 1.5:
        insights.append(f"✅ **İyi Verimlilik:** Profit Factor {pf:.2f}. Sistem sürdürülebilir.")
    elif pf > 1.0:
        insights.append(f"⚠️ **Düşük Verimlilik:** Profit Factor {pf:.2f}. Kâr ediyor ama riskli sınırda.")
    else:
        insights.append(f"❌ **Zarar:** Sistem para kaybediyor (PF: {pf:.2f}).")

    # 2. Risk & Drawdown
    mdd = metrics['max_drawdown']
    if mdd < 10:
        insights.append(f"🛡️ **Düşük Risk:** Max Drawdown sadece %{mdd:.2f}. Sermaye güvende.")
    elif mdd < 20:
        insights.append(f"⚠️ **Orta Risk:** Max Drawdown %{mdd:.2f}. Kabul edilebilir ama dikkatli olunmalı.")
    else:
        insights.append(f"🚨 **YÜKSEK RİSK:** Max Drawdown %{mdd:.2f}! Sermayenin ciddi kısmı erime riski taşıyor.")

    # 3. Streaks
    loss_streak = metrics['max_loss_streak']
    if loss_streak >= 5:
        insights.append(f"🔥 **Psikolojik Baskı:** Arka arkaya {loss_streak} kayıp yaşanmış. Sabırlı olunmalı.")
        
    # 4. Duration
    avg_dur = metrics['avg_duration_seconds']
    hours = avg_dur / 3600
    if hours < 1:
        insights.append(f"⚡ **Scalper:** İşlemler ortalama {hours*60:.0f} dakika sürüyor.")
    elif hours < 24:
        insights.append(f"📅 **Day Trader:** İşlemler ortalama {hours:.1f} saat sürüyor.")
    else:
        insights.append(f"🗓️ **Swing Trader:** İşlemler ortalama {hours/24:.1f} gün sürüyor.")
    
    return insights

def get_db_connection():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def format_timestamp(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime('%d/%m/%Y %H:%M:%S')

def format_duration_str(seconds: int) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}s {minutes}dk"

async def send_telegram_report(report_text: str):
    """Sends the report to the admin user via Telegram."""
    if not TELEGRAM_BOT_TOKEN or not ADMIN_USER_IDS:
        print("⚠️ Telegram credentials missing.")
        return

    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        admin_id = int(ADMIN_USER_IDS.split(',')[0].strip())
        
        chunk_size = 4000
        for i in range(0, len(report_text), chunk_size):
            chunk = report_text[i:i + chunk_size]
            # Use Markdown parse mode for better mobile formatting
            try:
                await bot.send_message(chat_id=admin_id, text=chunk, parse_mode='Markdown')
            except Exception:
                # Fallback to plain text if Markdown parsing fails
                await bot.send_message(chat_id=admin_id, text=chunk)
        print(f"✅ Report sent to admin ID: {admin_id}")
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

def simulate(initial_balance: float, risk_per_trade: float, leverage: int, commission_rate: float, send_telegram: bool = False, summary_only: bool = False, silent: bool = False, auto_optimized: dict = None, mmr: float = DEFAULT_MAINTENANCE_MARGIN_RATE) -> Dict:
    report_buffer = []
    
    def log(message: str = "", detail: bool = True):
        if silent:
            return
        if summary_only and detail:
            return
        print(message)
        report_buffer.append(message)

    # Auto-optimization info will be shown after simulation report header

    log(f"🚀 Starting Professional Simulation (ISOLATED MARGIN)")
    log(f"💰 Initial Balance: ${initial_balance:,.2f}")
    log(f"⚠️  Risk: {risk_per_trade}% | Leverage: {leverage}x | Comm: {commission_rate}%")
    log("-" * 60)

    # Read all signals from database and create immutable snapshot
    # This ensures deterministic results even if DB is updated during simulation
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM signals ORDER BY created_at ASC")
    signals_raw = cursor.fetchall()
    conn.close()  # Close connection immediately after reading
    
    # Convert sqlite3.Row to dict first, then create deep copy to prevent race conditions
    signals = [copy.deepcopy(dict(signal)) for signal in signals_raw]

    # Track simulation time range
    if signals:
        first_signal_time = signals[0]['created_at']
        last_signal_time = signals[-1]['created_at']
        simulation_duration = last_signal_time - first_signal_time
    else:
        first_signal_time = 0
        last_signal_time = 0
        simulation_duration = 0

    # 1. Generate Events
    events: List[Event] = []
    
    for signal in signals:
        events.append(Event(
            timestamp=signal['created_at'],
            type='ENTRY',
            signal=copy.deepcopy(signal),  # Deep copy to ensure immutability
            details={}
        ))
        
        exit_time = None
        exit_type = None
        exit_price = 0.0
        
        # Collect all possible exits with their timestamps
        possible_exits = []
        
        if signal['tp1_hit'] and signal['tp1_hit_at']:
            possible_exits.append({
                'type': 'EXIT_TP',
                'time': signal['tp1_hit_at'],
                'price': signal['tp1_price']
            })
        
        if signal['sl1_hit'] and signal['sl1_hit_at']:
            possible_exits.append({
                'type': 'EXIT_SL',
                'time': signal['sl1_hit_at'],
                'price': signal['sl1_price']
            })
        elif signal['sl1_5_hit'] and signal['sl1_5_hit_at']:
            possible_exits.append({
                'type': 'EXIT_SL',
                'time': signal['sl1_5_hit_at'],
                'price': signal['sl1_5_price']
            })
        elif signal['sl2_hit'] and signal['sl2_hit_at']:
            possible_exits.append({
                'type': 'EXIT_SL',
                'time': signal['sl2_hit_at'],
                'price': signal['sl2_price']
            })
        
        # Select the exit that happened first (chronological order)
        if possible_exits:
            # Sort by timestamp to get the earliest exit
            possible_exits.sort(key=lambda x: x['time'])
            earliest_exit = possible_exits[0]
            exit_type = earliest_exit['type']
            exit_time = earliest_exit['time']
            exit_price = earliest_exit['price']
        
        if exit_type and exit_time:
            events.append(Event(
                timestamp=exit_time,
                type=exit_type,
                signal=copy.deepcopy(signal),  # Deep copy to ensure immutability
                details={'exit_price': exit_price}
            ))

    events.sort()
    
    # Validate chronological order (for debugging)
    if not silent and not summary_only:
        log(f"\n📅 ZAMAN DAMGASI DOĞRULAMA:")
        log(f"   Toplam {len(events)} event bulundu")
        if len(events) > 0:
            log(f"   İlk event: {format_timestamp(events[0].timestamp)}")
            log(f"   Son event: {format_timestamp(events[-1].timestamp)}")
            
            # Check for chronological order
            prev_timestamp = 0
            out_of_order_count = 0
            for i, event in enumerate(events):
                if event.timestamp < prev_timestamp:
                    out_of_order_count += 1
                    log(f"   ⚠️  Sıralama hatası: Event {i} ({format_timestamp(event.timestamp)}) önceki event'ten ({format_timestamp(prev_timestamp)}) önce!")
                prev_timestamp = event.timestamp
            
            if out_of_order_count == 0:
                log(f"   ✅ Tüm event'ler kronolojik sırada")
            else:
                log(f"   ❌ {out_of_order_count} event sıralama hatası var!")
        log("")

    # 3. Process Events
    portfolio = Portfolio(initial_balance, commission_rate)
    active_positions: Dict[str, Dict] = {} # signal_id -> position_data
    step = 1
    
    # Table header for step-by-step tracking
    if not silent and not summary_only:
        log("\n" + "="*120)
        log(f"{'ADIM':<6} {'TARİH':<20} {'İŞLEM':<12} {'COIN':<15} {'YÖN':<6} {'SERBEST (ÖNCE)':<15} {'SERBEST (SONRA)':<15} {'RİSK':<10} {'KOMİSYON':<12} {'NET PNL':<12}")
        log("="*120)

    for event in events:
        current_time_str = format_timestamp(event.timestamp)
        signal = event.signal
        sig_id = signal['signal_id']
        symbol = signal['symbol']
        direction = signal['direction']

        if event.type == 'ENTRY':
            # Calculate Position Size based on Risk
            risk_amount = portfolio.balance * (risk_per_trade / 100)
            entry_price = signal['signal_price']
            
            sl_price = signal['sl2_price'] or signal['sl1_price']
            if not sl_price:
                sl_price = entry_price * 0.95 if direction == 'LONG' else entry_price * 1.05
            
            sl_distance_pct = abs(entry_price - sl_price) / entry_price
            if sl_distance_pct == 0: sl_distance_pct = 0.01
            
            position_size_usd = risk_amount / sl_distance_pct
            margin_required = position_size_usd / leverage
            
            # Liquidation Calculation (Real Binance Formula)
            # Quantity = position_size_usd / entry_price (coin amount)
            # LONG: LP = (Entry × Quantity - Margin) / (Quantity × (1 - MMR))
            # SHORT: LP = (Entry × Quantity + Margin) / (Quantity × (1 + MMR))
            # MMR (Maintenance Margin Rate) = 0.004 (%0.4) for small positions
            quantity = position_size_usd / entry_price
            
            if direction == 'LONG':
                # LONG: Fiyat düştükçe zarar, likidasyon entry'nin altında
                liq_price = (entry_price * quantity - margin_required) / (quantity * (1 - mmr))
            else:
                # SHORT: Fiyat yükseldikçe zarar, likidasyon entry'nin üstünde
                liq_price = (entry_price * quantity + margin_required) / (quantity * (1 + mmr))

            # Smart Filter: Check if Liq is hit before SL
            # User wouldn't enter a trade if they would get liquidated before hitting SL
            skip_trade = False
            skip_reason = ""
            
            if direction == 'LONG':
                if liq_price >= sl_price: # Liq is higher (closer) than SL
                    skip_trade = True
                    skip_reason = f"Likidite Riski (Liq: ${liq_price:.4f} > SL: ${sl_price:.4f})"
            else: # SHORT
                if liq_price <= sl_price: # Liq is lower (closer) than SL
                    skip_trade = True
                    skip_reason = f"Likidite Riski (Liq: ${liq_price:.4f} < SL: ${sl_price:.4f})"

            # Check Funds (Isolated Margin)
            if not skip_trade and margin_required > portfolio.free_balance:
                skip_trade = True
                skip_reason = f"Yetersiz Serbest Bakiye (Gereken: ${margin_required:.2f}, Mevcut: ${portfolio.free_balance:.2f})"

            free_balance_before = portfolio.free_balance
            
            if skip_trade:
                if not silent and not summary_only:
                    log(f"{step:<6} {current_time_str:<20} {'SKIP':<12} {symbol:<15} {'-':<6} ${free_balance_before:>13.2f} {'-':<15} {'-':<10} {'-':<12} {'-':<12}")
                    log(f"      Sebep: {skip_reason}")
            else:
                # Lock Margin
                portfolio.lock_margin(margin_required)
                portfolio.open_trades += 1
                
                active_positions[sig_id] = {
                    'entry_price': entry_price,
                    'position_size_usd': position_size_usd,
                    'margin_used': margin_required,
                    'start_time': event.timestamp,
                    'liq_price': liq_price,
                    'sl_price': sl_price,
                    'risk_amount': risk_amount
                }
                
                if not silent and not summary_only:
                    log(f"{step:<6} {current_time_str:<20} {'ENTRY':<12} {symbol:<15} {direction:<6} ${free_balance_before:>13.2f} ${portfolio.free_balance:>13.2f} ${risk_amount:>8.2f} {'-':<12} {'-':<12}")
                    log(f"      Fiyat: ${entry_price:.4f} | Liq: ${liq_price:.4f} | Margin: ${margin_required:.2f} | Toplam: ${portfolio.balance:.2f}")

        elif event.type in ['EXIT_TP', 'EXIT_SL']:
            if sig_id in active_positions:
                pos = active_positions[sig_id]
                exit_price = event.details['exit_price']
                duration = event.timestamp - pos['start_time']
                
                # Liquidation Check
                is_liquidated = False
                if direction == 'LONG':
                    if pos['sl_price'] <= pos['liq_price']: # SL is below Liq Price -> Guaranteed Liq
                        is_liquidated = True
                        exit_price = pos['liq_price']
                    elif exit_price <= pos['liq_price']: # Hit Liq Price
                        is_liquidated = True
                        exit_price = pos['liq_price']
                else: # SHORT
                    if pos['sl_price'] >= pos['liq_price']: # SL is above Liq Price -> Guaranteed Liq
                        is_liquidated = True
                        exit_price = pos['liq_price']
                    elif exit_price >= pos['liq_price']: # Hit Liq Price
                        is_liquidated = True
                        exit_price = pos['liq_price']

                # Calculate PnL
                if is_liquidated:
                    pnl = -pos['margin_used'] # Lose entire margin
                    status = 'LIQUIDATED'
                    icon = "💀 LIQUIDATED"
                else:
                    price_change_pct = 0.0
                    if direction == 'LONG':
                        price_change_pct = (exit_price - pos['entry_price']) / pos['entry_price']
                    else:
                        price_change_pct = (pos['entry_price'] - exit_price) / pos['entry_price']
                    
                    pnl = pos['position_size_usd'] * price_change_pct
                    status = 'WIN' if event.type == 'EXIT_TP' else 'LOSS'
                    icon = "✅ WIN" if event.type == 'EXIT_TP' else "❌ LOSS"

                # Update Portfolio
                portfolio.open_trades -= 1
                
                # Calculate commission before updating portfolio
                position_size = pos['position_size_usd']
                entry_comm = position_size * (commission_rate / 100)
                exit_comm = position_size * (commission_rate / 100)
                total_comm = entry_comm + exit_comm
                net_pnl = pnl - total_comm
                
                # Store free balance before trade result
                free_balance_before = portfolio.free_balance
                
                trade_result = {
                    'symbol': symbol,
                    'direction': direction,
                    'status': status,
                    'pnl': pnl,  # Gross PnL
                    'margin_used': pos['margin_used'],
                    'position_size': pos['position_size_usd'],
                    'duration': duration
                }
                portfolio.add_trade_result(trade_result)
                
                del active_positions[sig_id]
                
                # Detailed logging
                gross_pnl_str = f"+${pnl:.2f}" if pnl > 0 else f"-${abs(pnl):.2f}"
                net_pnl_str = f"+${net_pnl:.2f}" if net_pnl > 0 else f"-${abs(net_pnl):.2f}"
                
                if not silent and not summary_only:
                    risk_amount = pos.get('risk_amount', 0)
                    log(f"{step:<6} {current_time_str:<20} {status:<12} {symbol:<15} {direction:<6} ${free_balance_before:>13.2f} ${portfolio.free_balance:>13.2f} ${risk_amount:>8.2f} ${total_comm:>10.2f} {net_pnl_str:>11}")
                    log(f"      Çıkış: ${exit_price:.4f} | Gross PnL: {gross_pnl_str} | Süre: {format_duration_str(duration)} | Toplam: ${portfolio.balance:.2f}")
            else:
                pass

        step += 1

    # Final Report
    summary = portfolio.get_summary()
    insights = interpret_results(summary)
    
    # Add simulation duration to summary
    summary['simulation_duration'] = simulation_duration
    summary['first_signal_time'] = first_signal_time
    summary['last_signal_time'] = last_signal_time
    
    # Visual header (Mobile-friendly Telegram format)
    log("📊 *SİMÜLASYON RAPORU (İzole Margin)*", detail=False)
    log("", detail=False)  # Empty line for spacing
    
    # Add auto-optimization info if applicable
    if auto_optimized:
        log("🔍 Optimizasyon Modu: Otomatik", detail=False)
        log(f"✅ En iyi konfigürasyon: Risk %{auto_optimized['risk']} | Kaldıraç {auto_optimized['leverage']}x", detail=False)
        log("", detail=False)  # Empty line after optimization info
    
    # Financials with emojis
    log("💰 *FİNANSAL ÖZET*", detail=False)
    
    pnl_emoji = "📈" if summary['pnl_amount'] > 0 else "📉" if summary['pnl_amount'] < 0 else "➡️"
    log(f"💵 Başlangıç  : ${summary['initial_balance']:>10,.2f}", detail=False)
    log(f"{pnl_emoji} Final      : ${summary['final_balance']:>10,.2f}", detail=False)
    
    pnl_sign = "+" if summary['pnl_amount'] > 0 else ""
    pnl_color = "🟢" if summary['pnl_amount'] > 0 else "🔴" if summary['pnl_amount'] < 0 else "⚪"
    log(f"{pnl_color} Net PnL    : {pnl_sign}${summary['pnl_amount']:>9,.2f} ({summary['pnl_percent']:+.2f}%)", detail=False)

    # Detailed Statistics
    log("\n📈 *İSTATİSTİKLER*", detail=False)
    
    win_rate_emoji = "🟢" if summary['win_rate'] >= 60 else "🟡" if summary['win_rate'] >= 50 else "🔴"
    log(f"{win_rate_emoji} Win Rate   : %{summary['win_rate']:.1f} ({summary['wins']}W-{summary['losses']}L)", detail=False)
    
    dd_risk_level = "Orta" if summary['max_drawdown'] > 10 else "Düşük" if summary['max_drawdown'] < 5 else "Yüksek" if summary['max_drawdown'] > 20 else "Makul"
    dd_emoji = "🟢" if summary['max_drawdown'] < 10 else "🟡" if summary['max_drawdown'] < 20 else "🔴"
    log(f"{dd_emoji} Max DD     : %{summary['max_drawdown']:.2f} ({dd_risk_level})", detail=False)
    
    pf_emoji = "🟢" if summary['profit_factor'] > 1.5 else "🟡" if summary['profit_factor'] > 1.0 else "🔴"
    log(f"{pf_emoji} Profit F.  : {summary['profit_factor']:.2f}", detail=False)
    
    log(f"📊 Toplam     : {summary['total_trades']} işlem", detail=False)
    log(f"💸 Ödenen Kom.: ${portfolio.total_commission_paid:,.2f}", detail=False)
    
    if summary['liquidations'] > 0:
        log(f"💀 Likidasyon  : {summary['liquidations']} adet ⚠️", detail=False)
    
    # Detailed Analysis
    log("\n🔍 *DETAYLI ANALİZ*", detail=False)
    
    # Average Win/Loss
    if summary['wins'] > 0:
        log(f"💚 Ort. Kazanç : ${summary['avg_win']:>10,.2f}", detail=False)
    if summary['losses'] > 0:
        log(f"❌ Ort. Kayıp  : ${summary['avg_loss']:>10,.2f}", detail=False)
    
    # Win/Loss Ratio
    if summary['avg_loss'] > 0:
        win_loss_ratio = summary['avg_win'] / summary['avg_loss']
        log(f"⚖️  K/Z Oranı  : {win_loss_ratio:.2f}x", detail=False)
    
    # Streaks
    streak_emoji = "🔥" if summary['max_win_streak'] >= 5 else "✅"
    log(f"{streak_emoji} Max Seri    : {summary['max_win_streak']}W/{summary['max_loss_streak']}L", detail=False)
    
    # Long/Short Stats
    if summary['long_stats']['total'] > 0:
        long_emoji = "🟢" if summary['long_stats']['win_rate'] >= 50 else "🔴"
        log(f"📊 LONG        : {summary['long_stats']['wins']}W/{summary['long_stats']['total']}T (%{summary['long_stats']['win_rate']:.1f})", detail=False)
    
    if summary['short_stats']['total'] > 0:
        short_emoji = "🟢" if summary['short_stats']['win_rate'] >= 50 else "🔴"
        log(f"📉 SHORT       : {summary['short_stats']['wins']}W/{summary['short_stats']['total']}T (%{summary['short_stats']['win_rate']:.1f})", detail=False)

    # AI Insights with visual formatting
    
    pf = summary['profit_factor']
    if pf > 2.0: 
        verim = "Verim: Mükemmel 🎯"
        verim_emoji = "🌟"
    elif pf > 1.5: 
        verim = "Verim: İyi 👍"
        verim_emoji = "✅"
    elif pf > 1.0: 
        verim = "Verim: Düşük, risk sınırda"
        verim_emoji = "⚠️"
    else: 
        verim = "Verim: Zarar"
        verim_emoji = "❌"
    log(f"{verim_emoji} {verim}", detail=False)
    
    ls = summary['max_loss_streak']
    if ls >= 5: 
        psikoloji = f"{ls} ardışık kayıp riski"
        psikoloji_emoji = "😰"
    else: 
        psikoloji = "Psikoloji: Kontrol altında"
        psikoloji_emoji = "😊"
    log(f"{psikoloji_emoji} {psikoloji}", detail=False)
    
    avg_dur = summary['avg_duration_seconds']
    hours = avg_dur / 3600
    minutes = (avg_dur % 3600) / 60
    if avg_dur < 3600: 
        style = "Scalper (<1 saat)"
        style_emoji = "⚡"
    elif avg_dur < 86400: 
        style = f"Day Trader ({int(hours)}sa {int(minutes)}dk)"
        style_emoji = "📅"
    else: 
        style = "Swing Trader (>1 gün)"
        style_emoji = "🗓️"
    log(f"{style_emoji} {style}", detail=False)
    
    # Time Range
    if summary['simulation_duration'] > 0:
        duration_days = summary['simulation_duration'] / 86400
        start_date = format_timestamp(summary['first_signal_time']).split()[0]
        end_date = format_timestamp(summary['last_signal_time']).split()[0]
        
        if duration_days < 1:
            duration_str = f"{duration_days * 24:.1f} saat"
        elif duration_days < 30:
            duration_str = f"{duration_days:.1f} gün"
        else:
            duration_str = f"{duration_days / 30:.1f} ay"
        
        
        log(f"\n📆 {start_date} - {end_date}", detail=False)
        log(f"⏱️  Süre: {duration_str}", detail=False)

    if send_telegram:
        full_report = "\n".join(report_buffer)
        asyncio.run(send_telegram_report(full_report))
        
    return summary

def run_optimization(initial_balance: float, commission_rate: float, silent: bool = False, show_all_rankings: bool = False, mmr: float = DEFAULT_MAINTENANCE_MARGIN_RATE, top_n: int = 10):
    if not silent:
        print(f"🧪 OPTİMİZASYON MODU BAŞLATILIYOR...")
        print(f"💰 Başlangıç Bakiyesi: ${initial_balance:,.2f}")
        print(f"💸 Komisyon Oranı: %{commission_rate}")
        print("-" * 60)
    
    risk_ranges = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    leverage_ranges = [1, 2, 3, 4, 5, 7, 10, 12, 15, 20, 25, 30, 35, 40, 45, 50]
    
    results = []
    total_combinations = len(risk_ranges) * len(leverage_ranges)
    count = 0
    
    if not silent:
        print(f"⏳ Toplam {total_combinations} kombinasyon test ediliyor...")
    
    for risk in risk_ranges:
        for lev in leverage_ranges:
            count += 1
            # Print progress every 10 steps
            if not silent and count % 10 == 0:
                print(f"   ... {count}/{total_combinations} tamamlandı")
                
            summary = simulate(
                initial_balance=initial_balance,
                risk_per_trade=risk,
                leverage=lev,
                commission_rate=commission_rate,
                send_telegram=False,
                summary_only=True,
                silent=True,
                mmr=mmr
            )
            
            # Calculate risk-adjusted return and composite score
            # If MaxDD is 0 and PnL > 0, this is the best case (infinite risk-adjusted return)
            if summary['max_drawdown'] > 0:
                risk_adj_return = summary['pnl_percent'] / summary['max_drawdown']
                composite_score = (summary['pnl_percent'] * summary['profit_factor']) / summary['max_drawdown']
            elif summary['pnl_percent'] > 0:
                # No drawdown with positive return = perfect scenario
                risk_adj_return = float('inf')
                composite_score = float('inf')
            else:
                # No drawdown, no profit = neutral
                risk_adj_return = 0
                composite_score = 0
            
            results.append({
                'risk': risk,
                'leverage': lev,
                'pnl_amount': summary['pnl_amount'],
                'pnl_percent': summary['pnl_percent'],
                'max_drawdown': summary['max_drawdown'],
                'profit_factor': summary['profit_factor'],
                'trades': summary['total_trades'],
                'liquidations': summary['liquidations'],
                'risk_adj_return': risk_adj_return,
                'composite_score': composite_score
            })
    
    # Filter results to only configurations with sufficient data
    MIN_TRADES = 5  # Minimum trades for statistical significance
    valid_results = [r for r in results if r['trades'] >= MIN_TRADES]
    
    if show_all_rankings and not silent:
        # Show all ranking methods
        print("\n" + "="*90)
        print("📊 ÇOKLU ANALİZ SONUÇLARI")
        print(f"ℹ️  Minimum {MIN_TRADES} trade olan konfigürasyonlar gösteriliyor (istatistiksel güvenilirlik)")
        print("="*90)
        
        # 1. Risk-Adjusted Return
        sorted_rar = sorted(valid_results, key=lambda x: x['risk_adj_return'], reverse=True)
        print("\n🎯 EN İYİ 5 KONFİGÜRASYON (Risk-Adjusted Return)")
        print("-" * 90)
        for i, res in enumerate(sorted_rar[:5]):
            pnl_str = f"+${res['pnl_amount']:,.0f}" if res['pnl_amount'] > 0 else f"${res['pnl_amount']:,.0f}"
            print(f"{i+1}. Risk {res['risk']}% | {res['leverage']}x → R/R: {res['risk_adj_return']:.2f} | PnL: {pnl_str} | DD: {res['max_drawdown']:.1f}%")
        
        # 2. Maximum PnL
        sorted_pnl = sorted(valid_results, key=lambda x: x['pnl_amount'], reverse=True)
        print("\n💰 EN İYİ 5 KONFİGÜRASYON (Maksimum PnL)")
        print("-" * 90)
        for i, res in enumerate(sorted_pnl[:5]):
            pnl_str = f"+${res['pnl_amount']:,.0f}" if res['pnl_amount'] > 0 else f"${res['pnl_amount']:,.0f}"
            print(f"{i+1}. Risk {res['risk']}% | {res['leverage']}x → PnL: {pnl_str} ({res['pnl_percent']:.1f}%) | DD: {res['max_drawdown']:.1f}% | PF: {res['profit_factor']:.2f}")
        
        # 3. Profit Factor (filter out empty configs)
        valid_results = [r for r in results if r['trades'] > 0]
        sorted_pf = sorted(valid_results, key=lambda x: x['profit_factor'], reverse=True)
        print("\n🎯 EN İYİ 5 KONFİGÜRASYON (Profit Factor - Tutarlılık)")
        print("-" * 90)
        for i, res in enumerate(sorted_pf[:5]):
            pnl_str = f"+${res['pnl_amount']:,.0f}" if res['pnl_amount'] > 0 else f"${res['pnl_amount']:,.0f}"
            print(f"{i+1}. Risk {res['risk']}% | {res['leverage']}x → PF: {res['profit_factor']:.2f} | PnL: {pnl_str} | DD: {res['max_drawdown']:.1f}%")
        
        # 4. Composite Score
        sorted_comp = sorted(valid_results, key=lambda x: x['composite_score'], reverse=True)
        print("\n⚖️ EN İYİ 5 KONFİGÜRASYON (Composite Score)")
        print("-" * 90)
        for i, res in enumerate(sorted_comp[:5]):
            pnl_str = f"+${res['pnl_amount']:,.0f}" if res['pnl_amount'] > 0 else f"${res['pnl_amount']:,.0f}"
            print(f"{i+1}. Risk {res['risk']}% | {res['leverage']}x → Score: {res['composite_score']:.2f} | PnL: {pnl_str} | PF: {res['profit_factor']:.2f}")
        
        print("\n" + "="*90)
        print("ℹ️  Profit Factor (PF) varsayılan sıralama kriteri olarak kullanılacak.")
        print("="*90)
    elif not silent:
        # Show PnL-first rankings (default behavior for parameterless run)
        MIN_TRADES = 5
        valid_results = [r for r in results if r['trades'] >= MIN_TRADES]
        
        # 1. Maximum PnL Ranking (primary)
        sorted_pnl = sorted(valid_results, key=lambda x: x['pnl_amount'], reverse=True)
        print("\n" + "="*90)
        print(f"💰 EN İYİ {top_n} KONFİGÜRASYON (Maksimum PnL) - Min {MIN_TRADES} trade")
        print("="*90)
        print(f"{'Rank':<5} | {'Risk':<6} | {'Lev':<5} | {'PnL ($)':<12} | {'PnL (%)':<8} | {'MaxDD':<8} | {'PF':<6} | {'R/R':<6} | {'Liq':<4}")
        print("-" * 90)
        
        for i, res in enumerate(sorted_pnl[:top_n]):
            rank = i + 1
            pnl_str = f"${res['pnl_amount']:,.2f}"
            if res['pnl_amount'] > 0: pnl_str = "+" + pnl_str
            
            print(f"{rank:<5} | {res['risk']:<4}% | {res['leverage']:<3}x  | {pnl_str:<12} | {res['pnl_percent']:>6.2f}% | {res['max_drawdown']:>6.2f}% | {res['profit_factor']:>4.2f} | {res['risk_adj_return']:>4.2f} | {res['liquidations']:<4}")
            
        print("="*90)
        
        # 2. Profit Factor Ranking (secondary)
        sorted_pf = sorted(valid_results, key=lambda x: x['profit_factor'], reverse=True)
        print("\n" + "="*90)
        print(f"🏆 EN İYİ {top_n} KONFİGÜRASYON (Profit Factor) - Min {MIN_TRADES} trade")
        print("="*90)
        print(f"{'Rank':<5} | {'Risk':<6} | {'Lev':<5} | {'PnL ($)':<12} | {'PnL (%)':<8} | {'MaxDD':<8} | {'PF':<6} | {'R/R':<6} | {'Liq':<4}")
        print("-" * 90)
        
        for i, res in enumerate(sorted_pf[:top_n]):
            rank = i + 1
            pnl_str = f"${res['pnl_amount']:,.2f}"
            if res['pnl_amount'] > 0: pnl_str = "+" + pnl_str
            
            print(f"{rank:<5} | {res['risk']:<4}% | {res['leverage']:<3}x  | {pnl_str:<12} | {res['pnl_percent']:>6.2f}% | {res['max_drawdown']:>6.2f}% | {res['profit_factor']:>4.2f} | {res['risk_adj_return']:>4.2f} | {res['liquidations']:<4}")
            
        print("="*90)
        results = sorted_pnl  # Return PnL sorted for best config selection
    else:
        # Silent mode - filter and sort by Profit Factor
        MIN_TRADES = 5
        valid_results = [r for r in results if r['trades'] >= MIN_TRADES]
        results = sorted(valid_results, key=lambda x: x['pnl_amount'], reverse=True)
    
    # Return best configuration (always based on Profit Factor, min 5 trades)
    if len(results) == 0:
        # Fallback: no config with 5+ trades, use all results
        results = sorted(results if 'results' in locals() else [], key=lambda x: x.get('profit_factor', 0), reverse=True)
    
    best = results[0] if results else {'risk': 1.0, 'leverage': 1}
    return {'risk': best['risk'], 'leverage': best['leverage']}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TrendBot Event-Driven Simulator')
    parser.add_argument('--send-telegram', action='store_true', help='Send report to Telegram Admin')
    parser.add_argument('--summary', action='store_true', help='Only output condensed summary report')
    parser.add_argument('--opt', action='store_true', help='Run optimization mode (parameter sweep)')
    parser.add_argument('--balance', type=float, default=DEFAULT_INITIAL_BALANCE, help='Initial Balance (USDT)')
    parser.add_argument('--risk', type=float, default=DEFAULT_RISK_PER_TRADE_PERCENT, help='Risk per trade (%%)')
    parser.add_argument('--leverage', type=int, default=DEFAULT_LEVERAGE, help='Leverage (x)')
    parser.add_argument('--commission', type=float, default=DEFAULT_COMMISSION_RATE, help='Commission rate per side (%%)')
    parser.add_argument('--mmr', type=float, default=DEFAULT_MAINTENANCE_MARGIN_RATE, help='Maintenance Margin Rate (default: 0.004 = 0.4%%)')
    
    args = parser.parse_args()
    
    if args.send_telegram:
        # Auto-optimize before sending to Telegram
        print("🔍 Otomatik optimizasyon çalıştırılıyor...")
        best_config = run_optimization(args.balance, args.commission, silent=True, mmr=args.mmr)
        print(f"✅ En iyi konfigürasyon bulundu: Risk %{best_config['risk']} | Kaldıraç {best_config['leverage']}x\n")
        
        # Run simulation with best parameters and send to Telegram
        simulate(
            initial_balance=args.balance,
            risk_per_trade=best_config['risk'],
            leverage=best_config['leverage'],
            commission_rate=args.commission,
            send_telegram=True,
            summary_only=True,
            auto_optimized=best_config,
            mmr=args.mmr
        )
    elif args.opt:
        # Explicit --opt flag: Show all rankings (top 10)
        run_optimization(args.balance, args.commission, show_all_rankings=True, mmr=args.mmr, top_n=10)
    elif args.risk != DEFAULT_RISK_PER_TRADE_PERCENT or args.leverage != DEFAULT_LEVERAGE or args.summary:
        # Explicit simulation parameters provided: Run normal simulation
        simulate(
            initial_balance=args.balance,
            risk_per_trade=args.risk,
            leverage=args.leverage,
            commission_rate=args.commission,
            send_telegram=False,
            summary_only=args.summary,
            mmr=args.mmr
        )
    else:
        # Default behavior: Run optimization with top 5 results (Profit Factor + PnL)
        run_optimization(args.balance, args.commission, show_all_rankings=False, mmr=args.mmr, top_n=5)
