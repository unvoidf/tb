"""
CommandHandler: Telegram bot komutlarını işler.
/trend, /analiz ve /ayarlar komutlarını yönetir.
"""
from typing import Dict, List, Optional
from datetime import datetime
import time
from utils.logger import LoggerManager
from bot.message_formatter import MessageFormatter
from bot.user_whitelist import UserWhitelist
from data.market_data_manager import MarketDataManager
from data.coin_filter import CoinFilter
from analysis.signal_generator import SignalGenerator
from strategy.position_calculator import PositionCalculator
from strategy.risk_manager import RiskManager
from scheduler.components.signal_ranker import SignalRanker


class CommandHandler:
    """Bot komutlarını işler."""
    
    def __init__(self,
                 whitelist: UserWhitelist,
                 formatter: MessageFormatter,
                 market_data: MarketDataManager,
                 coin_filter: CoinFilter,
                 signal_generator: SignalGenerator,
                 position_calc: PositionCalculator,
                 risk_manager: RiskManager,
                 timeframes: List[str],
                 top_count: int = 20,
                 top_signals: int = 5):
        """CommandHandler'ı başlatır."""
        self.whitelist = whitelist
        self.formatter = formatter
        self.market_data = market_data
        self.coin_filter = coin_filter
        self.signal_gen = signal_generator
        self.position_calc = position_calc
        self.risk_mgr = risk_manager
        self.timeframes = timeframes
        self.top_count = top_count
        self.top_signals = top_signals
        self.logger = LoggerManager().get_logger('CommandHandler')
        self.user_notifications = {}  # user_id: bool
        # Basit per-user debounce/ratelimit (son /analiz zamanı)
        self._last_analyze_ts: Dict[int, float] = {}
        self._analyze_cooldown_seconds: int = 5
        # /tahmin çıktıları için cache (devre dışı)
        self.forecast_cache = None
        # Reminder manager (sonradan set edilecek)
        self.reminder_manager = None
        # Signal ranker (gelişmiş skorlama için)
        self.signal_ranker = SignalRanker()
        
        # Sinyal cache sistemi kaldırıldı
    
    def handle_trend(self, user_id: int) -> str:
        """
        /trend komutunu işler.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Response mesajı
        """
        if not self.whitelist.is_authorized(user_id):
            return self.whitelist.get_unauthorized_message()
        
        self.logger.info(f"User {user_id} - /trend komutu")
        
        try:
            # Top futures coinleri al
            symbols = self.coin_filter.get_top_futures_coins(self.top_count)
            
            if not symbols:
                return self.formatter.format_error_message('no_data')
            
            # Her coin için sinyal üret
            all_signals = []
            
            for symbol in symbols:
                signal_data = self._analyze_symbol(symbol)
                if signal_data:
                    all_signals.append({
                        'symbol': symbol,
                        'signal': signal_data
                    })
            
            if not all_signals:
                return self.formatter.format_error_message('analysis_failed')
            
            self.logger.info(f"Toplam {len(all_signals)} coin analiz edildi")
            
            # Sinyal dağılımını say (debug için)
            direction_counts = {'LONG': 0, 'SHORT': 0, 'NEUTRAL': 0}
            for signal_data in all_signals:
                direction_counts[signal_data['signal']['direction']] += 1
            
            self.logger.info(
                f"Sinyal dağılımı - "
                f"LONG: {direction_counts['LONG']}, "
                f"SHORT: {direction_counts['SHORT']}, "
                f"NEUTRAL: {direction_counts['NEUTRAL']}"
            )
            
            # SignalRanker ile gelişmiş skorlama ve sıralama
            top_signals = self.signal_ranker.rank_signals(all_signals, self.top_signals)
            
            self.logger.info(
                f"Top {len(top_signals)} sinyal seçildi: " + 
                ", ".join([s['symbol'] for s in top_signals])
            )
            
            return self.formatter.format_trend_summary_with_prices(top_signals, self.market_data)
            
        except Exception as e:
            self.logger.error(f"Trend analizi hatası: {str(e)}", exc_info=True)
            return self.formatter.format_error_message('analysis_failed')
    
    def handle_analyze(self, user_id: int, symbol: str, 
                      message_id: int = None) -> str:
        """
        /analiz [COIN] komutunu işler.
        
        Args:
            user_id: Telegram user ID
            symbol: Coin sembolü
            
        Returns:
            Response mesajı
        """
        if not self.whitelist.is_authorized(user_id):
            return self.whitelist.get_unauthorized_message()
        
        # Sembolü normalize et
        if not symbol.endswith('/USDT'):
            symbol = f"{symbol.upper()}/USDT"

        # Per-user debounce
        now_ts = time.time()
        last_ts = self._last_analyze_ts.get(user_id, 0)
        if now_ts - last_ts < self._analyze_cooldown_seconds:
            wait_sec = int(self._analyze_cooldown_seconds - (now_ts - last_ts))
            return (
                f"⌛ Lütfen {wait_sec}s bekleyip tekrar deneyin.\n"
                f"Örnek semboller: BTC/USDT, ETH/USDT, BNB/USDT"
            )
        self._last_analyze_ts[user_id] = now_ts
        
        self.logger.info(f"User {user_id} - /analiz {symbol}")
        
        try:
            # Sembol whitelist kontrolü (MarketDataManager üzerinden)
            if hasattr(self.market_data, 'is_valid_symbol') and not self.market_data.is_valid_symbol(symbol):
                # En yakın öneriler (basit baş harf eşleştirme)
                suggestions = []
                try:
                    valid = list(getattr(self.market_data, 'valid_symbols', []))
                    base = symbol.split('/')[0]
                    suggestions = [s for s in valid if s.startswith(base)]
                except Exception:
                    suggestions = []
                suggestion_text = ("\nÖneriler: " + ", ".join(suggestions[:5])) if suggestions else ""
                return (
                    "❌ Geçersiz sembol! Lütfen geçerli bir çift girin.\n"
                    "Örnek: BTC/USDT, ETH/USDT" + suggestion_text
                )

            signal = self._analyze_symbol(symbol)
            
            if not signal:
                return self.formatter.format_error_message('no_data')
            
            # Güncel fiyat her zaman gerekli
            current_price = self.market_data.get_latest_price(symbol)
            
            # Pozisyon hesapla
            position = None
            risk = None
            
            if signal['direction'] != 'NEUTRAL' and current_price:
                # İlk timeframe'in datasını kullan
                first_tf = self.timeframes[0]
                tf_data = signal['timeframe_signals'][first_tf]
                df = self.market_data.fetch_ohlcv(symbol, first_tf)
                atr = tf_data['indicators']['atr']
                
                position = self.position_calc.calculate_position(
                    df, signal, atr
                )
                
                if position:
                    risk = self.risk_mgr.calculate_position_size(
                        position, signal['confidence']
                    )
            else:
                # NEUTRAL ise de current_price'ı göstermek için dummy position
                if current_price:
                    position = {'current_price': current_price}
            
            return self.formatter.format_detailed_analysis(
                symbol, signal, position, risk
            )
            
        except Exception as e:
            self.logger.error(
                f"Analiz hatası ({symbol}): {str(e)}", 
                exc_info=True
            )
            return self.formatter.format_error_message('analysis_failed')
    
    def handle_tahmin(self, user_id: int, symbol: str) -> str:
        """
        /tahmin [SYMBOL] komutunu işler.
        Timeframe bazlı yükseliş/düşüş ihtimallerini gösterir.
        
        Args:
            user_id: Telegram user ID
            symbol: Coin sembolü
            
        Returns:
            Response mesajı
        """
        if not self.whitelist.is_authorized(user_id):
            return self.whitelist.get_unauthorized_message()
        
        # Sembolü normalize et
        if not symbol.endswith('/USDT'):
            symbol = f"{symbol.upper()}/USDT"
        
        self.logger.info(f"User {user_id} - /tahmin {symbol}")
        
        try:
            # Sembol whitelist kontrolü (MarketDataManager üzerinden)
            if hasattr(self.market_data, 'is_valid_symbol') and not self.market_data.is_valid_symbol(symbol):
                return (
                    "❌ Geçersiz sembol! Lütfen geçerli bir çift girin.\n"
                    "Örnek: BTC/USDT, ETH/USDT"
                )

            signal = self._analyze_symbol(symbol)
            self.logger.debug(f"/tahmin signal: {signal}")
            
            if not signal:
                return self.formatter.format_error_message('no_data')
            
            # Güncel fiyat
            current_price = self.market_data.get_latest_price(symbol)
            self.logger.debug(f"/tahmin current_price: {current_price}")
            if not current_price:
                return self.formatter.format_error_message('no_data')

            # ATR tabanlı fiyat tahmini
            tf_horizon_multiplier = {
                '1h': 1.0,
                '4h': 2.0,
                '1d': 4.0,
            }
            forecasts: Dict[str, float] = {}

            # Baskın yön ve ağırlıklı güven için topla
            tf_conf: Dict[str, float] = {}
            tf_dir: Dict[str, str] = {}

            for tf in self.timeframes:
                tf_signal = signal['timeframe_signals'].get(tf)
                if not tf_signal:
                    continue

                direction = tf_signal['direction']
                confidence = max(0.0, min(1.0, tf_signal['confidence']))
                indicators = tf_signal.get('indicators', {})
                atr = indicators.get('atr')
                self.logger.debug(
                    f"TF {tf} -> direction={direction}, confidence={confidence:.3f}, atr={atr}"
                )

                # Yön işareti
                if direction == 'LONG':
                    sign = 1
                elif direction == 'SHORT':
                    sign = -1
                else:
                    sign = 0

                # ATR yoksa yüzdesel fallback
                horizon_k = tf_horizon_multiplier.get(tf, 1.0)
                label = '24h' if tf == '1d' else tf

                # Range tahmini: low/high
                if atr:
                    base_amp = atr * horizon_k * max(0.6, confidence)
                else:
                    pct = 0.005 * max(0.6, confidence) * horizon_k
                    base_amp = current_price * pct
                self.logger.debug(
                    f"TF {tf} horizon_k={horizon_k}, label={label}, base_amp={base_amp}"
                )

                # NEUTRAL: simetrik ve çok dar aralık (≈ binde 1)
                if sign == 0:
                    neutral_amp = current_price * 0.001  # 0.1%
                    low = current_price - neutral_amp
                    high = current_price + neutral_amp
                # LONG: aralık tamamı güncel fiyatın ÜSTÜNDE
                elif sign == 1:
                    low = current_price + base_amp * 0.3
                    high = current_price + base_amp * 1.3
                # SHORT: aralık tamamı güncel fiyatın ALTINDA
                else:  # sign == -1
                    low = current_price - base_amp * 1.3
                    high = current_price - base_amp * 0.3

                forecasts[label] = {'low': low, 'high': high}
                self.logger.debug(
                    f"TF {tf} {label} forecast -> low={low}, high={high}"
                )

                # Özet verileri
                tf_conf[label] = confidence
                tf_dir[label] = 'Yükseliş' if sign == 1 else ('Düşüş' if sign == -1 else 'Nötr')

            # Ağırlıklı güven ve baskın yön
            weights = {'1h': 0.40, '4h': 0.35, '24h': 0.25}
            weighted = 0.0
            dir_score = 0.0
            for lbl, conf in tf_conf.items():
                w = weights.get(lbl, 0)
                weighted += conf * w
                d = 0
                if tf_dir.get(lbl) == 'Yükseliş':
                    d = 1
                elif tf_dir.get(lbl) == 'Düşüş':
                    d = -1
                dir_score += d * w
            if dir_score > 0.05:
                dominant = 'Yükseliş'
            elif dir_score < -0.05:
                dominant = 'Düşüş'
            else:
                dominant = 'Nötr'
            self.logger.debug(
                f"overall_weighted_confidence={weighted:.3f}, dir_score={dir_score:.3f} -> dominant={dominant}"
            )
            if dir_score > 0.05:
                dominant = 'Yükseliş'
            elif dir_score < -0.05:
                dominant = 'Düşüş'
            else:
                dominant = 'Nötr'

            summary_line = f"Baskın yön: {dominant} • Ağırlıklı güven: %{weighted*100:.1f}"
            breakdown = []
            for lbl in ['1h', '4h', '24h']:
                if lbl in tf_conf:
                    # tf_dir türkçe
                    dtr = 'LONG' if tf_dir[lbl] == 'Yükseliş' else ('SHORT' if tf_dir[lbl] == 'Düşüş' else 'NEUTRAL')
                    breakdown.append(f"{lbl}: {dtr} %{tf_conf[lbl]*100:.1f}")

            message_text = self.formatter.format_price_forecast(
                symbol=symbol,
                generated_at=datetime.utcnow(),
                current_price=current_price,
                forecasts=forecasts,
                summary_line=summary_line,
                tf_breakdown=breakdown
            )

            # Tahmini cache'e kaydetmek için geri dönen mesajı Telegram katmanında yakalayacağız,
            # bu yüzden burada sadece mesaj içeriğini döndürüyoruz.
            return message_text
            
        except Exception as e:
            self.logger.error(
                f"Tahmin hatası ({symbol}): {str(e)}", 
                exc_info=True
            )
            return self.formatter.format_error_message('analysis_failed')
    
    def handle_settings(self, user_id: int) -> str:
        """
        /settings komutunu işler (bildirim toggle).
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Response mesajı
        """
        if not self.whitelist.is_authorized(user_id):
            return self.whitelist.get_unauthorized_message()
        
        # Toggle notification
        current = self.user_notifications.get(user_id, True)
        self.user_notifications[user_id] = not current
        
        self.logger.info(
            f"User {user_id} - Bildirimler: {not current}"
        )
        
        return self.formatter.format_settings_message(not current)
    
    def is_notifications_enabled(self, user_id: int) -> bool:
        """
        Kullanıcının bildirimleri açık mı kontrol eder.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True ise bildirimler açık
        """
        return self.user_notifications.get(user_id, True)
    
    def _analyze_symbol(self, symbol: str) -> Optional[Dict]:
        """
        Tek sembol için multi-timeframe analiz yapar.
        
        Args:
            symbol: Trading pair
            
        Returns:
            Sinyal bilgisi veya None
        """
        # Multi-timeframe veri çek
        multi_tf_data = self.market_data.fetch_multi_timeframe(
            symbol, self.timeframes
        )
        
        if not multi_tf_data:
            return None
        
        # Sinyal üret
        signal = self.signal_gen.generate_signal(multi_tf_data)
        
        return signal

