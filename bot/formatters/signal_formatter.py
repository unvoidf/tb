"""
SignalFormatter: Sinyal bildirimi mesajları için formatlama.
Signal alert mesajı ve inline keyboard oluşturma.
"""
import time
from typing import Dict, List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bot.formatters.base_formatter import BaseFormatter


class SignalFormatter(BaseFormatter):
    """Sinyal bildirimi mesajlarını formatlar."""
    
    def format_signal_alert(
        self,
        symbol: str,
        signal_data: Dict,
        entry_levels: Dict,
        signal_price: float,
        now_price: float,
        tp_hits: Optional[Dict[int, bool]] = None,
        sl_hits: Optional[Dict[str, bool]] = None,
        created_at: Optional[int] = None,
        current_price_timestamp: Optional[int] = None,
        tp_hit_times: Optional[Dict[int, Optional[int]]] = None,
        sl_hit_times: Optional[Dict[str, Optional[int]]] = None,
        signal_id: Optional[str] = None,
        signal_log: Optional[List[Dict]] = None,
        confidence_change: Optional[float] = None,
    ) -> str:
        """
        Signal scanner çıktısını formatlar.
        
        Args:
            symbol: Trading pair (örn: BTC/USDT)
            signal_data: Sinyal verisi
            entry_levels: Dynamic entry levels
            signal_price: Sinyal fiyatı
            now_price: Mevcut fiyat
            tp_hits: TP hit durumları {1: True/False, 2: True/False, 3: True/False}
            sl_hits: SL hit durumları {'1': True/False, '1.5': True/False, '2': True/False}
            created_at: Sinyal oluşturulma zamanı
            current_price_timestamp: Güncel fiyatın ölçüm zamanı
            tp_hit_times: TP hit zamanları
            sl_hit_times: SL hit zamanları
            signal_id: Sinyal ID (örn: 20251107-074546-FILUSDT)
            signal_log: Sinyal günlüğü
            confidence_change: Güven değişimi
            
        Returns:
            Formatlanmış signal alert mesajı
        """
        try:
            # Yardımcılar
            direction = signal_data.get('direction', 'NEUTRAL')
            confidence = signal_data.get('confidence', 0.0)
            confidence_pct_raw = confidence * 100  # Float olarak tut (tam değer için)
            confidence_pct = int(round(confidence * 100))  # Eski format için (cap kontrolünde kullanılacak)
            direction_emoji = self.DIRECTION_EMOJI.get(direction, '➡️')
            direction_text = self.DIRECTION_TR.get(direction, direction)

            def fmt_price(price: float) -> str:
                """Fiyatı monospace (code block) formatında döndürür - tek tıkla kopyalama için."""
                if price is None:
                    return "-"
                if abs(price) >= 1:
                    return f"`${price:,.2f}`"
                return f"`${price:,.6f}`"

            # PNL (Kar/Zarar) hesaplama - Direction'a göre doğru formül
            try:
                if direction == 'LONG':
                    # LONG: Fiyat yükseldiğinde kar (pozitif)
                    pnl_pct = ((now_price - signal_price) / signal_price) * 100 if signal_price else 0.0
                elif direction == 'SHORT':
                    # SHORT: Fiyat düştüğünde kar (pozitif) - ÖNEMLİ: Ters formül
                    pnl_pct = ((signal_price - now_price) / signal_price) * 100 if signal_price else 0.0
                else:
                    pnl_pct = 0.0
            except Exception:
                pnl_pct = 0.0

            direction_title = self.DIRECTION_TITLE.get(direction, direction.upper())
            strategy_type = signal_data.get('strategy_type', 'trend')
            custom_targets = signal_data.get('custom_targets') if isinstance(signal_data.get('custom_targets'), dict) else {}
            is_ranging_strategy = strategy_type == 'ranging' and bool(custom_targets)
            forecast_text = 'N/A'
            try:
                tf_signals = signal_data.get('timeframe_signals')
                if isinstance(tf_signals, dict) and '4h' in tf_signals:
                    bias_dir = (tf_signals.get('4h') or {}).get('direction')
                    forecast_text = self.DIRECTION_FORECAST.get(bias_dir, 'Nötr')
            except Exception:
                forecast_text = 'N/A'

            # Timestamp'ler
            signal_time_str = self.format_timestamp_with_seconds(created_at) if created_at else self.format_timestamp_with_seconds(int(time.time()))
            current_price_time = current_price_timestamp if current_price_timestamp is not None else int(time.time())
            current_time_str = self.format_timestamp_with_seconds(current_price_time)

            # R/R Oranı Hesapla (TP1'in R/R'si - Finans Uzmanı Önerisi)
            rr_ratio_str = "N/A"
            try:
                # Önce custom targets'tan dene (ranging stratejisi için)
                if is_ranging_strategy:
                    tp1_price = custom_targets.get('tp1', {}).get('price')
                    sl_price = custom_targets.get('stop_loss', {}).get('price')
                    if tp1_price and sl_price:
                        risk = abs(signal_price - sl_price)
                        reward = abs(tp1_price - signal_price)
                        if risk > 0:
                            rr_val = reward / risk
                            rr_ratio_str = f"{rr_val:.2f}"
                else:
                    # Trend stratejisi için TP1'in R/R'sini hesapla (sinyal fiyatı bazlı)
                    # TP1 ve SL seviyelerini kullan (gerçek R:R)
                    atr = entry_levels.get('atr')
                    if atr:
                        # TP1 = 3x ATR (1.5R), SL = 2x ATR (TP1'in R/R = 1.5R)
                        if direction == 'LONG':
                            tp1_price = signal_price + (atr * 3)
                            sl_price = signal_price - (atr * 2)
                        else:  # SHORT
                            tp1_price = signal_price - (atr * 3)
                            sl_price = signal_price + (atr * 2)
                        
                        risk = abs(signal_price - sl_price)
                        reward = abs(tp1_price - signal_price)
                        if risk > 0:
                            rr_val = reward / risk
                            rr_ratio_str = f"{rr_val:.2f}"
                    else:
                        # Fallback: Optimal entry'den al (eski yöntem)
                        optimal_entry = entry_levels.get('optimal', {})
                        if optimal_entry and 'risk_reward' in optimal_entry:
                            rr_val = optimal_entry['risk_reward']
                            rr_ratio_str = f"{rr_val:.2f}"
            except Exception:
                pass

            # Başlık - Kısa ve öz
            direction_color = '🔴' if direction == 'SHORT' else '🟢'
            header_line = f"{direction_color} {direction_title} | {symbol}"
            lines = [header_line]
            
            # Sinyal tarih/saat bilgisi
            signal_created_at = created_at if created_at else int(time.time())
            signal_datetime = self.format_timestamp(signal_created_at)
            lines.append(f"🕐 {signal_datetime}")
            lines.append("")
            
            # Sinyal ve Güncel Fiyat
            lines.append(f"🔔 *Sinyal:* {fmt_price(signal_price)}")
            
            # Güncel fiyatı sadece güncelleme mesajlarında veya ciddi fark varsa göster
            # İlk mesajda (elapsed < 2 dk ve hit yok) gizle
            elapsed_seconds = current_price_time - signal_created_at
            
            has_hits = bool(tp_hits or sl_hits or (sl_hit_times and any(sl_hit_times.values())) or (tp_hit_times and any(tp_hit_times.values())))
            is_initial_message = elapsed_seconds < 120 and not has_hits
            
            if not is_initial_message:
                lines.append(f"💵 *Güncel:* {fmt_price(now_price)}")
            
            # R/R Bilgisi kaldırıldı (kullanıcı talebi)
            # lines.append(f"*R/R:* `{rr_ratio_str}`")
            
            # PNL (Kar/Zarar) - Direction'a göre doğru gösterim
            pnl_emoji = '✅' if pnl_pct > 0 else '❌' if pnl_pct < 0 else '🔁'
            pnl_status = "Kar" if pnl_pct > 0 else "Zarar" if pnl_pct < 0 else "Nötr"
            
            # Durum: "Durum:" yazısı kaldırıldı, sadece emoji ve yüzde gösteriliyor
            lines.append(f"{pnl_emoji} *{pnl_pct:+.2f}%* ({pnl_status})")
            
            # Geçen süre
            # signal_created_at ve current_price_time zaten yukarıda hesaplandı
            elapsed_time_str = self.format_time_elapsed(signal_created_at, current_price_time)
            if elapsed_time_str != "-":
                # Italic için _ kullan (MarkdownV2'de * bold, _ italic)
                lines.append(f"⏱ _{elapsed_time_str}_")
            
            lines.append("")

            atr = entry_levels.get('atr')
            timeframe = entry_levels.get('timeframe') or ''

            # TP seviyeleri (başlık kaldırıldı, direkt TP1/TP2 gösteriliyor)
            if is_ranging_strategy:
                # Ranging için SL fiyatını al (R/R hesaplaması için)
                stop_info = custom_targets.get('stop_loss', {})
                sl_price_ranging = stop_info.get('price')
                
                for idx, key in enumerate(['tp1', 'tp2', 'tp3'], start=1):
                    target_info = custom_targets.get(key)
                    if not target_info:
                        continue
                    price = target_info.get('price')
                    if price is None:
                        continue
                    try:
                        if direction == 'LONG':
                            tp_pct = ((price - signal_price) / signal_price) * 100 if signal_price else 0.0
                        else:
                            tp_pct = ((signal_price - price) / signal_price) * 100 if signal_price else 0.0
                    except Exception:
                        tp_pct = 0.0
                    
                    # R/R oranı hesapla
                    rr_ratio = 0.0
                    if sl_price_ranging:
                        try:
                            if direction == 'LONG':
                                risk = abs(signal_price - sl_price_ranging)
                                reward = abs(price - signal_price)
                            else:  # SHORT
                                risk = abs(signal_price - sl_price_ranging)
                                reward = abs(signal_price - price)
                            if risk > 0:
                                rr_ratio = reward / risk
                        except Exception:
                            pass
                    
                    hit_status = bool(tp_hits and tp_hits.get(idx, False))
                    hit_emoji = "✅" if hit_status else "⏳"
                    label = target_info.get('label', f"TP{idx}")
                    # R/R oranını parantez içinde ekle, format: 🎯 TP1 $PRICE (+X%) (YR) ⏳
                    if rr_ratio > 0:
                        lines.append(f"🎯 TP{idx} {fmt_price(price)} ({tp_pct:+.2f}%) ({rr_ratio:.2f}R) {hit_emoji}")
                    else:
                        lines.append(f"🎯 TP{idx} {fmt_price(price)} ({tp_pct:+.2f}%) {hit_emoji}")
            else:
                # Risk mesafesi: ATR 1.0 (veya %1 fallback)
                # TP seviyeleri (Dengeli Yaklaşım: TP1=1.5R, TP2=2.5R)
                # TP1 = 3x ATR (1.5R), TP2 = 5x ATR (2.5R)
                if atr:
                    risk_dist = atr
                else:
                    risk_dist = signal_price * 0.01
                tps = []
                # TP multipliers: [3, 5] -> TP1=1.5R, TP2=2.5R (SL=2x ATR bazlı)
                # SL mesafesi (R/R hesaplaması için)
                sl_distance = risk_dist * 2.0  # SL = 2x ATR
                
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
                        try:
                            tp_pct = ((tp_price - signal_price) / signal_price) * 100 if signal_price else 0.0
                        except Exception:
                            tp_pct = 0.0
                        
                        # R/R oranı hesapla (TP mesafesi / SL mesafesi)
                        rr_ratio = 0.0
                        try:
                            tp_distance = abs(offset)
                            if sl_distance > 0:
                                rr_ratio = tp_distance / sl_distance
                        except Exception:
                            pass
                        
                        # Hit durumunu kontrol et (tp_hits keyleri 1, 2 olarak gelir)
                        hit_status = bool(tp_hits and tp_hits.get(idx, False))
                        hit_emoji = "✅" if hit_status else "⏳"
                        # TP formatı: 🎯 TP1 $PRICE (+X%) (YR) ⏳
                        if rr_ratio > 0:
                            tps.append(f"🎯 TP{idx} {fmt_price(tp_price)} ({tp_pct:+.2f}%) ({rr_ratio:.2f}R) {hit_emoji}")
                        else:
                            tps.append(f"🎯 TP{idx} {fmt_price(tp_price)} ({tp_pct:+.2f}%) {hit_emoji}")
                lines.extend(tps)
            lines.append("")
            # SL seviyeleri (başlık kaldırıldı, direkt SL gösteriliyor)
            
            # SL seviyelerini sadeleştir: Tek bir SL listesi göster
            sl_levels = []
            # Ranging stratejisi için
            if is_ranging_strategy:
                stop_info = custom_targets.get('stop_loss')
                if stop_info and stop_info.get('price') is not None:
                    stop_price = stop_info.get('price')
                    try:
                        if direction == 'LONG':
                            sl_pct = ((stop_price - signal_price) / signal_price) * 100 if signal_price else 0.0
                        else:
                            sl_pct = ((signal_price - stop_price) / signal_price) * 100 if signal_price else 0.0
                    except Exception:
                        sl_pct = 0.0
                    
                    # Hit durumunu kontrol et (Ranging'de tek SL, '2' veya 'stop' olarak gelebilir)
                    is_hit = False
                    if sl_hits:
                        is_hit = sl_hits.get('2') or sl_hits.get('stop')
                        
                    hit_emoji = "❌" if is_hit else "⏳"
                    label = stop_info.get('label', 'Stop-Loss')
                    risk_pct = abs(sl_pct)
                    sl_levels.append(f"⛔️ SL {fmt_price(stop_price)} (Risk: {risk_pct:.1f}%) {hit_emoji}")
            
            # Trend stratejisi için
            else:
                # Dengeli yaklaşım: Tek SL (2x ATR)
                sl_multiplier = 2.0
                if atr:
                    offset = atr * sl_multiplier
                    if direction == 'LONG':
                        sl_price = signal_price - offset
                    elif direction == 'SHORT':
                        sl_price = signal_price + offset
                    else:
                        sl_price = None
                else:
                    # ATR yoksa yüzde fallback
                    pct = float(sl_multiplier)
                    if direction == 'LONG':
                        sl_price = signal_price * (1 - pct/100)
                    elif direction == 'SHORT':
                        sl_price = signal_price * (1 + pct/100)
                    else:
                        sl_price = None
                
                if sl_price:
                    try:
                        if direction == 'LONG':
                            sl_pct = ((sl_price - signal_price) / signal_price) * 100 if signal_price else 0.0
                        else:
                            sl_pct = ((signal_price - sl_price) / signal_price) * 100 if signal_price else 0.0
                    except Exception:
                        sl_pct = 0.0
                    
                    # Hit durumunu kontrol et (sl_hits key'i '2' olarak gelir)
                    is_hit = False
                    if sl_hits:
                        # '2' veya 2.0 olarak gelebilir
                        for k, v in sl_hits.items():
                            try:
                                if abs(float(k) - 2.0) < 1e-6:
                                    if v: is_hit = True
                            except:
                                if str(k) == '2':
                                    if v: is_hit = True
                    
                    hit_emoji = "❌" if is_hit else "⏳"
                    risk_pct = abs(sl_pct)
                    sl_levels.append(f"⛔️ SL {fmt_price(sl_price)} (Risk: {risk_pct:.1f}%) {hit_emoji}")

            if sl_levels:
                lines.extend(sl_levels)
            else:
                lines.append("   -")

            # TP/SL hit timeline (sadece hit'leri göster, signal log kaldırıldı)
            timeline: List[tuple[int, str]] = []

            # TP/SL hit'leri ekle
            if tp_hit_times:
                for level, ts in tp_hit_times.items():
                    if not ts:
                        continue
                    try:
                        timeline.append((int(ts), f"TP{level}🎯"))
                    except Exception:
                        continue

            if sl_hit_times:
                # Ranging stratejisinde tek SL var, onu "STOP" olarak göster
                if is_ranging_strategy:
                    sl_labels = {'1': 'STOP', '1.5': 'STOP', '2': 'STOP', 'stop': 'STOP'}
                else:
                    sl_labels = {'1': 'SL1', '1.5': 'SL1.5', '2': 'SL2'}
                
                for key, ts in sl_hit_times.items():
                    if not ts:
                        continue
                    label = sl_labels.get(str(key), f"SL{key}")
                    try:
                        timeline.append((int(ts), f"{label}🛡️"))
                    except Exception:
                        continue

            # Tüm hit entries'i timestamp'e göre sırala
            timeline.sort(key=lambda item: item[0])

            # Sinyal günlüğü bölümü (sadece hit varsa göster)
            if timeline:
                lines.append("")
                lines.append("📝 *Sinyal Günlüğü:*")
                for ts, desc in timeline:
                    lines.append(f"{self.format_timestamp_with_seconds(ts)} - {desc}")

            # Teknik detaylar (footer) - başlık kaldırıldı
            lines.append("")
            strategy_name = "Mean Reversion" if is_ranging_strategy else "Trend Following"
            
            # Confidence Cap: Maksimum %99 göster
            confidence_pct_capped = min(confidence_pct_raw, 99.0)
            
            # Güven değerini tam değerle göster (1 ondalık basamak - Finans Uzmanı Önerisi)
            confidence_display = f"{confidence_pct_capped:.1f}%"
            
            # Code block içine aldığımız değişkenleri escape ETMEYELİM
            # Code block içinde backslash literal olarak görünüyor, çirkin duruyor
            lines.append(f"📈 Strateji: `{strategy_name}`")
            lines.append(f"⚡ Güven: `{confidence_display}`")
            
            # 4H Teyit: Sadece ana yönle ÇELİŞİYORSA veya N/A değilse göster.
            # Eğer ana yön LONG ve 4H de Yükseliş (LONG) ise gösterme (redundant).
            show_forecast = False
            if forecast_text != 'N/A':
                direction_forecast = self.DIRECTION_FORECAST.get(direction)
                # Eğer tahmin ana yönle aynıysa gösterme
                if forecast_text != direction_forecast:
                    show_forecast = True
            
            if show_forecast:
                # Code block içine aldığımız için escape etmiyoruz
                # Alt çizgi hatası: 4h_teyit -> 4H Teyit (boşluklu)
                lines.append(f"4H Teyit: `{forecast_text}`")

            # Mesajı birleştir
            message = '\n'.join(lines)
            
            # MarkdownV2 için escape et
            # parse_mode='MarkdownV2' kullanıldığı için bold/italic formatlarını KORUYORUZ
            # Sadece code block dışındaki özel karakterleri escape et
            try:
                # Code block'ları koruyarak escape et
                # Bold (*text*) ve italic (_text_) formatlarını KORUYORUZ
                message = self.escape_markdown_v2_smart(message, preserve_code_blocks=True)
            except Exception as e:
                self.logger.warning(f"Markdown escape hatası, mesaj olduğu gibi gönderilecek: {str(e)}")
                # Hata durumunda sadece kritik karakterleri escape et (bold/italic'i koru)
                # Bold/italic formatlarını escape ETME
                # Sadece gerçekten gerekli karakterleri escape et
                message = message.replace('[', '\\[').replace(']', '\\]').replace('~', '\\~').replace('|', '\\|')
            
            return message
            
        except Exception as e:
            self.logger.error(f"Signal alert formatlama hatası: {str(e)}", exc_info=True)
            return f"❌ {symbol} sinyal formatlanamadı"
    
    def create_signal_keyboard(self, signal_id: str) -> InlineKeyboardMarkup:
        """
        Sinyal mesajı için inline keyboard oluşturur.
        
        Args:
            signal_id: Sinyal ID
            
        Returns:
            InlineKeyboardMarkup instance
        """
        button = InlineKeyboardButton(
            text="🔄 Güncelle",
            callback_data=f"update_signal:{signal_id}"
        )
        keyboard = [[button]]
        return InlineKeyboardMarkup(keyboard)

