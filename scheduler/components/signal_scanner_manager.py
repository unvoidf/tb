"""
SignalScannerManager: Arkaplanda sinyal tarayan ve bildirim gönderen manager.
Top 5 futures coin'i tarar, güçlü sinyalleri yakalar ve cooldown mekanizması uygular.
"""
import time
import json
from typing import Dict, List, Optional
from utils.logger import LoggerManager
from data.coin_filter import CoinFilter
from bot.command_handler import CommandHandler
from strategy.dynamic_entry_calculator import DynamicEntryCalculator
from bot.message_formatter import MessageFormatter
from bot.telegram_bot_manager import TelegramBotManager
from scheduler.components.signal_ranker import SignalRanker
from data.signal_repository import SignalRepository
from strategy.risk_reward_calculator import RiskRewardCalculator


class SignalScannerManager:
    """Sinyal tarama ve bildirim manager'ı."""
    
    def __init__(
        self,
        coin_filter: CoinFilter,
        command_handler: CommandHandler,
        entry_calculator: DynamicEntryCalculator,
        message_formatter: MessageFormatter,
        bot_manager: TelegramBotManager,
        channel_id: str,
        signal_repository: Optional[SignalRepository] = None,
        confidence_threshold: float = 0.69,
        cooldown_hours: int = 1,
        ranging_min_sl_percent: float = 0.5,
        risk_reward_calc: Optional[RiskRewardCalculator] = None,
        signal_tracker: Optional[object] = None  # SignalTracker instance (optional)
    ):
        """
        SignalScannerManager'ı başlatır.
        
        Args:
            coin_filter: Coin filter instance
            command_handler: Command handler instance
            entry_calculator: Dynamic entry calculator
            message_formatter: Message formatter
            bot_manager: Telegram bot manager
            channel_id: Telegram kanal ID
            signal_repository: Signal repository (opsiyonel, sinyal kaydetme için)
            confidence_threshold: Minimum confidence threshold (default: 0.69 = %69)
                NOT: Bu değer bir fallback'tir. Gerçek değer config'den (.env -> CONFIDENCE_THRESHOLD)
                gelir ve bu default değeri override eder. application_factory.py'de
                config.confidence_threshold kullanılır.
            cooldown_hours: Cooldown süresi (saat)
        """
        self.coin_filter = coin_filter
        self.cmd_handler = command_handler
        self.entry_calc = entry_calculator
        self.formatter = message_formatter
        self.bot_mgr = bot_manager
        self.channel_id = channel_id
        self.signal_repository = signal_repository
        self.confidence_threshold = confidence_threshold
        self.cooldown_seconds = cooldown_hours * 3600
        self.risk_reward_calc = risk_reward_calc  # Risk/Reward calculator
        self.signal_tracker = signal_tracker  # SignalTracker instance (optional, for message updates)
        self.ranging_min_sl_percent = ranging_min_sl_percent
        
        self.logger = LoggerManager().get_logger('SignalScannerManager')
        
        # SignalRanker instance'ı (RSI ve volume bonusları için)
        self.signal_ranker = SignalRanker()
        
        # Sinyal cache: {symbol: {last_signal_time, last_direction, confidence}}
        self.signal_cache: Dict[str, Dict] = {}
        
        self.logger.info(
            "SignalScannerManager başlatıldı - "
            "threshold=%s, cooldown=%sh, ranging_min_sl=%s%%",
            confidence_threshold,
            cooldown_hours,
            ranging_min_sl_percent,
        )

        # Hibrit cooldown için cache warmup
        self._warmup_cache_from_db()
    
    def scan_for_signals(self) -> None:
        """
        Top 20 futures coin'i tarar ve güçlü sinyalleri yakalar.
        """
        try:
            self.logger.info("Sinyal tarama başlatıldı")
            
            # Piyasa Nabzı Raporu (Market Pulse Log) - Tarama başında
            self._log_market_pulse()
            
            # Top 20 futures coin'i al
            symbols = self.coin_filter.get_top_futures_coins(20)
            
            if not symbols:
                self.logger.warning("Futures coin listesi alınamadı")
                return
            
            self.logger.debug(f"Taranacak coinler: {symbols}")
            
            # Her coin için sinyal kontrolü
            for symbol in symbols:
                try:
                    self._check_symbol_signal(symbol)
                except Exception as e:
                    self.logger.error(f"{symbol} sinyal kontrolü hatası: {str(e)}", exc_info=True)
            
            self.logger.info("Sinyal tarama tamamlandı")
            
        except Exception as e:
            self.logger.error(f"Sinyal tarama hatası: {str(e)}", exc_info=True)
    
    def _check_symbol_signal(self, symbol: str) -> None:
        """
        Tek bir coin için sinyal kontrolü yapar.
        
        Args:
            symbol: Trading pair (örn: BTC/USDT)
        """
        try:
            # Coin için sinyal analizi yap
            signal_data = self.cmd_handler._analyze_symbol(symbol)
            
            if not signal_data:
                self.logger.debug(f"{symbol} için sinyal verisi yok")
                return
            
            # DEBUG: Type check
            if not isinstance(signal_data, dict):
                self.logger.error(f"{symbol} signal_data is NOT a dict! Type: {type(signal_data)}, Value: {signal_data}")
                return
            
            # Genel sinyal bilgilerini al
            overall_direction = signal_data.get('direction')
            overall_confidence = signal_data.get('confidence', 0.0)
            
            # SignalRanker ile bonus skorları hesapla
            # SignalRanker'ın beklediği format: [{'symbol': str, 'signal': dict}]
            signal_for_ranker = [{
                'symbol': symbol,
                'signal': signal_data
            }]
            
            # RSI ve volume bonusları ile total score hesapla
            ranked_signals = self.signal_ranker.rank_signals(signal_for_ranker, top_count=1)
            
            if ranked_signals:
                # Rank edilmiş sinyal bulundu, total score'u direkt al (tekrar hesaplama yok!)
                ranked_signal = ranked_signals[0]
                
                # SignalRanker'dan gelen _ranking_info içinde tüm score bilgileri var
                ranking_info = ranked_signal.get('_ranking_info', {})
                total_score = ranking_info.get('total_score', 0.0)
                rsi_bonus = ranking_info.get('rsi_bonus', 0.0)
                volume_bonus = ranking_info.get('volume_bonus', 0.0)
                base_score = ranking_info.get('base_score', 0.0)

                # BUG FIX: Raporlanan güven skorunu, bonuslar dahil edilmiş total_score ile güncelle.
                # Bu, filtrelenen skor ile kullanıcıya gösterilen skorun aynı olmasını sağlar.
                signal_data['confidence'] = total_score
                
                self.logger.debug(
                    f"{symbol} sinyal: direction={overall_direction}, "
                    f"confidence={overall_confidence:.3f}, "
                    f"rsi_bonus={rsi_bonus:.3f}, volume_bonus={volume_bonus:.3f}, "
                    f"total_score={total_score:.3f}"
                )
                
                # Total score threshold kontrolü (bonuslar dahil)
                if total_score < self.confidence_threshold:
                    # Reddedilme Karnesi (Rejection Scorecard) - Detaylı log
                    self._log_rejection_scorecard(
                        symbol, total_score, self.confidence_threshold,
                        signal_data, ranking_info
                    )
                    return
            else:
                # Rank edilemedi (threshold altı)
                self.logger.debug(
                    f"{symbol} sinyal: direction={overall_direction}, "
                    f"confidence={overall_confidence:.3f} (rank edilemedi)"
                )
                
                # Eski yöntem: sadece confidence kontrolü
                if overall_confidence < self.confidence_threshold:
                    # Reddedilme Karnesi (Rejection Scorecard) - Detaylı log
                    self._log_rejection_scorecard(
                        symbol, overall_confidence, self.confidence_threshold,
                        signal_data, None
                    )
                    return

            # NEUTRAL yönlü sinyaller kanala gönderilmez (UX/gürültü kontrolü)
            if overall_direction == 'NEUTRAL':
                self.logger.debug(
                    f"{symbol} sinyali NEUTRAL (score={total_score:.3f}); kanal bildirimi atlandı"
                )
                return
            
            # RANGING PİYASA FİLTRESİ (Finans Uzmanı Önerisi)
            # Yatay piyasada sadece yüksek güvenli sinyaller geçsin
            market_context = signal_data.get('market_context', {})
            regime = market_context.get('regime')
            adx_strength = market_context.get('adx_strength', 0)
            
            if regime == 'ranging' or adx_strength < 25:
                # Ranging piyasada veya zayıf trend gücünde threshold yükselt
                ranging_threshold = 0.8
                if total_score < ranging_threshold:
                    self.logger.info(
                        f"{symbol} ranging/zayıf trend (ADX={adx_strength:.1f}), "
                        f"score={total_score:.3f} < {ranging_threshold}, atlandı"
                    )
                    return

            # _temp_signal_data'yı doldur (rejected signal kaydı için)
            if not hasattr(self, '_temp_signal_data'):
                self._temp_signal_data = {}
            self._temp_signal_data[symbol] = signal_data

            # Cooldown kontrolü
            should_send = self._should_send_notification(symbol, overall_direction)
            if not should_send:
                # Cooldown aktif - yön değişmemişse log ekle
                self._handle_cooldown_active_signal(symbol, overall_direction, signal_data)
                return
            
            # Bildirim gönder
            self._send_signal_notification(symbol, signal_data)
            
        except Exception as e:
            self.logger.error(f"{symbol} sinyal kontrolü hatası: {str(e)}", exc_info=True)
    
    def _should_send_notification(self, symbol: str, direction: str) -> bool:
        """
        Bildirim gönderilip gönderilmeyeceğini kontrol eder.
        
        Args:
            symbol: Trading pair
            direction: LONG/SHORT
            
        Returns:
            True ise bildirim gönderilmeli
        """
        cache_entry = self.signal_cache.get(symbol)

        if cache_entry is None:
            cache_entry = self._load_cache_entry_from_db(symbol)
            if cache_entry is None:
                self.logger.debug("%s için cache ve DB kaydı yok, bildirim gönderilecek", symbol)
                return True
            self.logger.debug(
                "%s cache DB'den dolduruldu: direction=%s, created_at=%s",
                symbol,
                cache_entry.get('last_direction'),
                cache_entry.get('last_signal_time')
            )
        
        last_direction = cache_entry.get('last_direction')
        last_signal_time = cache_entry.get('last_signal_time', 0)
        
        current_time = int(time.time())

        # NEUTRAL yön değişimi cooldown bypass etmez
        if direction == 'NEUTRAL':
            self.logger.debug(
                f"{symbol} NEUTRAL yönlü sinyal cooldown sebebiyle gönderilmiyor"
            )
            # Rejected signal kaydet
            if self.signal_repository and hasattr(self, '_temp_signal_data'):
                signal_data = self._temp_signal_data.get(symbol, {})
                score_breakdown = signal_data.get('score_breakdown', {})
                market_context = signal_data.get('market_context', {})
                current_price = self.cmd_handler.market_data.get_latest_price(symbol)
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

        # Yön değişmişse (NEUTRAL hariç) hemen bildirim gönder
        if last_direction != direction:
            self.logger.debug(f"{symbol} yön değişti: {last_direction} -> {direction}")
            return True
        
        # Aynı yön, cooldown kontrolü
        time_since_last = current_time - last_signal_time
        
        if time_since_last >= self.cooldown_seconds:
            self.logger.debug(f"{symbol} cooldown süresi doldu: {time_since_last}s")
            return True
        
        self.logger.debug(
            f"{symbol} cooldown aktif: {time_since_last}s/{self.cooldown_seconds}s"
        )
        # Rejected signal kaydet
        if self.signal_repository and hasattr(self, '_temp_signal_data'):
            signal_data = self._temp_signal_data.get(symbol, {})
            score_breakdown = signal_data.get('score_breakdown', {})
            market_context = signal_data.get('market_context', {})
            current_price = self.cmd_handler.market_data.get_latest_price(symbol)
            self.signal_repository.save_rejected_signal(
                symbol=symbol,
                direction=direction,
                confidence=signal_data.get('confidence', 0),
                signal_price=current_price if current_price else 0,
                rejection_reason='cooldown_active',
                score_breakdown=json.dumps(score_breakdown) if score_breakdown else None,
                market_context=json.dumps(market_context) if market_context else None
            )
        return False
    
    def _load_cache_entry_from_db(self, symbol: str) -> Optional[Dict]:
        """Cache miss olduğunda veritabanından son sinyali yükler."""
        if not self.signal_repository:
            return None

        summary = self.signal_repository.get_last_signal_summary(symbol)
        if not summary:
            return None

        return self._update_signal_cache(
            symbol=symbol,
            direction=summary.get('direction', 'NEUTRAL'),
            confidence=float(summary.get('confidence', 0.0) or 0.0),
            timestamp=summary.get('created_at'),
            source='db-fallback'
        )
    
    def _handle_cooldown_active_signal(
        self, symbol: str, direction: str, signal_data: Dict
    ) -> None:
        """
        Cooldown aktif durumunda yeni sinyal tespit edildiğinde çağrılır.
        Yön değişmemişse, aktif sinyalin günlüğüne log ekler ve mesajı günceller.
        
        Args:
            symbol: Trading pair
            direction: LONG/SHORT (yön değişmemiş)
            signal_data: Yeni sinyal verisi
        """
        try:
            if not self.signal_repository:
                self.logger.debug(f"{symbol} signal_repository yok, log eklenemedi")
                return
            
            # Yeni sinyal fiyatını al
            current_price = self.cmd_handler.market_data.get_latest_price(symbol)
            if not current_price:
                self.logger.debug(f"{symbol} güncel fiyat alınamadı, log eklenemedi")
                return
            
            new_confidence = signal_data.get('confidence', 0.0)
            
            # Aktif sinyali bul
            active_signal = self.signal_repository.get_latest_active_signal_by_symbol_direction(
                symbol, direction
            )
            
            if not active_signal:
                self.logger.debug(
                    f"{symbol} {direction} için aktif sinyal bulunamadı, log eklenemedi"
                )
                return
            
            active_signal_id = active_signal.get('signal_id')
            old_confidence = active_signal.get('confidence', 0.0)
            
            # Confidence değerlerini float'a çevir (floating point precision sorunlarını önlemek için)
            old_confidence = float(old_confidence) if old_confidence is not None else 0.0
            new_confidence = float(new_confidence) if new_confidence is not None else 0.0
            
            # Debug: Confidence değerlerini logla
            confidence_change_calc = new_confidence - old_confidence
            self.logger.debug(
                f"{symbol} cooldown aktif - confidence karşılaştırması: "
                f"yeni={new_confidence:.6f} ({new_confidence * 100:.2f}%), "
                f"eski={old_confidence:.6f} ({old_confidence * 100:.2f}%), "
                f"fark={confidence_change_calc:+.6f}"
            )
            
            # Sinyal günlüğüne entry ekle (flood önleme ile)
            # Minimum 10 dakika aralık veya %5 confidence değişikliği ile filtreleme
            success = self.signal_repository.add_signal_log_entry(
                signal_id=active_signal_id,
                price=current_price,
                confidence=new_confidence,
                old_confidence=old_confidence,
                min_log_interval_seconds=600,  # 10 dakika
                min_confidence_change=0.05  # %5
            )
            
            if success:
                self.logger.info(
                    f"{symbol} cooldown aktif - yeni sinyal günlüğe eklendi: "
                    f"signal_id={active_signal_id}, price={current_price}, "
                    f"confidence={new_confidence:.3f} ({new_confidence * 100:.2f}%), "
                    f"eski={old_confidence:.3f} ({old_confidence * 100:.2f}%), "
                    f"change={confidence_change_calc:+.6f}"
                )
                
                # Mesaj güncellemesi kaldırıldı - kullanıcı buton ile manuel güncelleyecek
                # veya TP/SL hit olunca otomatik güncellenecek
                self.logger.debug(
                    f"{symbol} cooldown aktif - sinyal günlüğüne entry eklendi, "
                    f"mesaj güncellemesi kullanıcı buton ile yapılacak veya TP/SL hit olunca otomatik yapılacak"
                )
            else:
                # Log eklenmedi - bu filtreleme nedeniyle olabilir (normal durum)
                # veya bir hata olabilir
                self.logger.debug(
                    f"{symbol} sinyal günlüğüne entry eklenmedi "
                    f"(filtreleme veya hata): {active_signal_id}"
                )
                
        except Exception as e:
            self.logger.error(
                f"{symbol} cooldown aktif sinyal işleme hatası: {str(e)}",
                exc_info=True
            )

    def _send_signal_notification(self, symbol: str, signal_data: Dict) -> None:
        """
        Sinyal bildirimi gönderir.
        
        Args:
            symbol: Trading pair
            signal_data: Sinyal verisi
        """
        try:
            # Sinyal üretim anındaki fiyat (signal_price)
            current_price = self.cmd_handler.market_data.get_latest_price(symbol)
            signal_price = current_price
            signal_created_at = int(time.time())
            
            if not current_price:
                self.logger.warning(f"{symbol} güncel fiyat alınamadı")
                return
            
            # Dynamic entry levels hesapla
            direction = signal_data.get('direction')
            confidence = signal_data.get('confidence', 0.0)
            
            # OHLCV verisi al (entry calculation için)
            df = None
            atr = None
            
            try:
                # 1h timeframe'den veri al
                df = self.cmd_handler.market_data.fetch_ohlcv(symbol, '1h', 200)
                
                # ATR hesapla (doğru sınıf adı: TechnicalIndicatorCalculator)
                if df is not None and len(df) > 14:
                    from analysis.technical_indicators import TechnicalIndicatorCalculator
                    indicators = TechnicalIndicatorCalculator()
                    atr = indicators.calculate_atr(df, period=14)
            except Exception as e:
                self.logger.warning(f"{symbol} OHLCV/ATR hesaplama hatası: {str(e)}")
            
            # Entry levels hesapla
            entry_levels = self.entry_calc.calculate_entry_levels(
                symbol=symbol,
                direction=direction,
                current_price=current_price,
                df=df,
                atr=atr,
                timeframe='1h'
            )
            
            # Gönderim anındaki anlık fiyatı yeniden al (küçük farkları göstermek için)
            now_price = self.cmd_handler.market_data.get_latest_price(symbol)
            if not now_price:
                now_price = signal_price
            current_price_timestamp = int(time.time())

            # Signal ID oluştur (mesaj formatında gösterilmek için)
            signal_id = None
            if self.signal_repository:
                signal_id = self.signal_repository.generate_signal_id(symbol)

            # Mesaj formatla
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
                confidence_change=None  # Yeni sinyal, değişiklik yok
            )
            
            # Inline keyboard oluştur
            keyboard = self.formatter.create_signal_keyboard(signal_id)
            
            # Telegram kanalına gönder ve message_id al (keyboard ile)
            message_id = self._send_to_channel(message, reply_markup=keyboard)
            
            if message_id:
                self.logger.info(
                    f"{symbol} sinyal bildirimi gönderildi - "
                    f"Message ID: {message_id}, Signal ID: {signal_id}"
                )
                
                # Sinyali veritabanına kaydet
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

                # Cache güncelle (hibrit cooldown)
                self._update_signal_cache(
                    symbol=symbol,
                    direction=direction,
                    confidence=confidence,
                    timestamp=signal_created_at,
                    source='send'
                )
            else:
                # Mesaj gönderilemedi veya message_id alınamadı
                error_msg = (
                    f"{symbol} sinyal bildirimi gönderilemedi veya message_id alınamadı - "
                    f"Signal ID: {signal_id if signal_id else 'None'}"
                )
                self.logger.error(error_msg)
                
                # Eğer signal_id varsa, bu durumu daha detaylı logla
                # (Mesaj gönderilmiş olabilir ama message_id alınamamış olabilir)
                if signal_id:
                    self.logger.warning(
                        f"⚠️ KRİTİK: {symbol} için sinyal mesajı gönderilmeye çalışıldı ama "
                        f"message_id alınamadı. Signal ID: {signal_id}. "
                        f"Eğer mesaj Telegram'da görünüyorsa, bu sinyal veritabanına kaydedilmemiş olabilir. "
                        f"Bu sinyal manuel olarak veritabanına eklenmelidir."
                    )
                
                # ÖNEMLİ: Cache güncellemesi message_id alınamasa bile yapılmalı
                # Çünkü mesaj Telegram'a gönderilmiş olabilir (ama message_id alınamamış olabilir)
                # Bu durumda en azından cooldown mekanizması çalışmalı ki aynı sinyal tekrar gönderilmesin
                # Cache güncelleme, cooldown kontrolü için kritik öneme sahiptir
                self.logger.warning(
                    f"{symbol} için cache güncelleniyor (message_id alınamadı ama cooldown korunmalı) - "
                    f"Signal ID: {signal_id}, Direction: {direction}, Timestamp: {signal_created_at}"
                )
                self._update_signal_cache(
                    symbol=symbol,
                    direction=direction,
                    confidence=confidence,
                    timestamp=signal_created_at,
                    source='send-failed'  # Kaynak olarak 'send-failed' kullan
                )
            
        except Exception as e:
            self.logger.error(f"{symbol} bildirim gönderme hatası: {str(e)}", exc_info=True)
            
            # Exception durumunda bile cache güncellemesi yapılmalı (cooldown korunmalı)
            # Eğer mesaj gönderilmeye çalışıldıysa ama exception oluştuysa,
            # cooldown mekanizmasının çalışması için cache güncellenmelidir
            try:
                # signal_data parametre olarak geldiği için direkt erişilebilir
                direction = signal_data.get('direction')
                confidence = signal_data.get('confidence', 0.0)
                signal_created_at = int(time.time())
                
                if direction:
                    self.logger.warning(
                        f"{symbol} için cache güncelleniyor (exception sonrası cooldown korunmalı) - "
                        f"Direction: {direction}, Timestamp: {signal_created_at}"
                    )
                    self._update_signal_cache(
                        symbol=symbol,
                        direction=direction,
                        confidence=confidence,
                        timestamp=signal_created_at,
                        source='send-exception'  # Kaynak olarak 'send-exception' kullan
                    )
            except Exception as cache_error:
                self.logger.error(
                    f"{symbol} cache güncelleme hatası (exception durumunda): {str(cache_error)}",
                    exc_info=True
                )
    
    def _send_to_channel(self, message: str, reply_markup=None) -> Optional[int]:
        """
        Mesajı Telegram kanalına gönderir.
        
        Args:
            message: Gönderilecek mesaj
            reply_markup: Inline keyboard markup (opsiyonel)
            
        Returns:
            Telegram message_id veya None
        """
        try:
            # Bot manager'ın güvenli sync wrapper metodunu kullan
            # Bu metod _run_on_bot_loop kullanarak event loop hatalarını önler
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
        TP ve SL seviyelerini hesaplar (message_formatter ile aynı mantık).
        
        Args:
            signal_price: Sinyal fiyatı
            direction: LONG/SHORT
            atr: ATR değeri
            timeframe: Timeframe
            
        Returns:
            TP ve SL seviyeleri dict
        """
        tp_levels = {}
        sl_levels = {}
        
        # TP seviyeleri (R:R 1:1, 1:2, 1:3)
        if atr:
            risk_dist = atr
        else:
            risk_dist = signal_price * 0.01
        
        for rr in [1, 2, 3]:
            offset = risk_dist * rr
            if direction == 'LONG':
                tp_price = signal_price + offset
            elif direction == 'SHORT':
                tp_price = signal_price - offset
            else:
                tp_price = None
            
            if tp_price:
                tp_levels[f'tp{rr}_price'] = tp_price
        
        # SL seviyeleri (ATR 1.0, 1.5, 2.0)
        multipliers = [1.0, 1.5, 2.0]
        for m in multipliers:
            if atr:
                offset = atr * m
                if direction == 'LONG':
                    sl_price = signal_price - offset
                elif direction == 'SHORT':
                    sl_price = signal_price + offset
                else:
                    sl_price = None
            else:
                pct = float(m)
                if direction == 'LONG':
                    sl_price = signal_price * (1 - pct/100)
                elif direction == 'SHORT':
                    sl_price = signal_price * (1 + pct/100)
                else:
                    sl_price = None
            
            if sl_price:
                if m == 1.0:
                    sl_levels['sl1_price'] = sl_price
                elif m == 1.5:
                    sl_levels['sl1_5_price'] = sl_price
                elif m == 2.0:
                    sl_levels['sl2_price'] = sl_price
        
        return {**tp_levels, **sl_levels}

    def _build_custom_tp_sl_levels(
        self,
        custom_targets: Dict[str, Dict[str, float]]
    ) -> Dict:
        """Custom hedeflerden TP/SL seviyeleri oluşturur."""
        def _price_for(key: str) -> Optional[float]:
            info = custom_targets.get(key, {})
            price = info.get('price')
            try:
                return float(price) if price is not None else None
            except (TypeError, ValueError):
                return None
        
        tp1_price = _price_for('tp1')
        tp2_price = _price_for('tp2')
        tp3_price = _price_for('tp3')
        stop_price = _price_for('stop_loss')
        
        # Ranging stratejisinde sadece 2 TP ve 1 SL var
        # SL'yi sadece sl2_price olarak set et (diğerleri None)
        return {
            'tp1_price': tp1_price,
            'tp2_price': tp2_price,
            'tp3_price': tp3_price,
            'sl1_price': None,
            'sl1_5_price': None,
            'sl2_price': stop_price  # Ranging'de tek SL, sl2 olarak kaydediliyor
        }
    
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
        Sinyali veritabanına kaydeder.
        
        Args:
            symbol: Trading pair
            signal_data: Sinyal verisi
            entry_levels: Entry levels
            signal_price: Sinyal fiyatı
            atr: ATR değeri
            timeframe: Timeframe
            telegram_message_id: Telegram mesaj ID
            telegram_channel_id: Telegram kanal ID
            signal_id: Sinyal ID (verilmezse oluşturulur)
        """
        try:
            if not self.signal_repository:
                return
            
            # Signal ID oluştur (verilmediyse)
            if not signal_id:
                signal_id = self.signal_repository.generate_signal_id(symbol)
            
            # Direction ve confidence
            direction = signal_data.get('direction', 'NEUTRAL')
            confidence = signal_data.get('confidence', 0.0)
            strategy_type = signal_data.get('strategy_type', 'trend')
            custom_targets = signal_data.get('custom_targets') if isinstance(signal_data.get('custom_targets'), dict) else {}
            
            # TP/SL seviyelerini hesapla
            if strategy_type == 'ranging' and custom_targets:
                tp_sl_levels = self._build_custom_tp_sl_levels(custom_targets)
            else:
                tp_sl_levels = self._calculate_tp_sl_levels(
                    signal_price=signal_price,
                    direction=direction,
                    atr=atr,
                    timeframe=timeframe
                )
            
            # Score breakdown ve market context (JSON)
            score_breakdown = signal_data.get('score_breakdown', {})
            market_context = signal_data.get('market_context', {})
            
            # Type safety: Ensure dict type
            if not isinstance(score_breakdown, dict):
                score_breakdown = {}
            if not isinstance(market_context, dict):
                market_context = {}
            
            # Ticker bilgisi ile market context zenginleştir
            ticker = self.cmd_handler.market_data.get_ticker_info(symbol)
            if ticker and market_context:
                market_context['volume_24h_usd'] = ticker.get('quoteVolume', 0)
                market_context['price_change_24h_pct'] = ticker.get('percentage', 0)
            
            # R-distances hesapla
            r_distances = {}
            if self.risk_reward_calc:
                r_distances = self.risk_reward_calc.calculate_r_distances(
                    signal_price=signal_price,
                    direction=direction,
                    tp1=tp_sl_levels.get('tp1_price'),
                    tp2=tp_sl_levels.get('tp2_price'),
                    tp3=tp_sl_levels.get('tp3_price'),
                    sl1=tp_sl_levels.get('sl1_price'),
                    sl2=tp_sl_levels.get('sl2_price')
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
            
            # Sinyali kaydet
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
                tp3_price=tp_sl_levels.get('tp3_price'),
                sl1_price=tp_sl_levels.get('sl1_price'),
                sl1_5_price=tp_sl_levels.get('sl1_5_price'),
                sl2_price=tp_sl_levels.get('sl2_price'),
                signal_data=signal_data,
                entry_levels=entry_levels,
                signal_score_breakdown=json.dumps(score_breakdown) if score_breakdown else None,
                market_context=json.dumps(market_context) if market_context else None,
                tp1_distance_r=r_distances.get('tp1_distance_r'),
                tp2_distance_r=r_distances.get('tp2_distance_r'),
                tp3_distance_r=r_distances.get('tp3_distance_r'),
                sl1_distance_r=r_distances.get('sl1_distance_r'),
                sl2_distance_r=r_distances.get('sl2_distance_r'),
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
        direction: str,
        confidence: float,
        timestamp: Optional[int] = None,
        source: str = 'runtime'
    ) -> Dict:
        """
        Sinyal cache'ini günceller.
        
        Args:
            symbol: Trading pair
            direction: LONG/SHORT
            confidence: Confidence değeri
            timestamp: Sinyal zamanı (None ise current time)
            source: Güncelleme kaynağı (loglama için)
        """
        current_time = timestamp if timestamp is not None else int(time.time())
        
        self.signal_cache[symbol] = {
            'last_signal_time': current_time,
            'last_direction': direction,
            'confidence': confidence
        }
        
        self.logger.debug(
            "%s cache güncellendi (%s): direction=%s, time=%s, confidence=%.3f",
            symbol,
            source,
            direction,
            current_time,
            confidence
        )
        return self.signal_cache[symbol]
    
    def _warmup_cache_from_db(self) -> None:
        """Uygulama başlatılırken cooldown cache'ini veritabanından doldurur."""
        if not self.signal_repository:
            self.logger.debug("Cooldown cache warmup atlandı: SignalRepository tanımlı değil")
            return

        base_hours = int(self.cooldown_seconds / 3600)
        if base_hours <= 0:
            base_hours = 1
        lookback_hours = max(24, base_hours * 3)

        summaries = self.signal_repository.get_recent_signal_summaries(lookback_hours)
        if not summaries:
            self.logger.debug(
                "Cooldown cache warmup verisi bulunamadı (lookback=%dh)",
                lookback_hours
            )
            return

        for summary in summaries:
            self._update_signal_cache(
                symbol=summary.get('symbol'),
                direction=summary.get('direction', 'NEUTRAL'),
                confidence=float(summary.get('confidence', 0.0) or 0.0),
                timestamp=summary.get('created_at'),
                source='warmup'
            )

        self.logger.info(
            "Cooldown cache warmup tamamlandı: %d sembol yüklendi (lookback=%dh)",
            len(summaries),
            lookback_hours
        )

    def get_cache_stats(self) -> Dict:
        """
        Cache istatistiklerini döndürür.
        
        Returns:
            Cache istatistikleri
        """
        current_time = int(time.time())
        
        active_signals = 0
        for symbol, data in self.signal_cache.items():
            time_since_last = current_time - data.get('last_signal_time', 0)
            if time_since_last < self.cooldown_seconds:
                active_signals += 1
        
        return {
            'total_cached_symbols': len(self.signal_cache),
            'active_cooldowns': active_signals,
            'confidence_threshold': self.confidence_threshold,
            'cooldown_hours': self.cooldown_seconds / 3600
        }
    
    def cleanup_old_cache(self) -> None:
        """Eski cache girişlerini temizler."""
        current_time = int(time.time())
        cleanup_threshold = self.cooldown_seconds * 2  # 2x cooldown süresi
        
        symbols_to_remove = []
        
        for symbol, data in self.signal_cache.items():
            time_since_last = current_time - data.get('last_signal_time', 0)
            if time_since_last > cleanup_threshold:
                symbols_to_remove.append(symbol)
        
        for symbol in symbols_to_remove:
            del self.signal_cache[symbol]
            self.logger.debug(f"{symbol} cache'den temizlendi")
        
        if symbols_to_remove:
            self.logger.info(f"{len(symbols_to_remove)} eski cache girişi temizlendi")
    
    def _log_rejection_scorecard(
        self,
        symbol: str,
        score: float,
        threshold: float,
        signal_data: Dict,
        ranking_info: Optional[Dict] = None
    ) -> None:
        """
        Reddedilme Karnesi (Rejection Scorecard) - Detaylı log.
        
        Args:
            symbol: Trading pair
            score: Toplam skor (confidence)
            threshold: Minimum eşik değeri
            signal_data: Sinyal verisi (score_breakdown, market_context içerir)
            ranking_info: Ranking bilgileri (opsiyonel)
        """
        try:
            score_breakdown = signal_data.get('score_breakdown', {})
            market_context = signal_data.get('market_context', {})
            direction = signal_data.get('direction', 'UNKNOWN')
            
            # RSI bilgisi
            rsi_value = score_breakdown.get('rsi_value', 0)
            rsi_signal = score_breakdown.get('rsi_signal', 'NEUTRAL')
            rsi_status = self._get_indicator_status(rsi_signal, direction, rsi_value)
            
            # Trend bilgisi
            adx_value = score_breakdown.get('adx_value', 0)
            adx_signal = score_breakdown.get('adx_signal', 'NEUTRAL')
            trend_status = self._get_trend_status(adx_signal, direction, adx_value)
            
            # Hacim bilgisi
            volume_relative = score_breakdown.get('volume_relative', 1.0)
            volume_signal = score_breakdown.get('volume_signal', 'NEUTRAL')
            volume_status = self._get_volume_status(volume_relative, volume_signal)
            
            # Bonus bilgileri (eğer varsa)
            base_score = ranking_info.get('base_score', score) if ranking_info else score
            rsi_bonus = ranking_info.get('rsi_bonus', 0.0) if ranking_info else 0.0
            volume_bonus = ranking_info.get('volume_bonus', 0.0) if ranking_info else 0.0
            
            # Log mesajı oluştur
            log_lines = [
                f"❌ {symbol} Sinyali Yetersiz (Puan: {score:.2f} / Eşik: {threshold:.2f})",
                f"📊 Karne:",
                f"   • Yön: {direction}",
                f"   • Base Score: {base_score:.3f}",
            ]
            
            if rsi_bonus != 0.0 or volume_bonus != 0.0:
                log_lines.append(f"   • RSI Bonus: {rsi_bonus:+.3f}")
                log_lines.append(f"   • Volume Bonus: {volume_bonus:+.3f}")
            
            log_lines.extend([
                f"   • RSI: {rsi_status} (Değer: {rsi_value:.1f})",
                f"   • Trend: {trend_status} (ADX: {adx_value:.1f})",
                f"   • Hacim: {volume_status} (Ortalamanın {volume_relative*100:.0f}%)"
            ])
            
            # Market context bilgileri
            regime = market_context.get('regime', 'unknown')
            volatility = market_context.get('volatility_percentile', 0)
            log_lines.append(f"   • Piyasa Rejimi: {regime.upper()}")
            log_lines.append(f"   • Volatilite: {volatility:.1f}%")
            
            self.logger.info("\n".join(log_lines))
            
        except Exception as e:
            # Hata durumunda basit log
            self.logger.debug(
                f"{symbol} confidence düşük: {score:.3f} (scorecard hatası: {str(e)})"
            )
    
    def _get_indicator_status(self, signal: str, direction: str, value: float) -> str:
        """İndikatör durumunu formatla."""
        if signal == direction:
            return f"✅ Uyumlu ({signal})"
        elif signal == 'NEUTRAL':
            return f"⚪ Nötr"
        else:
            return f"❌ Ters ({signal})"
    
    def _get_trend_status(self, signal: str, direction: str, adx_value: float) -> str:
        """Trend durumunu formatla."""
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
        """Hacim durumunu formatla."""
        if relative >= 1.5:
            return f"✅ Yüksek (x{relative:.2f})"
        elif relative >= 1.0:
            return f"⚪ Normal (x{relative:.2f})"
        else:
            return f"❌ Düşük (x{relative:.2f})"
    
    def _log_market_pulse(self) -> None:
        """
        Piyasa Nabzı Raporu (Market Pulse Log) - Genel piyasa durumunu özetler.
        """
        try:
            from datetime import datetime
            
            # BTC durumunu kontrol et
            btc_ticker = None
            btc_status = "Bilinmiyor"
            btc_change_24h = 0.0
            btc_rsi = 0.0
            
            try:
                if self.cmd_handler and self.cmd_handler.market_data:
                    btc_ticker = self.cmd_handler.market_data.get_ticker_info("BTC/USDT")
                    if btc_ticker:
                        # CCXT standart alanı: 'percentage' (SignalGenerator ile tutarlı)
                        btc_change_24h = float(btc_ticker.get('percentage', 0) or 0)
                        # Eğer 'percentage' yoksa, 'info' içindeki ham veriye bak
                        if btc_change_24h == 0 and 'info' in btc_ticker:
                            btc_change_24h = float(btc_ticker['info'].get('priceChangePercent', 0) or 0)
                        # RSI için 1h veri çek
                        btc_1h_data = self.cmd_handler.market_data.fetch_ohlcv("BTC/USDT", "1h", limit=200)
                        if btc_1h_data is not None and len(btc_1h_data) > 0:
                            from analysis.technical_indicators import TechnicalIndicatorCalculator
                            indicator_calc = TechnicalIndicatorCalculator()
                            indicators = indicator_calc.calculate_all(btc_1h_data)
                            rsi_data = indicators.get('rsi', {})
                            btc_rsi = rsi_data.get('value', 0)
                        
                        # BTC durumunu belirle
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
            
            # Zaman bilgisi
            current_time = datetime.now().strftime("%H:%M")
            
            # Log mesajı
            log_lines = [
                f"🌍 PİYASA NABZI ({current_time}):",
                f"   • BTC Durumu: {btc_status} (24h: {btc_change_24h:+.2f}%, RSI: {btc_rsi:.1f})"
            ]
            
            self.logger.info("\n".join(log_lines))
            
        except Exception as e:
            self.logger.debug(f"Piyasa nabzı raporu hatası: {str(e)}")
