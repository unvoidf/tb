"""
SignalRanker: Component that ranks signals.
Filters and ranks signals based on confidence score, RSI extremity level, and volume strength.
"""
from typing import List, Dict
from utils.logger import LoggerManager


class SignalRanker:
    """Component that ranks signals."""
    
    def __init__(self):
        """Initializes SignalRanker."""
        self.logger = LoggerManager().get_logger('SignalRanker')
    
    def rank_signals(self, all_signals: List[Dict], top_count: int = 5) -> List[Dict]:
        """
        Ranks signals according to advanced scoring system.
        Confidence + RSI extremity score + Volume strength score.
        
        Args:
            all_signals: List of all signals
            top_count: Number of top signals to select
            
        Returns:
            Sorted list of top signals
        """
        if not all_signals:
            return []
        
        # Minimum confidence threshold (35%)
        MIN_CONFIDENCE = 0.35
        
        # Filter and score signals
        scored_signals = []
        for signal_data in all_signals:
            direction = signal_data['signal']['direction']
            confidence = signal_data['signal']['confidence']
            
            # Skip very low confidence
            if confidence < MIN_CONFIDENCE:
                continue
            
            # Base score (current system)
            if direction == 'NEUTRAL':
                base_score = confidence * 0.8
            else:
                base_score = confidence * 1.1
            
            # Calculate extra points
            rsi_bonus = self._calculate_rsi_extremity_bonus(
                signal_data['signal'], direction
            )
            volume_bonus = self._calculate_volume_strength_bonus(
                signal_data['signal']
            )
            
            # Total score (confidence score + bonuses)
            # Bonuses are added as normalized values between 0-1
            total_score = base_score + (rsi_bonus * 0.3) + (volume_bonus * 0.2)
            
            scored_signals.append({
                'data': signal_data,
                'score': total_score,
                'base_score': base_score,
                'rsi_bonus': rsi_bonus,
                'volume_bonus': volume_bonus
            })
            
            self.logger.debug(
                f"{signal_data['symbol']}: base={base_score:.3f}, "
                f"rsi_bonus={rsi_bonus:.3f}, volume_bonus={volume_bonus:.3f}, "
                f"total={total_score:.3f}"
            )
        
        # Sort by score
        sorted_signals = sorted(
            scored_signals,
            key=lambda x: x['score'],
            reverse=True
        )
        
        # Select Top N (with both data and score info)
        top_signals = []
        for s in sorted_signals[:top_count]:
            signal_with_score = s['data'].copy()
            signal_with_score['_ranking_info'] = {
                'total_score': s['score'],
                'base_score': s['base_score'],
                'rsi_bonus': s['rsi_bonus'],
                'volume_bonus': s['volume_bonus']
            }
            top_signals.append(signal_with_score)
        
        self.logger.info(
            f"Top {len(top_signals)} signals selected: " + 
            ", ".join([s['symbol'] for s in top_signals])
        )
        
        return top_signals
    
    def _calculate_rsi_extremity_bonus(
        self, signal: Dict, direction: str
    ) -> float:
        """
        Calculates bonus points based on RSI extremity level.
        
        Args:
            signal: Signal dict
            direction: Signal direction (LONG/SHORT/NEUTRAL)
            
        Returns:
            Normalized bonus score between 0-1
        """
        # Use strongest timeframe in multi-timeframe signals
        # or prioritize 4h timeframe
        timeframe_signals = signal.get('timeframe_signals', {})
        
        # DEBUG: Type check
        if not isinstance(timeframe_signals, dict):
            self.logger.error(f"timeframe_signals is NOT a dict! Type: {type(timeframe_signals)}, Value: {timeframe_signals}")
        
        # Priority: 4h > 1d > 1h
        preferred_tfs = ['4h', '1d', '1h']
        rsi_value = None
        
        for tf in preferred_tfs:
            if tf in timeframe_signals:
                tf_signal = timeframe_signals[tf]
                indicators = tf_signal.get('indicators', {})
                if indicators and 'rsi' in indicators:
                    rsi_data = indicators['rsi']
                    if isinstance(rsi_data, dict) and 'value' in rsi_data:
                        rsi_value = rsi_data['value']
                        self.logger.debug(f"RSI bonus calculation: tf={tf}, rsi_value={rsi_value:.2f}, direction={direction}")
                        break
        
        if rsi_value is None:
            self.logger.debug(f"RSI bonus calculation: RSI value not found (timeframe_signals={list(timeframe_signals.keys())})")
            return 0.0
        
        bonus = 0.0
        
        # For LONG signal: Bonus at extremely low RSI levels
        if direction == 'LONG':
            if rsi_value <= 20:
                # Very extreme oversold - maximum bonus
                bonus = 1.0
            elif rsi_value <= 25:
                # Extreme oversold - high bonus
                bonus = 0.7
            elif rsi_value <= 30:
                # Oversold - medium bonus
                bonus = 0.4
            elif rsi_value <= 35:
                # Slightly oversold - low bonus
                bonus = 0.15
            # LONG signal + high RSI = logical contradiction (no bonus)
        
        # For SHORT signal: Bonus at extremely high RSI levels
        elif direction == 'SHORT':
            if rsi_value >= 80:
                # Very extreme overbought - maximum bonus
                bonus = 1.0
            elif rsi_value >= 75:
                # Extreme overbought - high bonus
                bonus = 0.7
            elif rsi_value >= 70:
                # Overbought - medium bonus
                bonus = 0.4
            elif rsi_value >= 65:
                # Slightly overbought - low bonus
                bonus = 0.15
            # SHORT signal + low RSI = logical contradiction (no bonus)
        
        # For NEUTRAL signal: Bonus at extreme RSI levels in both directions
        elif direction == 'NEUTRAL':
            # High RSI (overbought) - sign of extremity in NEUTRAL too
            if rsi_value >= 75:
                bonus = 0.5
            elif rsi_value >= 70:
                bonus = 0.3
            elif rsi_value >= 65:
                bonus = 0.15
            # Low RSI (oversold) - sign of extremity in NEUTRAL too
            elif rsi_value <= 25:
                bonus = 0.5
            elif rsi_value <= 30:
                bonus = 0.3
            elif rsi_value <= 35:
                bonus = 0.15
        
        return bonus
    
    def _calculate_volume_strength_bonus(self, signal: Dict) -> float:
        """
        Calculates bonus points based on volume strength.
        
        Args:
            signal: Signal dict
            
        Returns:
            Normalized bonus score between 0-1
        """
        # Use strongest timeframe in multi-timeframe signals
        timeframe_signals = signal.get('timeframe_signals', {})
        
        # Priority: 4h > 1d > 1h
        preferred_tfs = ['4h', '1d', '1h']
        volume_data = None
        
        for tf in preferred_tfs:
            if tf in timeframe_signals:
                tf_signal = timeframe_signals[tf]
                volume = tf_signal.get('volume')
                
                # Debug: Check volume structure
                if volume:
                    self.logger.debug(
                        f"Volume bonus calculation: tf={tf}, "
                        f"volume_type={type(volume).__name__}, "
                        f"volume_keys={list(volume.keys()) if isinstance(volume, dict) else 'N/A'}"
                    )
                
                if volume and isinstance(volume, dict):
                    volume_data = volume
                    break
        
        if not volume_data:
            self.logger.debug("Volume bonus calculation: volume_data not found")
            return 0.0
        
        relative_volume = volume_data.get('relative', 0)
        
        # Debug: Log relative volume value
        if relative_volume > 0:
            self.logger.debug(
                f"Volume bonus calculation: relative_volume={relative_volume:.3f}"
            )
        
        # Bonus based on volume spike levels
        if relative_volume >= 3.0:
            # Very strong volume spike (3x+) - maximum bonus
            return 1.0
        elif relative_volume >= 2.5:
            # Strong volume spike (2.5x+) - high bonus
            return 0.8
        elif relative_volume >= 2.0:
            # Volume spike (2x+) - medium-high bonus
            return 0.6
        elif relative_volume >= 1.5:
            # High volume (1.5x+) - medium bonus
            return 0.4
        elif relative_volume >= 1.2:
            # Increasing volume (1.2x+) - low bonus
            return 0.2
        else:
            # Normal volume
            return 0.0
