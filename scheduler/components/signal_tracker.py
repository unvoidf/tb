"""
SignalTracker: Class that tracks TP/SL levels and updates messages.
Checks active signals, updates TP/SL hit statuses, and manages Telegram messages.
"""
import time
from typing import Dict, Optional
from utils.logger import LoggerManager
from data.signal_repository import SignalRepository
from data.market_data_manager import MarketDataManager
from bot.telegram_bot_manager import TelegramBotManager
from bot.message_formatter import MessageFormatter
from tools.archiver import SignalArchiver


class SignalTracker:
    """Tracks TP/SL levels and updates messages."""
    
    def __init__(
        self,
        signal_repository: SignalRepository,
        market_data: MarketDataManager,
        bot_manager: TelegramBotManager,
        message_formatter: MessageFormatter,
        liquidation_safety_filter: Optional['LiquidationSafetyFilter'] = None,
        message_update_delay: float = 0.6
    ):
        """
        Initializes SignalTracker.
        
        Args:
            signal_repository: Signal repository
            market_data: Market data manager
            bot_manager: Telegram bot manager
            message_formatter: Message formatter
            message_update_delay: Minimum wait time between message updates (seconds, default: 0.6)
        """
        self.repository = signal_repository
        self.market_data = market_data
        self.bot_manager = bot_manager
        self.formatter = message_formatter
        self.liquidation_safety_filter = liquidation_safety_filter
        # Minimum wait time between message updates (for Telegram rate limit)
        # Default 0.6 seconds (to avoid Telegram flood control)
        self.message_update_delay = message_update_delay if message_update_delay > 0 else 0.6
        self.logger = LoggerManager().get_logger('SignalTracker')
        self._last_update_time = 0.0
        self._last_message_check_time = 0.0
        self._last_archive_check_time = 0.0
        self.message_check_interval = 600  # 10 minutes
        self.archive_check_interval = 600  # 10 minutes
        
        # Thresholds for message update check
        self.mfe_mae_update_threshold_pct = 2.0  # Update on 2% MFE/MAE change
        self.hit_signal_update_interval = 7200  # Update every 2 hours for hit signals
        self.confidence_change_threshold = 0.05  # Update on 5% confidence change
        
        # Initialize Archiver
        # We use the same DB path from the repository
        self.archiver = SignalArchiver(db_path=self.repository.db.db_path)
    
    def _calculate_price_difference(
        self,
        target_price: Optional[float],
        current_price: Optional[float],
        direction: str,
        is_tp: bool
    ) -> Optional[float]:
        """Calculates difference between target and current price (remaining to target)."""
        if target_price is None or current_price is None:
            return None

        if is_tp:
            if direction == 'LONG':
                return target_price - current_price
            if direction == 'SHORT':
                return current_price - target_price
        else:
            if direction == 'LONG':
                return current_price - target_price
            if direction == 'SHORT':
                return target_price - current_price

        return None

    def _calculate_percentage_to_target(
        self,
        target_price: Optional[float],
        current_price: Optional[float],
        direction: str,
        is_tp: bool
    ) -> Optional[float]:
        """Calculates percentage remaining to target."""
        if target_price is None or current_price in (None, 0):
            return None

        price_diff = self._calculate_price_difference(target_price, current_price, direction, is_tp)
        if price_diff is None:
            return None

        return (price_diff / current_price) * 100

    def _log_signal_snapshot(
        self,
        signal: Dict,
        current_price: float,
        direction: str
    ) -> None:
        """Logs signal current status in detail."""
        signal_id = signal.get('signal_id', 'unknown')
        symbol = signal.get('symbol', 'unknown')
        signal_price = signal.get('signal_price')

        self.logger.info(
            "Signal tracking started: id=%s symbol=%s direction=%s signal_price=%.6f current_price=%.6f",
            signal_id,
            symbol,
            direction,
            signal_price if signal_price is not None else 0.0,
            current_price
        )

        for tp_level in [1, 2, 3]:
            tp_price = signal.get(f'tp{tp_level}_price')
            if tp_price is None:
                continue

            tp_hit = signal.get(f'tp{tp_level}_hit', 0) == 1
            price_diff = self._calculate_price_difference(tp_price, current_price, direction, is_tp=True)
            remaining_pct = self._calculate_percentage_to_target(tp_price, current_price, direction, is_tp=True)

            self.logger.debug(
                "%s TP%d: target=%.6f status=%s price_diff=%s remaining_pct=%s",
                signal_id,
                tp_level,
                tp_price,
                "HIT" if tp_hit else "PENDING",
                "N/A" if price_diff is None else f"{price_diff:.6f}",
                "N/A" if remaining_pct is None else f"{remaining_pct:.2f}%"
            )

        sl_price = signal.get('sl_price')
        if sl_price is not None:
            sl_hit = signal.get('sl_hit', 0) == 1
            price_diff = self._calculate_price_difference(sl_price, current_price, direction, is_tp=False)
            remaining_pct = self._calculate_percentage_to_target(sl_price, current_price, direction, is_tp=False)

            self.logger.debug(
                "%s SL: target=%.6f status=%s price_diff=%s remaining_pct=%s",
                signal_id,
                sl_price,
                "HIT" if sl_hit else "PENDING",
                "N/A" if price_diff is None else f"{price_diff:.6f}",
                "N/A" if remaining_pct is None else f"{remaining_pct:.2f}%"
            )

    def check_all_active_signals(self) -> None:
        """
        Checks and updates all active signals if necessary.
        """
        try:
            active_signals = self.repository.get_active_signals()
            
            if not active_signals:
                self.logger.debug("No active signals")
                return
            
            self.logger.info(f"{len(active_signals)} active signals being checked")
            
            for signal in active_signals:
                try:
                    self.check_signal_levels(signal)
                except Exception as e:
                    self.logger.error(
                        f"Signal check error ({signal.get('signal_id', 'unknown')}): {str(e)}",
                        exc_info=True
                    )
            
            # Periodic message check (Heartbeat)
            self.check_messages_existence(active_signals)
            
            # Periodic archive check (archive signals with message_deleted=1)
            self.archive_deleted_signals()
                    
        except Exception as e:
            self.logger.error(f"Active signal check error: {str(e)}", exc_info=True)
    
    def check_signal_levels(self, signal: Dict) -> None:
        """
        Checks TP/SL levels for a single signal.
        
        Args:
            signal: Signal dict (from database)
        """
        try:
            signal_id = signal.get('signal_id')
            symbol = signal.get('symbol')
            direction = signal.get('direction')
            signal_price = signal.get('signal_price')
            
            if not all([signal_id, symbol, direction, signal_price]):
                self.logger.warning(f"Missing signal info: {signal_id}")
                return
            
            # Get current price
            current_price = self.market_data.get_latest_price(symbol)
            if not current_price:
                self.logger.warning(f"{symbol} current price could not be obtained")
                return

            self._log_signal_snapshot(signal, current_price, direction)
            
            # 1. Update Metrics (Snapshot, MFE/MAE, Alt Entry)
            mfe_updated, mae_updated, old_mfe, old_mae = self._update_signal_metrics(signal, current_price, direction)
            
            # 2. Check TP/SL Status
            tp_hits, sl_hits = self._check_tp_sl_status(signal, current_price, direction)
            
            # 3. Evaluate Update Condition (Hybrid Logic)
            mfe_mae_info = {
                'mfe_updated': mfe_updated,
                'mae_updated': mae_updated,
                'old_mfe': old_mfe,
                'old_mae': old_mae
            }
            should_update, update_reasons = self._evaluate_update_condition(signal, current_price, direction, tp_hits, sl_hits, mfe_mae_info)
            
            # 4. Process Update
            if should_update:
                self._process_signal_update(signal, tp_hits, sl_hits, update_reasons)
            else:
                self.logger.debug(f"{symbol} update not required")
                
        except Exception as e:
            self.logger.error(f"Signal level check error: {str(e)}", exc_info=True)

    def _update_signal_metrics(self, signal: Dict, current_price: float, direction: str) -> tuple:
        """Updates snapshot, MFE/MAE, and alternative entry hits."""
        # 1) SAVE SNAPSHOT
        self.repository.save_price_snapshot(
            signal_id=signal.get('signal_id'),
            timestamp=int(time.time()),
            price=current_price,
            source='tracker_tick'
        )
        
        # 2) UPDATE MFE/MAE
        # Store old values first (for threshold check)
        old_mfe = signal.get('mfe_price')
        old_mae = signal.get('mae_price')
        
        mfe_updated, mae_updated = self._update_mfe_mae(signal, current_price, direction)
        
        # If MFE/MAE updated, update signal dict (for threshold check)
        if mfe_updated:
            signal['mfe_price'] = current_price
            signal['mfe_at'] = int(time.time())
        if mae_updated:
            signal['mae_price'] = current_price
            signal['mae_at'] = int(time.time())
        
        # 3) ALTERNATIVE ENTRY HIT CHECK
        self._check_alternative_entry_hit(signal, current_price, direction)
        
        return mfe_updated, mae_updated, old_mfe, old_mae

    def _check_tp_sl_status(self, signal: Dict, current_price: float, direction: str) -> tuple:
        """Checks TP and SL levels."""
        tp_hits = self._check_tp_levels(signal, current_price, direction)
        sl_hits = self._check_sl_levels(signal, current_price, direction)
        return tp_hits, sl_hits

    def _evaluate_update_condition(
        self, 
        signal: Dict, 
        current_price: float, 
        direction: str, 
        tp_hits: Dict, 
        sl_hits: Dict, 
        mfe_mae_info: Dict
    ) -> tuple:
        """Evaluates if message update is required."""
        # 1. New hit check (priority)
        has_new_tp_hits = any(tp_hits.values()) if tp_hits else False
        has_new_sl_hits = any(sl_hits.values()) if sl_hits else False
        
        # 2. MFE/MAE threshold check
        mfe_mae_threshold_crossed = self._check_mfe_mae_threshold_crossed(
            signal, current_price, direction, 
            mfe_mae_info['mfe_updated'], mfe_mae_info['mae_updated'],
            mfe_mae_info['old_mfe'], mfe_mae_info['old_mae']
        )
        
        # 3. Timeout check for hit signals (fall-back)
        hit_signal_timeout_reached = self._check_hit_signal_timeout(signal)
        
        # 4. Confidence change check (bonus)
        confidence_changed = self._check_confidence_change(signal)
        
        should_update = (
            has_new_tp_hits or 
            has_new_sl_hits or 
            mfe_mae_threshold_crossed or 
            hit_signal_timeout_reached or 
            confidence_changed
        )
        
        update_reasons = []
        if should_update:
            if has_new_tp_hits or has_new_sl_hits:
                update_reasons.append(f"new hit (TP: {has_new_tp_hits}, SL: {has_new_sl_hits})")
            if mfe_mae_threshold_crossed:
                update_reasons.append("MFE/MAE threshold")
            if hit_signal_timeout_reached:
                update_reasons.append("hit signal timeout")
            if confidence_changed:
                update_reasons.append("confidence change")
                
        return should_update, update_reasons

    def _process_signal_update(self, signal: Dict, tp_hits: Dict, sl_hits: Dict, update_reasons: list) -> None:
        """Logs reasons and updates Telegram message."""
        symbol = signal.get('symbol')
        self.logger.debug(
            f"{symbol} message update required - "
            f"Reasons: {', '.join(update_reasons)}"
        )
        # Update message (confidence_change will be calculated inside)
        self._update_telegram_message(signal, tp_hits, sl_hits)
    
    def update_message_for_signal(self, signal: Dict) -> None:
        """
        Updates signal message (for signal log changes).
        Does not check TP/SL hits, only updates the message.
        
        Args:
            signal: Signal dict (from database, with current signal_log)
        """
        try:
            signal_id = signal.get('signal_id')
            symbol = signal.get('symbol')
            
            if not all([signal_id, symbol]):
                self.logger.warning(f"Missing signal info (message update): {signal_id}")
                return
            
            # Get current price
            current_price = self.market_data.get_latest_price(symbol)
            if not current_price:
                self.logger.warning(f"{symbol} current price could not be obtained (message update)")
                return
            
            # Check TP/SL hit statuses (but update message even if not hit)
            tp_hits = self._check_tp_levels(signal, current_price, signal.get('direction', 'LONG'))
            sl_hits = self._check_sl_levels(signal, current_price, signal.get('direction', 'LONG'))
            
            # Update message (even if not hit - for manual update with button)
            # confidence_change will be calculated inside
            self._update_telegram_message(signal, tp_hits, sl_hits)
                
        except Exception as e:
            self.logger.error(f"Signal message update error: {str(e)}", exc_info=True)
    
    def _check_tp_levels(
        self,
        signal: Dict,
        current_price: float,
        direction: str
    ) -> Dict[int, bool]:
        """
        Checks TP levels.
        
        Args:
            signal: Signal dict
            current_price: Current price
            direction: LONG/SHORT
            
        Returns:
            TP hit statuses {1: True/False, 2: True/False}
        """
        tp_hits = {}
        
        # Balanced approach: Only TP1 and TP2 are checked (TP3 removed)
        for tp_level in [1, 2]:
            tp_price_key = f'tp{tp_level}_price'
            tp_hit_key = f'tp{tp_level}_hit'
            
            tp_price = signal.get(tp_price_key)
            tp_already_hit = signal.get(tp_hit_key, 0) == 1
            
            if not tp_price:
                tp_hits[tp_level] = False
                continue

            price_diff = self._calculate_price_difference(tp_price, current_price, direction, is_tp=True)
            remaining_pct = self._calculate_percentage_to_target(tp_price, current_price, direction, is_tp=True)
            self.logger.debug(
                "%s TP%d check: target=%.6f current=%.6f price_diff=%s remaining_pct=%s status=%s",
                signal.get('signal_id', 'unknown'),
                tp_level,
                tp_price,
                current_price,
                "N/A" if price_diff is None else f"{price_diff:.6f}",
                "N/A" if remaining_pct is None else f"{remaining_pct:.2f}%",
                "HIT" if tp_already_hit else "PENDING"
            )

            if tp_already_hit:
                tp_hits[tp_level] = False
                continue
            
            # Touch check
            if direction == 'LONG':
                hit = current_price >= tp_price
            elif direction == 'SHORT':
                hit = current_price <= tp_price
            else:
                hit = False
            
            tp_hits[tp_level] = hit
            
            # If hit, update database
            if hit:
                self.repository.update_tp_hit(signal_id=signal['signal_id'], tp_level=tp_level)
                self.logger.info(
                    f"TP{tp_level} hit: {signal['symbol']} @ {current_price} >= {tp_price}"
                )
        
        return tp_hits
    
    def _check_sl_levels(
        self,
        signal: Dict,
        current_price: float,
        direction: str
    ) -> Dict[str, bool]:
        """
        Checks SL levels.
        
        Args:
            signal: Signal dict
            current_price: Current price
            direction: LONG/SHORT
            
        Returns:
            SL hit status {'sl': True/False}
        """
        sl_hits = {'sl': False}
        sl_price = signal.get('sl_price')
        sl_already_hit = signal.get('sl_hit', 0) == 1
        
        if not sl_price:
            return sl_hits

        price_diff = self._calculate_price_difference(sl_price, current_price, direction, is_tp=False)
        remaining_pct = self._calculate_percentage_to_target(sl_price, current_price, direction, is_tp=False)
        self.logger.debug(
            "%s SL check: target=%.6f current=%.6f price_diff=%s remaining_pct=%s status=%s",
            signal.get('signal_id', 'unknown'),
            sl_price,
            current_price,
            "N/A" if price_diff is None else f"{price_diff:.6f}",
            "N/A" if remaining_pct is None else f"{remaining_pct:.2f}%",
            "HIT" if sl_already_hit else "PENDING"
        )

        if sl_already_hit:
            return sl_hits
        
        # Touch check
        if direction == 'LONG':
            hit = current_price <= sl_price
        elif direction == 'SHORT':
            hit = current_price >= sl_price
        else:
            hit = False
        
        sl_hits['sl'] = hit
        
        if hit:
            self.repository.update_sl_hit(signal_id=signal['signal_id'])
            self.logger.info(
                f"SL hit: {signal['symbol']} @ {current_price}"
            )
        
        return sl_hits
    
    def _update_telegram_message(
        self,
        signal: Dict,
        tp_hits: Dict[int, bool],
        sl_hits: Dict[str, bool],
        confidence_change: Optional[float] = None
    ) -> None:
        """
        Updates Telegram message.
        
        Args:
            signal: Signal dict
            tp_hits: TP hit statuses
            sl_hits: SL hit statuses
        """
        try:
            message_id = signal.get('telegram_message_id')
            channel_id = signal.get('telegram_channel_id')
            symbol = signal.get('symbol')
            
            if not all([message_id, channel_id, symbol]):
                self.logger.warning(f"Missing info for message update: {signal.get('signal_id')}")
                return
            
            # Get signal data
            signal_data = signal.get('signal_data', {})
            entry_levels = signal.get('entry_levels', {})
            signal_price = signal.get('signal_price')
            
            # Get current price
            current_price, current_price_ts = self.market_data.get_latest_price_with_timestamp(symbol)
            if not current_price:
                current_price = signal_price
            if not current_price_ts:
                current_price_ts = int(time.time())
            
            # Get current hit statuses from database
            updated_signal = self.repository.get_signal(signal['signal_id'])
            if not updated_signal:
                self.logger.warning(f"Signal not found: {signal['signal_id']}")
                return
            
            # Convert TP hit statuses to dict
            tp_hits_dict = {
                1: updated_signal.get('tp1_hit', 0) == 1,
                2: updated_signal.get('tp2_hit', 0) == 1
            }
            tp_hit_times = {
                1: updated_signal.get('tp1_hit_at'),
                2: updated_signal.get('tp2_hit_at')
            }
            
            # Convert SL hit statuses to dict
            sl_hits_dict = {
                'sl': updated_signal.get('sl_hit', 0) == 1
            }
            sl_hit_times = {
                'sl': updated_signal.get('sl_hit_at')
            }

            created_at = updated_signal.get('created_at') or signal.get('created_at')
            signal_id = updated_signal.get('signal_id') or signal.get('signal_id')
            
            # Get latest confidence change
            confidence_change = self.repository.get_latest_confidence_change(signal_id)
            
            # Liquidation Risk Calculation (If missing)
            if 'liquidation_risk_percentage' not in signal_data and self.liquidation_safety_filter:
                try:
                    direction = signal.get('direction', 'NEUTRAL')
                    # Get SL price (from custom_targets or entry_levels)
                    sl_price = None
                    
                    # 1. Custom Targets check (for Mean Reversion)
                    # custom_targets is in signal_data (parsed by SignalRepository.row_to_dict)
                    custom_targets = signal_data.get('custom_targets', {})
                    # Type safety: Ensure custom_targets is a dict
                    if not isinstance(custom_targets, dict):
                        custom_targets = {}
                    if custom_targets:
                        # Check 'sl' or 'stop_loss' key
                        sl_section = custom_targets.get('sl') or custom_targets.get('stop_loss')
                        if sl_section:
                            sl_price = sl_section.get('stop_loss')
                            if sl_price is None:
                                sl_price = sl_section.get('price')
                    
                    # 2. Entry Levels check (fallback for Trend)
                    if sl_price is None:
                         # Check entry_levels structure
                         # Generally: {'sl_price': ...} or {'conservative': {'sl_price': ...}}
                         sl_price = entry_levels.get('sl_price')
                    
                    if sl_price and signal_price:
                        default_balance = 10000.0
                        risk_pct = self.liquidation_safety_filter.calculate_liquidation_risk_percentage(
                            entry_price=signal_price,
                            sl_price=sl_price,
                            direction=direction,
                            balance=default_balance
                        )
                        signal_data['liquidation_risk_percentage'] = risk_pct
                        self.logger.info(f"Liquidation risk on-the-fly calculated for {symbol}: {risk_pct}%")
                        
                except Exception as e:
                    self.logger.warning(f"On-the-fly liquidation risk calculation failed: {e}")

            # Reformat message
            message = self.formatter.format_signal_alert(
                symbol=symbol,
                signal_data=signal_data,
                entry_levels=entry_levels,
                signal_price=signal_price,
                now_price=current_price,
                tp_hits=tp_hits_dict,
                sl_hits=sl_hits_dict,
                created_at=created_at,
                current_price_timestamp=current_price_ts,
                tp_hit_times=tp_hit_times,
                sl_hit_times=sl_hit_times,
                signal_id=signal_id,
                confidence_change=confidence_change
            )
            
            # DEBUG: Log formatter input to identify empty message cause
            self.logger.debug(
                f"Formatting message for {symbol}: signal_price={signal_price}, "
                f"current_price={current_price}, entry_levels={entry_levels is not None}, "
                f"signal_data keys={list(signal_data.keys()) if signal_data else 'None'}"
            )
            
            # Check if message is not empty (to prevent Telegram API empty message error)
            if not message or not message.strip():
                self.logger.error(
                    f"Message formatter returned empty message for {symbol} (signal_id: {signal_id}). "
                    f"Skipping Telegram update. Signal data might be corrupted or incomplete."
                )
                return
            
            # Rate limiting: Minimum delay between message updates
            current_time = time.time()
            time_since_last_update = current_time - self._last_update_time
            if time_since_last_update < self.message_update_delay:
                sleep_time = self.message_update_delay - time_since_last_update
                self.logger.debug(f"Rate limiting: {sleep_time:.3f} seconds waiting")
                time.sleep(sleep_time)
            
            # Fetch message to get keyboard from existing message
            # But this requires an extra API call, so
            # We use the same keyboard to preserve it while updating message
            # (Keyboard added when sending in SignalScannerManager)
            keyboard = self.formatter.create_signal_keyboard(signal_id)
            
            # Update Telegram message (with keyboard)
            success, message_not_found = self.bot_manager.edit_channel_message(
                channel_id=channel_id,
                message_id=message_id,
                message=message,
                reply_markup=keyboard
            )
            
            # Save last update time
            self._last_update_time = time.time()
            
            if success:
                self.logger.info(
                    f"Telegram message updated: {signal['signal_id']} - "
                    f"TP hits: {sum(tp_hits_dict.values())}, "
                    f"SL hits: {sum(sl_hits_dict.values())}"
                )
            elif message_not_found:
                # Message deleted, remove signal from active tracking
                self.logger.warning(
                    f"Telegram message deleted, removing signal from active tracking: {signal['signal_id']}"
                )
                self.repository.mark_message_deleted(signal['signal_id'])
                
                # Trigger Archival Immediately
                self.logger.info(f"Triggering archival for deleted signal: {signal['signal_id']}")
                self.archiver.archive_signal(signal['signal_id'])
            else:
                self.logger.warning(f"Telegram message could not be updated: {signal['signal_id']}")
                
        except Exception as e:
            self.logger.error(
                f"Telegram message update error: {str(e)}",
                exc_info=True
            )
    
    def _update_mfe_mae(self, signal: Dict, current_price: float, direction: str) -> tuple:
        """
        Calculates and updates MFE/MAE, returns True if updated.
        
        Args:
            signal: Signal dict
            current_price: Current price
            direction: Signal direction
            
        Returns:
            (mfe_updated, mae_updated) tuple
        """
        signal_id = signal['signal_id']
        mfe_price = signal.get('mfe_price')
        mae_price = signal.get('mae_price')
        
        mfe_updated = False
        mae_updated = False
        
        if direction == 'LONG':
            # MFE: Highest price
            if mfe_price is None or current_price > mfe_price:
                mfe_price = current_price
                mfe_updated = True
            # MAE: Lowest price
            if mae_price is None or current_price < mae_price:
                mae_price = current_price
                mae_updated = True
        else:  # SHORT
            # MFE: Lowest price
            if mfe_price is None or current_price < mfe_price:
                mfe_price = current_price
                mfe_updated = True
            # MAE: Highest price
            if mae_price is None or current_price > mae_price:
                mae_price = current_price
                mae_updated = True
        
        if mfe_updated or mae_updated:
            self.repository.update_mfe_mae(
                signal_id=signal_id,
                mfe_price=mfe_price,
                mfe_at=int(time.time()) if mfe_updated else signal.get('mfe_at'),
                mae_price=mae_price,
                mae_at=int(time.time()) if mae_updated else signal.get('mae_at')
            )
            self.logger.debug(
                f"MFE/MAE updated: {signal_id} - "
                f"MFE: {mfe_price:.6f}, MAE: {mae_price:.6f}"
            )
        
        return mfe_updated, mae_updated
    
    def _check_mfe_mae_threshold_crossed(
        self,
        signal: Dict,
        current_price: float,
        direction: str,
        mfe_updated: bool,
        mae_updated: bool,
        old_mfe_price: Optional[float] = None,
        old_mae_price: Optional[float] = None
    ) -> bool:
        """
        Checks if there is a significant change in MFE/MAE.
        Returns True if threshold is crossed.
        
        Args:
            signal: Signal dict
            current_price: Current price
            direction: Signal direction
            mfe_updated: Is MFE updated?
            mae_updated: Is MAE updated?
            old_mfe_price: MFE value before update (optional)
            old_mae_price: MAE value before update (optional)
            
        Returns:
            True if threshold crossed, False otherwise
        """
        if not (mfe_updated or mae_updated):
            return False
        
        signal_price = signal.get('signal_price')
        if not signal_price or signal_price == 0:
            return False
        
        # Take old values as parameters (stored before update)
        # If parameter not provided, read from signal dict (fallback)
        if old_mfe_price is None:
            old_mfe_price = signal.get('mfe_price')
        if old_mae_price is None:
            old_mae_price = signal.get('mae_price')
        
        # If MFE/MAE is set for the first time, update is not significant
        # (First value is always set, threshold check starts from second update)
        if (mfe_updated and old_mfe_price is None) or (mae_updated and old_mae_price is None):
            return False
        
        # Get new MFE/MAE values from signal dict (updated in lines 220-224)
        # We don't recalculate unnecessarily, we use already updated values
        new_mfe_price = signal.get('mfe_price') if mfe_updated else old_mfe_price
        new_mae_price = signal.get('mae_price') if mae_updated else old_mae_price
        
        # Threshold check: % change relative to Signal price
        if mfe_updated and old_mfe_price is not None and new_mfe_price is not None:
            mfe_change_pct = abs((new_mfe_price - old_mfe_price) / signal_price) * 100
            if mfe_change_pct >= self.mfe_mae_update_threshold_pct:
                return True
        
        if mae_updated and old_mae_price is not None and new_mae_price is not None:
            mae_change_pct = abs((new_mae_price - old_mae_price) / signal_price) * 100
            if mae_change_pct >= self.mfe_mae_update_threshold_pct:
                return True
        
        return False
    
    def _check_hit_signal_timeout(self, signal: Dict) -> bool:
        """
        Checks timeout for hit signals.
        Update should be done at least every 2 hours.
        
        Args:
            signal: Signal dict
            
        Returns:
            True if timeout reached, False otherwise
        """
        # Hit check
        sl_hit = signal.get('sl_hit', 0) == 1
        tp1_hit = signal.get('tp1_hit', 0) == 1
        tp2_hit = signal.get('tp2_hit', 0) == 1
        
        if not (sl_hit or tp1_hit or tp2_hit):
            return False
        
        # Calculate last update time from hit time
        # Use the time of the last hit level
        last_update = None
        
        # Collect all hit times and take the latest one
        hit_times = []
        if sl_hit and signal.get('sl_hit_at'):
            hit_times.append(signal.get('sl_hit_at'))
        if tp1_hit and signal.get('tp1_hit_at'):
            hit_times.append(signal.get('tp1_hit_at'))
        if tp2_hit and signal.get('tp2_hit_at'):
            hit_times.append(signal.get('tp2_hit_at'))
        
        if hit_times:
            # Get latest hit time
            last_update = max(hit_times)
        else:
            # If no hit time, use created_at
            last_update = signal.get('created_at', 0)
        
        current_time = int(time.time())
        time_since_update = current_time - (last_update or 0)
        
        # Update if 2 hours (7200 seconds) passed
        return time_since_update >= self.hit_signal_update_interval
    
    def _check_confidence_change(self, signal: Dict) -> bool:
        """
        Checks if there is a significant change in confidence value.
        
        Args:
            signal: Signal dict
            
        Returns:
            True if confidence changed significantly, False otherwise
        """
        # Get last confidence change from signal log
        signal_log_raw = signal.get('signal_log')
        if not signal_log_raw:
            return False
        
        # signal_log is stored as JSON string, parse it
        try:
            import json
            if isinstance(signal_log_raw, str):
                signal_log = json.loads(signal_log_raw)
            elif isinstance(signal_log_raw, list):
                signal_log = signal_log_raw
            else:
                return False
        except (json.JSONDecodeError, TypeError):
            return False
        
        if not signal_log or not isinstance(signal_log, list):
            return False
        
        # Find last log entry
        last_entry = None
        for entry in reversed(signal_log):
            if entry.get('event_type') == 'new_signal' and 'confidence_change' in entry:
                last_entry = entry
                break
        
        if not last_entry:
            return False
        
        # True if confidence change passed threshold
        confidence_change = abs(last_entry.get('confidence_change', 0))
        return confidence_change >= self.confidence_change_threshold
    
    def _check_alternative_entry_hit(self, signal: Dict, current_price: float, direction: str):
        """
        Record if optimal/conservative entry prices are reached.
        
        Args:
            signal: Signal dict
            current_price: Current price
            direction: Signal direction
        """
        signal_id = signal['signal_id']
        optimal_entry = signal.get('optimal_entry_price')
        conservative_entry = signal.get('conservative_entry_price')
        
        if optimal_entry and not signal.get('optimal_entry_hit'):
            if (direction == 'LONG' and current_price <= optimal_entry) or \
               (direction == 'SHORT' and current_price >= optimal_entry):
                self.repository.update_alternative_entry_hit(signal_id, 'optimal', int(time.time()))
                self.logger.info(f"Optimal entry hit: {signal_id} @ {current_price}")
        
        if conservative_entry and not signal.get('conservative_entry_hit'):
            if (direction == 'LONG' and current_price <= conservative_entry) or \
               (direction == 'SHORT' and current_price >= conservative_entry):
                self.repository.update_alternative_entry_hit(signal_id, 'conservative', int(time.time()))
                self.logger.info(f"Conservative entry hit: {signal_id} @ {current_price}")
    
    def _should_finalize_signal(self, signal: Dict) -> bool:
        """
        Checks if signal should be finalized.
        
        Only checks for 72 hours. TP/SL hit statuses are not finalization reasons,
        because user might be managing TP/SL manually.
        
        Args:
            signal: Signal dict
            
        Returns:
            True if should be finalized (only if 72 hours passed)
        """
        # Only check 72 hours
        # TP/SL hit statuses are not finalization reasons (user might manage manually)
        created_at = signal.get('created_at', 0)
        if int(time.time()) - created_at > 72 * 3600:
            return True
        return False
    
    def _determine_final_outcome(self, signal: Dict) -> str:
        """
        Determines final_outcome value.
        
        Args:
            signal: Signal dict
            
        Returns:
            Final outcome string
        """
        if signal.get('tp2_hit'):
            return 'tp2_reached'
        if signal.get('tp1_hit'):
            return 'tp1_reached'
        if signal.get('sl_hit'):
            return 'sl_hit'
        return 'expired_no_target'

    def check_messages_existence(self, active_signals: list) -> None:
        """
        Checks if Telegram messages of active signals still exist.
        If message is deleted, archives the signal.
        """
        current_time = time.time()
        if current_time - self._last_message_check_time < self.message_check_interval:
            return

        self.logger.info("Heartbeat: Message existence check starting...")
        
        for signal in active_signals:
            try:
                signal_id = signal.get('signal_id')
                channel_id = signal.get('telegram_channel_id')
                message_id = signal.get('telegram_message_id')
                
                if not all([signal_id, channel_id, message_id]):
                    continue
                    
                # Check message existence (only by updating reply_markup)
                keyboard = self.formatter.create_signal_keyboard(signal_id)
                exists, message_not_found = self.bot_manager.check_message_exists(
                    channel_id=channel_id,
                    message_id=message_id,
                    reply_markup=keyboard
                )
                
                if message_not_found:
                    self.logger.warning(f"Heartbeat: Message deleted, archiving: {signal_id}")
                    self.repository.mark_message_deleted(signal_id)
                    self.archiver.archive_signal(signal_id)
                    
            except Exception as e:
                self.logger.error(f"Heartbeat error ({signal_id}): {str(e)}")
        
        self._last_message_check_time = current_time
        self.logger.info("Heartbeat: Check completed.")
    
    def archive_deleted_signals(self) -> None:
        """
        Checks and archives signals with message_deleted=1.
        Runs every 10 minutes.
        """
        current_time = time.time()
        if current_time - self._last_archive_check_time < self.archive_check_interval:
            return
        
        try:
            # Get signals with message_deleted=1
            with self.repository.db.get_db_context() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT signal_id FROM signals
                    WHERE message_deleted = 1
                    ORDER BY created_at DESC
                """)
                deleted_signals = [row['signal_id'] for row in cursor.fetchall()]
            
            if not deleted_signals:
                self.logger.debug("No deleted signals to archive")
                self._last_archive_check_time = current_time
                return
            
            self.logger.info(f"Archive check: {len(deleted_signals)} deleted signals found, archiving...")
            
            archived_count = 0
            for signal_id in deleted_signals:
                try:
                    if self.archiver.archive_signal(signal_id):
                        archived_count += 1
                        self.logger.info(f"Archived: {signal_id}")
                    else:
                        self.logger.warning(f"Could not archive: {signal_id}")
                except Exception as e:
                    self.logger.error(f"Archiving error ({signal_id}): {str(e)}", exc_info=True)
            
            self.logger.info(f"Archive check completed: {archived_count}/{len(deleted_signals)} signals archived")
            
            # Archive rejected signals (Immediate archiving)
            try:
                rejected_count = self.archiver.archive_rejected_signals(age_hours=0)
                if rejected_count > 0:
                    self.logger.info(f"Archived {rejected_count} rejected signals")
            except Exception as e:
                self.logger.error(f"Rejected signals archiving error: {str(e)}")
            
            self._last_archive_check_time = current_time
            
        except Exception as e:
            self.logger.error(f"Archive check error: {str(e)}", exc_info=True)
