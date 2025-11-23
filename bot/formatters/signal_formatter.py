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
            sl_hits: SL hit statuses {'1': True/False, '1.5': True/False, '2': True/False}
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
            confidence = signal_data.get('confidence', 0.0)
            confidence_pct_raw = confidence * 100  # Keep as float (for exact value)
            confidence_pct = int(round(confidence * 100))  # For old format (used in cap check)
            direction_emoji = self.DIRECTION_EMOJI.get(direction, '➡️')
            direction_text = self.DIRECTION_TR.get(direction, direction)

            def fmt_price(price: float) -> str:
                """Returns price in monospace (code block) format - for one-click copy."""
                if price is None:
                    return "-"
                if abs(price) >= 1:
                    return f"`${price:,.2f}`"
                return f"`${price:,.6f}`"

            # PNL (Profit/Loss) calculation - Correct formula based on Direction
            try:
                if direction == 'LONG':
                    # LONG: Profit when price rises (positive)
                    pnl_pct = ((now_price - signal_price) / signal_price) * 100 if signal_price else 0.0
                elif direction == 'SHORT':
                    # SHORT: Profit when price falls (positive) - IMPORTANT: Reverse formula
                    pnl_pct = ((signal_price - now_price) / signal_price) * 100 if signal_price else 0.0
                else:
                    pnl_pct = 0.0
            except Exception:
                pnl_pct = 0.0

            direction_title = self.DIRECTION_TITLE.get(direction, direction.upper())
            strategy_type = signal_data.get('strategy_type', 'trend')
            custom_targets = signal_data.get('custom_targets') if isinstance(signal_data.get('custom_targets'), dict) else {}
            # Ranging strategy is determined by strategy_type, can be ranging even if custom_targets is empty
            is_ranging_strategy = strategy_type == 'ranging'
            forecast_text = 'N/A'
            try:
                tf_signals = signal_data.get('timeframe_signals')
                if isinstance(tf_signals, dict) and '4h' in tf_signals:
                    bias_dir = (tf_signals.get('4h') or {}).get('direction')
                    forecast_text = self.DIRECTION_FORECAST.get(bias_dir, 'Neutral')
            except Exception:
                forecast_text = 'N/A'

            # Timestamps
            signal_time_str = self.format_timestamp_with_seconds(created_at) if created_at else self.format_timestamp_with_seconds(int(time.time()))
            current_price_time = current_price_timestamp if current_price_timestamp is not None else int(time.time())
            current_time_str = self.format_timestamp_with_seconds(current_price_time)

            # Calculate R/R Ratio (TP1's R/R - Financial Expert Recommendation)
            rr_ratio_str = "N/A"
            try:
                # Try custom targets first (for ranging strategy)
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
                    # Calculate TP1's R/R for trend strategy (based on signal price)
                    # Use TP1 and SL levels (real R:R)
                    atr = entry_levels.get('atr')
                    if atr:
                        # TP1 = 3x ATR (1.5R), SL = SL_MULTIPLIER x ATR
                        if direction == 'LONG':
                            tp1_price = signal_price + (atr * 3)
                            sl_price = signal_price - (atr * SL_MULTIPLIER)
                        else:  # SHORT
                            tp1_price = signal_price - (atr * 3)
                            sl_price = signal_price + (atr * SL_MULTIPLIER)
                        
                        risk = abs(signal_price - sl_price)
                        reward = abs(tp1_price - signal_price)
                        if risk > 0:
                            rr_val = reward / risk
                            rr_ratio_str = f"{rr_val:.2f}"
                    else:
                        # Fallback: Get from optimal entry (old method)
                        optimal_entry = entry_levels.get('optimal', {})
                        if optimal_entry and 'risk_reward' in optimal_entry:
                            rr_val = optimal_entry['risk_reward']
                            rr_ratio_str = f"{rr_val:.2f}"
            except Exception:
                pass

            # Header - Short and concise
            direction_color = '🔴' if direction == 'SHORT' else '🟢'
            header_line = f"{direction_color} {direction_title} | {symbol}"
            lines = [header_line]
            
            # Signal date/time info
            signal_created_at = created_at if created_at else int(time.time())
            signal_datetime = self.format_timestamp(signal_created_at)
            lines.append(f"🕐 {signal_datetime}")
            if signal_id:
                lines.append(f"🆔 ID: `{signal_id}`")
            lines.append("")
            
            # Signal and Current Price
            lines.append(f"🔔 *Signal:* {fmt_price(signal_price)}")
            
            # Show current price only in update messages or if there is a significant difference
            # Hide in initial message (elapsed < 2 min and no hits)
            elapsed_seconds = current_price_time - signal_created_at
            
            has_hits = bool(tp_hits or sl_hits or (sl_hit_times and any(sl_hit_times.values())) or (tp_hit_times and any(tp_hit_times.values())))
            is_initial_message = elapsed_seconds < 120 and not has_hits
            
            if not is_initial_message:
                lines.append(f"💵 *Current:* {fmt_price(now_price)}")
            
            # R/R Info removed (user request)
            # lines.append(f"*R/R:* `{rr_ratio_str}`")
            
            # PNL (Profit/Loss) - Correct display based on Direction
            pnl_emoji = '✅' if pnl_pct > 0 else '❌' if pnl_pct < 0 else '🔁'
            pnl_status = "Profit" if pnl_pct > 0 else "Loss" if pnl_pct < 0 else "Neutral"
            
            # Status: "Status:" text removed, only showing emoji and percentage
            lines.append(f"{pnl_emoji} *{pnl_pct:+.2f}%* ({pnl_status})")
            
            # Elapsed time
            # signal_created_at and current_price_time already calculated above
            elapsed_time_str = self.format_time_elapsed(signal_created_at, current_price_time)
            if elapsed_time_str != "-":
                # Use _ for italic (MarkdownV2 uses * for bold, _ for italic)
                lines.append(f"⏱ _{elapsed_time_str}_")
            
            lines.append("")

            atr = entry_levels.get('atr')
            timeframe = entry_levels.get('timeframe') or ''

            # TP levels (header removed, showing TP1/TP2 directly)
            if is_ranging_strategy:
                # Get SL price for Ranging (for R/R calculation)
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
                    
                    # Calculate R/R ratio
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
                    # Add R/R ratio in parentheses, format: 🎯 TP1 $PRICE (+X%) (YR) ⏳
                    if rr_ratio > 0:
                        lines.append(f"🎯 TP{idx} {fmt_price(price)} ({tp_pct:+.2f}%) ({rr_ratio:.2f}R) {hit_emoji}")
                    else:
                        lines.append(f"🎯 TP{idx} {fmt_price(price)} ({tp_pct:+.2f}%) {hit_emoji}")
            else:
                # Risk distance: ATR 1.0 (or 1% fallback)
                # TP levels (Balanced Approach: TP1=1.5R, TP2=2.5R)
                # TP1 = 3x ATR (1.5R), TP2 = 5x ATR (2.5R)
                if atr:
                    risk_dist = atr
                else:
                    risk_dist = signal_price * 0.01
                tps = []
                # TP multipliers: [3, 5] -> TP1=1.5R, TP2=2.5R (SL=SL_MULTIPLIER x ATR based)
                # SL distance (for R/R calculation)
                sl_distance = risk_dist * SL_MULTIPLIER  # SL = SL_MULTIPLIER x ATR
                
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
                        
                        # Calculate R/R ratio (TP distance / SL distance)
                        rr_ratio = 0.0
                        try:
                            tp_distance = abs(offset)
                            if sl_distance > 0:
                                rr_ratio = tp_distance / sl_distance
                        except Exception:
                            pass
                        
                        # Check hit status (tp_hits keys come as 1, 2)
                        hit_status = bool(tp_hits and tp_hits.get(idx, False))
                        hit_emoji = "✅" if hit_status else "⏳"
                        # TP format: 🎯 TP1 $PRICE (+X%) (YR) ⏳
                        if rr_ratio > 0:
                            tps.append(f"🎯 TP{idx} {fmt_price(tp_price)} ({tp_pct:+.2f}%) ({rr_ratio:.2f}R) {hit_emoji}")
                        else:
                            tps.append(f"🎯 TP{idx} {fmt_price(tp_price)} ({tp_pct:+.2f}%) {hit_emoji}")
                lines.extend(tps)
            lines.append("")
            
            # Liquidation Risk Info (if available)
            liquidation_risk_pct = signal_data.get('liquidation_risk_percentage')
            if liquidation_risk_pct is not None:
                # Select emoji based on risk level
                if liquidation_risk_pct < 20:
                    risk_emoji = "🟢"  # Low risk
                    risk_text = "Low"
                elif liquidation_risk_pct < 50:
                    risk_emoji = "🟡"  # Medium risk
                    risk_text = "Medium"
                else:
                    risk_emoji = "🔴"  # High risk
                    risk_text = "High"
                
                lines.append(f"{risk_emoji} *Liquidation Risk:* %{liquidation_risk_pct:.2f} ({risk_text})")
                lines.append("")
            
            # SL levels (header removed, showing SL directly)
            
            # Simplify SL levels: Show a single SL list
            sl_levels = []
            # For Ranging strategy
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
                    
                    # Check hit status (In Ranging single SL, can come as '2' or 'stop')
                    is_hit = False
                    if sl_hits:
                        is_hit = sl_hits.get('2') or sl_hits.get('stop')
                        
                    hit_emoji = "❌" if is_hit else "⏳"
                    label = stop_info.get('label', 'Stop-Loss')
                    risk_pct = abs(sl_pct)
                    sl_levels.append(f"⛔️ SL {fmt_price(stop_price)} (Risk: {risk_pct:.1f}%) {hit_emoji}")
            
            # For Trend strategy
            else:
                # Balanced approach: Single SL (SL_MULTIPLIER x ATR)
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
                    # Percentage fallback if no ATR
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
                    
                    # Check hit status (sl_hits key comes as '2')
                    is_hit = False
                    if sl_hits:
                        # Can come as '2' or 2.0
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

            # TP/SL hit timeline (show only hits, signal log removed)
            timeline: List[tuple[int, str]] = []

            # Add TP/SL hits
            if tp_hit_times:
                for level, ts in tp_hit_times.items():
                    if not ts:
                        continue
                    try:
                        timeline.append((int(ts), f"TP{level}🎯"))
                    except Exception:
                        continue

            if sl_hit_times:
                # Now only SL2 is used (SL1 and SL1.5 removed)
                # Show "STOP" in Ranging strategy, "SL" in Trend Following
                if is_ranging_strategy:
                    sl_labels = {'1': 'STOP', '1.5': 'STOP', '2': 'STOP', 'stop': 'STOP'}
                else:
                    # Trend Following: Only SL2 is used, show as "SL"
                    sl_labels = {'1': 'SL', '1.5': 'SL', '2': 'SL'}
                
                for key, ts in sl_hit_times.items():
                    if not ts:
                        continue
                    label = sl_labels.get(str(key), 'SL')
                    try:
                        timeline.append((int(ts), f"{label}🛡️"))
                    except Exception:
                        continue

            # Sort all hit entries by timestamp
            timeline.sort(key=lambda item: item[0])

            # Signal log section (show only if there are hits)
            if timeline:
                lines.append("")
                lines.append("📝 *Signal Log:*")
                for ts, desc in timeline:
                    lines.append(f"{self.format_timestamp_with_seconds(ts)} - {desc}")

            # Technical details (footer) - header removed
            lines.append("")
            strategy_name = "Mean Reversion" if is_ranging_strategy else "Trend Following"
            
            # Confidence Cap: Show maximum 99%
            confidence_pct_capped = min(confidence_pct_raw, 99.0)
            
            # Show confidence value with exact value (1 decimal place - Financial Expert Recommendation)
            confidence_display = f"{confidence_pct_capped:.1f}%"
            
            # Do NOT escape variables inside code blocks
            # Backslash appears as literal in code block, looks ugly
            lines.append(f"📈 Strategy: `{strategy_name}`")
            lines.append(f"⚡ Confidence: `{confidence_display}`")
            
            # 4H Confirmation: Show only if CONTRADICTS main direction or is not N/A.
            # If main direction is LONG and 4H is also Bullish (LONG), do not show (redundant).
            show_forecast = False
            if forecast_text != 'N/A':
                direction_forecast = self.DIRECTION_FORECAST.get(direction)
                # If forecast is same as main direction, do not show
                if forecast_text != direction_forecast:
                    show_forecast = True
            
            if show_forecast:
                # Not escaping because it's inside code block
                # Underscore error: 4h_confirmation -> 4H Confirmation (with space)
                lines.append(f"4H Confirmation: `{forecast_text}`")

            # Join message
            message = '\n'.join(lines)
            
            # Escape for MarkdownV2
            # PRESERVING bold/italic formats because parse_mode='MarkdownV2' is used
            # Only escape special characters outside code blocks
            try:
                # Escape preserving code blocks
                # PRESERVING Bold (*text*) and italic (_text_) formats
                message = self.escape_markdown_v2_smart(message, preserve_code_blocks=True)
            except Exception as e:
                self.logger.warning(f"Markdown escape error, message will be sent as is: {str(e)}")
                # In case of error, escape only critical characters (preserve bold/italic)
                # DO NOT escape Bold/italic formats
                # Only escape truly necessary characters
                message = message.replace('[', '\\[').replace(']', '\\]').replace('~', '\\~').replace('|', '\\|')
            
            return message
            
        except Exception as e:
            self.logger.error(f"Signal alert formatting error: {str(e)}", exc_info=True)
            return f"❌ {symbol} signal could not be formatted"
    
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
