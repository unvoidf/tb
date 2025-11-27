"""
SignalFormatter: Formatting for signal notification messages.
Signal alert message and inline keyboard creation.
"""
import time
from typing import Dict, List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config.constants import SL_MULTIPLIER
from bot.formatters.base_formatter import BaseFormatter


class SignalFormatter(BaseFormatter):
    """Formats signal notification messages."""
    
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
        Formats signal scanner output.
        
        Args:
            symbol: Trading pair (e.g., BTC/USDT)
            signal_data: Signal data
            entry_levels: Dynamic entry levels
            signal_price: Signal price
            now_price: Current price
            tp_hits: TP hit statuses {1: True/False, 2: True/False, 3: True/False}
            sl_hits: SL hit statuses {'sl': True/False}
            created_at: Signal creation time
            current_price_timestamp: Measurement time of current price
            tp_hit_times: TP hit times
            sl_hit_times: SL hit times
            signal_id: Signal ID (e.g., 20251107-074546-FILUSDT)
            signal_log: Signal log
            confidence_change: Confidence change
            
        Returns:
            Formatted signal alert message
        """
        try:
            # Helpers
            direction = signal_data.get('direction', 'NEUTRAL')
            
            # 1. Format Header
            lines = self._format_header(direction, symbol, signal_id, created_at)
            
            # 2. Format Price Info
            lines.extend(self._format_price_info(
                signal_price, now_price, created_at, current_price_timestamp, 
                direction, tp_hits, sl_hits, sl_hit_times, tp_hit_times
            ))
            
            # 3. Format Entry Levels (TP/SL)
            strategy_type = signal_data.get('strategy_type', 'trend')
            custom_targets = signal_data.get('custom_targets') if isinstance(signal_data.get('custom_targets'), dict) else {}
            
            lines.extend(self._format_entry_levels(
                entry_levels, custom_targets, direction, signal_price, 
                strategy_type, tp_hits, sl_hits
            ))
            
            # 4. Format Timeline (Signal Log)
            is_ranging_strategy = strategy_type == 'ranging'
            lines.extend(self._format_timeline(
                created_at, tp_hit_times, sl_hit_times, is_ranging_strategy
            ))
            
            # 5. Format Footer
            confidence = signal_data.get('confidence', 0.0)
            liquidation_risk_pct = signal_data.get('liquidation_risk_percentage')
            
            # Forecast text logic
            forecast_text = 'N/A'
            try:
                tf_signals = signal_data.get('timeframe_signals')
                if isinstance(tf_signals, dict) and '4h' in tf_signals:
                    bias_dir = (tf_signals.get('4h') or {}).get('direction')
                    forecast_text = self.DIRECTION_FORECAST.get(bias_dir, 'Neutral')
            except Exception:
                pass
                
            lines.extend(self._format_footer(
                confidence, strategy_type, liquidation_risk_pct, forecast_text, direction
            ))

            # Join message
            message = '\n'.join(lines)
            
            # Escape for MarkdownV2
            try:
                message = self.escape_markdown_v2_smart(message, preserve_code_blocks=True)
            except Exception as e:
                self.logger.warning(f"Markdown escape error, message will be sent as is: {str(e)}")
                message = message.replace('[', '\\[').replace(']', '\\]').replace('~', '\\~').replace('|', '\\|')
            
            return message
            
        except Exception as e:
            self.logger.error(f"Signal alert formatting error: {str(e)}", exc_info=True)
            return f"❌ {symbol} signal could not be formatted"

    def _format_header(self, direction: str, symbol: str, signal_id: Optional[str], created_at: Optional[int]) -> List[str]:
        """Formats the signal header."""
        direction_title = self.DIRECTION_TITLE.get(direction, direction.upper())
        direction_color = '🔴' if direction == 'SHORT' else '🟢'
        header_line = f"{direction_color} {direction_title} | {symbol}"
        lines = [header_line]
        
        if signal_id:
            lines.append(f"🆔 ID: `{signal_id}`")
        lines.append("")
        return lines

    def _format_price_info(
        self, signal_price: float, now_price: float, created_at: Optional[int], 
        current_price_timestamp: Optional[int], direction: str,
        tp_hits: Optional[Dict], sl_hits: Optional[Dict],
        sl_hit_times: Optional[Dict], tp_hit_times: Optional[Dict]
    ) -> List[str]:
        """Formats signal price, current price, PNL and elapsed time."""
        lines = []
        
        def fmt_price(price: float) -> str:
            if price is None: return "-"
            if abs(price) >= 1: return f"`${price:,.2f}`"
            return f"`${price:,.6f}`"

        # Signal Price
        lines.append(f"🔔 *Signal:* {fmt_price(signal_price)}")
        
        # Current Price logic
        signal_created_at = created_at if created_at else int(time.time())
        current_price_time = current_price_timestamp if current_price_timestamp is not None else int(time.time())
        elapsed_seconds = current_price_time - signal_created_at
        
        has_hits = bool(tp_hits or sl_hits or (sl_hit_times and any(sl_hit_times.values())) or (tp_hit_times and any(tp_hit_times.values())))
        is_initial_message = elapsed_seconds < 120 and not has_hits
        
        if not is_initial_message:
            lines.append(f"💵 *Current:* {fmt_price(now_price)}")
        
        # PNL Calculation
        try:
            if direction == 'LONG':
                pnl_pct = ((now_price - signal_price) / signal_price) * 100 if signal_price else 0.0
            elif direction == 'SHORT':
                pnl_pct = ((signal_price - now_price) / signal_price) * 100 if signal_price else 0.0
            else:
                pnl_pct = 0.0
        except Exception:
            pnl_pct = 0.0
            
        pnl_emoji = '✅' if pnl_pct > 0 else '❌' if pnl_pct < 0 else '🔁'
        pnl_status = "Profit" if pnl_pct > 0 else "Loss" if pnl_pct < 0 else "Neutral"
        
        lines.append(f"{pnl_emoji} *{pnl_pct:+.2f}%* ({pnl_status})")
        
        # Elapsed Time
        elapsed_time_str = self.format_time_elapsed(signal_created_at, current_price_time)
        if elapsed_time_str != "-":
            lines.append(f"⏱ _{elapsed_time_str}_")
        
        lines.append("")
        return lines

    def _format_entry_levels(
        self, entry_levels: Dict, custom_targets: Dict, direction: str, 
        signal_price: float, strategy_type: str, tp_hits: Optional[Dict], sl_hits: Optional[Dict]
    ) -> List[str]:
        """Formats TP and SL levels."""
        lines = []
        is_ranging_strategy = strategy_type == 'ranging'
        atr = entry_levels.get('atr')
        
        def fmt_price(price: float) -> str:
            if price is None: return "-"
            if abs(price) >= 1: return f"`${price:,.2f}`"
            return f"`${price:,.6f}`"

        # TP Levels
        if is_ranging_strategy:
            stop_info = custom_targets.get('sl') or custom_targets.get('stop_loss', {})
            sl_price_ranging = stop_info.get('price')
            
            for idx, key in enumerate(['tp1', 'tp2'], start=1):
                target_info = custom_targets.get(key)
                if not target_info: continue
                price = target_info.get('price')
                if price is None: continue
                
                try:
                    if direction == 'LONG':
                        tp_pct = ((price - signal_price) / signal_price) * 100 if signal_price else 0.0
                    else:
                        tp_pct = ((signal_price - price) / signal_price) * 100 if signal_price else 0.0
                except Exception:
                    tp_pct = 0.0
                
                # R/R
                rr_ratio = 0.0
                if sl_price_ranging:
                    try:
                        if direction == 'LONG':
                            risk = abs(signal_price - sl_price_ranging)
                            reward = abs(price - signal_price)
                        else:
                            risk = abs(signal_price - sl_price_ranging)
                            reward = abs(signal_price - price)
                        if risk > 0:
                            rr_ratio = reward / risk
                    except Exception:
                        pass
                
                hit_status = bool(tp_hits and tp_hits.get(idx, False))
                hit_emoji = "✅" if hit_status else "⏳"
                
                if rr_ratio > 0:
                    lines.append(f"🎯 TP{idx} {fmt_price(price)} ({tp_pct:+.2f}%) ({rr_ratio:.2f}R) {hit_emoji}")
                else:
                    lines.append(f"🎯 TP{idx} {fmt_price(price)} ({tp_pct:+.2f}%) {hit_emoji}")
        else:
            # Trend Strategy
            if atr:
                risk_dist = atr
            else:
                risk_dist = signal_price * 0.01
            
            sl_distance = risk_dist * SL_MULTIPLIER
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
                    
                    rr_ratio = 0.0
                    try:
                        tp_distance = abs(offset)
                        if sl_distance > 0:
                            rr_ratio = tp_distance / sl_distance
                    except Exception:
                        pass
                    
                    hit_status = bool(tp_hits and tp_hits.get(idx, False))
                    hit_emoji = "✅" if hit_status else "⏳"
                    
                    if rr_ratio > 0:
                        lines.append(f"🎯 TP{idx} {fmt_price(tp_price)} ({tp_pct:+.2f}%) ({rr_ratio:.2f}R) {hit_emoji}")
                    else:
                        lines.append(f"🎯 TP{idx} {fmt_price(tp_price)} ({tp_pct:+.2f}%) {hit_emoji}")

        # SL Levels
        sl_levels = []
        if is_ranging_strategy:
            stop_info = custom_targets.get('sl') or custom_targets.get('stop_loss')
            if stop_info and stop_info.get('price') is not None:
                stop_price = stop_info.get('price')
                try:
                    if direction == 'LONG':
                        sl_pct = ((stop_price - signal_price) / signal_price) * 100 if signal_price else 0.0
                    else:
                        sl_pct = ((signal_price - stop_price) / signal_price) * 100 if signal_price else 0.0
                except Exception:
                    sl_pct = 0.0
                
                is_hit = False
                if sl_hits:
                    is_hit = bool(sl_hits.get('sl') or sl_hits.get('stop'))
                    
                hit_emoji = "❌" if is_hit else "⏳"
                risk_pct = abs(sl_pct)
                sl_levels.append(f"⛔️ SL {fmt_price(stop_price)} (Risk: {risk_pct:.1f}%) {hit_emoji}")
        else:
            # Trend Strategy
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
                try:
                    if direction == 'LONG':
                        sl_pct = ((sl_price - signal_price) / signal_price) * 100 if signal_price else 0.0
                    else:
                        sl_pct = ((signal_price - sl_price) / signal_price) * 100 if signal_price else 0.0
                except Exception:
                    sl_pct = 0.0
                
                is_hit = False
                if sl_hits:
                    is_hit = bool(sl_hits.get('sl') or sl_hits.get('stop'))
                
                hit_emoji = "❌" if is_hit else "⏳"
                risk_pct = abs(sl_pct)
                sl_levels.append(f"⛔️ SL {fmt_price(sl_price)} (Risk: {risk_pct:.1f}%) {hit_emoji}")

        if sl_levels:
            lines.extend(sl_levels)
        else:
            lines.append("   -")
            
        return lines

    def _format_timeline(
        self, created_at: Optional[int], tp_hit_times: Optional[Dict], 
        sl_hit_times: Optional[Dict], is_ranging_strategy: bool
    ) -> List[str]:
        """Formats the signal timeline (log)."""
        lines = []
        timeline: List[tuple[int, str]] = []

        if created_at:
            timeline.append((created_at, "Signal Created 🔔"))

        if tp_hit_times:
            for level, ts in tp_hit_times.items():
                if not ts: continue
                try:
                    timeline.append((int(ts), f"TP{level}🎯"))
                except Exception:
                    continue

        if sl_hit_times:
            if is_ranging_strategy:
                sl_labels = {'sl': 'STOP', 'stop': 'STOP'}
            else:
                sl_labels = {'sl': 'SL'}
            
            for key, ts in sl_hit_times.items():
                if not ts: continue
                label = sl_labels.get(str(key), 'SL')
                try:
                    timeline.append((int(ts), f"{label}🛡️"))
                except Exception:
                    continue

        timeline.sort(key=lambda item: item[0])

        if timeline:
            lines.append("")
            lines.append("📝 *Signal Log:*")
            for ts, desc in timeline:
                lines.append(f"{self.format_timestamp_with_seconds(ts)} - {desc}")
        
        return lines

    def _format_footer(
        self, confidence: float, strategy_type: str, liquidation_risk_pct: Optional[float],
        forecast_text: str, direction: str
    ) -> List[str]:
        """Formats the message footer (Strategy, Confidence, Risk)."""
        lines = []
        lines.append("")
        
        is_ranging_strategy = strategy_type == 'ranging'
        strategy_name = "Mean Reversion" if is_ranging_strategy else "Trend Following"
        
        confidence_pct_raw = confidence * 100
        confidence_pct_capped = min(confidence_pct_raw, 99.0)
        confidence_display = f"{confidence_pct_capped:.1f}%"
        
        lines.append(f"📈 Strategy: `{strategy_name}`")
        lines.append(f"⚡ Confidence: `{confidence_display}`")
        
        if liquidation_risk_pct is not None:
            if liquidation_risk_pct < 20:
                risk_emoji = "🟢"
                risk_text = "Low"
            elif liquidation_risk_pct < 50:
                risk_emoji = "🟡"
                risk_text = "Medium"
            else:
                risk_emoji = "🔴"
                risk_text = "High"
            
            lines.append(f"{risk_emoji} *Liquidation Risk:* %{liquidation_risk_pct:.2f} ({risk_text})")
        
        show_forecast = False
        if forecast_text != 'N/A':
            direction_forecast = self.DIRECTION_FORECAST.get(direction)
            if forecast_text != direction_forecast:
                show_forecast = True
        
        if show_forecast:
            lines.append(f"4H Confirmation: `{forecast_text}`")
            
        return lines
    
    def create_signal_keyboard(self, signal_id: str) -> InlineKeyboardMarkup:
        """
        Creates inline keyboard for signal message.
        
        Args:
            signal_id: Signal ID
            
        Returns:
            InlineKeyboardMarkup instance
        """
        button = InlineKeyboardButton(
            text="🔄 Update",
            callback_data=f"update_signal:{signal_id}"
        )
        keyboard = [[button]]
        return InlineKeyboardMarkup(keyboard)
