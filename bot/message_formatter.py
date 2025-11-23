"""
MessageFormatter: Telegram message formatting class.
Converts analysis results into Turkish emoji messages.

Note: This class inherits from SignalFormatter and TrackerFormatter.
BaseFormatter is inherited by both formatters.
"""
import time
from typing import Dict, List, Any
from bot.formatters.signal_formatter import SignalFormatter
from bot.formatters.tracker_formatter import TrackerFormatter
from utils.logger import LoggerManager


class MessageFormatter(SignalFormatter, TrackerFormatter):
    """Formats Telegram messages."""
    
    def __init__(self):
        super().__init__()
        self.logger = LoggerManager().get_logger('MessageFormatter')
    
    def format_trend_summary(
        self, top_signals: List[Dict[str, Any]]
    ) -> str:
        """
        Formats trend summary message.
        
        Args:
            top_signals: Top signal list
            
        Returns:
            Formatted message
        """
        lines = ["🔍 MARKET TREND ANALYSIS\n"]
        
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
                f"   🎯 Confidence: %{confidence:.0f}\n"
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
        Formats trend summary message (with current prices).
        
        Args:
            top_signals: Top signal list
            market_data: Market data manager
            
        Returns:
            Formatted message
        """
        lines = ["🔍 MARKET TREND ANALYSIS\n"]
        
        for i, signal_data in enumerate(top_signals, 1):
            symbol = signal_data['symbol']
            signal = signal_data['signal']
            
            direction = signal['direction']
            confidence = signal['confidence'] * 100
            
            emoji = self.DIRECTION_EMOJI[direction]
            direction_tr = self.DIRECTION_TR[direction]
            
            # Get current price (with date/time)
            try:
                current_price = market_data.get_latest_price(symbol)
                if current_price:
                    current_timestamp = int(time.time())
                    price_text = self.format_price_with_timestamp(current_price, current_timestamp)
                else:
                    price_text = "💰 Price unavailable"
            except Exception:
                price_text = "💰 Price unavailable"
            
            lines.append(
                f"{i}. {symbol.replace('/USDT', '')}\n"
                f"   {emoji} {direction_tr}\n"
                f"   {price_text}\n"
                f"   🎯 Confidence: %{confidence:.0f}\n"
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
        Formats detailed analysis message.
        
        Args:
            symbol: Trading pair
            signal: Signal info
            position: Position info
            risk: Risk info
            
        Returns:
            Formatted detailed message
        """
        direction = signal['direction']
        emoji = self.DIRECTION_EMOJI[direction]
        direction_tr = self.DIRECTION_TR[direction]
        confidence = signal['confidence'] * 100
        
        lines = [
            f"📊 {symbol.replace('/USDT', '')} DETAILED ANALYSIS\n",
            f"{emoji} Signal: {direction_tr}",
            f"🎯 Confidence: %{confidence:.0f}"
        ]
        
        # Current price (always show)
        if position and position.get('current_price'):
            current = position['current_price']
            # If timestamp info exists, add it
            timestamp = position.get('price_timestamp')
            if timestamp:
                price_text = self.format_price_with_timestamp(current, timestamp)
            else:
                price_text = f"📍 Current Price: ${current:.4f}"
            lines.append(f"{price_text}\n")
        elif signal.get('timeframe_signals'):
            # If NEUTRAL and no position, try to fetch price from first timeframe
            # (should have been fetched already)
            lines.append("")
        else:
            lines.append("")
        
        # Entry status warning
        if position and position.get('entry_status'):
            warning = self._format_entry_warning(position)
            if warning:
                lines.append(warning)
        
        # Position info
        if position:
            lines.extend(self._format_position_info(position))
        
        # Risk management
        if risk:
            lines.append("\n💼 Risk Management:")
            lines.append(self._format_risk_info(risk))
        
        # Technical indicators
        if 'timeframe_signals' in signal:
            lines.append("\n📈 Timeframe Analysis:")
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
        """Creates warning message based on entry status."""
        status = position.get('entry_status')
        current = position.get('current_price')
        entry = position.get('entry')
        fib_ideal = position.get('fib_ideal_entry')
        
        if status == 'PRICE_MOVED' and fib_ideal:
            diff_percent = abs((current - fib_ideal) / fib_ideal) * 100
            return (
                f"\n⚠️ PRICE MOVED!\n"
                f"Ideal Entry: ${fib_ideal:.4f} (%{diff_percent:.1f} away)\n"
                f"Note: Position levels calculated from current price.\n"
            )
        elif status == 'WAIT_FOR_PULLBACK' and fib_ideal:
            return (
                f"\n💡 WAIT FOR PULLBACK\n"
                f"Ideal Entry: ${fib_ideal:.4f}\n"
                f"Strategy: Wait for price to reach this level.\n"
            )
        elif status == 'PULLBACK_EXPECTED' and fib_ideal:
            return (
                f"\n📍 IDEAL ENTRY LEVEL\n"
                f"Target: ${fib_ideal:.4f}\n"
            )
        
        return ""
    
    def _format_position_info(self, position: Dict[str, Any]) -> List[str]:
        """Formats position info."""
        # If only current_price exists, this is NEUTRAL dummy position
        if 'entry' not in position:
            return []
        
        lines = [
            "\n💡 IF POSITION IS DESIRED AT THIS PRICE:"
        ]
        
        # Determine label based on entry status
        entry_status = position.get('entry_status')
        entry = position['entry']
        
        # If pullback expected "Ideal Entry", else "Entry"
        if entry_status in ['WAIT_FOR_PULLBACK', 'PULLBACK_EXPECTED']:
            lines.append(f"💰 Ideal Entry: ${entry:.4f}")
        else:
            # PRICE_MOVED veya None (optimal)
            lines.append(f"💰 Entry: ${entry:.4f}")
        
        lines.append(f"🛡️ Stop-Loss: ${position['stop_loss']:.4f}")
        lines.append(f"📍 Risk: %{position['risk_percent']:.2f}\n")
        
        lines.append("🎯 Take-Profit Levels:")
        for i, target in enumerate(position['targets'], 1):
            lines.append(
                f"   TP{i}: ${target['price']:.4f} "
                f"(R:R {target['risk_reward']:.2f})"
            )
        
        return lines
    
    def _format_risk_info(self, risk: Dict) -> str:
        """Formats risk info."""
        risk_tr = {
            'low': 'Low',
            'medium': 'Medium',
            'high': 'High'
        }
        
        return (
            f"   Risk Level: {risk_tr[risk['risk_level']]}\n"
            f"   Position Size: %{risk['position_size_percent']:.1f}\n"
            f"   ⚡ Leverage: {risk['leverage']}x"
        )
    
    def _format_timeframe_signals(
        self, tf_signals: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        """Formats timeframe signals."""
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
        Formats error message.
        
        Args:
            error_type: Error type
            
        Returns:
            Formatted error message
        """
        messages = {
            'no_data': (
                "❌ Data unavailable\n"
                "Please try again later."
            ),
            'invalid_symbol': (
                "❌ Invalid symbol\n"
                "Please enter a valid coin symbol."
            ),
            'analysis_failed': (
                "❌ Analysis failed\n"
                "A technical error occurred."
            )
        }
        
        msg = messages.get(
            error_type,
            "❌ An error occurred."
        )
        try:
            self.logger.debug(f"format_error_message: type={error_type}")
        except Exception:
            pass
        return msg
    
    def format_settings_message(self, notifications_enabled: bool) -> str:
        """
        Formats settings message.
        
        Args:
            notifications_enabled: Notification status
            
        Returns:
            Formatted settings message
        """
        status = "On ✅" if notifications_enabled else "Off ❌"
        
        return (
            "⚙️ SETTINGS\n\n"
            f"🔔 Hourly Notifications: {status}\n\n"
            "Type /settings again to toggle notifications."
        )
