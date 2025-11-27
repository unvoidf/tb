"""
TrackerFormatter: Formatting for position tracking and prediction messages.
Profit/loss tracking, price predictions, and position status messages.
"""
import os
from typing import Dict, List, Optional
from datetime import datetime, timezone
from bot.formatters.base_formatter import BaseFormatter


class TrackerFormatter(BaseFormatter):
    """Formats position tracking and prediction messages."""
    
    def format_profit_check(self, symbol: str, position: Dict,
                           current_price: float, pnl: Dict,
                           target_progress: List, risk_status: Dict) -> str:
        """
        Formats position profit/loss tracking message.
        
        Args:
            symbol: Trading pair
            position: Position info
            current_price: Current price
            pnl: Profit/loss info
            target_progress: Target progress list
            risk_status: Risk status
            
        Returns:
            Formatted profit check message
        """
        direction = position['direction']
        direction_emoji = self.DIRECTION_EMOJI[direction]
        
        # Profit/loss emoji and color
        if pnl['is_profit']:
            pnl_emoji = "✅"
            pnl_status = "Profit"
        else:
            pnl_emoji = "❌"
            pnl_status = "Loss"
        
        # Price change
        price_change = (
            (current_price - position['entry']) / position['entry']
        ) * 100
        price_emoji = "📈" if price_change > 0 else "📉"
        
        # Current price timestamp (if available)
        current_timestamp = position.get('current_price_timestamp')
        if current_timestamp:
            current_price_text = self.format_price_with_timestamp(current_price, current_timestamp)
        else:
            current_price_text = f"📍 Current: ${current_price:.4f} ({price_emoji}{price_change:+.2f}%)"
        
        lines = [
            f"📊 POSITION TRACKING - {symbol.replace('/USDT', '')}\n",
            f"{direction_emoji} Direction: {self.DIRECTION_TR[direction]}",
            f"💰 Entry: ${position['entry']:.4f}",
            f"{current_price_text}\n"
        ]
        
        # Profit/Loss
        lines.append(f"💵 Profit/Loss Status:")
        lines.append(
            f"{pnl_emoji} {pnl_status}: "
            f"${pnl['pnl_amount']:.2f} ({pnl['pnl_percent']:+.2f}%)"
        )
        
        if position['leverage'] > 1:
            lines.append(f"⚡ Leverage: {position['leverage']}x")
            lines.append(
                f"💰 Real Profit/Loss: "
                f"{pnl['real_pnl_percent']:+.2f}%\n"
            )
        else:
            lines.append("")
        
        # Target progress
        lines.append("🎯 Distance to Targets:")
        for i, progress in enumerate(target_progress, 1):
            target_price = progress['target_price']
            prog_percent = progress['progress']
            reached = progress['reached']
            
            if reached:
                status = "✅ Reached!"
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
        
        # Stop-loss status
        sl_emoji = "🛡️"
        if risk_status['is_hit']:
            sl_emoji = "💥"
            lines.append(f"{sl_emoji} Stop-Loss Triggered!")
        else:
            lines.append(
                f"{sl_emoji} Stop-Loss: "
                f"${risk_status['stop_loss']:.4f} "
                f"({risk_status['percent']:+.2f}%)"
            )
            
            risk_level = risk_status['risk_level']
            if risk_level == 'CRITICAL':
                lines.append("⚠️⚠️ VERY CLOSE TO SL!")
            elif risk_level == 'HIGH':
                lines.append("⚠️ Close to SL!")
        
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
        Formats prediction message.
        
        Args:
            symbol: Coin symbol (e.g., BTC/USDT)
            probabilities: Timeframe based probabilities
                          {'1h': {'up': 65, 'down': 35}, ...}
        
        Returns:
            Formatted message
        """
        clean_symbol = symbol.replace('/USDT', '')
        lines = [f"🔮 {clean_symbol} PREDICTION\n"]
        
        # Bullish probabilities
        lines.append("📈 Bullish Probability:")
        for tf in ['1h', '4h', '24h']:
            if tf in probabilities:
                up_prob = probabilities[tf]['up']
                lines.append(f"   {tf}: %{up_prob:.0f}")
        
        lines.append("")  # Empty line
        
        # Bearish probabilities
        lines.append("📉 Bearish Probability:")
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
        Formats price forecast message.
        
        Args:
            symbol: Coin (e.g., BTC/USDT)
            generated_at: Forecast generation time
            current_price: Current price
            forecasts: {'1h': price, '4h': price, '24h': price}
            summary_line: Summary info line
            tf_breakdown: Timeframe based detail list
        
        Returns:
            Formatted message
        """
        clean = symbol.replace('/USDT', '')
        # Local time format: First TZ env, otherwise system timezone
        tz_name = os.getenv('TZ')
        try:
            base_utc = generated_at.replace(tzinfo=timezone.utc)
            if tz_name:
                from zoneinfo import ZoneInfo
                local_dt = base_utc.astimezone(ZoneInfo(tz_name))
            else:
                # Local time based on container's /etc/localtime setting
                local_dt = base_utc.astimezone()
            ts_str = local_dt.strftime('%Y-%m-%d %H:%M')
        except Exception:
            # Last resort: Show UTC
            ts_str = generated_at.strftime('%Y-%m-%d %H:%M UTC')
        
        def fmt(price: float) -> str:
            """Formats price with appropriate decimal places based on value."""
            if price is None:
                return "-"
            # 1$ and above: 2 decimals, thousand separator; below 1$: 6 decimals
            if abs(price) >= 1:
                return f"${price:,.2f}"
            return f"${price:,.6f}"
        
        lines = [
            f"🔮 {clean} PRICE FORECAST",
            f"🕒 As of {ts_str}",
            f"📍 Current Price: {fmt(current_price)}",
            "",
        ]
        
        # Optional summary
        if summary_line:
            lines.append(summary_line)
        if tf_breakdown:
            lines.append("(" + " • ".join(tf_breakdown) + ")")
        if summary_line or tf_breakdown:
            lines.append("")
        
        lines.append("📅 Estimated Prices:")
        
        # Sequential printing
        mapping = [('1h', 'After 1 Hour'), ('4h', 'After 4 Hours'), ('24h', 'After 24 Hours')]
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
