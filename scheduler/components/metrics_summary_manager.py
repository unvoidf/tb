"""
MetricsSummaryManager: Günlük/haftalık performans özeti hesaplar.
DB'den aktif sinyalleri alıp aggregate metrikleri hesaplar ve kaydeder.
"""
import time
import json
from typing import Dict, List
from data.signal_repository import SignalRepository
from utils.logger import LoggerManager


class MetricsSummaryManager:
    """Günlük/haftalık performans özeti hesaplayıcı."""
    
    def __init__(self, signal_repository: SignalRepository):
        """
        MetricsSummaryManager'ı başlatır.
        
        Args:
            signal_repository: Signal repository instance
        """
        self.repository = signal_repository
        self.logger = LoggerManager().get_logger('MetricsSummaryManager')
    
    def generate_daily_summary(self):
        """Son 24 saatin özet metriklerini hesapla ve kaydet."""
        period_end = int(time.time())
        period_start = period_end - 24 * 3600
        
        # Tüm sinyalleri çek
        signals = self.repository.get_signals_by_time_range(period_start, period_end)
        
        if not signals:
            self.logger.info("Son 24 saatte sinyal yok, özet kaydedilmedi")
            return
        
        # Aggregate metrikler
        metrics = self._calculate_metrics(signals)
        
        # Kaydet
        self.repository.save_metrics_summary(period_start, period_end, metrics)
        self.logger.info(f"Günlük özet kaydedildi: {len(signals)} sinyal")
    
    def _calculate_metrics(self, signals: list) -> Dict:
        """
        Sinyal listesinden aggregate metrikler hesapla.
        
        Args:
            signals: Sinyal listesi
            
        Returns:
            Metrics dict
        """
        total = len(signals)
        long_count = sum(1 for s in signals if s['direction'] == 'LONG')
        short_count = sum(1 for s in signals if s['direction'] == 'SHORT')
        neutral_count = total - long_count - short_count
        
        avg_confidence = sum(s['confidence'] for s in signals) / total if total else 0
        
        # TP/SL hit rates
        tp1_hit_rate = sum(1 for s in signals if s.get('tp1_hit')) / total if total else 0
        tp2_hit_rate = sum(1 for s in signals if s.get('tp2_hit')) / total if total else 0
        sl_hit_rate = sum(1 for s in signals if s.get('sl_hit')) / total if total else 0
        
        # MFE/MAE ortalama (sadece var olanlar)
        mfe_list = [
            self._calc_percent_diff(s['signal_price'], s['mfe_price'], s['direction'], True) 
            for s in signals if s.get('mfe_price')
        ]
        mae_list = [
            self._calc_percent_diff(s['signal_price'], s['mae_price'], s['direction'], False) 
            for s in signals if s.get('mae_price')
        ]
        
        avg_mfe = sum(mfe_list) / len(mfe_list) if mfe_list else 0
        avg_mae = sum(mae_list) / len(mae_list) if mae_list else 0
        
        # İlk target'a kadar süre (TP1 veya SL hit olanlar)
        time_to_first = []
        for s in signals:
            created = s['created_at']
            tp1_at = s.get('tp1_hit_at')
            sl_at = s.get('sl_hit_at')
            hit_times = [t for t in [tp1_at, sl_at] if t]
            if hit_times:
                first_hit = min(hit_times)
                time_to_first.append((first_hit - created) / 3600.0)  # saat
        avg_time_to_first = sum(time_to_first) / len(time_to_first) if time_to_first else 0
        
        # Market regime (dominant, market_context JSON'dan çıkar)
        regimes = [self._extract_regime(s.get('market_context')) for s in signals]
        regimes = [r for r in regimes if r != 'unknown']
        dominant_regime = max(set(regimes), key=regimes.count) if regimes else 'unknown'
        
        return {
            'total_signals': total,
            'long_signals': long_count,
            'short_signals': short_count,
            'neutral_filtered': neutral_count,
            'avg_confidence': avg_confidence,
            'tp1_hit_rate': tp1_hit_rate,
            'tp2_hit_rate': tp2_hit_rate,
            'sl_hit_rate': sl_hit_rate,
            'avg_mfe_percent': avg_mfe,
            'avg_mae_percent': avg_mae,
            'avg_time_to_first_target_hours': avg_time_to_first,
            'market_regime': dominant_regime
        }
    
    def _calc_percent_diff(self, signal_price, extreme_price, direction, is_mfe):
        """Yüzdelik fark hesapla."""
        if direction == 'LONG':
            return ((extreme_price - signal_price) / signal_price) * 100 if is_mfe else ((signal_price - extreme_price) / signal_price) * 100
        else:
            return ((signal_price - extreme_price) / signal_price) * 100 if is_mfe else ((extreme_price - signal_price) / signal_price) * 100
    
    def _extract_regime(self, market_context_json):
        """market_context JSON'dan regime çıkar."""
        if not market_context_json:
            return 'unknown'
        try:
            ctx = json.loads(market_context_json)
            return ctx.get('regime', 'unknown')
        except:
            return 'unknown'

