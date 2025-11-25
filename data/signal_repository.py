"""
SignalRepository: Signal database operations.
CRUD operations and signal ID generation.
"""
import json
import sqlite3
import time
from datetime import datetime
from typing import Dict, List, Optional, Union
from data.signal_database import SignalDatabase
from data.repositories.base_repository import BaseRepository
from utils.logger import LoggerManager


class SignalRepository(BaseRepository):
    """Signal database repository."""
    
    def __init__(self, database: SignalDatabase):
        """
        Initializes SignalRepository.
        
        Args:
            database: SignalDatabase instance
        """
        super().__init__()
        self.db = database
        # Backwards compatibility for tests/scripts referencing .database
        self.database = database
        self.logger = LoggerManager().get_logger('SignalRepository')
    
    def generate_signal_id(self, symbol: str) -> str:
        """
        Generates timestamp-based unique signal ID.
        
        Format: YYYYMMDD-HHMMSS-SYMBOL
        Example: 20241215-143022-BTCUSDT
        
        Args:
            symbol: Trading pair (e.g. BTC/USDT)
            
        Returns:
            Unique signal ID
        """
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        symbol_clean = symbol.replace('/', '').replace(':', '').upper()
        signal_id = f"{timestamp}-{symbol_clean}"
        return signal_id
    
    def save_signal(
        self,
        signal_id: Union[str, Dict],
        symbol: Optional[str] = None,
        direction: Optional[str] = None,
        signal_price: Optional[float] = None,
        confidence: Optional[float] = None,
        atr: Optional[float] = None,
        timeframe: Optional[str] = None,
        telegram_message_id: Optional[int] = None,
        telegram_channel_id: Optional[str] = None,
        tp1_price: Optional[float] = None,
        tp2_price: Optional[float] = None,
        tp3_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        signal_data: Optional[Dict] = None,
        entry_levels: Optional[Dict] = None,
        signal_score_breakdown: Optional[str] = None,
        market_context: Optional[str] = None,
        tp1_distance_r: Optional[float] = None,
        tp2_distance_r: Optional[float] = None,
        tp3_distance_r: Optional[float] = None,
        sl_distance_r: Optional[float] = None,
        optimal_entry_price: Optional[float] = None,
        conservative_entry_price: Optional[float] = None
    ) -> bool:
        """
        Saves a new signal.
        
        Args:
            signal_id: Unique signal ID
            symbol: Trading pair
            direction: LONG/SHORT
            signal_price: Signal price
            confidence: Confidence score
            atr: ATR value
            timeframe: Timeframe
            telegram_message_id: Telegram message ID
            telegram_channel_id: Telegram channel ID
            tp1_price, tp2_price, tp3_price: TP levels
            sl_price: Stop-loss level
            signal_data: Signal data dict (will be converted to JSON)
            entry_levels: Entry levels dict (will be converted to JSON)
            
        Returns:
            True if successful
        """
        try:
            if isinstance(signal_id, dict):
                prepared = self._prepare_signal_kwargs_from_dict(signal_id)
                return self.save_signal(**prepared)
            
            required_fields = {
                'symbol': symbol,
                'direction': direction,
                'signal_price': signal_price,
                'confidence': confidence
            }
            missing = [name for name, value in required_fields.items() if value is None]
            if missing:
                raise ValueError(f"Missing signal fields: {', '.join(missing)}")

            if telegram_message_id is None:
                telegram_message_id = 0
            if telegram_channel_id is None:
                telegram_channel_id = ''
            if signal_data is None:
                signal_data = {}
            if entry_levels is None:
                entry_levels = {}

            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                
                created_at = int(time.time())
                # Clean dicts for JSON serialization (convert numpy/pandas bools to Python bool)
                signal_data_clean = self.clean_for_json(signal_data)
                entry_levels_clean = self.clean_for_json(entry_levels)
                signal_data_json = json.dumps(signal_data_clean)
                entry_levels_json = json.dumps(entry_levels_clean)
                
                cursor.execute("""
                    INSERT INTO signals (
                        signal_id, symbol, direction, signal_price, confidence,
                        atr, timeframe, telegram_message_id, telegram_channel_id,
                        created_at, tp1_price, tp2_price, tp3_price,
                        sl_price,
                        signal_data, entry_levels,
                        signal_score_breakdown, market_context,
                        tp1_distance_r, tp2_distance_r, tp3_distance_r,
                        sl_distance_r,
                        optimal_entry_price, conservative_entry_price
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    signal_id, symbol, direction, signal_price, confidence,
                    atr, timeframe, telegram_message_id, telegram_channel_id,
                    created_at, tp1_price, tp2_price, tp3_price,
                    sl_price,
                    signal_data_json, entry_levels_json,
                    signal_score_breakdown, market_context,
                    tp1_distance_r, tp2_distance_r, tp3_distance_r,
                    sl_distance_r,
                    optimal_entry_price, conservative_entry_price
                ))
                
                conn.commit()
                
                self.logger.info(f"Signal saved: {signal_id} - {symbol} {direction}")
                return True
            
        except Exception as e:
            self.logger.error(f"Signal save error: {str(e)}", exc_info=True)
            return False
    
    def _prepare_signal_kwargs_from_dict(self, data: Dict) -> Dict:
        """
        Normalizes legacy dict payloads (used by tests and scripts) into the keyword
        arguments expected by save_signal.
        """
        symbol = data.get('symbol')
        signal_id = data.get('signal_id') or (symbol and self.generate_signal_id(symbol)) or self.generate_signal_id('UNKNOWN')
        signal_data = data.get('signal_data', data)
        entry_levels = data.get('entry_levels', {})
        
        return {
            'signal_id': signal_id,
            'symbol': symbol,
            'direction': data.get('direction', 'NEUTRAL'),
            'signal_price': data.get('signal_price', 0.0),
            'confidence': data.get('confidence', 0.0),
            'atr': data.get('atr'),
            'timeframe': data.get('timeframe'),
            'telegram_message_id': data.get('telegram_message_id', 0),
            'telegram_channel_id': data.get('telegram_channel_id', ''),
            'tp1_price': data.get('tp1_price'),
            'tp2_price': data.get('tp2_price'),
            'tp3_price': data.get('tp3_price'),
            'sl_price': data.get('sl_price'),
            'signal_data': signal_data,
            'entry_levels': entry_levels,
            'signal_score_breakdown': data.get('score_breakdown'),
            'market_context': data.get('market_context'),
            'tp1_distance_r': data.get('tp1_distance_r', data.get('tp1_r')),
            'tp2_distance_r': data.get('tp2_distance_r', data.get('tp2_r')),
            'tp3_distance_r': data.get('tp3_distance_r', data.get('tp3_r')),
            'sl_distance_r': data.get('sl_distance_r', data.get('sl_r')),
            'optimal_entry_price': data.get('optimal_entry_price'),
            'conservative_entry_price': data.get('conservative_entry_price')
        }
    
    def get_signal(self, signal_id: str) -> Optional[Dict]:
        """
        Retrieves a signal.
        
        Args:
            signal_id: Signal ID
            
        Returns:
            Signal dict or None
        """
        try:
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM signals WHERE signal_id = ?
                """, (signal_id,))
                
                row = cursor.fetchone()
                
                if row:
                    result = self.row_to_dict(row)
                    if 'is_active' not in result:
                        final_outcome = result.get('final_outcome')
                        result['is_active'] = 0 if final_outcome else 1
                    return result
                return None
            
        except Exception as e:
            self.logger.error(f"Signal retrieval error: {str(e)}", exc_info=True)
            return None
    
    def get_signal_by_id(self, signal_id: str) -> Optional[Dict]:
        """Alias for legacy test compatibility."""
        return self.get_signal(signal_id)
    
    def get_active_signals(self) -> List[Dict]:
        """
        Retrieves active signals (newer than 72 hours).
        Checks only 72 hours condition, regardless of TP/SL status.
        
        Returns:
            List of active signals
        """
        try:
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                
                # 72 hours = 259200 seconds
                hours_72_seconds = 72 * 3600
                
                # Get UTC timestamp (independent of system time)
                current_time_utc = int(time.time())
                threshold_time = current_time_utc - hours_72_seconds
                
                # Signals newer than 72 hours (regardless of TP/SL status)
                # Signals not deleted (message_deleted = 0)
                # Works independent of system time using UTC timestamp from Python
                cursor.execute("""
                    SELECT * FROM signals
                    WHERE created_at > ? AND (message_deleted = 0 OR message_deleted IS NULL)
                    ORDER BY created_at DESC
                """, (threshold_time,))
                
                rows = cursor.fetchall()
                active_count = len(rows)
                
                # Count signals older than 72 hours (for logger)
                cursor.execute("""
                    SELECT COUNT(*) FROM signals
                    WHERE created_at <= ?
                """, (threshold_time,))
                expired_count = cursor.fetchone()[0]
                
                # Logger messages
                self.logger.debug(f"Active signal query: {active_count} active, {expired_count} expired (older than 72h, UTC timestamp: {current_time_utc})")
                if expired_count > 0:
                    self.logger.info(f"{expired_count} signals removed from active list as they are older than 72 hours")
                
                return [self.row_to_dict(row) for row in rows]
            
        except Exception as e:
            self.logger.error(f"Active signal retrieval error: {str(e)}", exc_info=True)
            return []
    
    def get_last_signal_summary(self, symbol: str) -> Optional[Dict]:
        """Returns summary of the last active signal (message not deleted) for the specified symbol."""
        try:
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT symbol, direction, confidence, created_at
                    FROM signals
                    WHERE symbol = ?
                      AND (message_deleted = 0 OR message_deleted IS NULL)
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (symbol,)
                )

                row = cursor.fetchone()

                if row:
                    summary = {
                        'symbol': row['symbol'],
                        'direction': row['direction'],
                        'confidence': row['confidence'],
                        'created_at': row['created_at']
                    }
                    self.logger.debug(
                        "Last signal summary retrieved: %s %s @ %s",
                        summary['symbol'],
                        summary['direction'],
                        summary['created_at']
                    )
                    return summary

                self.logger.debug("Signal summary not found for %s", symbol)
                return None

        except Exception as e:
            self.logger.error(f"Last signal summary retrieval error: {str(e)}", exc_info=True)
            return None

    def get_recent_signal_summaries(self, lookback_hours: int) -> List[Dict]:
        """Returns the most recent signal summary for each symbol within the specified time range.
        
        Returns only active (message not deleted) signals.
        """
        if lookback_hours <= 0:
            lookback_hours = 24

        try:
            threshold = int(time.time()) - (lookback_hours * 3600)
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT symbol, direction, confidence, created_at
                    FROM signals
                    WHERE created_at >= ? 
                      AND (message_deleted = 0 OR message_deleted IS NULL)
                    ORDER BY created_at DESC
                    """,
                    (threshold,)
                )

                rows = cursor.fetchall()

                summaries: List[Dict] = []
                processed_symbols = set()

                for row in rows:
                    symbol = row['symbol']
                    if symbol in processed_symbols:
                        continue

                    summaries.append({
                        'symbol': symbol,
                        'direction': row['direction'],
                        'confidence': row['confidence'],
                        'created_at': row['created_at']
                    })
                    processed_symbols.add(symbol)

                self.logger.debug(
                    "Found %d symbols for cache warmup (lookback=%dh)",
                    len(summaries),
                    lookback_hours
                )
                return summaries

        except Exception as e:
            self.logger.error(f"Cache warmup data retrieval error: {str(e)}", exc_info=True)
            return []

    def update_tp_hit(
        self,
        signal_id: str,
        tp_level: int,
        hit_at: Optional[int] = None
    ) -> bool:
        """
        Updates TP hit status.
        
        Args:
            signal_id: Signal ID
            tp_level: TP level (1, 2, or 3)
            hit_at: Hit time (Unix timestamp, current time if None)
            
        Returns:
            True if successful
        """
        try:
            if hit_at is None:
                hit_at = int(time.time())
            
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                
                if tp_level == 1:
                    cursor.execute("""
                        UPDATE signals
                        SET tp1_hit = 1, tp1_hit_at = ?
                        WHERE signal_id = ? AND tp1_hit = 0
                    """, (hit_at, signal_id))
                elif tp_level == 2:
                    cursor.execute("""
                        UPDATE signals
                        SET tp2_hit = 1, tp2_hit_at = ?
                        WHERE signal_id = ? AND tp2_hit = 0
                    """, (hit_at, signal_id))
                elif tp_level == 3:
                    cursor.execute("""
                        UPDATE signals
                        SET tp3_hit = 1, tp3_hit_at = ?
                        WHERE signal_id = ? AND tp3_hit = 0
                    """, (hit_at, signal_id))
                else:
                    self.logger.warning(f"Invalid TP level: {tp_level}")
                    return False
                
                conn.commit()
                rows_affected = cursor.rowcount
                
                if rows_affected > 0:
                    self.logger.info(f"TP{tp_level} hit updated: {signal_id}")
                    return True
                else:
                    self.logger.debug(f"TP{tp_level} already hit or signal not found: {signal_id}")
                    return False
            
        except Exception as e:
            self.logger.error(f"TP hit update error: {str(e)}", exc_info=True)
            return False
    
    def update_sl_hit(
        self,
        signal_id: str,
        hit_at: Optional[int] = None
    ) -> bool:
        """
        Updates stop-loss hit status for the single SL model.
        """
        try:
            if hit_at is None:
                hit_at = int(time.time())
            
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE signals
                    SET sl_hit = 1, sl_hit_at = ?
                    WHERE signal_id = ? AND sl_hit = 0
                """, (hit_at, signal_id))
                
                conn.commit()
                rows_affected = cursor.rowcount
                
                if rows_affected > 0:
                    self.logger.info(f"SL hit updated: {signal_id}")
                    return True
                
                self.logger.debug(f"SL already hit or signal not found: {signal_id}")
                return False
            
        except Exception as e:
            self.logger.error(f"SL hit update error: {str(e)}", exc_info=True)
            return False
    
    def mark_message_deleted(self, signal_id: str) -> bool:
        """
        Marks signal's Telegram message as deleted.
        This signal will no longer appear in the active list.
        
        Args:
            signal_id: Signal ID
            
        Returns:
            True if successful
        """
        try:
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE signals
                    SET message_deleted = 1
                    WHERE signal_id = ?
                """, (signal_id,))
                
                conn.commit()
                rows_affected = cursor.rowcount
                
                if rows_affected > 0:
                    self.logger.info(f"Signal message marked as deleted: {signal_id}")
                    return True
                else:
                    self.logger.warning(f"Signal not found (message_deleted): {signal_id}")
                    return False
                
        except Exception as e:
            self.logger.error(f"Message deleted marking error: {str(e)}", exc_info=True)
            return False
    
    
    
    def get_latest_active_signal_by_symbol_direction(
        self, symbol: str, direction: str
    ) -> Optional[Dict]:
        """
        Finds the latest active signal for the specified symbol and direction.
        
        Args:
            symbol: Trading pair (e.g. BTC/USDT)
            direction: LONG/SHORT
            
        Returns:
            Signal dict or None
        """
        try:
            import time
            hours_72_seconds = 72 * 3600
            current_time_utc = int(time.time())
            threshold_time = current_time_utc - hours_72_seconds
            
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM signals
                    WHERE symbol = ? 
                      AND direction = ?
                      AND created_at > ?
                      AND (message_deleted = 0 OR message_deleted IS NULL)
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (symbol, direction, threshold_time))
                
                row = cursor.fetchone()
                
                if row:
                    signal = self.row_to_dict(row)
                    self.logger.debug(
                        "Active signal found: %s %s @ %s (signal_id: %s)",
                        symbol, direction, signal.get('created_at'), signal.get('signal_id')
                    )
                    return signal
                
                self.logger.debug("Active signal not found for %s %s", symbol, direction)
                return None
            
        except Exception as e:
            self.logger.error(
                f"Active signal finding error ({symbol} {direction}): {str(e)}",
                exc_info=True
            )
            return None
    
    def add_signal_log_entry(
        self,
        signal_id: str,
        price: float,
        confidence: float,
        old_confidence: float,
        min_log_interval_seconds: int = 600,  # 10 dakika default
        min_confidence_change: float = 0.05  # %5 default
    ) -> bool:
        """
        Adds a new entry to signal log (when new signal detected during cooldown).
        Applies filtering to prevent flooding:
        - If at least min_log_interval_seconds passed since last log entry OR
        - If confidence change exceeded min_confidence_change threshold
        - Then adds log
        
        Args:
            signal_id: Active signal ID
            price: New signal price
            confidence: New signal confidence score
            old_confidence: Active signal confidence score
            min_log_interval_seconds: Minimum log interval (seconds, default: 600 = 10 minutes)
            min_confidence_change: Minimum confidence change threshold (default: 0.05 = 5%)
            
        Returns:
            True if successful, False if skipped due to filtering
        """
        try:
            import time
            current_time = int(time.time())
            # Round to prevent floating point precision issues
            # Round to 6 decimal places, but capture very small differences too
            raw_change = confidence - old_confidence
            confidence_change = round(raw_change, 6)
            
            # If 0.0 after rounding but raw_change is not 0,
            # it means there is a very small difference, keep it
            if confidence_change == 0.0 and abs(raw_change) > 1e-10:
                # Record very small differences too (e.g. 0.76 - 0.759 = 0.001)
                confidence_change = raw_change
            
            # Get current signal info
            signal = self.get_signal(signal_id)
            if not signal:
                self.logger.warning(f"Signal not found (add log): {signal_id}")
                return False
            
            # Get current signal_log or create empty list
            signal_log = signal.get('signal_log', [])
            if not isinstance(signal_log, list):
                signal_log = []
            
            # Flood prevention: Check last log entry
            if signal_log:
                # Get last entry (most recently added)
                last_entry = signal_log[-1]
                last_timestamp = last_entry.get('timestamp', 0)
                time_since_last = current_time - last_timestamp
                
                # Get absolute value of confidence change
                abs_confidence_change = abs(confidence_change)
                
                # Filtering: Add log only if significant change or time interval passed
                should_log = (
                    time_since_last >= min_log_interval_seconds or  # Time interval passed
                    abs_confidence_change >= min_confidence_change  # Significant confidence change
                )
                
                if not should_log:
                    # Log not added (due to filtering)
                    self.logger.debug(
                        f"Signal log entry skipped (filtering): {signal_id} - "
                        f"son_log={time_since_last}s, confidence_change={confidence_change:+.3f}, "
                        f"min_interval={min_log_interval_seconds}s, min_change={min_confidence_change}"
                    )
                    return False
            
            # Create new entry
            new_entry = {
                "timestamp": current_time,
                "event_type": "new_signal",
                "price": float(price),
                "confidence": float(confidence),
                "confidence_change": float(confidence_change)
            }
            
            # Add entry
            signal_log.append(new_entry)
            
            # Convert to JSON and update
            signal_log_json = json.dumps(signal_log)
            
            # Convert to JSON and update
            signal_log_json = json.dumps(signal_log)
            
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE signals
                    SET signal_log = ?
                    WHERE signal_id = ?
                """, (signal_log_json, signal_id))
                
                conn.commit()
                rows_affected = cursor.rowcount
                
                if rows_affected > 0:
                    self.logger.info(
                        f"Signal log entry added: {signal_id} - "
                        f"price={price}, confidence={confidence:.3f}, change={confidence_change:+.3f}"
                    )
                    return True
                else:
                    self.logger.warning(f"Signal could not be updated (add log): {signal_id}")
                    return False
                
        except Exception as e:
            self.logger.error(
                f"Signal log entry add error: {str(e)}",
                exc_info=True
            )
            return False
    
    def get_latest_confidence_change(self, signal_id: str) -> Optional[float]:
        """
        Returns the latest confidence_change value from signal log.
        
        Args:
            signal_id: Signal ID
            
        Returns:
            Latest confidence_change value or None
        """
        try:
            signal = self.get_signal(signal_id)
            if not signal:
                return None
            
            signal_log = signal.get('signal_log', [])
            if not isinstance(signal_log, list) or not signal_log:
                return None
            
            # Get last entry (should be sorted by timestamp)
            # Or get the most recently added entry
            latest_entry = signal_log[-1]
            
            if latest_entry.get('event_type') == 'new_signal':
                confidence_change = latest_entry.get('confidence_change')
                if confidence_change is not None:
                    return float(confidence_change)
            
            return None
            
        except Exception as e:
            self.logger.error(
                f"Latest confidence_change retrieval error: {str(e)}",
                exc_info=True
            )
            return None
    
    def update_mfe_mae(
        self,
        signal_id: str,
        mfe_price: Optional[float],
        mfe_at: Optional[int],
        mae_price: Optional[float],
        mae_at: Optional[int]
    ) -> bool:
        """
        Updates MFE/MAE.
        
        Args:
            signal_id: Signal ID
            mfe_price: Maximum Favorable Excursion price
            mfe_at: MFE time (unix timestamp)
            mae_price: Maximum Adverse Excursion price
            mae_at: MAE time (unix timestamp)
            
        Returns:
            True if successful
        """
        try:
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE signals
                    SET mfe_price = ?, mfe_at = ?, mae_price = ?, mae_at = ?
                    WHERE signal_id = ?
                """, (mfe_price, mfe_at, mae_price, mae_at, signal_id))
                
                conn.commit()
            
            self.logger.debug(f"MFE/MAE updated: {signal_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"MFE/MAE update error: {str(e)}", exc_info=True)
            return False
    
    def update_alternative_entry_hit(
        self,
        signal_id: str,
        entry_type: str,
        hit_at: int
    ) -> bool:
        """
        Records optimal/conservative entry hit.
        
        Args:
            signal_id: Signal ID
            entry_type: 'optimal' or 'conservative'
            hit_at: Hit time (unix timestamp)
            
        Returns:
            True if successful
        """
        try:
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                
                if entry_type == 'optimal':
                    cursor.execute("""
                        UPDATE signals
                        SET optimal_entry_hit = 1, optimal_entry_hit_at = ?
                        WHERE signal_id = ?
                    """, (hit_at, signal_id))
                elif entry_type == 'conservative':
                    cursor.execute("""
                        UPDATE signals
                        SET conservative_entry_hit = 1, conservative_entry_hit_at = ?
                        WHERE signal_id = ?
                    """, (hit_at, signal_id))
                else:
                    self.logger.warning(f"Invalid entry_type: {entry_type}")
                    return False
                
                conn.commit()
            
            self.logger.debug(f"Alternative entry hit: {signal_id} - {entry_type}")
            return True
            
        except Exception as e:
            self.logger.error(f"Alternative entry hit update error: {str(e)}", exc_info=True)
            return False
    
    def finalize_signal(
        self,
        signal_id: str,
        final_price: float,
        final_outcome: str
    ) -> bool:
        """
        Records signal closure.
        
        Args:
            signal_id: Signal ID
            final_price: Signal closing price
            final_outcome: 'tp1_reached', 'tp2_reached', 'tp3_reached',
                          'sl_hit', 'expired_no_target'
            
        Returns:
            True if successful
        """
        try:
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE signals
                    SET final_price = ?, final_outcome = ?
                    WHERE signal_id = ?
                """, (final_price, final_outcome, signal_id))
                
                conn.commit()
            
            self.logger.info(f"Sinyal finalized: {signal_id} - {final_outcome} @ {final_price}")
            return True
            
        except Exception as e:
            self.logger.error(f"Sinyal finalize hatası: {str(e)}", exc_info=True)
            return False
    
    def save_price_snapshot(
        self,
        signal_id: str,
        timestamp: int,
        price: float,
        source: str
    ) -> bool:
        """
        Snapshot kaydeder.
        
        Args:
            signal_id: Signal ID
            timestamp: Unix timestamp
            price: Fiyat
            source: 'tracker_tick', 'manual_update', 'finalize'
            
        Returns:
            True ise başarılı
        """
        try:
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO signal_price_snapshots (signal_id, timestamp, price, source)
                    VALUES (?, ?, ?, ?)
                """, (signal_id, timestamp, price, source))
                
                conn.commit()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Snapshot kayıt hatası: {str(e)}", exc_info=True)
            return False
    
    def save_rejected_signal(
        self,
        symbol: Union[str, Dict],
        direction: Optional[str] = None,
        confidence: Optional[float] = None,
        signal_price: Optional[float] = None,
        rejection_reason: Optional[str] = None,
        score_breakdown: Optional[str] = None,
        market_context: Optional[str] = None,
        signal_id: Optional[str] = None
    ) -> bool:
        """
        Reddedilen sinyal kaydeder.
        
        Args:
            symbol: Trading pair
            direction: LONG/SHORT/NEUTRAL
            confidence: Güven skoru
            signal_price: Sinyal fiyatı
            rejection_reason: 'direction_neutral', 'cooldown_active', 'confidence_below_threshold'
            score_breakdown: JSON string
            market_context: JSON string
            
        Returns:
            True ise başarılı
        """
        try:
            if isinstance(symbol, dict):
                data = symbol
                return self.save_rejected_signal(
                    symbol=data.get('symbol'),
                    direction=data.get('direction'),
                    confidence=data.get('confidence'),
                    signal_price=data.get('signal_price', 0.0),
                    rejection_reason=data.get('rejection_reason') or data.get('rejected_reason'),
                    score_breakdown=data.get('score_breakdown'),
                    market_context=data.get('market_context'),
                    signal_id=data.get('signal_id')
                )
            
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                
                created_at = int(time.time())
                
                cursor.execute("""
                    INSERT INTO rejected_signals (
                        signal_id, symbol, direction, confidence, signal_price,
                        created_at, rejection_reason, score_breakdown, market_context, rejected_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    signal_id or f"REJ-{created_at}",
                    symbol,
                    direction,
                    confidence,
                    signal_price or 0.0,
                    created_at,
                    rejection_reason,
                    score_breakdown,
                    market_context,
                    rejection_reason
                ))
                
                conn.commit()
            
            self.logger.debug(f"Rejected signal kaydedildi: {symbol} - {rejection_reason}")
            return True
            
        except Exception as e:
            self.logger.error(f"Rejected signal kayıt hatası: {str(e)}", exc_info=True)
            return False
    
    def get_price_snapshots(self, signal_id: str) -> List[Dict]:
        """
        Sinyale ait tüm snapshot'ları döner.
        
        Args:
            signal_id: Signal ID
            
        Returns:
            Snapshot listesi
        """
        try:
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM signal_price_snapshots
                    WHERE signal_id = ?
                    ORDER BY timestamp
                """, (signal_id,))
                
                rows = cursor.fetchall()
            
            snapshots = [dict(row) for row in rows]
            return snapshots
            
        except Exception as e:
            self.logger.error(f"Snapshot getirme hatası: {str(e)}", exc_info=True)
            return []
    
    def save_metrics_summary(
        self,
        period_start: int,
        period_end: int,
        metrics: Dict
    ) -> bool:
        """
        Özet metrik kaydeder.
        
        Args:
            period_start: Dönem başlangıcı (unix timestamp)
            period_end: Dönem sonu (unix timestamp)
            metrics: Metrikler dict
            
        Returns:
            True ise başarılı
        """
        try:
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                
                metrics_json = json.dumps(metrics)
                cursor.execute("""
                    INSERT INTO signal_metrics_summary (
                        period_start, period_end,
                        total_signals, long_signals, short_signals, neutral_filtered,
                        avg_confidence, tp1_hit_rate, tp2_hit_rate, tp3_hit_rate,
                        sl_hit_rate,
                        avg_mfe_percent, avg_mae_percent,
                        avg_time_to_first_target_hours, market_regime, metrics_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    period_start, period_end,
                    metrics.get('total_signals', 0),
                    metrics.get('long_signals', 0),
                    metrics.get('short_signals', 0),
                    metrics.get('neutral_filtered', 0),
                    metrics.get('avg_confidence', 0.0),
                    metrics.get('tp1_hit_rate', 0.0),
                    metrics.get('tp2_hit_rate', 0.0),
                    metrics.get('tp3_hit_rate', 0.0),
                    metrics.get('sl_hit_rate', 0.0),
                    metrics.get('avg_mfe_percent', 0.0),
                    metrics.get('avg_mae_percent', 0.0),
                    metrics.get('avg_time_to_first_target_hours', 0.0),
                    metrics.get('market_regime', 'unknown'),
                    metrics_json
                ))
                
                conn.commit()
            
            self.logger.info(f"Metrics summary kaydedildi: {period_start} - {period_end}")
            return True
            
        except Exception as e:
            self.logger.error(f"Metrics summary kayıt hatası: {str(e)}", exc_info=True)
            return False
    
    def get_signals_by_time_range(self, start_ts: int, end_ts: int) -> List[Dict]:
        """
        Belirli zaman aralığındaki sinyalleri döner.
        
        Args:
            start_ts: Başlangıç timestamp
            end_ts: Bitiş timestamp
            
        Returns:
            Sinyal listesi
        """
        try:
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM signals
                    WHERE created_at >= ? AND created_at <= ?
                    ORDER BY created_at
                """, (start_ts, end_ts))
                
                rows = cursor.fetchall()
            
            signals = []
            for row in rows:
                signal = dict(row)
                # Parse JSON fields
                if signal.get('signal_data'):
                    try:
                        signal['signal_data'] = json.loads(signal['signal_data'])
                    except:
                        pass
                if signal.get('entry_levels'):
                    try:
                        signal['entry_levels'] = json.loads(signal['entry_levels'])
                    except:
                        pass
                if signal.get('signal_log'):
                    try:
                        signal['signal_log'] = json.loads(signal['signal_log'])
                    except:
                        pass
                signals.append(signal)
            
            return signals
            
        except Exception as e:
            self.logger.error(f"Time range signals getirme hatası: {str(e)}", exc_info=True)
            return []

