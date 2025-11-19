"""
TrackerFormatter: Pozisyon takip ve tahmin mesajları için formatlama.
Kar/zarar takibi, fiyat tahminleri ve pozisyon durumu mesajları.
"""
import os
from typing import Dict, List, Optional
from datetime import datetime, timezone
from bot.formatters.base_formatter import BaseFormatter


class TrackerFormatter(BaseFormatter):
    """Pozisyon takip ve tahmin mesajlarını formatlar."""
    
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
            current_price_text = self.format_price_with_timestamp(current_price, current_timestamp)
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
            summary_line: Özet bilgi satırı
            tf_breakdown: Timeframe bazlı detay listesi
        
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
        ]
        
        # Opsiyonel özet
        if summary_line:
            lines.append(summary_line)
        if tf_breakdown:
            lines.append("(" + " • ".join(tf_breakdown) + ")")
        if summary_line or tf_breakdown:
            lines.append("")
        
        lines.append("📅 Tahmini Fiyatlar:")
        
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

