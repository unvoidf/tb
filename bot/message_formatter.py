"""
MessageFormatter: Telegram mesaj formatlama sınıfı.
Analiz sonuçlarını Türkçe emoji'li mesajlara çevirir.
"""
from typing import Dict, List, Optional
from datetime import datetime, timezone
import os
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils.logger import LoggerManager


class MessageFormatter:
    """Telegram mesajlarını formatlar."""
    
    def __init__(self):
        self.logger = LoggerManager().get_logger('MessageFormatter')
    
    DIRECTION_EMOJI = {
        'LONG': '📈',
        'SHORT': '📉',
        'NEUTRAL': '➡️'
    }
    
    DIRECTION_TR = {
        'LONG': 'LONG (Alış)',
        'SHORT': 'SHORT (Satış)',
        'NEUTRAL': 'NEUTRAL (Nötr)'
    }

    DIRECTION_TITLE = {
        'LONG': 'LONG',
        'SHORT': 'SHORT',
        'NEUTRAL': 'NEUTRAL'
    }

    DIRECTION_FORECAST = {
        'LONG': 'Yükseliş',
        'SHORT': 'Düşüş',
        'NEUTRAL': 'Nötr'
    }
    
    def _format_timestamp(self, timestamp: int) -> str:
        """
        Unix timestamp'i Türkiye saatine (UTC+3) formatlar.
        TZ environment variable varsa onu kullanır, yoksa varsayılan olarak Europe/Istanbul kullanır.
        
        Args:
            timestamp: Unix timestamp (saniye, UTC)
            
        Returns:
            Formatlanmış tarih/saat string (Türkiye saati - UTC+3)
        """
        try:
            # Unix timestamp'i UTC datetime'a çevir
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            
            # TZ environment variable kontrolü (esneklik için)
            tz_name = os.getenv('TZ')
            if not tz_name:
                # Varsayılan timezone: Türkiye saati (UTC+3)
                tz_name = 'Europe/Istanbul'
            
            try:
                from zoneinfo import ZoneInfo
                local_dt = dt.astimezone(ZoneInfo(tz_name))
            except ImportError:
                # zoneinfo modülü yoksa (Python < 3.9) UTC kullan
                local_dt = dt
            except Exception:
                # ZoneInfo hata verirse UTC kullan
                local_dt = dt
            
            formatted = local_dt.strftime('%d/%m/%Y %H:%M:%S')
            try:
                self.logger.debug(f"_format_timestamp: ts={timestamp} -> {formatted} (timezone: {tz_name})")
            except Exception:
                pass
            return formatted
        except Exception as e:
            # Son çare: basit datetime formatı (sistem saatine göre)
            try:
                return datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y %H:%M:%S')
            except Exception:
                return "Tarih alınamadı"
    
    def _format_timestamp_with_seconds(self, timestamp: Optional[int]) -> str:
        """Opsiyonel timestamp'i formatlar."""
        if timestamp is None:
            return "-"
        return self._format_timestamp(timestamp)
    
    def _format_time_elapsed(self, start_timestamp: Optional[int], end_timestamp: Optional[int]) -> str:
        """
        İki timestamp arasındaki geçen süreyi human readable formatında döndürür.
        
        Args:
            start_timestamp: Başlangıç timestamp (saniye)
            end_timestamp: Bitiş timestamp (saniye, None ise şu anki zaman)
            
        Returns:
            Human readable zaman farkı (örn: "2 saat 11 dakika", "1 gün 3 saat", "45 dakika")
        """
        try:
            if start_timestamp is None:
                return "-"
            
            if end_timestamp is None:
                end_timestamp = int(time.time())
            
            elapsed_seconds = end_timestamp - start_timestamp
            
            if elapsed_seconds < 0:
                return "-"
            
            # Gün, saat, dakika hesapla
            days = elapsed_seconds // 86400
            hours = (elapsed_seconds % 86400) // 3600
            minutes = (elapsed_seconds % 3600) // 60
            
            # Formatla
            parts = []
            if days > 0:
                parts.append(f"{days} gün" if days == 1 else f"{days} gün")
            if hours > 0:
                parts.append(f"{hours} saat" if hours == 1 else f"{hours} saat")
            if minutes > 0:
                parts.append(f"{minutes} dakika" if minutes == 1 else f"{minutes} dakika")
            
            # Eğer hiçbir şey yoksa (çok kısa süre)
            if not parts:
                if elapsed_seconds > 0:
                    return "1 dakikadan az"
                return "0 dakika"
            
            return " ".join(parts)
            
        except Exception:
            return "-"

    def _format_price_with_timestamp(self, price: float, timestamp: Optional[int] = None) -> str:
        """
        Fiyatı tarih/saat bilgisi ile formatlar.
        
        Args:
            price: Fiyat
            timestamp: Unix timestamp (opsiyonel)
            
        Returns:
            Formatlanmış fiyat string
        """
        if price is None:
            return "💰 Fiyat alınamadı"
        
        price_str = f"💰 ${price:,.4f}"
        
        if timestamp:
            time_str = self._format_timestamp(timestamp)
            price_str += f" ({time_str})"
        
        try:
            self.logger.debug(f"_format_price_with_timestamp: price={price}, ts={timestamp} -> {price_str}")
        except Exception:
            pass
        return price_str
    
    def format_trend_summary(
        self, top_signals: List[Dict]
    ) -> str:
        """
        Trend özeti mesajı formatlar.
        
        Args:
            top_signals: Top sinyal listesi
            
        Returns:
            Formatlanmış mesaj
        """
        lines = ["🔍 PIYASA TREND ANALIZI\n"]
        
        for i, signal_data in enumerate(top_signals, 1):
            symbol = signal_data['symbol']
            signal = signal_data['signal']
            
            direction = signal['direction']
            confidence = signal['confidence'] * 100
            
            emoji = self.DIRECTION_EMOJI[direction]
            direction_tr = self.DIRECTION_TR[direction]
            
            lines.append(
                f"{i}. {symbol.replace('/USDT', '')}\n"
                f"   {emoji} {direction_tr}\n"
                f"   🎯 Güvenilirlik: %{confidence:.0f}\n"
            )
        
        msg = '\n'.join(lines)
        try:
            self.logger.debug(f"format_trend_summary: len={len(msg)}")
        except Exception:
            pass
        return msg
    
    def format_trend_summary_with_prices(
        self, top_signals: List[Dict], market_data
    ) -> str:
        """
        Trend özeti mesajı formatlar (güncel fiyatlarla).
        
        Args:
            top_signals: Top sinyal listesi
            market_data: Market data manager
            
        Returns:
            Formatlanmış mesaj
        """
        lines = ["🔍 PIYASA TREND ANALIZI\n"]
        
        for i, signal_data in enumerate(top_signals, 1):
            symbol = signal_data['symbol']
            signal = signal_data['signal']
            
            direction = signal['direction']
            confidence = signal['confidence'] * 100
            
            emoji = self.DIRECTION_EMOJI[direction]
            direction_tr = self.DIRECTION_TR[direction]
            
            # Güncel fiyatı al (tarih/saat ile)
            try:
                current_price = market_data.get_latest_price(symbol)
                if current_price:
                    import time
                    current_timestamp = int(time.time())
                    price_text = self._format_price_with_timestamp(current_price, current_timestamp)
                else:
                    price_text = "💰 Fiyat alınamadı"
            except Exception:
                price_text = "💰 Fiyat alınamadı"
            
            lines.append(
                f"{i}. {symbol.replace('/USDT', '')}\n"
                f"   {emoji} {direction_tr}\n"
                f"   {price_text}\n"
                f"   🎯 Güvenilirlik: %{confidence:.0f}\n"
            )
        
        msg = '\n'.join(lines)
        try:
            self.logger.debug(f"format_trend_summary_with_prices: len={len(msg)}")
        except Exception:
            pass
        return msg
    
    def format_detailed_analysis(
        self, symbol: str, signal: Dict, 
        position: Dict, risk: Dict
    ) -> str:
        """
        Detaylı analiz mesajı formatlar.
        
        Args:
            symbol: Trading pair
            signal: Sinyal bilgisi
            position: Pozisyon bilgisi
            risk: Risk bilgisi
            
        Returns:
            Formatlanmış detaylı mesaj
        """
        direction = signal['direction']
        emoji = self.DIRECTION_EMOJI[direction]
        direction_tr = self.DIRECTION_TR[direction]
        confidence = signal['confidence'] * 100
        
        lines = [
            f"📊 {symbol.replace('/USDT', '')} DETAYLI ANALİZ\n",
            f"{emoji} Sinyal: {direction_tr}",
            f"🎯 Güvenilirlik: %{confidence:.0f}"
        ]
        
        # Güncel fiyat (her zaman göster)
        if position and position.get('current_price'):
            current = position['current_price']
            # Eğer timestamp bilgisi varsa ekle
            timestamp = position.get('price_timestamp')
            if timestamp:
                price_text = self._format_price_with_timestamp(current, timestamp)
            else:
                price_text = f"📍 Güncel Fiyat: ${current:.4f}"
            lines.append(f"{price_text}\n")
        elif signal.get('timeframe_signals'):
            # NEUTRAL ise ve position yoksa, sadece fiyat bilgisi için
            # ilk timeframe'den fiyat çekmeye çalış (zaten çekilmiş olmalı)
            lines.append("")
        else:
            lines.append("")
        
        # Entry status uyarısı
        if position and position.get('entry_status'):
            warning = self._format_entry_warning(position)
            if warning:
                lines.append(warning)
        
        # Pozisyon bilgileri
        if position:
            lines.extend(self._format_position_info(position))
        
        # Risk yönetimi
        if risk:
            lines.append("\n💼 Risk Yönetimi:")
            lines.append(self._format_risk_info(risk))
        
        # Teknik göstergeler
        if 'timeframe_signals' in signal:
            lines.append("\n📈 Timeframe Analizi:")
            lines.extend(
                self._format_timeframe_signals(
                    signal['timeframe_signals']
                )
            )
        
        msg = '\n'.join(lines)
        try:
            self.logger.debug(f"format_detailed_analysis: len={len(msg)}")
        except Exception:
            pass
        return msg
    
    def _format_entry_warning(self, position: Dict) -> str:
        """Entry status'a göre uyarı mesajı oluşturur."""
        status = position.get('entry_status')
        current = position.get('current_price')
        entry = position.get('entry')
        fib_ideal = position.get('fib_ideal_entry')
        
        if status == 'PRICE_MOVED' and fib_ideal:
            diff_percent = abs((current - fib_ideal) / fib_ideal) * 100
            return (
                f"\n⚠️ FİYAT KAÇMIŞ!\n"
                f"İdeal Giriş: ${fib_ideal:.4f} (%{diff_percent:.1f} uzakta)\n"
                f"Not: Pozisyon seviyeler güncel fiyattan hesaplandı.\n"
            )
        elif status == 'WAIT_FOR_PULLBACK' and fib_ideal:
            return (
                f"\n💡 DÜZELTMEYİ BEKLEYİN\n"
                f"İdeal Giriş: ${fib_ideal:.4f}\n"
                f"Strateji: Fiyatın bu seviyeye gelmesini bekleyin.\n"
            )
        elif status == 'PULLBACK_EXPECTED' and fib_ideal:
            return (
                f"\n📍 İDEAL GİRİŞ SEVİYESİ\n"
                f"Hedef: ${fib_ideal:.4f}\n"
            )
        
        return ""
    
    def _format_position_info(self, position: Dict) -> List[str]:
        """Pozisyon bilgilerini formatlar."""
        # Sadece current_price varsa bu NEUTRAL dummy position
        if 'entry' not in position:
            return []
        
        lines = [
            "\n💡 BU FİYATTAN POZİSYON ALMAK İSTENİRSE:"
        ]
        
        # Entry status'a göre etiket belirle
        entry_status = position.get('entry_status')
        entry = position['entry']
        
        # Eğer düzeltme bekleniyorsa "İdeal Giriş", değilse "Giriş"
        if entry_status in ['WAIT_FOR_PULLBACK', 'PULLBACK_EXPECTED']:
            lines.append(f"💰 İdeal Giriş: ${entry:.4f}")
        else:
            # PRICE_MOVED veya None (optimal)
            lines.append(f"💰 Giriş: ${entry:.4f}")
        
        lines.append(f"🛡️ Stop-Loss: ${position['stop_loss']:.4f}")
        lines.append(f"📍 Risk: %{position['risk_percent']:.2f}\n")
        
        lines.append("🎯 Take-Profit Seviyeleri:")
        for i, target in enumerate(position['targets'], 1):
            lines.append(
                f"   TP{i}: ${target['price']:.4f} "
                f"(R:R {target['risk_reward']:.2f})"
            )
        
        return lines
    
    def _format_risk_info(self, risk: Dict) -> str:
        """Risk bilgilerini formatlar."""
        risk_tr = {
            'low': 'Düşük',
            'medium': 'Orta',
            'high': 'Yüksek'
        }
        
        return (
            f"   Risk Seviyesi: {risk_tr[risk['risk_level']]}\n"
            f"   Pozisyon Büyüklüğü: %{risk['position_size_percent']:.1f}\n"
            f"   ⚡ Leverage: {risk['leverage']}x"
        )
    
    def _format_timeframe_signals(
        self, tf_signals: Dict[str, Dict]
    ) -> List[str]:
        """Timeframe sinyallerini formatlar."""
        lines = []
        
        for tf in ['1h', '4h', '1d']:
            if tf in tf_signals:
                signal = tf_signals[tf]
                direction = signal['direction']
                emoji = self.DIRECTION_EMOJI[direction]
                confidence = signal['confidence'] * 100
                
                lines.append(
                    f"   {tf}: {emoji} %{confidence:.0f}"
                )
        
        return lines
    
    def format_error_message(self, error_type: str) -> str:
        """
        Hata mesajı formatlar.
        
        Args:
            error_type: Hata tipi
            
        Returns:
            Formatlanmış hata mesajı
        """
        messages = {
            'no_data': (
                "❌ Veri alınamadı\n"
                "Lütfen daha sonra tekrar deneyin."
            ),
            'invalid_symbol': (
                "❌ Geçersiz sembol\n"
                "Lütfen geçerli bir coin sembolü girin."
            ),
            'analysis_failed': (
                "❌ Analiz başarısız\n"
                "Teknik bir hata oluştu."
            )
        }
        
        msg = messages.get(
            error_type,
            "❌ Bir hata oluştu."
        )
        try:
            self.logger.debug(f"format_error_message: type={error_type}")
        except Exception:
            pass
        return msg
    
    def format_settings_message(self, notifications_enabled: bool) -> str:
        """
        Ayarlar mesajı formatlar.
        
        Args:
            notifications_enabled: Bildirim durumu
            
        Returns:
            Formatlanmış ayarlar mesajı
        """
        status = "Açık ✅" if notifications_enabled else "Kapalı ❌"
        
        return (
            "⚙️ AYARLAR\n\n"
            f"🔔 Saatlik Bildirimler: {status}\n\n"
            "Bildirimleri değiştirmek için tekrar /settings yazın."
        )
    
    def format_profit_check(self, symbol: str, position: Dict,
                           current_price: float, pnl: Dict,
                           target_progress: List, risk_status: Dict) -> str:
        """
        Pozisyon kar/zarar takibi mesajı formatlar.
        
        Args:
            symbol: Trading pair
            position: Pozisyon bilgisi
            current_price: Güncel fiyat
            pnl: Kar/zarar bilgisi
            target_progress: Hedef ilerleme listesi
            risk_status: Risk durumu
            
        Returns:
            Formatlanmış profit check mesajı
        """
        direction = position['direction']
        direction_emoji = self.DIRECTION_EMOJI[direction]
        
        # Kar/zarar emoji ve renk
        if pnl['is_profit']:
            pnl_emoji = "✅"
            pnl_status = "Kar"
        else:
            pnl_emoji = "❌"
            pnl_status = "Zarar"
        
        # Fiyat değişimi
        price_change = (
            (current_price - position['entry']) / position['entry']
        ) * 100
        price_emoji = "📈" if price_change > 0 else "📉"
        
        # Güncel fiyat timestamp'i (eğer varsa)
        current_timestamp = position.get('current_price_timestamp')
        if current_timestamp:
            current_price_text = self._format_price_with_timestamp(current_price, current_timestamp)
        else:
            current_price_text = f"📍 Güncel: ${current_price:.4f} ({price_emoji}{price_change:+.2f}%)"
        
        lines = [
            f"📊 POZİSYON TAKİBİ - {symbol.replace('/USDT', '')}\n",
            f"{direction_emoji} Yön: {self.DIRECTION_TR[direction]}",
            f"💰 Giriş: ${position['entry']:.4f}",
            f"{current_price_text}\n"
        ]
        
        # Kar/Zarar
        lines.append(f"💵 Kar/Zarar Durumu:")
        lines.append(
            f"{pnl_emoji} {pnl_status}: "
            f"${pnl['pnl_amount']:.2f} ({pnl['pnl_percent']:+.2f}%)"
        )
        
        if position['leverage'] > 1:
            lines.append(f"⚡ Leverage: {position['leverage']}x")
            lines.append(
                f"💰 Gerçek Kar/Zarar: "
                f"{pnl['real_pnl_percent']:+.2f}%\n"
            )
        else:
            lines.append("")
        
        # Hedef ilerleme
        lines.append("🎯 Hedeflere Uzaklık:")
        for i, progress in enumerate(target_progress, 1):
            target_price = progress['target_price']
            prog_percent = progress['progress']
            reached = progress['reached']
            
            if reached:
                status = "✅ Ulaşıldı!"
                prog_bar = "█" * 10
            else:
                status = f"%{prog_percent:.0f}"
                filled = int(prog_percent / 10)
                prog_bar = "█" * filled + "░" * (10 - filled)
            
            lines.append(
                f"   TP{i} (${target_price:.4f}): "
                f"{prog_bar} {status}"
            )
        
        lines.append("")
        
        # Stop-loss durumu
        sl_emoji = "🛡️"
        if risk_status['is_hit']:
            sl_emoji = "💥"
            lines.append(f"{sl_emoji} Stop-Loss Tetiklendi!")
        else:
            lines.append(
                f"{sl_emoji} Stop-Loss: "
                f"${risk_status['stop_loss']:.4f} "
                f"({risk_status['percent']:+.2f}%)"
            )
            
            risk_level = risk_status['risk_level']
            if risk_level == 'CRITICAL':
                lines.append("⚠️⚠️ SL'ye ÇOK YAKINSINIZ!")
            elif risk_level == 'HIGH':
                lines.append("⚠️ SL'ye yaklaştınız!")
        
        msg = '\n'.join(lines)
        try:
            self.logger.debug(f"format_profit_check: len={len(msg)}")
        except Exception:
            pass
        return msg
    
    def format_prediction(
        self, symbol: str, probabilities: Dict[str, Dict[str, float]]
    ) -> str:
        """
        Tahmin mesajını formatlar.
        
        Args:
            symbol: Coin sembolü (örn: BTC/USDT)
            probabilities: Timeframe bazlı ihtimaller
                          {'1h': {'up': 65, 'down': 35}, ...}
        
        Returns:
            Formatlanmış mesaj
        """
        clean_symbol = symbol.replace('/USDT', '')
        lines = [f"🔮 {clean_symbol} TAHMİN\n"]
        
        # Yükseliş ihtimalleri
        lines.append("📈 Yükseliş İhtimali:")
        for tf in ['1h', '4h', '24h']:
            if tf in probabilities:
                up_prob = probabilities[tf]['up']
                lines.append(f"   {tf}: %{up_prob:.0f}")
        
        lines.append("")  # Boş satır
        
        # Düşüş ihtimalleri
        lines.append("📉 Düşüş İhtimali:")
        for tf in ['1h', '4h', '24h']:
            if tf in probabilities:
                down_prob = probabilities[tf]['down']
                lines.append(f"   {tf}: %{down_prob:.0f}")
        
        msg = '\n'.join(lines)
        try:
            self.logger.debug(f"format_prediction: len={len(msg)}")
        except Exception:
            pass
        return msg

    def format_price_forecast(
        self,
        symbol: str,
        generated_at: datetime,
        current_price: float,
        forecasts: Dict[str, float],
        summary_line: str = "",
        tf_breakdown: List[str] | None = None
    ) -> str:
        """
        Fiyat tahmin mesajını formatlar.
        
        Args:
            symbol: Coin (örn: BTC/USDT)
            generated_at: Tahmin oluşturulma zamanı
            current_price: Güncel fiyat
            forecasts: {'1h': price, '4h': price, '24h': price}
        
        Returns:
            Formatlanmış mesaj
        """
        clean = symbol.replace('/USDT', '')
        # Yerel saat formatı: Önce TZ env, yoksa sistem saat dilimi
        tz_name = os.getenv('TZ')
        try:
            base_utc = generated_at.replace(tzinfo=timezone.utc)
            if tz_name:
                from zoneinfo import ZoneInfo
                local_dt = base_utc.astimezone(ZoneInfo(tz_name))
            else:
                # Container'ın /etc/localtime ayarına göre yerel saat
                local_dt = base_utc.astimezone()
            ts_str = local_dt.strftime('%Y-%m-%d %H:%M')
        except Exception:
            # Son çare: UTC göster
            ts_str = generated_at.strftime('%Y-%m-%d %H:%M UTC')
        
        def fmt(price: float) -> str:
            if price is None:
                return "-"
            # 1$ ve üzeri: 2 ondalık, binlik ayraç; 1$ altı: 6 ondalık
            if abs(price) >= 1:
                return f"${price:,.2f}"
            return f"${price:,.6f}"
        lines = [
            f"🔮 {clean} FİYAT TAHMİNİ",
            f"🕒 {ts_str} itibarıyla",
            f"📍 Güncel Fiyat: {fmt(current_price)}",
            "",
            # Opsiyonel özet
        ]
        if summary_line:
            lines.append(summary_line)
        if tf_breakdown:
            lines.append("(" + " • ".join(tf_breakdown) + ")")
        if summary_line or tf_breakdown:
            lines.append("")
        lines += [
            "📅 Tahmini Fiyatlar:",
        ]
        # Sıralı yazdırma
        mapping = [('1h', '1 Saat Sonra'), ('4h', '4 Saat Sonra'), ('24h', '24 Saat Sonra')]
        for key, label in mapping:
            if key in forecasts and forecasts[key] is not None:
                val = forecasts[key]
                if isinstance(val, dict) and 'low' in val and 'high' in val:
                    lines.append(f"- {label}: {fmt(val['low'])} – {fmt(val['high'])}")
                else:
                    lines.append(f"- {label}: {fmt(val)}")
        msg = '\n'.join(lines)
        try:
            self.logger.debug(f"format_price_forecast: len={len(msg)}")
        except Exception:
            pass
        return msg
    
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
            
        Returns:
            Formatlanmış signal alert mesajı
        """
        try:
            # Yardımcılar
            direction = signal_data.get('direction', 'NEUTRAL')
            confidence = signal_data.get('confidence', 0.0)
            confidence_pct = int(round(confidence * 100))
            direction_emoji = self.DIRECTION_EMOJI.get(direction, '➡️')
            direction_text = self.DIRECTION_TR.get(direction, direction)

            def fmt_price(price: float) -> str:
                if price is None:
                    return "-"
                if abs(price) >= 1:
                    return f"${price:,.2f}"
                return f"${price:,.6f}"

            def fmt_money_2(price: float) -> str:
                try:
                    return f"${float(price):,.2f}"
                except Exception:
                    return "$-"

            # Fark yüzdesi (anlık - sinyal)
            try:
                diff_pct = ((now_price - signal_price) / signal_price) * 100 if signal_price else 0.0
            except Exception:
                diff_pct = 0.0

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
            signal_time_str = self._format_timestamp_with_seconds(created_at) if created_at else self._format_timestamp_with_seconds(int(time.time()))
            current_price_time = current_price_timestamp if current_price_timestamp is not None else int(time.time())
            current_time_str = self._format_timestamp_with_seconds(current_price_time)

            # Başlık ve ana bilgiler
            # 4H Teyit bilgisini başlığa ekle
            # Güven yüzdesi değişikliği gösterimi (eğer significant ise)
            confidence_change_text = ""
            if confidence_change is not None and abs(confidence_change) >= 0.01:
                # %1'den büyük değişiklikler göster
                confidence_change_pct = confidence_change * 100
                if confidence_change > 0:
                    confidence_change_text = f" (🟢 +{confidence_change_pct:.1f}%)"
                elif confidence_change < 0:
                    confidence_change_text = f" (🔴 {confidence_change_pct:.1f}%)"
            
            header_line = f"🔮 {direction_title} Sinyali: {symbol} {direction_emoji} (Güven: {confidence_pct}%{confidence_change_text})"
            if is_ranging_strategy:
                header_line += " [Mean Reversion]"
            if forecast_text != 'N/A':
                header_line += f" (4H Teyit: {forecast_text})"
            lines = [header_line]
            
            # Sinyal ID ekle (varsa)
            if signal_id:
                lines.append(f"🆔 Sinyal ID: {signal_id}")
                lines.append("")  # Boş satır
            
            # Fark işareti
            diff_sign = ''
            if now_price < signal_price:
                diff_sign = '-'
            elif now_price > signal_price:
                diff_sign = '+'
            diff_amount = abs(now_price - signal_price) if signal_price and now_price else 0.0
            
            # Emoji seçimi (direction ve farka göre)
            diff_emoji = '🔁'  # Default
            if abs(diff_pct) > 0.01:  # Fark sıfır değilse (küçük yuvarlama hatalarını göz ardı et)
                if direction == 'LONG':
                    if diff_pct > 0:
                        diff_emoji = '😊'  # LONG + pozitif = iyi
                    else:
                        diff_emoji = '😠'  # LONG + negatif = kötü
                elif direction == 'SHORT':
                    if diff_pct < 0:
                        diff_emoji = '😊'  # SHORT + negatif = iyi (fiyat düşmüş)
                    else:
                        diff_emoji = '😠'  # SHORT + pozitif = kötü (fiyat yükselmiş)
            
            # Geçen süre hesapla
            signal_created_at = created_at if created_at else int(time.time())
            elapsed_time_str = self._format_time_elapsed(signal_created_at, current_price_time)
            
            # Fark satırını oluştur
            diff_line = f"{diff_emoji} Fark: {diff_pct:+.2f}% | {diff_sign}{fmt_money_2(diff_amount)}"
            if elapsed_time_str != "-":
                diff_line += f" | ({elapsed_time_str})"
            
            lines.extend([
                f"⏰ Sinyal Geliş Zamanı: {signal_time_str}",
                f"📍 Sinyal Fiyatı: {fmt_price(signal_price)}",
                "",
                f"📍 Güncel Fiyat: {fmt_price(now_price)} ({current_time_str})",
                diff_line,
                "",
            ])

            atr = entry_levels.get('atr')
            timeframe = entry_levels.get('timeframe') or ''

            # TP seviyeleri (R:R 1:1, 1:2, 1:3) - ÖNCE
            lines.append("🎯 TP Seviyeleri:")
            if is_ranging_strategy:
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
                    hit_status = bool(tp_hits and tp_hits.get(idx, False))
                    hit_emoji = "✅" if hit_status else "⏳"
                    label = target_info.get('label', f"TP{idx}")
                    lines.append(f"   {label}: {fmt_price(price)} ({tp_pct:+.2f}%) {hit_emoji}")
            else:
                # Risk mesafesi: ATR 1.0 (veya %1 fallback)
                if atr:
                    risk_dist = atr
                else:
                    risk_dist = signal_price * 0.01
                tps = []
                for rr in [1, 2, 3]:
                    offset = risk_dist * rr
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
                        # Hit durumunu kontrol et
                        hit_status = bool(tp_hits and tp_hits.get(rr, False))
                        hit_emoji = "✅" if hit_status else "⏳"
                        tps.append(f"🎯 {fmt_price(tp_price)} ({tp_pct:+.2f}%) (RR {float(rr):.1f}) {hit_emoji}")
                lines.extend(tps)
            lines.append("")
            
            # SL seviyeleri
            lines.append("🛡️ Stop-Loss Seviyeleri:")
            sl_levels = []
            multipliers = [1.0, 1.5, 2.0]
            sl_keys_order = ['1', '1.5', '2']
            sl_hit_status = {key: False for key in sl_keys_order}
            
            def _normalize_sl_key(raw_key: str) -> Optional[str]:
                try:
                    value = float(raw_key)
                    if abs(value - 1.0) < 1e-6:
                        return '1'
                    if abs(value - 1.5) < 1e-6:
                        return '1.5'
                    if abs(value - 2.0) < 1e-6:
                        return '2'
                except Exception:
                    pass
                if raw_key in sl_keys_order:
                    return raw_key
                return None
            
            if is_ranging_strategy:
                sl_levels = []
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
                    # Ranging stratejisinde SL sl2_price olarak kaydediliyor, bu yüzden '2' kontrol et
                    # SL hit olduğunda ❌ (zarar demek, kötü bir şey)
                    hit_emoji = "❌" if sl_hits and (sl_hits.get('2') or sl_hits.get('stop')) else "⏳"
                    label = stop_info.get('label', 'Stop-Loss')
                    sl_levels.append(f"   {label}: {fmt_price(stop_price)} ({sl_pct:+.2f}%) {hit_emoji}")
                    if sl_hits:
                        for key, value in sl_hits.items():
                            normalized_key = _normalize_sl_key(str(key))
                            if normalized_key:
                                sl_hit_status[normalized_key] = bool(value)
                lines.extend(sl_levels)
                if not sl_levels:
                    lines.append("   -")
                lines.append("")
                extra_sl_lines = []
            else:
                sl_levels = []
                if sl_hits:
                    for key, value in sl_hits.items():
                        normalized_key = _normalize_sl_key(str(key))
                        if normalized_key:
                            sl_hit_status[normalized_key] = bool(value)
                for multiplier, key in zip(multipliers, sl_keys_order):
                    if atr:
                        offset = atr * multiplier
                        if direction == 'LONG':
                            sl_price = signal_price - offset
                        elif direction == 'SHORT':
                            sl_price = signal_price + offset
                        else:
                            sl_price = None
                    else:
                        pct = float(multiplier)
                        if direction == 'LONG':
                            sl_price = signal_price * (1 - pct/100)
                        elif direction == 'SHORT':
                            sl_price = signal_price * (1 + pct/100)
                        else:
                            sl_price = None
                    
                    if sl_price:
                        try:
                            sl_pct = ((sl_price - signal_price) / signal_price) * 100 if signal_price else 0.0
                        except Exception:
                            sl_pct = 0.0
                        # SL hit olduğunda ❌ (zarar demek, kötü bir şey)
                        hit_emoji = "❌" if sl_hit_status.get(key, False) else "⏳"
                        sl_levels.append(
                            f"   SL {key}x ATR: {fmt_price(sl_price)} ({sl_pct:+.2f}%) {hit_emoji}"
                        )
                
                lines.extend(sl_levels)
                if not sl_levels:
                    lines.append("   -")
                lines.append("")
                
                if sl_hits:
                    for key, value in sl_hits.items():
                        normalized_key = _normalize_sl_key(str(key))
                        if normalized_key:
                            sl_hit_status[normalized_key] = bool(value)
                
                if sl_hit_times:
                    for key, ts in sl_hit_times.items():
                        if ts:
                            normalized_key = _normalize_sl_key(str(key))
                            if normalized_key:
                                sl_hit_status[normalized_key] = True
                
                highest_hit_index = -1
                for idx, key in enumerate(sl_keys_order):
                    if sl_hit_status.get(key):
                        highest_hit_index = idx
                
                if highest_hit_index >= 0:
                    for idx in range(highest_hit_index + 1):
                        sl_hit_status[sl_keys_order[idx]] = True
                
                extra_sl_lines = []
                for m in multipliers:
                    if atr:
                        offset = atr * m
                        if direction == 'LONG':
                            sl_price = signal_price - offset
                        elif direction == 'SHORT':
                            sl_price = signal_price + offset
                        else:
                            sl_price = None
                        label = f"ATR {m:g} ({timeframe})"
                        if abs(m - 1.0) < 1e-6:
                            sl_key = '1'
                        elif abs(m - 1.5) < 1e-6:
                            sl_key = '1.5'
                        else:
                            sl_key = '2'
                    else:
                        pct = m if m != 1.5 else 1.5
                        pct = float(pct)
                        if direction == 'LONG':
                            sl_price = signal_price * (1 - pct/100)
                        elif direction == 'SHORT':
                            sl_price = signal_price * (1 + pct/100)
                        else:
                            sl_price = None
                        label = f"%{pct:g}"
                        if abs(m - 1.0) < 1e-6:
                            sl_key = '1'
                        elif abs(m - 1.5) < 1e-6:
                            sl_key = '1.5'
                        else:
                            sl_key = '2'
                    if sl_price:
                        try:
                            sl_pct = ((sl_price - signal_price) / signal_price) * 100 if signal_price else 0.0
                        except Exception:
                            sl_pct = 0.0
                        hit_status = sl_hit_status.get(sl_key, False)
                        hit_emoji = "❌" if hit_status else "⏳"
                        extra_sl_lines.append(f"🛡️ {label}: {fmt_price(sl_price)} ({sl_pct:+.2f}%) {hit_emoji}")
            
            if extra_sl_lines:
                lines.extend(extra_sl_lines)
                lines.append("")
            lines.append("")

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

            # Sinyal günlüğü bölümü (hit varsa listele, yoksa bilgi ver)
            lines.append("📝 Sinyal Günlüğü:")
            if timeline:
                for ts, desc in timeline:
                    lines.append(f"{self._format_timestamp_with_seconds(ts)} - {desc}")
            else:
                lines.append("Henüz kayıt yok")

            return '\n'.join(lines)
            
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
        keyboard = InlineKeyboardMarkup([[button]])
        return keyboard

