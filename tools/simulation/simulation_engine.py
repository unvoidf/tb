"""
Simulation Engine
-----------------
Core simulation engine for event-driven backtesting.
"""
import copy
import os
from typing import List, Dict, Optional, Any
from .models import Event
from .portfolio import Portfolio
from .position_manager import PositionSlot, get_position_slot
from .database_manager import DatabaseManager
from .report_generator import ReportGenerator
from .notification_manager import NotificationManager
from .utils import format_timestamp, format_duration_str

DEFAULT_MAINTENANCE_MARGIN_RATE = 0.004  # %0.4 (Binance default)
DEFAULT_MIN_SL_LIQ_BUFFER = 0.01  # %1 (default buffer between SL and liquidation)


class SimulationEngine:
    """Core engine for running simulations."""
    
    def __init__(
        self,
        initial_balance: float,
        risk_per_trade: float,
        leverage: int,
        commission_rate: float,
        mmr: float = DEFAULT_MAINTENANCE_MARGIN_RATE,
        min_sl_liq_buffer: Optional[float] = None,
        db_path: str = "data/signals.db"
    ):
        self.initial_balance = initial_balance
        self.risk_per_trade = risk_per_trade
        self.leverage = leverage
        self.commission_rate = commission_rate
        self.mmr = mmr
        self.min_sl_liq_buffer = min_sl_liq_buffer or self._load_min_sl_liq_buffer()
        
        self.db_manager = DatabaseManager(db_path)
        self.portfolio: Optional[Portfolio] = None
        self.report_generator: Optional[ReportGenerator] = None
        self.notification_manager: Optional[NotificationManager] = None
        
        self.events: List[Event] = []
        self.signals: List[Dict[str, Any]] = []
    
    def generate_events(self) -> List[Event]:
        """Generates events from signals."""
        events: List[Event] = []
        
        for signal in self.signals:
            # Entry event
            events.append(Event(
                timestamp=signal['created_at'],
                type='ENTRY',
                signal=copy.deepcopy(signal),
                details={}
            ))
            
            # Collect all possible exits
            exit_time = None
            exit_type = None
            exit_price = 0.0
            
            possible_exits = []
            
            if signal.get('tp1_hit') and signal.get('tp1_hit_at'):
                possible_exits.append({
                    'type': 'EXIT_TP',
                    'time': signal['tp1_hit_at'],
                    'price': signal['tp1_price']
                })
            
            if signal.get('sl1_hit') and signal.get('sl1_hit_at'):
                possible_exits.append({
                    'type': 'EXIT_SL',
                    'time': signal['sl1_hit_at'],
                    'price': signal['sl1_price']
                })
            elif signal.get('sl1_5_hit') and signal.get('sl1_5_hit_at'):
                possible_exits.append({
                    'type': 'EXIT_SL',
                    'time': signal['sl1_5_hit_at'],
                    'price': signal['sl1_5_price']
                })
            elif signal.get('sl2_hit') and signal.get('sl2_hit_at'):
                possible_exits.append({
                    'type': 'EXIT_SL',
                    'time': signal['sl2_hit_at'],
                    'price': signal['sl2_price']
                })
            
            # Select the exit that happened first
            if possible_exits:
                possible_exits.sort(key=lambda x: x['time'])
                earliest_exit = possible_exits[0]
                exit_type = earliest_exit['type']
                exit_time = earliest_exit['time']
                exit_price = earliest_exit['price']
            
            if exit_type and exit_time:
                events.append(Event(
                    timestamp=exit_time,
                    type=exit_type,
                    signal=copy.deepcopy(signal),
                    details={'exit_price': exit_price}
                ))
        
        events.sort()
        return events
    
    def process_entry(
        self,
        event: Event,
        position_book: Dict[str, Dict[str, PositionSlot]],
        active_positions: Dict[str, Dict],
        step: int,
        silent: bool,
        summary_only: bool
    ) -> None:
        """Processes an entry event."""
        signal = event.signal
        sig_id = signal['signal_id']
        symbol = signal['symbol']
        direction = signal['direction']
        current_time_str = format_timestamp(event.timestamp)
        
        # Calculate Position Size based on Risk
        risk_amount = self.portfolio.balance * (self.risk_per_trade / 100)
        entry_price = signal['signal_price']
        
        sl_price = signal.get('sl2_price') or signal.get('sl1_price')
        if not sl_price:
            sl_price = entry_price * 0.95 if direction == 'LONG' else entry_price * 1.05
        
        sl_distance_pct = abs(entry_price - sl_price) / entry_price
        if sl_distance_pct == 0:
            sl_distance_pct = 0.01
        
        position_size_usd = risk_amount / sl_distance_pct
        margin_required = position_size_usd / self.leverage
        quantity = position_size_usd / entry_price

        slot = get_position_slot(position_book, symbol, direction)
        preview_qty, preview_avg, preview_margin, preview_liq = slot.preview_after_add(
            quantity, entry_price, margin_required, self.mmr
        )

        skip_trade = False
        skip_reason = ""
        
        # Use configurable buffer from .env (OPTIMIZE_MIN_SL_LIQ_BUFFER)
        if direction == 'LONG':
            safe_threshold = sl_price * (1 - self.min_sl_liq_buffer)
            if preview_liq >= safe_threshold:
                skip_trade = True
                skip_reason = (
                    f"Likidite Riski (Liq: ${preview_liq:.4f} ~ SL: ${sl_price:.4f} | "
                    f"Buffer: %{self.min_sl_liq_buffer*100:.1f})"
                )
        else:
            safe_threshold = sl_price * (1 + self.min_sl_liq_buffer)
            if preview_liq <= safe_threshold:
                skip_trade = True
                skip_reason = (
                    f"Likidite Riski (Liq: ${preview_liq:.4f} ~ SL: ${sl_price:.4f} | "
                    f"Buffer: %{self.min_sl_liq_buffer*100:.1f})"
                )

        # Check Funds (Isolated Margin)
        if not skip_trade and margin_required > self.portfolio.free_balance:
            skip_trade = True
            skip_reason = (
                f"Yetersiz Serbest Bakiye (Gereken: ${margin_required:.2f}, "
                f"Mevcut: ${self.portfolio.free_balance:.2f})"
            )

        free_balance_before = self.portfolio.free_balance
        
        if skip_trade:
            if not silent and not summary_only:
                self.report_generator.log(
                    f"{step:<6} {current_time_str:<20} {'SKIP':<12} {symbol:<15} "
                    f"{'-':<6} ${free_balance_before:>13.2f} {'-':<15} {'-':<10} "
                    f"{'-':<12} {'-':<12}"
                )
                self.report_generator.log(f"      Sebep: {skip_reason}")
        else:
            # Lock Margin
            self.portfolio.lock_margin(margin_required)
            self.portfolio.open_trades += 1
            
            slot.apply_add(quantity, entry_price, margin_required, self.mmr)

            active_positions[sig_id] = {
                'symbol': symbol,
                'direction': direction,
                'entry_price': entry_price,
                'position_size_usd': position_size_usd,
                'quantity': quantity,
                'margin_used': margin_required,
                'start_time': event.timestamp,
                'liq_price': slot.liquidation_price,
                'sl_price': sl_price,
                'risk_amount': risk_amount
            }
            
            if not silent and not summary_only:
                self.report_generator.log(
                    f"{step:<6} {current_time_str:<20} {'ENTRY':<12} {symbol:<15} "
                    f"{direction:<6} ${free_balance_before:>13.2f} "
                    f"${self.portfolio.free_balance:>13.2f} ${risk_amount:>8.2f} "
                    f"{'-':<12} {'-':<12}"
                )
                self.report_generator.log(
                    f"      Fiyat: ${entry_price:.4f} | Slot Avg: ${slot.avg_entry_price:.4f} | "
                    f"Liq: ${slot.liquidation_price:.4f} | Margin: ${margin_required:.2f} | "
                    f"Toplam: ${self.portfolio.balance:.2f}"
                )
    
    def process_exit(
        self,
        event: Event,
        position_book: Dict[str, Dict[str, PositionSlot]],
        active_positions: Dict[str, Dict],
        step: int,
        silent: bool,
        summary_only: bool
    ) -> None:
        """Processes an exit event (TP or SL)."""
        signal = event.signal
        sig_id = signal['signal_id']
        
        if sig_id not in active_positions:
            return
        
        pos = active_positions[sig_id]
        exit_price = event.details['exit_price']
        duration = event.timestamp - pos['start_time']
        quantity = pos['quantity']
        margin_used = pos['margin_used']
        symbol = pos['symbol']
        direction = pos['direction']
        current_time_str = format_timestamp(event.timestamp)

        slot = get_position_slot(position_book, symbol, direction)
        slot_liq = slot.liquidation_price if slot.is_active() else pos['liq_price']
        avg_entry_for_close = (
            slot.avg_entry_price if slot.is_active() 
            else pos['entry_price']
        )

        # Liquidation Check
        is_liquidated = False
        if direction == 'LONG':
            if pos['sl_price'] <= slot_liq:
                is_liquidated = True
                exit_price = slot_liq
            elif exit_price <= slot_liq:
                is_liquidated = True
                exit_price = slot_liq
        else:
            if pos['sl_price'] >= slot_liq:
                is_liquidated = True
                exit_price = slot_liq
            elif exit_price >= slot_liq:
                is_liquidated = True
                exit_price = slot_liq

        # Calculate PnL
        if is_liquidated:
            pnl = -margin_used
            status = 'LIQUIDATED'
        else:
            if direction == 'LONG':
                price_change = exit_price - avg_entry_for_close
            else:
                price_change = avg_entry_for_close - exit_price
            pnl = price_change * quantity
            status = 'WIN' if event.type == 'EXIT_TP' else 'LOSS'

        # Update aggregated slot before releasing funds
        slot.apply_reduce(quantity, margin_used, self.mmr)

        # Update Portfolio
        self.portfolio.open_trades -= 1
        
        # Calculate commission
        position_size = pos['position_size_usd']
        entry_comm = position_size * (self.commission_rate / 100)
        exit_comm = position_size * (self.commission_rate / 100)
        total_comm = entry_comm + exit_comm
        net_pnl = pnl - total_comm
        
        # Store free balance before trade result
        free_balance_before = self.portfolio.free_balance
        
        trade_result = {
            'symbol': symbol,
            'direction': direction,
            'status': status,
            'pnl': pnl,  # Gross PnL
            'margin_used': margin_used,
            'position_size': position_size,
            'duration': duration
        }
        self.portfolio.add_trade_result(trade_result)
        
        del active_positions[sig_id]
        
        # Detailed logging
        gross_pnl_str = f"+${pnl:.2f}" if pnl > 0 else f"-${abs(pnl):.2f}"
        net_pnl_str = f"+${net_pnl:.2f}" if net_pnl > 0 else f"-${abs(net_pnl):.2f}"
        
        if not silent and not summary_only:
            risk_amount = pos.get('risk_amount', 0)
            self.report_generator.log(
                f"{step:<6} {current_time_str:<20} {status:<12} {symbol:<15} "
                f"{direction:<6} ${free_balance_before:>13.2f} "
                f"${self.portfolio.free_balance:>13.2f} ${risk_amount:>8.2f} "
                f"${total_comm:>10.2f} {net_pnl_str:>11}"
            )
            self.report_generator.log(
                f"      Çıkış: ${exit_price:.4f} | Slot Avg: ${avg_entry_for_close:.4f} | "
                f"Gross PnL: {gross_pnl_str} | Süre: {format_duration_str(duration)} | "
                f"Toplam: ${self.portfolio.balance:.2f}"
            )
    
    def run(
        self,
        send_telegram: bool = False,
        summary_only: bool = False,
        silent: bool = False,
        auto_optimized: Optional[Dict] = None,
        manual_config: Optional[Dict] = None
    ) -> Dict:
        """Runs the simulation."""
        # Initialize components
        self.portfolio = Portfolio(self.initial_balance, self.commission_rate)
        self.report_generator = ReportGenerator()
        self.notification_manager = NotificationManager()
        
        # Setup logging - callback for report generator
        def log_callback(message: str = "", detail: bool = True):
            """Callback function for report generator that respects silent mode."""
            if silent:
                return
            if summary_only and detail:
                return
            print(message)
        
        # Set log callback first before using report_generator
        self.report_generator.log_callback = log_callback
        
        # Helper function for direct logging - uses report_generator which calls log_callback
        def log(message: str = "", detail: bool = True):
            """Direct log function that uses report_generator."""
            # Early return for silent mode to avoid unnecessary processing
            if silent:
                return
            if summary_only and detail:
                return
            # report_generator.log() will call log_callback internally
            # which also handles silent/summary checks and prints
            self.report_generator.log(message, detail)
        
        # Load signals
        self.signals = self.db_manager.load_all_signals()
        
        # Track simulation time range
        if self.signals:
            first_signal_time = self.signals[0]['created_at']
            last_signal_time = self.signals[-1]['created_at']
            simulation_duration = last_signal_time - first_signal_time
        else:
            first_signal_time = 0
            last_signal_time = 0
            simulation_duration = 0
        
        # Generate events
        log(f"🚀 Starting Professional Simulation (ISOLATED MARGIN)")
        log(f"💰 Initial Balance: ${self.initial_balance:,.2f}")
        log(f"⚠️  Risk: {self.risk_per_trade}% | Leverage: {self.leverage}x | "
            f"Comm: {self.commission_rate}%")
        log("-" * 60)
        
        self.events = self.generate_events()
        
        # Validate chronological order
        if not silent and not summary_only:
            log(f"\n📅 ZAMAN DAMGASI DOĞRULAMA:")
            log(f"   Toplam {len(self.events)} event bulundu")
            if len(self.events) > 0:
                log(f"   İlk event: {format_timestamp(self.events[0].timestamp)}")
                log(f"   Son event: {format_timestamp(self.events[-1].timestamp)}")
                
                prev_timestamp = 0
                out_of_order_count = 0
                for i, event in enumerate(self.events):
                    if event.timestamp < prev_timestamp:
                        out_of_order_count += 1
                        log(
                            f"   ⚠️  Sıralama hatası: Event {i} "
                            f"({format_timestamp(event.timestamp)}) önceki event'ten "
                            f"({format_timestamp(prev_timestamp)}) önce!"
                        )
                    prev_timestamp = event.timestamp
                
                if out_of_order_count == 0:
                    log(f"   ✅ Tüm event'ler kronolojik sırada")
                else:
                    log(f"   ❌ {out_of_order_count} event sıralama hatası var!")
            log("")
        
        # Process events
        active_positions: Dict[str, Dict] = {}
        position_book: Dict[str, Dict[str, PositionSlot]] = {}
        step = 1
        
        # Table header for step-by-step tracking
        if not silent and not summary_only:
            log("\n" + "="*120)
            log(
                f"{'ADIM':<6} {'TARİH':<20} {'İŞLEM':<12} {'COIN':<15} {'YÖN':<6} "
                f"{'SERBEST (ÖNCE)':<15} {'SERBEST (SONRA)':<15} {'RİSK':<10} "
                f"{'KOMİSYON':<12} {'NET PNL':<12}"
            )
            log("="*120)
        
        for event in self.events:
            if event.type == 'ENTRY':
                self.process_entry(
                    event, position_book, active_positions, step, silent, summary_only
                )
            elif event.type in ['EXIT_TP', 'EXIT_SL']:
                self.process_exit(
                    event, position_book, active_positions, step, silent, summary_only
                )
            step += 1
        
        # Generate final report
        summary = self.portfolio.get_summary()
        summary['simulation_duration'] = simulation_duration
        summary['first_signal_time'] = first_signal_time
        summary['last_signal_time'] = last_signal_time
        
        # Generate summary report
        self.report_generator.generate_summary_report(
            summary, self.portfolio, auto_optimized, manual_config
        )
        
        # Send Telegram if requested
        if send_telegram:
            full_report = self.report_generator.get_report_text()
            self.notification_manager.send_report(full_report)
        
        return summary
    
    def _load_min_sl_liq_buffer(self) -> float:
        """Load minimum SL-Liq buffer from .env or use default."""
        try:
            val = os.getenv('OPTIMIZE_MIN_SL_LIQ_BUFFER')
            return float(val) if val is not None else DEFAULT_MIN_SL_LIQ_BUFFER
        except Exception:
            return DEFAULT_MIN_SL_LIQ_BUFFER

