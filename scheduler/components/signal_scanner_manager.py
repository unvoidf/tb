"""
SignalScannerManager: Background signal scanner and notification manager.
Scans top 5 futures coins, captures strong signals, and applies active signal checks.
"""
import time
import json
from typing import Dict, List, Optional, Union, Tuple, Any
from utils.logger import LoggerManager
from data.coin_filter import CoinFilter
from config.constants import SL_MULTIPLIER

from strategy.dynamic_entry_calculator import DynamicEntryCalculator
from bot.message_formatter import MessageFormatter
from bot.telegram_bot_manager import TelegramBotManager
from scheduler.components.signal_ranker import SignalRanker
from data.signal_repository import SignalRepository
from strategy.risk_reward_calculator import RiskRewardCalculator
from strategy.liquidation_safety_filter import LiquidationSafetyFilter
from analysis.signal_generator import SignalGenerator
from data.market_data_manager import MarketDataManager


class SignalScannerManager:
    """Signal scanning and notification manager."""
    
    def __init__(
        self,
        coin_filter: CoinFilter,
        market_data: MarketDataManager,
        signal_generator: SignalGenerator,
        entry_calculator: DynamicEntryCalculator,
        message_formatter: MessageFormatter,
        bot_manager: TelegramBotManager,
        channel_id: str,
        signal_repository: Optional[SignalRepository] = None,
        confidence_threshold: float = 0.69,
        ranging_min_sl_percent: float = 0.5,
        risk_reward_calc: Optional[RiskRewardCalculator] = None,
        liquidation_safety_filter: Optional[LiquidationSafetyFilter] = None,
        signal_tracker: Optional[object] = None,  # SignalTracker instance (optional)
        config=None  # ConfigManager instance for direction-specific thresholds
    ):
        """
        Initializes SignalScannerManager.
        
        Args:
        Args:
            coin_filter: Coin filter instance
            market_data: Market data manager
            signal_generator: Signal generator
            entry_calculator: Dynamic entry calculator
            message_formatter: Message formatter
            bot_manager: Telegram bot manager
            channel_id: Telegram channel ID
            signal_repository: Signal repository (optional, for saving signals)
            confidence_threshold: Minimum confidence threshold (default: 0.69 = %69)
                DEPRECATED: Use config.confidence_threshold_long/short instead
            config: ConfigManager instance (for direction-specific thresholds)
        """
        self.coin_filter = coin_filter
        self.coin_filter = coin_filter
        self.market_data = market_data
        self.signal_gen = signal_generator
        self.entry_calc = entry_calculator
        self.formatter = message_formatter
        self.bot_mgr = bot_manager
        self.channel_id = channel_id
        self.signal_repository = signal_repository
        self.confidence_threshold = confidence_threshold
        self.risk_reward_calc = risk_reward_calc  # Risk/Reward calculator
        self.liquidation_safety_filter = liquidation_safety_filter  # Liquidation safety filter
        self.signal_tracker = signal_tracker  # SignalTracker instance (optional, for message updates)
        self.ranging_min_sl_percent = ranging_min_sl_percent
        self.config = config  # Store config for direction-specific thresholds
        
        self.logger = LoggerManager().get_logger('SignalScannerManager')
        
        # SignalRanker instance (for RSI and volume bonuses)
        self.signal_ranker = SignalRanker()
        
        # Signal cache: {symbol: {last_signal_time, last_direction, confidence}}
        self.signal_cache: Dict[str, Dict] = {}
        
        # Log startup configuration
        self.logger.info(
            "SignalScannerManager başlatıldı - "
            "threshold=%s, ranging_min_sl=%s%%",
            confidence_threshold,
            ranging_min_sl_percent,
        )
        
        # Log direction-specific thresholds (from config or defaults)
        long_threshold = self.config.confidence_threshold_long if self.config else 0.90
        short_threshold = self.config.confidence_threshold_short if self.config else 0.69
        self.logger.info(
            "Direction-Specific Thresholds: LONG=%.2f (%.0f%%), SHORT=%.2f (%.0f%%)",
            long_threshold, long_threshold * 100,
            short_threshold, short_threshold * 100
        )

        # Cache warmup for active signal check
        self._warmup_cache_from_db()
    
    def scan_for_signals(self) -> None:
        """
        Scans Top Futures coins (Hybrid: Majors + Radar).
        """
        try:
            self.logger.info("Sinyal tarama başlatıldı (Hibrit Mod)")
            
            # Market Pulse Report (Market Pulse Log) - At the beginning of scan
            self._log_market_pulse()
            
            # Hybrid Scan List (Count = 50)
            symbols = self.coin_filter.get_top_futures_coins(50)
            
            if not symbols:
                self.logger.warning("Futures coin listesi alınamadı")
                return
            
            # Statistics
            stats = {
                'TOTAL_SCANNED': 0,
                'GENERATED': 0,
                'REJECTED_RR': 0,
                'REJECTED_TREND': 0,
                'REJECTED_CONFIDENCE': 0,
                'REJECTED_BTC': 0,
                'REJECTED_HIGH_VOLATILITY': 0,
                'NO_SIGNAL': 0
            }
            
            # Signal check for each coin
            for symbol in symbols:
                try:
                    stats['TOTAL_SCANNED'] += 1
                    self._check_symbol_signal(symbol, stats)
                except Exception as e:
                    self.logger.error(f"{symbol} sinyal kontrolü hatası: {str(e)}", exc_info=True)
            
            # Scan Summary Report
            self._log_scan_summary(stats)
            self.logger.info("Sinyal tarama tamamlandı")
            
        except Exception as e:
            self.logger.error(f"Sinyal tarama hatası: {str(e)}", exc_info=True)
    
    def _check_symbol_signal(self, symbol: str, stats: Dict = None) -> None:
        """
        Performs signal check for a single coin.
        
        Args:
            symbol: Trading pair (örn: BTC/USDT)
            stats: İstatistik dict (referans olarak güncellenir)
        """
        try:
            # Analyze signal for coin (with return_reason=True)
            signal_data, reason = self._analyze_symbol(symbol, return_reason=True)
            
            if not signal_data:
                self.logger.debug(f"{symbol} için sinyal verisi yok (Reason: {reason})")
                
                if stats:
                    if reason == 'FILTER_R_R':
                        stats['REJECTED_RR'] += 1
                    elif reason == 'FILTER_BTC_CRASH':
                        stats['REJECTED_BTC'] += 1
                    elif reason in ('FILTER_CIRCUIT_BREAKER', 'FILTER_VOLUME_CLIMAX', 'FILTER_BREAKOUT', 'FILTER_BREAKDOWN'):
                        stats['REJECTED_TREND'] += 1
                    else:
                        stats['NO_SIGNAL'] += 1
                return
            
            # DEBUG: Type check
            if not isinstance(signal_data, dict):
                self.logger.error(f"{symbol} signal_data is NOT a dict! Type: {type(signal_data)}, Value: {signal_data}")
                if stats: stats['NO_SIGNAL'] += 1
                return
            
            # Get general signal info
            overall_direction = signal_data.get('direction')
            overall_confidence = signal_data.get('confidence', 0.0)
            
            # Calculate bonus scores with SignalRanker
            # Format expected by SignalRanker: [{'symbol': str, 'signal': dict}]
            signal_for_ranker = [{
                'symbol': symbol,
                'signal': signal_data
            }]
            
            # Calculate total score with RSI and volume bonuses
            ranked_signals = self.signal_ranker.rank_signals(signal_for_ranker, top_count=1)
            
            if ranked_signals:
                # Ranked signal found, get total score directly (no recalculation!)
                ranked_signal = ranked_signals[0]
                
                # _ranking_info from SignalRanker contains all score info
                ranking_info = ranked_signal.get('_ranking_info', {})
                total_score = ranking_info.get('total_score', 0.0)
                rsi_bonus = ranking_info.get('rsi_bonus', 0.0)
                volume_bonus = ranking_info.get('volume_bonus', 0.0)
                base_score = ranking_info.get('base_score', 0.0)

                # BUG FIX: Update reported confidence score with total_score including bonuses.
                # This ensures the score filtered is the same as the one shown to the user.
                # Confidence value cannot exceed 100% (1.0 cap)
                capped_confidence = min(total_score, 1.0)
                signal_data['confidence'] = capped_confidence
                
                if total_score > 1.0:
                    self.logger.warning(
                        f"{symbol} total_score {total_score:.3f} > 1.0, confidence {capped_confidence:.3f} olarak cap'lendi"
                    )
                
                self.logger.debug(
                    f"{symbol} sinyal: direction={overall_direction}, "
                    f"base_confidence={overall_confidence:.3f}, "
                    f"rsi_bonus={rsi_bonus:.3f}, volume_bonus={volume_bonus:.3f}, "
                    f"total_score={total_score:.3f}, capped_confidence={capped_confidence:.3f}"
                )
                
                # Confidence threshold check (direction-specific)
                # Data: LONG 6.67% WR vs SHORT 36.84% WR → Different thresholds
                direction = signal_data.get('direction', 'NEUTRAL')
                min_threshold = self._get_direction_threshold(direction)
                
                if total_score < min_threshold:
                    self._log_rejection_scorecard(
                        symbol, total_score, min_threshold,
                        signal_data, ranking_info
                    )
                    if stats: stats['REJECTED_CONFIDENCE'] += 1
                    return
            else:
                # Could not be ranked (below threshold)
                self.logger.debug(
                    f"{symbol} sinyal: direction={overall_direction}, "
                    f"confidence={overall_confidence:.3f} (rank edilemedi)"
                )
                
                # Direction-specific threshold check
                min_threshold = self._get_direction_threshold(overall_direction)
                
                if overall_confidence < min_threshold:
                    self._log_rejection_scorecard(
                        symbol, overall_confidence, min_threshold,
                        signal_data, None
                    )
                    if stats: stats['REJECTED_CONFIDENCE'] += 1
                    return
            
            # ATR Minimum Filter (Data: 51.7% failure for ATR <2%)
            atr_value = signal_data.get('atr')
            entry_price = signal_data.get('entry_price') or signal_data.get('signal_price')
            
            if atr_value and entry_price:
                atr_percent = (atr_value / entry_price) * 100
                min_atr = self.config.min_atr_percent if self.config else 2.0
                
                if atr_percent < min_atr:
                    self.logger.warning(
                        f"{symbol} rejected: ATR too low ({atr_percent:.2f}% < {min_atr}%). "
                        f"Low volatility signals are unreliable (51.7% historical failure rate)."
                    )
                    if stats: 
                        if 'REJECTED_LOW_ATR' not in stats:
                            stats['REJECTED_LOW_ATR'] = 0
                        stats['REJECTED_LOW_ATR'] += 1
                    return
            
            # Trending market + opposite direction = mismatch
            # NEUTRAL direction signals are not sent to channel (UX/noise control)
            if overall_direction == 'NEUTRAL':
                self.logger.debug(
                    f"{symbol} sinyali NEUTRAL (score={total_score:.3f}); kanal bildirimi atlandı"
                )
                if stats: stats['NO_SIGNAL'] += 1 # NEUTRAL teknik olarak sinyal değil
                return
            
            # TREND-DIRECTION MISMATCH CHECK (Financial Expert Recommendation)
            # LONG signal in trending_down, SHORT signal in trending_up should be rejected
            market_context = signal_data.get('market_context', {})
            regime = market_context.get('regime')
            adx_strength = market_context.get('adx_strength', 0)
            
            if regime == 'trending_down' and overall_direction == 'LONG':
                self.logger.info(
                    f"{symbol} LONG sinyali reddedildi: Market regime 'trending_down' "
                    f"(ADX={adx_strength:.1f}). Trend-yön uyumsuzluğu."
                )
                if stats: stats['REJECTED_TREND'] += 1
                return
            
            if regime == 'trending_up' and overall_direction == 'SHORT':
                self.logger.info(
                    f"{symbol} SHORT sinyali reddedildi: Market regime 'trending_up' "
                    f"(ADX={adx_strength:.1f}). Trend-yön uyumsuzluğu."
                )
                if stats: stats['REJECTED_TREND'] += 1
                return
            
            # VOLATILITY FILTER (Financial Expert Recommendation)
            # NOTE: Volatility penalty is already applied in adaptive_thresholds.py.
            # Applying it here again creates a "double penalty".
            # Therefore, this code block is disabled.
            # volatility_percentile = market_context.get('volatility_percentile', 50.0)
            # if volatility_percentile > 80: ... (REMOVED)
            
            # RANGING MARKET FILTER (Financial Expert Recommendation)
            # Only high confidence signals should pass in ranging market
            if regime == 'ranging' or adx_strength < 25:
                # Raise threshold in ranging market or weak trend
                ranging_threshold = 0.8
                if total_score < ranging_threshold:
                    self.logger.info(
                        f"{symbol} ranging/zayıf trend (ADX={adx_strength:.1f}), "
                        f"score={total_score:.3f} < {ranging_threshold}, atlandı"
                    )
                    if stats: stats['REJECTED_CONFIDENCE'] += 1 # Stuck at high threshold
                    return

            # Successful signal
            if stats: stats['GENERATED'] += 1

            # Fill _temp_signal_data (for rejected signal record)
            if not hasattr(self, '_temp_signal_data'):
                self._temp_signal_data = {}
            self._temp_signal_data[symbol] = signal_data

            # Active signal check
            should_send = self._should_send_notification(symbol, overall_direction, signal_data)
            if not should_send:
                return
            
            # Send notification
            self._send_signal_notification(symbol, signal_data)
            
        except Exception as e:
            self.logger.error(f"{symbol} sinyal kontrolü hatası: {str(e)}", exc_info=True)

    
    def _should_send_notification(self, symbol: str, direction: str, signal_data: Dict) -> bool:
        """
        Checks whether notification should be sent.
        Rejected if active signal (message_deleted=0) exists.
        
        Args:
            symbol: Trading pair
            direction: LONG/SHORT/NEUTRAL
            signal_data: Signal data (for rejection record)
            
        Returns:
            True if notification should be sent (no active signal)
        """
        # NEUTRAL direction signals are always rejected
        if direction == 'NEUTRAL':
            self.logger.debug(
                f"{symbol} NEUTRAL yönlü sinyal gönderilmiyor"
            )
            # Save rejected signal
            if self.signal_repository:
                score_breakdown = signal_data.get('score_breakdown', {})
                market_context = signal_data.get('market_context', {})
                current_price = self.market_data.get_latest_price(symbol)
                self.signal_repository.save_rejected_signal(
                    symbol=symbol,
                    direction=direction,
                    confidence=signal_data.get('confidence', 0),
                    signal_price=current_price if current_price else 0,
                    rejection_reason='direction_neutral',
                    score_breakdown=json.dumps(score_breakdown) if score_breakdown else None,
                    market_context=json.dumps(market_context) if market_context else None
                )
            return False
        
        # Check if active signal exists in cache
        cache_entry = self.signal_cache.get(symbol)
        
        if cache_entry is None:
            # Cache miss: Check from DB
            cache_entry = self._load_cache_entry_from_db(symbol)
            if cache_entry is None:
                # No active signal in DB either
                self.logger.debug("%s için aktif sinyal yok, bildirim gönderilecek", symbol)
                return True
            # Active signal found in DB
            self.logger.debug(
                "%s için aktif sinyal bulundu (DB'den): signal_id=%s",
                symbol,
                cache_entry.get('signal_id')
            )
            # Save rejected signal
            if self.signal_repository:
                score_breakdown = signal_data.get('score_breakdown', {})
                market_context = signal_data.get('market_context', {})
                current_price = self.market_data.get_latest_price(symbol)
                self.signal_repository.save_rejected_signal(
                    symbol=symbol,
                    direction=direction,
                    confidence=signal_data.get('confidence', 0),
                    signal_price=current_price if current_price else 0,
                    rejection_reason='active_signal_exists',
                    score_breakdown=json.dumps(score_breakdown) if score_breakdown else None,
                    market_context=json.dumps(market_context) if market_context else None
                )
            return False
        
        # Is there active signal in cache?
        if cache_entry.get('has_active_signal', False):
            self.logger.debug(
                "%s için aktif sinyal var (cache'den), bildirim gönderilmeyecek",
                symbol
            )
            # Save rejected signal
            if self.signal_repository:
                score_breakdown = signal_data.get('score_breakdown', {})
                market_context = signal_data.get('market_context', {})
                current_price = self.market_data.get_latest_price(symbol)
                self.signal_repository.save_rejected_signal(
                    symbol=symbol,
                    direction=direction,
                    confidence=signal_data.get('confidence', 0),
                    signal_price=current_price if current_price else 0,
                    rejection_reason='active_signal_exists',
                    score_breakdown=json.dumps(score_breakdown) if score_breakdown else None,
                    market_context=json.dumps(market_context) if market_context else None
                )
            return False
        
        # No active signal
        return True
    
    def _load_cache_entry_from_db(self, symbol: str) -> Optional[Dict]:
        """Checks active signal from database on cache miss."""
        if not self.signal_repository:
            return None

        # Check if active signal exists (message_deleted=0, direction doesn't matter)
        active_signal = self.signal_repository.get_latest_active_signal_by_symbol(symbol)
        if not active_signal:
            # No active signal
            self._update_signal_cache(
                symbol=symbol,
                has_active_signal=False,
                source='db-fallback'
            )
            return None

        # Active signal exists
        return self._update_signal_cache(
            symbol=symbol,
            has_active_signal=True,
            signal_id=active_signal.get('signal_id'),
            direction=active_signal.get('direction', 'NEUTRAL'),
            confidence=float(active_signal.get('confidence', 0.0) or 0.0),
            timestamp=active_signal.get('created_at'),
            source='db-fallback'
        )
    

    def _send_signal_notification(self, symbol: str, signal_data: Dict) -> None:
        """
        Sends signal notification.
        
        Args:
            symbol: Trading pair
            signal_data: Signal data
        """
        try:
            # Price at signal generation time (signal_price)
            current_price = self.market_data.get_latest_price(symbol)
            signal_price = current_price
            signal_created_at = int(time.time())
            
            if not current_price:
                self.logger.warning(f"{symbol} güncel fiyat alınamadı")
                return
            
            # Calculate dynamic entry levels
            direction = signal_data.get('direction')
            confidence = signal_data.get('confidence', 0.0)
            strategy_type = signal_data.get('strategy_type', 'trend')
            custom_targets = signal_data.get('custom_targets') if isinstance(signal_data.get('custom_targets'), dict) else {}
            
            # Get OHLCV data (for entry calculation)
            df = None
            atr = None
            
            try:
                # Get data from 1h timeframe
                df = self.market_data.fetch_ohlcv(symbol, '1h', 200)
                
                # Calculate ATR (correct class name: TechnicalIndicatorCalculator)
                if df is not None and len(df) > 14:
                    from analysis.technical_indicators import TechnicalIndicatorCalculator
                    indicators = TechnicalIndicatorCalculator()
                    atr = indicators.calculate_atr(df, period=14)
            except Exception as e:
                self.logger.warning(f"{symbol} OHLCV/ATR hesaplama hatası: {str(e)}")
            
            # Calculate entry levels
            entry_levels = self.entry_calc.calculate_entry_levels(
                symbol=symbol,
                direction=direction,
                current_price=current_price,
                df=df,
                atr=atr,
                timeframe='1h'
            )
            
            # Get current price again at sending time (to show small differences)
            now_price = self.market_data.get_latest_price(symbol)
            if not now_price:
                now_price = signal_price
            current_price_timestamp = int(time.time())

            # Generate Signal ID (to be shown in message format)
            signal_id = None
            if self.signal_repository:
                signal_id = self.signal_repository.generate_signal_id(symbol)

            # Liquidation risk analysis (To be shown in Telegram message - BEFORE format_signal_alert)
            if self.liquidation_safety_filter:
                try:
                    # Calculate TP/SL levels (for liquidation risk analysis)
                    if strategy_type == 'ranging' and custom_targets:
                        tp_sl_levels = self._build_custom_tp_sl_levels(custom_targets)
                    else:
                        tp_sl_levels = self._calculate_tp_sl_levels(
                            signal_price=signal_price,
                            direction=direction,
                            atr=atr,
                            timeframe='1h'
                        )
                    
                    # Get SL price (single stop-loss)
                    sl_price = tp_sl_levels.get('sl_price')
                    
                    if sl_price and sl_price > 0:
                        # Default balance (can be read from config in real market)
                        default_balance = 10000.0  # USDT
                        
                        liquidation_risk_percentage = self.liquidation_safety_filter.calculate_liquidation_risk_percentage(
                            entry_price=signal_price,
                            sl_price=sl_price,
                            direction=direction,
                            balance=default_balance
                        )
                        
                        # Add to signal_data (to be shown in Telegram message)
                        if 'liquidation_risk_percentage' not in signal_data:
                            signal_data['liquidation_risk_percentage'] = liquidation_risk_percentage
                        
                        # Write to log
                        self.logger.info(
                            f"Bu sinyal %{liquidation_risk_percentage:.2f} likidite riski taşımaktadır. "
                            f"(Signal ID: {signal_id}, Symbol: {symbol})"
                        )
                        
                except Exception as liq_error:
                    self.logger.warning(
                        f"Liquidation risk analizi yapılamadı: {str(liq_error)} - "
                        f"Signal ID: {signal_id}, Symbol: {symbol}",
                        exc_info=True
                    )

            # Format message
            message = self.formatter.format_signal_alert(
                symbol=symbol,
                signal_data=signal_data,
                entry_levels=entry_levels,
                signal_price=signal_price,
                now_price=now_price,
                created_at=signal_created_at,
                current_price_timestamp=current_price_timestamp,
                tp_hit_times=None,
                sl_hit_times=None,
                signal_id=signal_id,
                confidence_change=None  # New signal, no change
            )
            
            # Create inline keyboard
            keyboard = self.formatter.create_signal_keyboard(signal_id)
            
            # Send to Telegram channel and get message_id (with keyboard)
            message_id = self._send_to_channel(message, reply_markup=keyboard)
            
            if message_id:
                self.logger.info(
                    f"{symbol} sinyal bildirimi gönderildi (dir={direction}, score={confidence:.3f}) - "
                    f"Message ID: {message_id}, Signal ID: {signal_id}"
                )
                
                # Save signal to database
                if self.signal_repository and signal_id:
                    try:
                        self._save_signal_to_db(
                            symbol=symbol,
                            signal_data=signal_data,
                            entry_levels=entry_levels,
                            signal_price=signal_price,
                            atr=atr,
                            timeframe='1h',
                            telegram_message_id=message_id,
                            telegram_channel_id=self.channel_id,
                            signal_id=signal_id
                        )
                    except Exception as db_error:
                        self.logger.error(
                            f"{symbol} sinyal veritabanına kaydedilemedi: {str(db_error)} - "
                            f"Signal ID: {signal_id}, Message ID: {message_id}",
                            exc_info=True
                        )

                # Update cache (active signal exists)
                self._update_signal_cache(
                    symbol=symbol,
                    has_active_signal=True,
                    signal_id=signal_id,
                    direction=direction,
                    confidence=confidence,
                    timestamp=signal_created_at,
                    source='send'
                )
            else:
                # Message could not be sent or message_id could not be obtained
                error_msg = (
                    f"{symbol} sinyal bildirimi gönderilemedi veya message_id alınamadı - "
                    f"Signal ID: {signal_id if signal_id else 'None'}"
                )
                self.logger.error(error_msg)
                
                # Eğer signal_id varsa, bu durumu daha detaylı logla
                # (Message might be sent but message_id missing)
                if signal_id:
                    self.logger.warning(
                        f"⚠️ KRİTİK: {symbol} için sinyal mesajı gönderilmeye çalışıldı ama "
                        f"message_id alınamadı. Signal ID: {signal_id}. "
                        f"Eğer mesaj Telegram'da görünüyorsa, bu sinyal veritabanına kaydedilmemiş olabilir. "
                        f"Bu sinyal manuel olarak veritabanına eklenmelidir."
                    )
                
                # IMPORTANT: Cache update must be done even if message_id is missing
                # Because message might be sent to Telegram (but message_id missing)
                # In this case active signal check must work so same signal is not sent again
                # Cache update is critical for active signal check
                self.logger.warning(
                    f"{symbol} için cache güncelleniyor (message_id alınamadı ama aktif sinyal korunmalı) - "
                    f"Signal ID: {signal_id}, Direction: {direction}, Timestamp: {signal_created_at}"
                )
                self._update_signal_cache(
                    symbol=symbol,
                    has_active_signal=True,
                    signal_id=signal_id,
                    direction=direction,
                    confidence=confidence,
                    timestamp=signal_created_at,
                    source='send-failed'  # Use 'send-failed' as source
                )
            
        except Exception as e:
            self.logger.error(f"{symbol} bildirim gönderme hatası: {str(e)}", exc_info=True)
            
            # Cache update must be done even in exception case (active signal must be preserved)
            # If message was attempted to be sent but exception occurred,
            # cache must be updated for active signal check to work
            try:
                # signal_data is available as parameter so can be accessed directly
                direction = signal_data.get('direction')
                confidence = signal_data.get('confidence', 0.0)
                signal_created_at = int(time.time())
                
                if direction:
                    self.logger.warning(
                        f"{symbol} için cache güncelleniyor (exception sonrası aktif sinyal korunmalı) - "
                        f"Direction: {direction}, Timestamp: {signal_created_at}"
                    )
                    self._update_signal_cache(
                        symbol=symbol,
                        has_active_signal=True,
                        direction=direction,
                        confidence=confidence,
                        timestamp=signal_created_at,
                        source='send-exception'  # Use 'send-exception' as source
                    )
            except Exception as cache_error:
                self.logger.error(
                    f"{symbol} cache güncelleme hatası (exception durumunda): {str(cache_error)}",
                    exc_info=True
                )
    
    def _send_to_channel(self, message: str, reply_markup: Optional[Any] = None) -> Optional[int]:
        """
        Sends message to Telegram channel.
        
        Args:
            message: Message to send
            reply_markup: Inline keyboard markup (optional)
            
        Returns:
            Telegram message_id or None
        """
        try:
            # Use bot manager's safe sync wrapper method
            # This method prevents event loop errors by using _run_on_bot_loop
            message_id = self.bot_mgr.send_channel_message(
                self.channel_id,
                message,
                reply_markup=reply_markup
            )
            
            if message_id:
                self.logger.debug(f"Kanal mesajı başarıyla gönderildi - Message ID: {message_id}")
            else:
                self.logger.warning("Kanal mesajı gönderildi ama message_id alınamadı")
            
            return message_id
            
        except Exception as e:
            self.logger.error(
                f"Kanal mesajı gönderme hatası: {str(e)}", 
                exc_info=True
            )
            return None
    
    def _calculate_tp_sl_levels(
        self,
        signal_price: float,
        direction: str,
        atr: Optional[float],
        timeframe: Optional[str]
    ) -> Dict:
        """
        Calculates TP and SL levels (same logic as message_formatter).
        
        Args:
            signal_price: Signal price
            direction: LONG/SHORT
            atr: ATR value
            timeframe: Timeframe
            
        Returns:
            TP and SL levels dict
        """
        tp_levels = {}
        sl_levels = {}
        
        # TP levels (Balanced Approach: TP1=1.5R, TP2=2.5R)
        # TP1 = 3x ATR (1.5R), TP2 = 5x ATR (2.5R)
        # Since SL = 2x ATR, TP1 R:R ratio is 1.5R, TP2 R:R ratio is 2.5R
        if atr:
            risk_dist = atr
        else:
            risk_dist = signal_price * 0.01
        
        # TP multipliers: [3, 5] -> TP1=1.5R, TP2=2.5R (SL=2x ATR based)
        tp_multipliers = [3, 5]
        for idx, multiplier in enumerate(tp_multipliers, start=1):
            offset = risk_dist * multiplier
            if direction == 'LONG':
                tp_price = signal_price + offset
            elif direction == 'SHORT':
                tp_price = signal_price - offset
            else:
                tp_price = None
            
            if tp_price:
                tp_levels[f'tp{idx}_price'] = tp_price
        
        # SL levels (Single SL: 2x ATR)
        # Balanced approach: Single stop-loss
        sl_multiplier = SL_MULTIPLIER
        if atr:
            offset = atr * sl_multiplier
            if direction == 'LONG':
                sl_price = signal_price - offset
            elif direction == 'SHORT':
                sl_price = signal_price + offset
            else:
                sl_price = None
        else:
            pct = float(sl_multiplier)
            if direction == 'LONG':
                sl_price = signal_price * (1 - pct/100)
            elif direction == 'SHORT':
                sl_price = signal_price * (1 + pct/100)
            else:
                sl_price = None
        
        if sl_price:
            sl_levels['sl_price'] = sl_price
        
        return {**tp_levels, **sl_levels}

    def _build_custom_tp_sl_levels(
        self,
        custom_targets: Dict[str, Dict[str, float]]
    ) -> Dict:
        """Creates custom TP/SL levels."""
        tp_levels = {}
        sl_levels = {}
        
        processed_levels = 0
        tp_section = custom_targets.get('tp')
        if isinstance(tp_section, dict):
            for key, value in tp_section.items():
                if processed_levels >= 2:
                    break
                normalized_key = 'tp1_price' if '1' in key else 'tp2_price'
                extracted_price = value.get('price') if isinstance(value, dict) else value
                if extracted_price is not None:
                    tp_levels[normalized_key] = extracted_price
                    processed_levels += 1
        
        if processed_levels < 2:
            for simple_key in ['tp1', 'tp2']:
                if processed_levels >= 2:
                    break
                target_info = custom_targets.get(simple_key) or {}
                price = target_info.get('price')
                if price is not None:
                    tp_levels[f'{simple_key}_price'] = price
                    processed_levels += 1
                
        # Check for 'sl' or 'stop_loss' key
        sl_section = custom_targets.get('sl') or custom_targets.get('stop_loss')
        
        if sl_section:
            stop_loss = sl_section.get('stop_loss')
            if stop_loss is None:
                stop_loss = sl_section.get('price')
            sl_levels['sl_price'] = stop_loss
                
        return {**tp_levels, **sl_levels}

    def _analyze_symbol(self, symbol: str, return_reason: bool = False) -> Union[Optional[Dict], Tuple[Optional[Dict], str]]:
        """
        Performs multi-timeframe analysis for a single symbol.
        
        Args:
            symbol: Trading pair
            return_reason: If True, returns (signal, reason) tuple
            
        Returns:
            Signal info or None (or tuple)
        """
        # Timeframes should be taken from config but hardcoded here or passed from config
        # Using standard timeframes for now
        timeframes = ['1h', '4h', '1d']
        
        # Fetch multi-timeframe data
        multi_tf_data = self.market_data.fetch_multi_timeframe(
            symbol, timeframes
        )
        
        if not multi_tf_data:
            if return_reason:
                return None, "NO_DATA"
            return None
        
        # Generate signal (symbol parameter added)
        signal = self.signal_gen.generate_signal(
            multi_tf_data, symbol=symbol, return_reason=return_reason
        )
        
        return signal
    
    def _save_signal_to_db(
        self,
        symbol: str,
        signal_data: Dict,
        entry_levels: Dict,
        signal_price: float,
        atr: Optional[float],
        timeframe: Optional[str],
        telegram_message_id: int,
        telegram_channel_id: str,
        signal_id: Optional[str] = None
    ) -> None:
        """
        Saves signal to database.
        
        Args:
            symbol: Trading pair
            signal_data: Signal data
            entry_levels: Entry levels
            signal_price: Signal price
            atr: ATR value
            timeframe: Timeframe
            telegram_message_id: Telegram message ID
            telegram_channel_id: Telegram channel ID
            signal_id: Signal ID (generated if not provided)
        """
        try:
            if not self.signal_repository:
                return
            
            # Generate Signal ID (if not provided)
            if not signal_id:
                signal_id = self.signal_repository.generate_signal_id(symbol)
            
            # Direction and confidence
            direction = signal_data.get('direction', 'NEUTRAL')
            confidence = signal_data.get('confidence', 0.0)
            strategy_type = signal_data.get('strategy_type', 'trend')
            custom_targets = signal_data.get('custom_targets') if isinstance(signal_data.get('custom_targets'), dict) else {}
            
            # Calculate TP/SL levels
            if strategy_type == 'ranging' and custom_targets:
                tp_sl_levels = self._build_custom_tp_sl_levels(custom_targets)
            else:
                tp_sl_levels = self._calculate_tp_sl_levels(
                    signal_price=signal_price,
                    direction=direction,
                    atr=atr,
                    timeframe=timeframe
                )
            
            # Score breakdown and market context (JSON)
            score_breakdown = signal_data.get('score_breakdown', {})
            market_context = signal_data.get('market_context', {})
            
            # Type safety: Ensure dict type
            if not isinstance(score_breakdown, dict):
                score_breakdown = {}
            if not isinstance(market_context, dict):
                market_context = {}
            
            # Enrich market context with ticker info
            ticker = self.market_data.get_ticker_info(symbol)
            if ticker and market_context:
                market_context['volume_24h_usd'] = ticker.get('quoteVolume', 0)
                market_context['price_change_24h_pct'] = ticker.get('percentage', 0)
            
            # Calculate R-distances
            r_distances = {}
            if self.risk_reward_calc:
                r_distances = self.risk_reward_calc.calculate_r_distances(
                    signal_price=signal_price,
                    direction=direction,
                    tp1=tp_sl_levels.get('tp1_price'),
                    tp2=tp_sl_levels.get('tp2_price'),
                    sl_price=tp_sl_levels.get('sl_price')
                )
            
            # Alternative entry prices
            optimal_dict = entry_levels.get('optimal', {})
            conservative_dict = entry_levels.get('conservative', {})
            
            # Type safety: Ensure dict type
            if not isinstance(optimal_dict, dict):
                optimal_dict = {}
            if not isinstance(conservative_dict, dict):
                conservative_dict = {}
            
            optimal_entry = optimal_dict.get('price')
            conservative_entry = conservative_dict.get('price')
            
            # Save signal
            success = self.signal_repository.save_signal(
                signal_id=signal_id,
                symbol=symbol,
                direction=direction,
                signal_price=signal_price,
                confidence=confidence,
                atr=atr,
                timeframe=timeframe,
                telegram_message_id=telegram_message_id,
                telegram_channel_id=telegram_channel_id,
                tp1_price=tp_sl_levels.get('tp1_price'),
                tp2_price=tp_sl_levels.get('tp2_price'),
                sl_price=tp_sl_levels.get('sl_price'),
                signal_data=signal_data,
                entry_levels=entry_levels,
                signal_score_breakdown=json.dumps(score_breakdown) if score_breakdown else None,
                market_context=json.dumps(market_context) if market_context else None,
                tp1_distance_r=r_distances.get('tp1_distance_r'),
                tp2_distance_r=r_distances.get('tp2_distance_r'),
                sl_distance_r=r_distances.get('sl_distance_r'),
                optimal_entry_price=optimal_entry,
                conservative_entry_price=conservative_entry
            )
            
            if success:
                self.logger.info(f"Sinyal veritabanına kaydedildi: {signal_id} - {symbol}")
            else:
                self.logger.error(f"Sinyal veritabanına kaydedilemedi: {signal_id} - {symbol}")
                
        except Exception as e:
            self.logger.error(f"Sinyal kaydetme hatası: {str(e)}", exc_info=True)
    
    def _update_signal_cache(
        self,
        symbol: str,
        has_active_signal: bool,
        signal_id: Optional[str] = None,
        direction: Optional[str] = None,
        confidence: Optional[float] = None,
        timestamp: Optional[int] = None,
        source: str = 'runtime'
    ) -> Optional[Dict]:
        """
        Updates signal cache (tracks active signal status).
        
        Args:
            symbol: Trading pair
            has_active_signal: Is there an active signal? (message_deleted=0)
            signal_id: Signal ID (optional)
            direction: LONG/SHORT (optional)
            confidence: Confidence value (optional)
            timestamp: Signal time (current time if None)
            source: Update source (for logging)
        """
        current_time = timestamp if timestamp is not None else int(time.time())
        
        self.signal_cache[symbol] = {
            'has_active_signal': has_active_signal,
            'last_updated': current_time
        }
        
        if signal_id:
            self.signal_cache[symbol]['signal_id'] = signal_id
        if direction:
            self.signal_cache[symbol]['direction'] = direction
        if confidence is not None:
            self.signal_cache[symbol]['confidence'] = confidence
        
        self.logger.debug(
            "%s cache güncellendi (%s): has_active_signal=%s, signal_id=%s",
            symbol,
            source,
            has_active_signal,
            signal_id or 'N/A'
        )
        return self.signal_cache[symbol]
    
    def _warmup_cache_from_db(self) -> None:
        """Populates active signal cache from database on startup."""
        if not self.signal_repository:
            self.logger.debug("Aktif sinyal cache warmup atlandı: SignalRepository tanımlı değil")
            return

        # Load active signals from last 24 hours
        lookback_hours = 24

        summaries = self.signal_repository.get_recent_signal_summaries(lookback_hours)
        if not summaries:
            self.logger.debug(
                "Aktif sinyal cache warmup verisi bulunamadı (lookback=%dh)",
                lookback_hours
            )
            return

        for summary in summaries:
            # Each summary means active signal (get_recent_signal_summaries already checks message_deleted=0)
            self._update_signal_cache(
                symbol=summary.get('symbol'),
                has_active_signal=True,
                signal_id=summary.get('signal_id'),
                direction=summary.get('direction', 'NEUTRAL'),
                confidence=float(summary.get('confidence', 0.0) or 0.0),
                timestamp=summary.get('created_at'),
                source='warmup'
            )

        self.logger.info(
            "Aktif sinyal cache warmup tamamlandı: %d sembol yüklendi (lookback=%dh)",
            len(summaries),
            lookback_hours
        )

    def _get_direction_threshold(self, direction: str) -> float:
        """
        Returns direction-specific confidence threshold from config.
        
        LONG signals require much higher confidence due to poor historical performance.
        Data analysis shows: LONG 6.67% win rate vs SHORT 36.84% win rate
        
        Args:
            direction: 'LONG', 'SHORT', or 'NEUTRAL'
        
        Returns:
            Minimum confidence threshold (from .env or defaults)
        """
        if self.config:
            if direction == 'LONG':
                return self.config.confidence_threshold_long
            return self.config.confidence_threshold_short
        
        # Fallback if config not provided
        if direction == 'LONG':
            return 0.90
        return 0.69

    def get_cache_stats(self) -> Dict:
        """
        Returns cache statistics.
        
        Returns:
            Cache statistics
        """
        active_signals = sum(
            1 for cache_entry in self.signal_cache.values()
            if cache_entry.get('has_active_signal', False)
        )
        
        return {
            'total_cached_symbols': len(self.signal_cache),
            'active_signals': active_signals,
            'confidence_threshold': self.confidence_threshold
        }
    
    def cleanup_old_cache(self) -> None:
        """Clears passive signals (has_active_signal=False) from cache."""
        symbols_to_remove = []
        
        for symbol, cache_entry in self.signal_cache.items():
            # Remove from cache if no active signal
            if not cache_entry.get('has_active_signal', False):
                symbols_to_remove.append(symbol)
        
        for symbol in symbols_to_remove:
            del self.signal_cache[symbol]
            self.logger.debug(f"{symbol} cache'den temizlendi (aktif sinyal yok)")
        
        if symbols_to_remove:
            self.logger.info(f"{len(symbols_to_remove)} pasif sinyal cache'den temizlendi")
    
    def _log_rejection_scorecard(
        self,
        symbol: str,
        score: float,
        threshold: float,
        signal_data: Dict,
        ranking_info: Optional[Dict] = None,
        reject_reason: str = None
    ) -> None:
        """
        Rejection Scorecard - Compact log.
        
        Args:
            symbol: Trading pair
            score: Total score (confidence)
            threshold: Minimum threshold value
            signal_data: Signal data (contains score_breakdown, market_context)
            ranking_info: Ranking info (optional)
            reject_reason: Rejection reason (optional)
        """
        try:
            market_context = signal_data.get('market_context', {})
            direction = signal_data.get('direction', 'UNKNOWN')
            regime = market_context.get('regime', 'unknown')
            
            # Concise INFO log (1-2 lines)
            reason_str = f" ({reject_reason})" if reject_reason else ""
            self.logger.info(
                f"❌ {symbol} rejected: score={score:.2f} < {threshold:.2f}{reason_str} "
                f"(dir={direction}, regime={regime})"
            )
            
            # Detailed scorecard only in DEBUG
            score_breakdown = signal_data.get('score_breakdown', {})
            rsi_value = score_breakdown.get('rsi_value', 0)
            rsi_signal = score_breakdown.get('rsi_signal', 'NEUTRAL')
            adx_value = score_breakdown.get('adx_value', 0)
            volume_relative = score_breakdown.get('volume_relative', 1.0)
            
            base_score = ranking_info.get('base_score', score) if ranking_info else score
            rsi_bonus = ranking_info.get('rsi_bonus', 0.0) if ranking_info else 0.0
            volume_bonus = ranking_info.get('volume_bonus', 0.0) if ranking_info else 0.0
            
            self.logger.debug(
                f"{symbol} rejection details: base={base_score:.3f}, rsi_bonus={rsi_bonus:+.3f}, "
                f"vol_bonus={volume_bonus:+.3f}, RSI={rsi_value:.1f}/{rsi_signal}, "
                f"ADX={adx_value:.1f}, vol={volume_relative:.2f}x"
            )
            
        except Exception as e:
            # Fallback to simple log
            self.logger.debug(
                f"{symbol} confidence low: {score:.3f} (scorecard error: {str(e)})"
            )
    
    def _get_indicator_status(self, signal: str, direction: str, value: float) -> str:
        """Format indicator status."""
        if signal == direction:
            return f"✅ Uyumlu ({signal})"
        elif signal == 'NEUTRAL':
            return f"⚪ Nötr"
        else:
            return f"❌ Ters ({signal})"
    
    def _get_trend_status(self, signal: str, direction: str, adx_value: float) -> str:
        """Format trend status."""
        if signal == direction:
            if adx_value > 25:
                return f"✅ Güçlü Trend ({signal})"
            else:
                return f"⚠️ Zayıf Trend ({signal})"
        elif signal == 'NEUTRAL':
            return f"⚪ Nötr"
        else:
            return f"❌ Ters Trend ({signal})"
    
    def _get_volume_status(self, relative: float, signal: str) -> str:
        """Format volume status."""
        if relative >= 1.5:
            return f"✅ Yüksek (x{relative:.2f})"
        elif relative >= 1.0:
            return f"⚪ Normal (x{relative:.2f})"
        else:
            return f"❌ Düşük (x{relative:.2f})"
    
    def _log_market_pulse(self) -> None:
        """
        Market Pulse Report (Market Pulse Log) - Summarizes general market status.
        """
        try:
            from datetime import datetime
            
            # Check BTC status
            btc_ticker = None
            btc_status = "Bilinmiyor"
            btc_change_24h = 0.0
            btc_rsi = 0.0
            
            try:
                if self.market_data:
                    btc_ticker = self.market_data.get_ticker_info("BTC/USDT")
                    if btc_ticker:
                        # CCXT standard field: 'percentage' (Consistent with SignalGenerator)
                        btc_change_24h = float(btc_ticker.get('percentage', 0) or 0)
                        # If 'percentage' missing, check raw data in 'info'
                        if btc_change_24h == 0 and 'info' in btc_ticker:
                            btc_change_24h = float(btc_ticker['info'].get('priceChangePercent', 0) or 0)
                        # Fetch 1h data for RSI
                        btc_1h_data = self.market_data.fetch_ohlcv("BTC/USDT", "1h", limit=200)
                        if btc_1h_data is not None and len(btc_1h_data) > 0:
                            from analysis.technical_indicators import TechnicalIndicatorCalculator
                            indicator_calc = TechnicalIndicatorCalculator()
                            indicators = indicator_calc.calculate_all(btc_1h_data)
                            rsi_data = indicators.get('rsi', {})
                            btc_rsi = rsi_data.get('value', 0)
                        
                        # Determine BTC status
                        if btc_change_24h < -3.0 or btc_rsi < 30:
                            btc_status = "⚠️ Çöküş Riski"
                        elif btc_change_24h < -1.0:
                            btc_status = "⚠️ Düşüş"
                        elif btc_change_24h > 3.0:
                            btc_status = "✅ Güçlü Yükseliş"
                        elif btc_change_24h > 1.0:
                            btc_status = "✅ Yükseliş"
                        else:
                            btc_status = "⚪ Güvenli"
            except Exception as e:
                self.logger.debug(f"BTC durumu kontrolü hatası: {str(e)}")
            
            # Time info
            current_time = datetime.now().strftime("%H:%M")
            
            # Log message
            log_lines = [
                f"🌍 PİYASA NABZI ({current_time}):",
                f"   • BTC Durumu: {btc_status} (24h: {btc_change_24h:+.2f}%, RSI: {btc_rsi:.1f})"
            ]
            
            self.logger.info("\n".join(log_lines))
            
        except Exception as e:
            self.logger.debug(f"Piyasa nabzı raporu hatası: {str(e)}")

    def _log_scan_summary(self, stats: Dict) -> None:
        """
        Scan Summary Report - Summarizes rejection reasons at the end of each cycle.
        """
        try:
            total = stats.get('TOTAL_SCANNED', 0)
            generated = stats.get('GENERATED', 0)
            rejected_rr = stats.get('REJECTED_RR', 0)
            rejected_trend = stats.get('REJECTED_TREND', 0)
            rejected_conf = stats.get('REJECTED_CONFIDENCE', 0)
            rejected_btc = stats.get('REJECTED_BTC', 0)
            rejected_volatility = stats.get('REJECTED_HIGH_VOLATILITY', 0)
            rejected_low_atr = stats.get('REJECTED_LOW_ATR', 0)
            no_signal = stats.get('NO_SIGNAL', 0)
            
            log_lines = [
                f"📊 TARAMA ÖZETİ ({total} Coin)",
                f"----------------------------------------",
                f"✅ Sinyal Üretildi: {generated}",
                f"",
                f"❌ Reddedilme Nedenleri:",
                f"  • Risk/Reward: {rejected_rr}",
                f"  • Trend Uyumsuzluğu: {rejected_trend}",
                f"  • Confidence Yetersiz: {rejected_conf}",
                f"  • BTC Crash Filtresi: {rejected_btc}",
                f"  • Yüksek Volatilite: {rejected_volatility}",
                f"  • Düşük ATR (<%2): {rejected_low_atr}",
                f"  • Sinyal Yok: {no_signal}",
            ]
            
            log_lines.append(f"----------------------------------------")
            
            # Result comment
            if generated > 0:
                result = "Fırsat bulundu!"
            elif rejected_btc > 0:
                result = "BTC kaynaklı risk, işlem açılmadı."
            elif rejected_rr > 0:
                result = "Fırsatlar var ama R/R kurtarmıyor."
            else:
                result = "Piyasa stabil/yatay, fırsat bekleniyor."
                
            log_lines.append(f"Sonuç: {result}")
            
            self.logger.info("\n".join(log_lines))
            
        except Exception as e:
            self.logger.error(f"Tarama özeti raporu hatası: {str(e)}")
