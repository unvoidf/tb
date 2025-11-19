"""
CoinScorer: Coin scoring and ranking helpers.
Liquidity, stability, momentum scoring functions.
"""
from typing import Dict, List
from utils.logger import LoggerManager


class CoinScorer:
    """Coin scoring helper sınıfı."""
    
    def __init__(self):
        self.logger = LoggerManager().get_logger('CoinScorer')
    
    def calculate_liquidity_score(self, ticker: Dict) -> float:
        """
        Likidite skoru hesaplar.
        
        Args:
            ticker: Ticker bilgisi
            
        Returns:
            Likidite skoru (0-100)
        """
        try:
            volume_24h = ticker.get('quoteVolume', 0) or 0
            
            # Volume skoru (logaritmik)
            if volume_24h > 0:
                import math
                volume_score = min(100, math.log10(volume_24h) * 10)
            else:
                volume_score = 0
            
            return volume_score
        except Exception:
            return 0
    
    def calculate_stability_score(self, ticker: Dict) -> float:
        """
        Stabilite skoru hesaplar.
        
        Args:
            ticker: Ticker bilgisi
            
        Returns:
            Stabilite skoru (0-100)
        """
        try:
            # Volatility bazlı (düşük volatility = yüksek stabilite)
            change_24h = abs(ticker.get('percentage', 0) or 0)
            
            # Volatility penalty
            if change_24h > 20:
                stability = 0
            elif change_24h > 10:
                stability = 50
            else:
                stability = 100 - (change_24h * 5)
            
            return max(0, min(100, stability))
        except Exception:
            return 50
    
    def calculate_momentum_score(self, ticker: Dict) -> float:
        """
        Momentum skoru hesaplar.
        
        Args:
            ticker: Ticker bilgisi
            
        Returns:
            Momentum skoru (0-100)
        """
        try:
            change_24h = ticker.get('percentage', 0) or 0
            volume_24h = ticker.get('quoteVolume', 0) or 0
            
            # Fiyat değişimi + hacim kombinasyonu
            price_momentum = min(abs(change_24h) * 10, 50)
            
            # Volume momentum
            import math
            if volume_24h > 10_000_000:
                volume_momentum = 50
            elif volume_24h > 1_000_000:
                volume_momentum = 25
            else:
                volume_momentum = 0
            
            return price_momentum + volume_momentum
        except Exception:
            return 0
    
    def rank_coins_by_score(
        self, 
        coins: List[Dict], 
        score_key: str, 
        count: int
    ) -> List[str]:
        """
        Coinleri skora göre sıralar.
        
        Args:
            coins: Coin listesi
            score_key: Score key (örn: 'smart_score')
            count: Döndürülecek coin sayısı
            
        Returns:
            Sıralanmış coin sembolleri
        """
        sorted_coins = sorted(
            coins,
            key=lambda x: x.get(score_key, 0),
            reverse=True
        )
        return [coin['symbol'] for coin in sorted_coins[:count]]

