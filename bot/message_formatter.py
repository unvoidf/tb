"""
MessageFormatter: Telegram mesaj formatlama sınıfı.
Analiz sonuçlarını Türkçe emoji'li mesajlara çevirir.

Not: Bu sınıf SignalFormatter ve TrackerFormatter'ı inherit eder.
BaseFormatter ise her iki formatter tarafından inherit edilir.
"""
import time
from typing import Dict, List, Any
from bot.formatters.signal_formatter import SignalFormatter
from bot.formatters.tracker_formatter import TrackerFormatter
from utils.logger import LoggerManager


class MessageFormatter(SignalFormatter, TrackerFormatter):
    """Telegram mesajlarını formatlar."""
    
    def __init__(self):
        super().__init__()
        self.logger = LoggerManager().get_logger('MessageFormatter')
    
    def format_trend_summary(
        self, top_signals: List[Dict[str, Any]]
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
        self, top_signals: List[Dict[str, Any]], market_data: Any
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
                    current_timestamp = int(time.time())
                    price_text = self.format_price_with_timestamp(current_price, current_timestamp)
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
                price_text = self.format_price_with_timestamp(current, timestamp)
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
    
    def _format_position_info(self, position: Dict[str, Any]) -> List[str]:
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
        self, tf_signals: Dict[str, Dict[str, Any]]
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
