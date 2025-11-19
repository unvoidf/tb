"""
CooldownManager: Sinyal cooldown yönetimi.
Aynı sembol için tekrarlanan sinyalleri önler.
"""
import time
from typing import Dict, Optional
from utils.logger import LoggerManager


class CooldownManager:
    """Sinyal cooldown mekanizmasını yönetir."""
    
    def __init__(self, cooldown_seconds: int, signal_repository=None):
        """
        CooldownManager'ı başlatır.
        
        Args:
            cooldown_seconds: Cooldown süresi (saniye)
            signal_repository: Signal repository (DB'den cache warmup için)
        """
        self.cooldown_seconds = cooldown_seconds
        self.signal_repository = signal_repository
        self.signal_cache: Dict[str, Dict] = {}
        self.logger = LoggerManager().get_logger('CooldownManager')
        
        # Cache warmup
        self._warmup_cache_from_db()
    
    def should_send_notification(self, symbol: str, direction: str) -> bool:
        """
        Bildirim gönderilip gönderilmeyeceğini kontrol eder.
        
        Args:
            symbol: Trading pair
            direction: Sinyal yönü
            
        Returns:
            True ise bildirim gönderilebilir
        """
        now = time.time()
        
        # Cache'de yok, gönder
        if symbol not in self.signal_cache:
            return True
        
        cached = self.signal_cache[symbol]
        last_signal_time = cached.get('last_signal_time', 0)
        last_direction = cached.get('last_direction')
        
        # Cooldown içinde mi?
        time_since_last = now - last_signal_time
        
        if time_since_last < self.cooldown_seconds:
            # Aynı yön, cooldown içinde
            if direction == last_direction:
                self.logger.info(
                    f"{symbol} cooldown içinde (aynı yön: {direction}), "
                    f"kalan: {(self.cooldown_seconds - time_since_last) / 60:.1f} dakika"
                )
                return False
            else:
                # Ters yön, izin ver (önemli değişim)
                self.logger.info(
                    f"{symbol} yön değişti ({last_direction} -> {direction}), "
                    "cooldown override"
                )
                return True
        
        # Cooldown dışında
        return True
    
    def update_cache(self, symbol: str, direction: str, confidence: float):
        """
        Cache'i günceller.
        
        Args:
            symbol: Trading pair
            direction: Sinyal yönü
            confidence: Güven skoru
        """
        self.signal_cache[symbol] = {
            'last_signal_time': time.time(),
            'last_direction': direction,
            'confidence': confidence
        }
    
    def load_cache_entry_from_db(self, symbol: str) -> Optional[Dict]:
        """
        Veritabanından cache entry yükler.
        
        Args:
            symbol: Trading pair
            
        Returns:
            Cache entry veya None
        """
        if not self.signal_repository:
            return None
        
        try:
            latest_signal = self.signal_repository.get_latest_signal_for_symbol(symbol)
            if latest_signal:
                return {
                    'last_signal_time': latest_signal.get('created_at', 0),
                    'last_direction': latest_signal.get('direction'),
                    'confidence': latest_signal.get('confidence', 0.0)
                }
        except Exception as e:
            self.logger.error(f"{symbol} DB cache load hatası: {str(e)}")
        
        return None
    
    def _warmup_cache_from_db(self) -> None:
        """Veritabanından cache'i önceden doldurur."""
        if not self.signal_repository:
            return
        
        try:
            recent_signals = self.signal_repository.get_recent_signals(limit=100)
            
            for signal in recent_signals:
                symbol = signal.get('symbol')
                if not symbol:
                    continue
                
                # Cache'de yoksa veya DB'deki daha yeni ise güncelle
                cached = self.signal_cache.get(symbol)
                db_time = signal.get('created_at', 0)
                
                if not cached or db_time > cached.get('last_signal_time', 0):
                    self.signal_cache[symbol] = {
                        'last_signal_time': db_time,
                        'last_direction': signal.get('direction'),
                        'confidence': signal.get('confidence', 0.0)
                    }
            
            self.logger.info(f"Cache warmup: {len(self.signal_cache)} sembol yüklendi")
        except Exception as e:
            self.logger.error(f"Cache warmup hatası: {str(e)}")
    
    def get_cache_stats(self) -> Dict:
        """
        Cache istatistiklerini döndürür.
        
        Returns:
            Cache istatistikleri
        """
        if not self.signal_cache:
            return {'size': 0, 'oldest_age_sec': None, 'newest_age_sec': None}
        
        now = time.time()
        ages = [now - entry['last_signal_time'] for entry in self.signal_cache.values()]
        
        return {
            'size': len(self.signal_cache),
            'oldest_age_sec': int(max(ages)) if ages else None,
            'newest_age_sec': int(min(ages)) if ages else None
        }
    
    def cleanup_old_cache(self) -> None:
        """24 saatten eski cache entry'lerini temizler."""
        try:
            now = time.time()
            cutoff = now - (24 * 3600)
            
            before_count = len(self.signal_cache)
            self.signal_cache = {
                symbol: entry
                for symbol, entry in self.signal_cache.items()
                if entry.get('last_signal_time', 0) > cutoff
            }
            after_count = len(self.signal_cache)
            
            removed = before_count - after_count
            if removed > 0:
                self.logger.info(f"Cache cleanup: {removed} eski entry kaldırıldı")
        except Exception as e:
            self.logger.error(f"Cache cleanup hatası: {str(e)}")

