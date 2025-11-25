"""
SignalTracker: TP/SL seviyelerini takip eden ve mesajları güncelleyen sınıf.
Aktif sinyalleri kontrol eder, TP/SL hit durumlarını günceller ve Telegram mesajlarını düzenler.
"""
import time
from typing import Dict, Optional
from utils.logger import LoggerManager
from data.signal_repository import SignalRepository
from data.market_data_manager import MarketDataManager
from bot.telegram_bot_manager import TelegramBotManager
from bot.message_formatter import MessageFormatter


class SignalTracker:
    """TP/SL seviyelerini takip eder ve mesajları günceller."""
    
    def __init__(
        self,
        signal_repository: SignalRepository,
        market_data: MarketDataManager,
        bot_manager: TelegramBotManager,
        message_formatter: MessageFormatter,
        message_update_delay: float = 0.6
    ):
        """
        SignalTracker'ı başlatır.
        
        Args:
            signal_repository: Signal repository
            market_data: Market data manager
            bot_manager: Telegram bot manager
            message_formatter: Message formatter
            message_update_delay: Mesaj güncellemeleri arası minimum bekleme süresi (saniye, default: 0.6)
        """
        self.repository = signal_repository
        self.market_data = market_data
        self.bot_manager = bot_manager
        self.formatter = message_formatter
        # Mesaj güncellemeleri arası minimum bekleme süresi (Telegram rate limit için)
        # Varsayılan 0.6 saniye (Telegram'ın flood control'üne takılmamak için)
        self.message_update_delay = message_update_delay if message_update_delay > 0 else 0.6
        self.logger = LoggerManager().get_logger('SignalTracker')
        self._last_update_time = 0.0
    
    def _calculate_price_difference(
        self,
        target_price: Optional[float],
        current_price: Optional[float],
        direction: str,
        is_tp: bool
    ) -> Optional[float]:
        """Hedef ve mevcut fiyat arasındaki farkı (hedefe kalan) hesaplar."""
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
        """Hedefe kalan yüzdeyi hesaplar."""
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
        """Sinyalin güncel durumunu detaylı şekilde loglar."""
        signal_id = signal.get('signal_id', 'unknown')
        symbol = signal.get('symbol', 'unknown')
        signal_price = signal.get('signal_price')

        self.logger.info(
            "Sinyal takibi başlatıldı: id=%s symbol=%s direction=%s signal_price=%.6f current_price=%.6f",
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
                "%s TP%d: hedef=%.6f durum=%s fiyat_farkı=%s kalan_yüzde=%s",
                signal_id,
                tp_level,
                tp_price,
                "HIT" if tp_hit else "BEKLEMEDE",
                "N/A" if price_diff is None else f"{price_diff:.6f}",
                "N/A" if remaining_pct is None else f"{remaining_pct:.2f}%"
            )

        sl_price = signal.get('sl_price')
        if sl_price is not None:
            sl_hit = signal.get('sl_hit', 0) == 1
            price_diff = self._calculate_price_difference(sl_price, current_price, direction, is_tp=False)
            remaining_pct = self._calculate_percentage_to_target(sl_price, current_price, direction, is_tp=False)

            self.logger.debug(
                "%s SL: hedef=%.6f durum=%s fiyat_farkı=%s kalan_yüzde=%s",
                signal_id,
                sl_price,
                "HIT" if sl_hit else "BEKLEMEDE",
                "N/A" if price_diff is None else f"{price_diff:.6f}",
                "N/A" if remaining_pct is None else f"{remaining_pct:.2f}%"
            )

    def check_all_active_signals(self) -> None:
        """
        Tüm aktif sinyalleri kontrol eder ve gerekirse günceller.
        """
        try:
            active_signals = self.repository.get_active_signals()
            
            if not active_signals:
                self.logger.debug("Aktif sinyal yok")
                return
            
            self.logger.info(f"{len(active_signals)} aktif sinyal kontrol ediliyor")
            
            for signal in active_signals:
                try:
                    self.check_signal_levels(signal)
                except Exception as e:
                    self.logger.error(
                        f"Sinyal kontrolü hatası ({signal.get('signal_id', 'unknown')}): {str(e)}",
                        exc_info=True
                    )
                    
        except Exception as e:
            self.logger.error(f"Aktif sinyal kontrolü hatası: {str(e)}", exc_info=True)
    
    def check_signal_levels(self, signal: Dict) -> None:
        """
        Tek bir sinyal için TP/SL seviyelerini kontrol eder.
        
        Args:
            signal: Sinyal dict (veritabanından gelen)
        """
        try:
            signal_id = signal.get('signal_id')
            symbol = signal.get('symbol')
            direction = signal.get('direction')
            signal_price = signal.get('signal_price')
            
            if not all([signal_id, symbol, direction, signal_price]):
                self.logger.warning(f"Eksik sinyal bilgisi: {signal_id}")
                return
            
            # Güncel fiyatı al
            current_price = self.market_data.get_latest_price(symbol)
            if not current_price:
                self.logger.warning(f"{symbol} güncel fiyat alınamadı")
                return

            self._log_signal_snapshot(signal, current_price, direction)
            
            # 1) SNAPSHOT KAYDET
            self.repository.save_price_snapshot(
                signal_id=signal_id,
                timestamp=int(time.time()),
                price=current_price,
                source='tracker_tick'
            )
            
            # 2) MFE/MAE GÜNCELLE
            self._update_mfe_mae(signal, current_price, direction)
            
            # 3) ALTERNATIVE ENTRY HIT KONTROLÜ
            self._check_alternative_entry_hit(signal, current_price, direction)
            
            # 4) FINALİZE KONTROLÜ
            if self._should_finalize_signal(signal):
                final_outcome = self._determine_final_outcome(signal)
                self.repository.finalize_signal(signal_id, current_price, final_outcome)
                self.logger.info(f"Sinyal finalized: {signal_id} - {final_outcome}")
            
            # TP seviyelerini kontrol et
            tp_hits = self._check_tp_levels(signal, current_price, direction)
            
            # SL seviyelerini kontrol et
            sl_hits = self._check_sl_levels(signal, current_price, direction)
            
            # Sadece gerçekten yeni hit olan seviyeler varsa mesajı güncelle
            # (tp_hits ve sl_hits dict'leri her zaman dolu, sadece True değerleri kontrol et)
            has_new_tp_hits = any(tp_hits.values()) if tp_hits else False
            has_new_sl_hits = any(sl_hits.values()) if sl_hits else False
            
            if has_new_tp_hits or has_new_sl_hits:
                self.logger.debug(
                    f"{symbol} yeni hit tespit edildi - "
                    f"TP hits: {[k for k, v in tp_hits.items() if v]}, "
                    f"SL hits: {[k for k, v in sl_hits.items() if v]}"
                )
                # Yeni hit varsa mesajı güncelle (confidence_change içeride hesaplanacak)
                self._update_telegram_message(signal, tp_hits, sl_hits)
            else:
                # Yeni hit yok, mesaj güncelleme yapma (gereksiz güncellemeleri önle)
                self.logger.debug(f"{symbol} yeni hit yok, mesaj güncellenmedi")
                
        except Exception as e:
            self.logger.error(f"Sinyal seviye kontrolü hatası: {str(e)}", exc_info=True)
    
    def update_message_for_signal(self, signal: Dict) -> None:
        """
        Sinyal mesajını günceller (signal log değişiklikleri için).
        TP/SL hit kontrolü yapmaz, sadece mesajı günceller.
        
        Args:
            signal: Sinyal dict (veritabanından gelen, güncel signal_log ile)
        """
        try:
            signal_id = signal.get('signal_id')
            symbol = signal.get('symbol')
            
            if not all([signal_id, symbol]):
                self.logger.warning(f"Eksik sinyal bilgisi (mesaj güncelleme): {signal_id}")
                return
            
            # Güncel fiyatı al
            current_price = self.market_data.get_latest_price(symbol)
            if not current_price:
                self.logger.warning(f"{symbol} güncel fiyat alınamadı (mesaj güncelleme)")
                return
            
            # TP/SL hit durumlarını kontrol et (ama hit olmasa bile mesajı güncelle)
            tp_hits = self._check_tp_levels(signal, current_price, signal.get('direction', 'LONG'))
            sl_hits = self._check_sl_levels(signal, current_price, signal.get('direction', 'LONG'))
            
            # Mesajı güncelle (hit olmasa bile - buton ile manuel güncelleme için)
            # confidence_change içeride hesaplanacak
            self._update_telegram_message(signal, tp_hits, sl_hits)
                
        except Exception as e:
            self.logger.error(f"Sinyal mesaj güncelleme hatası: {str(e)}", exc_info=True)
    
    def _check_tp_levels(
        self,
        signal: Dict,
        current_price: float,
        direction: str
    ) -> Dict[int, bool]:
        """
        TP seviyelerini kontrol eder.
        
        Args:
            signal: Sinyal dict
            current_price: Güncel fiyat
            direction: LONG/SHORT
            
        Returns:
            TP hit durumları {1: True/False, 2: True/False}
        """
        tp_hits = {}
        
        # Dengeli yaklaşım: Sadece TP1 ve TP2 kontrol edilir (TP3 kaldırıldı)
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
                "%s TP%d kontrolü: hedef=%.6f mevcut=%.6f fiyat_farkı=%s kalan_yüzde=%s durum=%s",
                signal.get('signal_id', 'unknown'),
                tp_level,
                tp_price,
                current_price,
                "N/A" if price_diff is None else f"{price_diff:.6f}",
                "N/A" if remaining_pct is None else f"{remaining_pct:.2f}%",
                "HIT" if tp_already_hit else "BEKLEMEDE"
            )

            if tp_already_hit:
                tp_hits[tp_level] = False
                continue
            
            # Touch kontrolü
            if direction == 'LONG':
                hit = current_price >= tp_price
            elif direction == 'SHORT':
                hit = current_price <= tp_price
            else:
                hit = False
            
            tp_hits[tp_level] = hit
            
            # Eğer hit olduysa, veritabanını güncelle
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
        SL seviyelerini kontrol eder.
        
        Args:
            signal: Sinyal dict
            current_price: Güncel fiyat
            direction: LONG/SHORT
            
        Returns:
            SL hit durumu {'sl': True/False}
        """
        sl_hits = {'sl': False}
        sl_price = signal.get('sl_price')
        sl_already_hit = signal.get('sl_hit', 0) == 1
        
        if not sl_price:
            return sl_hits

        price_diff = self._calculate_price_difference(sl_price, current_price, direction, is_tp=False)
        remaining_pct = self._calculate_percentage_to_target(sl_price, current_price, direction, is_tp=False)
        self.logger.debug(
            "%s SL kontrolü: hedef=%.6f mevcut=%.6f fiyat_farkı=%s kalan_yüzde=%s durum=%s",
            signal.get('signal_id', 'unknown'),
            sl_price,
            current_price,
            "N/A" if price_diff is None else f"{price_diff:.6f}",
            "N/A" if remaining_pct is None else f"{remaining_pct:.2f}%",
            "HIT" if sl_already_hit else "BEKLEMEDE"
        )

        if sl_already_hit:
            return sl_hits
        
        # Touch kontrolü
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
        Telegram mesajını günceller.
        
        Args:
            signal: Sinyal dict
            tp_hits: TP hit durumları
            sl_hits: SL hit durumları
        """
        try:
            message_id = signal.get('telegram_message_id')
            channel_id = signal.get('telegram_channel_id')
            symbol = signal.get('symbol')
            
            if not all([message_id, channel_id, symbol]):
                self.logger.warning(f"Mesaj güncelleme için eksik bilgi: {signal.get('signal_id')}")
                return
            
            # Sinyal verilerini al
            signal_data = signal.get('signal_data', {})
            entry_levels = signal.get('entry_levels', {})
            signal_price = signal.get('signal_price')
            
            # Güncel fiyatı al
            current_price, current_price_ts = self.market_data.get_latest_price_with_timestamp(symbol)
            if not current_price:
                current_price = signal_price
            if not current_price_ts:
                current_price_ts = int(time.time())
            
            # Veritabanından güncel hit durumlarını al
            updated_signal = self.repository.get_signal(signal['signal_id'])
            if not updated_signal:
                self.logger.warning(f"Sinyal bulunamadı: {signal['signal_id']}")
                return
            
            # TP hit durumlarını dict'e çevir
            tp_hits_dict = {
                1: updated_signal.get('tp1_hit', 0) == 1,
                2: updated_signal.get('tp2_hit', 0) == 1
            }
            tp_hit_times = {
                1: updated_signal.get('tp1_hit_at'),
                2: updated_signal.get('tp2_hit_at')
            }
            
            # SL hit durumlarını dict'e çevir
            sl_hits_dict = {
                'sl': updated_signal.get('sl_hit', 0) == 1
            }
            sl_hit_times = {
                'sl': updated_signal.get('sl_hit_at')
            }

            created_at = updated_signal.get('created_at') or signal.get('created_at')
            signal_id = updated_signal.get('signal_id') or signal.get('signal_id')
            
            # En son confidence değişikliğini al
            confidence_change = self.repository.get_latest_confidence_change(signal_id)
            
            # Mesajı yeniden formatla
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
            
            # Rate limiting: Mesaj güncellemeleri arasında minimum delay
            current_time = time.time()
            time_since_last_update = current_time - self._last_update_time
            if time_since_last_update < self.message_update_delay:
                sleep_time = self.message_update_delay - time_since_last_update
                self.logger.debug(f"Rate limiting: {sleep_time:.3f} saniye bekleniyor")
                time.sleep(sleep_time)
            
            # Mevcut mesajdan keyboard'u almak için mesajı çek
            # Ama bu ekstra bir API çağrısı gerektirir, bu yüzden
            # Mesaj güncellenirken keyboard'u korumak için her zaman aynı keyboard'u kullanıyoruz
            # (SignalScannerManager'da gönderilirken eklenen keyboard)
            keyboard = self.formatter.create_signal_keyboard(signal_id)
            
            # Telegram mesajını güncelle (keyboard ile)
            success, message_not_found = self.bot_manager.edit_channel_message(
                channel_id=channel_id,
                message_id=message_id,
                message=message,
                reply_markup=keyboard
            )
            
            # Son güncelleme zamanını kaydet
            self._last_update_time = time.time()
            
            if success:
                self.logger.info(
                    f"Telegram mesajı güncellendi: {signal['signal_id']} - "
                    f"TP hits: {sum(tp_hits_dict.values())}, "
                    f"SL hits: {sum(sl_hits_dict.values())}"
                )
            elif message_not_found:
                # Mesaj silinmiş, sinyali aktif takipten çıkar
                self.logger.warning(
                    f"Telegram mesajı silinmiş, sinyal aktif takipten çıkarılıyor: {signal['signal_id']}"
                )
                self.repository.mark_message_deleted(signal['signal_id'])
            else:
                self.logger.warning(f"Telegram mesajı güncellenemedi: {signal['signal_id']}")
                
        except Exception as e:
            self.logger.error(
                f"Telegram mesaj güncelleme hatası: {str(e)}",
                exc_info=True
            )
    
    def _update_mfe_mae(self, signal: Dict, current_price: float, direction: str) -> tuple:
        """
        MFE/MAE hesaplar ve güncellerse True döner.
        
        Args:
            signal: Sinyal dict
            current_price: Güncel fiyat
            direction: Sinyal yönü
            
        Returns:
            (mfe_updated, mae_updated) tuple
        """
        signal_id = signal['signal_id']
        mfe_price = signal.get('mfe_price')
        mae_price = signal.get('mae_price')
        
        mfe_updated = False
        mae_updated = False
        
        if direction == 'LONG':
            # MFE: En yüksek fiyat
            if mfe_price is None or current_price > mfe_price:
                mfe_price = current_price
                mfe_updated = True
            # MAE: En düşük fiyat
            if mae_price is None or current_price < mae_price:
                mae_price = current_price
                mae_updated = True
        else:  # SHORT
            # MFE: En düşük fiyat
            if mfe_price is None or current_price < mfe_price:
                mfe_price = current_price
                mfe_updated = True
            # MAE: En yüksek fiyat
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
                f"MFE/MAE güncellendi: {signal_id} - "
                f"MFE: {mfe_price:.6f}, MAE: {mae_price:.6f}"
            )
        
        return mfe_updated, mae_updated
    
    def _check_alternative_entry_hit(self, signal: Dict, current_price: float, direction: str):
        """
        optimal/conservative entry fiyatlarına ulaşılmışsa kaydet.
        
        Args:
            signal: Sinyal dict
            current_price: Güncel fiyat
            direction: Sinyal yönü
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
        Sinyal kapatılmalı mı kontrol eder.
        
        Sadece 72 saat kontrolü yapar. TP/SL hit durumları finalize sebebi değildir,
        çünkü kullanıcı manuel TP/SL yönetimi yapıyor olabilir.
        
        Args:
            signal: Sinyal dict
            
        Returns:
            True ise kapatılmalı (sadece 72 saat geçtiyse)
        """
        # Sadece 72 saat kontrolü yap
        # TP/SL hit durumları finalize sebebi değildir (kullanıcı manuel yönetim yapabilir)
        created_at = signal.get('created_at', 0)
        if int(time.time()) - created_at > 72 * 3600:
            return True
        return False
    
    def _determine_final_outcome(self, signal: Dict) -> str:
        """
        final_outcome değeri belirler.
        
        Args:
            signal: Sinyal dict
            
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

