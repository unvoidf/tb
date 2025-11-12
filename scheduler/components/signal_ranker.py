"""
SignalRanker: Sinyalleri sıralayan bileşen.
Güvenilirlik skoru, RSI aşırılık seviyesi ve hacim gücüne göre sinyalleri filtreler ve sıralar.
"""
from typing import List, Dict
from utils.logger import LoggerManager


class SignalRanker:
    """Sinyalleri sıralayan bileşen."""
    
    def __init__(self):
        """SignalRanker'ı başlatır."""
        self.logger = LoggerManager().get_logger('SignalRanker')
    
    def rank_signals(self, all_signals: List[Dict], top_count: int = 5) -> List[Dict]:
        """
        Sinyalleri gelişmiş skorlama sistemine göre sıralar.
        Confidence + RSI aşırılık puanı + Hacim gücü puanı.
        
        Args:
            all_signals: Tüm sinyal listesi
            top_count: Seçilecek top sinyal sayısı
            
        Returns:
            Sıralanmış top sinyal listesi
        """
        if not all_signals:
            return []
        
        # Minimum güvenilirlik threshold (35%)
        MIN_CONFIDENCE = 0.35
        
        # Sinyalleri filtrele ve skorla
        scored_signals = []
        for signal_data in all_signals:
            direction = signal_data['signal']['direction']
            confidence = signal_data['signal']['confidence']
            
            # Çok düşük güvenilirliği atla
            if confidence < MIN_CONFIDENCE:
                continue
            
            # Base skor (mevcut sistem)
            if direction == 'NEUTRAL':
                base_score = confidence * 0.8
            else:
                base_score = confidence * 1.1
            
            # Ekstra puanlar hesapla
            rsi_bonus = self._calculate_rsi_extremity_bonus(
                signal_data['signal'], direction
            )
            volume_bonus = self._calculate_volume_strength_bonus(
                signal_data['signal']
            )
            
            # Toplam skor (confidence skoru + bonuslar)
            # Bonuslar 0-1 arası normalize edilmiş değerler olarak eklenir
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
        
        # Skor'a göre sırala
        sorted_signals = sorted(
            scored_signals,
            key=lambda x: x['score'],
            reverse=True
        )
        
        # Top N'i seç (hem data hem score bilgisiyle)
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
            f"Top {len(top_signals)} sinyal seçildi: " + 
            ", ".join([s['symbol'] for s in top_signals])
        )
        
        return top_signals
    
    def _calculate_rsi_extremity_bonus(
        self, signal: Dict, direction: str
    ) -> float:
        """
        RSI aşırılık seviyesine göre bonus puan hesaplar.
        
        Args:
            signal: Sinyal dict
            direction: Sinyal yönü (LONG/SHORT/NEUTRAL)
            
        Returns:
            0-1 arası normalize edilmiş bonus puan
        """
        # Multi-timeframe sinyallerinde en güçlü timeframe'i kullan
        # veya 4h timeframe'ini önceliklendir
        timeframe_signals = signal.get('timeframe_signals', {})
        
        # DEBUG: Type check
        if not isinstance(timeframe_signals, dict):
            self.logger.error(f"timeframe_signals is NOT a dict! Type: {type(timeframe_signals)}, Value: {timeframe_signals}")
        
        # Öncelik: 4h > 1d > 1h
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
                        self.logger.debug(f"RSI bonus hesaplama: tf={tf}, rsi_value={rsi_value:.2f}, direction={direction}")
                        break
        
        if rsi_value is None:
            self.logger.debug(f"RSI bonus hesaplama: RSI değeri bulunamadı (timeframe_signals={list(timeframe_signals.keys())})")
            return 0.0
        
        bonus = 0.0
        
        # LONG sinyali için: RSI aşırı düşük seviyelerde bonus
        if direction == 'LONG':
            if rsi_value <= 20:
                # Çok aşırı oversold - maksimum bonus
                bonus = 1.0
            elif rsi_value <= 25:
                # Aşırı oversold - yüksek bonus
                bonus = 0.7
            elif rsi_value <= 30:
                # Oversold - orta bonus
                bonus = 0.4
            elif rsi_value <= 35:
                # Hafif oversold - düşük bonus
                bonus = 0.15
            # LONG sinyali + yüksek RSI = mantıksal çelişki (bonus yok)
        
        # SHORT sinyali için: RSI aşırı yüksek seviyelerde bonus
        elif direction == 'SHORT':
            if rsi_value >= 80:
                # Çok aşırı overbought - maksimum bonus
                bonus = 1.0
            elif rsi_value >= 75:
                # Aşırı overbought - yüksek bonus
                bonus = 0.7
            elif rsi_value >= 70:
                # Overbought - orta bonus
                bonus = 0.4
            elif rsi_value >= 65:
                # Hafif overbought - düşük bonus
                bonus = 0.15
            # SHORT sinyali + düşük RSI = mantıksal çelişki (bonus yok)
        
        # NEUTRAL sinyali için: Her iki yönde aşırı RSI değerlerinde bonus
        elif direction == 'NEUTRAL':
            # Yüksek RSI (overbought) - NEUTRAL'da da aşırılık işareti
            if rsi_value >= 75:
                bonus = 0.5
            elif rsi_value >= 70:
                bonus = 0.3
            elif rsi_value >= 65:
                bonus = 0.15
            # Düşük RSI (oversold) - NEUTRAL'da da aşırılık işareti
            elif rsi_value <= 25:
                bonus = 0.5
            elif rsi_value <= 30:
                bonus = 0.3
            elif rsi_value <= 35:
                bonus = 0.15
        
        return bonus
    
    def _calculate_volume_strength_bonus(self, signal: Dict) -> float:
        """
        Hacim gücüne göre bonus puan hesaplar.
        
        Args:
            signal: Sinyal dict
            
        Returns:
            0-1 arası normalize edilmiş bonus puan
        """
        # Multi-timeframe sinyallerinde en güçlü timeframe'i kullan
        timeframe_signals = signal.get('timeframe_signals', {})
        
        # Öncelik: 4h > 1d > 1h
        preferred_tfs = ['4h', '1d', '1h']
        volume_data = None
        
        for tf in preferred_tfs:
            if tf in timeframe_signals:
                tf_signal = timeframe_signals[tf]
                volume = tf_signal.get('volume')
                
                # Debug: Volume yapısını kontrol et
                if volume:
                    self.logger.debug(
                        f"Volume bonus hesaplama: tf={tf}, "
                        f"volume_type={type(volume).__name__}, "
                        f"volume_keys={list(volume.keys()) if isinstance(volume, dict) else 'N/A'}"
                    )
                
                if volume and isinstance(volume, dict):
                    volume_data = volume
                    break
        
        if not volume_data:
            self.logger.debug("Volume bonus hesaplama: volume_data bulunamadı")
            return 0.0
        
        relative_volume = volume_data.get('relative', 0)
        
        # Debug: Relative volume değerini logla
        if relative_volume > 0:
            self.logger.debug(
                f"Volume bonus hesaplama: relative_volume={relative_volume:.3f}"
            )
        
        # Hacim spike seviyelerine göre bonus
        if relative_volume >= 3.0:
            # Çok güçlü hacim spike (3x+) - maksimum bonus
            return 1.0
        elif relative_volume >= 2.5:
            # Güçlü hacim spike (2.5x+) - yüksek bonus
            return 0.8
        elif relative_volume >= 2.0:
            # Hacim spike (2x+) - orta-yüksek bonus
            return 0.6
        elif relative_volume >= 1.5:
            # Yüksek hacim (1.5x+) - orta bonus
            return 0.4
        elif relative_volume >= 1.2:
            # Artan hacim (1.2x+) - düşük bonus
            return 0.2
        else:
            # Normal hacim
            return 0.0
