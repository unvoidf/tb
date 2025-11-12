"""
CoinFilter: Hacim bazlı coin filtreleme sınıfı.
Son 1 saatlik hacmi en yüksek USDT çiftlerini seçer.
"""
import ccxt
import numpy as np
from typing import List, Dict
from utils.logger import LoggerManager
from utils.retry_handler import RetryHandler


class CoinFilter:
    """Binance'den hacim bazlı coin filtreleme yapar."""
    
    def __init__(self, retry_handler: RetryHandler):
        """
        CoinFilter'ı başlatır.
        
        Args:
            retry_handler: Retry mekanizması instance
        """
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        self.retry_handler = retry_handler
        self.logger = LoggerManager().get_logger('CoinFilter')
    
    def get_top_volume_coins(self, count: int = 20) -> List[str]:
        """
        Son 1 saatlik hacmi en yüksek USDT çiftlerini döndürür.
        
        Args:
            count: Döndürülecek coin sayısı
            
        Returns:
            Sembol listesi (örn: ['BTC/USDT', 'ETH/USDT', ...])
        """
        try:
            # Tüm ticker'ları çek
            tickers = self.retry_handler.execute(
                self.exchange.fetch_tickers
            )
            self.logger.debug(f"tickers_count={len(tickers)}")
            
            # USDT çiftlerini filtrele
            usdt_pairs = self._filter_usdt_pairs(tickers)
            self.logger.debug(f"usdt_pairs_count={len(usdt_pairs)}")
            
            # Hacme göre sırala ve top N'i al
            sorted_pairs = self._sort_by_volume(usdt_pairs, count)
            self.logger.debug(f"sorted_pairs_topN={sorted_pairs[:3]}")
            
            symbols = [item['symbol'] for item in sorted_pairs]
            
            self.logger.info(
                f"Top {count} hacimli coin seçildi: {', '.join(symbols[:5])}..."
            )
            
            return symbols
            
        except Exception as e:
            self.logger.error(
                f"Coin filtreleme hatası: {str(e)}",
                exc_info=True
            )
            return self._get_fallback_coins(count)
    
    def _filter_usdt_pairs(self, tickers: Dict) -> List[Dict]:
        """
        Sadece USDT çiftlerini filtreler.
        
        Args:
            tickers: Tüm ticker bilgileri
            
        Returns:
            USDT çiftleri listesi
        """
        usdt_pairs = []
        
        for symbol, ticker in tickers.items():
            if (symbol.endswith('/USDT') and 
                ticker.get('quoteVolume') is not None and
                not self._is_leveraged_token(symbol) and
                not self._is_stablecoin(symbol)):
                
                usdt_pairs.append({
                    'symbol': symbol,
                    'volume': ticker['quoteVolume'],
                    'price': ticker.get('last', 0)
                })
        
        return usdt_pairs
    
    def _is_leveraged_token(self, symbol: str) -> bool:
        """
        Leverage token kontrolü (UP, DOWN, BULL, BEAR vb.).
        
        Args:
            symbol: Trading pair
            
        Returns:
            True ise leverage token
        """
        leverage_keywords = ['UP/', 'DOWN/', 'BULL/', 'BEAR/']
        return any(keyword in symbol for keyword in leverage_keywords)
    
    def _is_stablecoin(self, symbol: str) -> bool:
        """
        Stablecoin kontrolü (USDC, USDT, BUSD, DAI vb.).
        
        Args:
            symbol: Trading pair
            
        Returns:
            True ise stablecoin
        """
        # Sadece gerçek stablecoin'leri filtrele
        stablecoins = ['USDC/USDT', 'BUSD/USDT', 'DAI/USDT', 'TUSD/USDT', 
                       'USDD/USDT', 'USDP/USDT', 'FDUSD/USDT', 'USDE/USDT']
        return symbol in stablecoins
    
    def _sort_by_volume(self, pairs: List[Dict], 
                       count: int) -> List[Dict]:
        """
        Çiftleri hacme göre sıralar ve ilk N'i döndürür.
        
        Args:
            pairs: Coin çiftleri listesi
            count: Döndürülecek sayı
            
        Returns:
            Sıralanmış liste
        """
        sorted_pairs = sorted(
            pairs,
            key=lambda x: x['volume'],
            reverse=True
        )
        return sorted_pairs[:count]
    
    def get_top_futures_coins(self, count: int = 20) -> List[str]:
        """
        Smart Liquidity + Stability Score ile top N coin çeker.
        
        Args:
            count: Döndürülecek coin sayısı
            
        Returns:
            Futures coin sembol listesi
        """
        try:
            # Futures exchange instance oluştur
            futures_exchange = ccxt.binance({
                'enableRateLimit': True,
                'options': {'defaultType': 'future'}
            })
            
            # Futures ticker'ları çek
            tickers = self.retry_handler.execute(
                futures_exchange.fetch_tickers
            )
            self.logger.debug(f"futures_tickers_count={len(tickers)}")
            
            # Smart coin selection uygula
            smart_coins = self._get_smart_coins(tickers, count)
            
            self.logger.info(
                f"Smart selection ile top {count} futures coin seçildi: {', '.join(smart_coins)}"
            )
            
            return smart_coins
            
        except Exception as e:
            self.logger.error(
                f"Smart coin filtreleme hatası: {str(e)}",
                exc_info=True
            )
            return self._get_futures_fallback_coins(count)
    
    def _filter_futures_usdt_pairs(self, tickers: Dict) -> List[Dict]:
        """
        Futures USDT çiftlerini filtreler (stablecoin'siz).
        
        Args:
            tickers: Futures ticker bilgileri
            
        Returns:
            Futures USDT çiftleri listesi
        """
        futures_pairs = []
        usdt_count = 0
        filtered_count = 0
        
        for symbol, ticker in tickers.items():
            # Futures sembol formatını normalize et (LQTY/USDT:USDT -> LQTY/USDT)
            normalized_symbol = symbol.replace(':USDT', '').replace(':USDC', '')
            
            # Debug: USDT pair sayısını say
            if normalized_symbol.endswith('/USDT'):
                usdt_count += 1
                
                # Debug: Filtreleme adımlarını kontrol et
                has_volume = ticker.get('quoteVolume') is not None
                is_leveraged = self._is_leveraged_token(normalized_symbol)
                is_stablecoin = self._is_stablecoin(normalized_symbol)
                is_excluded = self._is_futures_excluded(normalized_symbol)
                
                # Ölü coin kontrolü ekle
                is_dead_coin = self._is_dead_coin(normalized_symbol, ticker)
                
                if (has_volume and 
                    not is_leveraged and 
                    not is_stablecoin and 
                    not is_excluded and
                    not is_dead_coin):  # Ölü coin kontrolü eklendi
                    
                    futures_pairs.append({
                        'symbol': normalized_symbol,  # Normalize edilmiş sembol kullan
                        'volume': ticker['quoteVolume'],
                        'price': ticker.get('last', 0)
                    })
                    filtered_count += 1
                else:
                    # Debug: Neden filtrelendiğini logla
                    self.logger.debug(
                        f"Futures {normalized_symbol} filtrelendi: "
                        f"volume={has_volume}, leveraged={is_leveraged}, "
                        f"stablecoin={is_stablecoin}, excluded={is_excluded}, "
                        f"dead_coin={is_dead_coin}"
                    )
        
        self.logger.debug(f"Futures filtering: {usdt_count} USDT pairs, {filtered_count} passed filters")
        return futures_pairs
    
    def _is_futures_excluded(self, symbol: str) -> bool:
        """
        Futures'ta hariç tutulacak coinler.
        
        Args:
            symbol: Trading pair
            
        Returns:
            True ise hariç tutulacak
        """
        # Futures'ta olmayan veya problemli coinler
        excluded = [
            'LUNA/USDT', 'UST/USDT', 'FTT/USDT',  # Problemli coinler
            'BUSD/USDT', 'USDC/USDT',  # Stablecoin'ler
        ]
        return any(excluded_symbol in symbol for excluded_symbol in excluded)
    
    def _is_dead_coin(self, symbol: str, ticker: Dict) -> bool:
        """
        Ölü coin kontrolü yapar.
        
        Args:
            symbol: Coin sembolü
            ticker: Ticker bilgileri
            
        Returns:
            True ise ölü coin
        """
        # Volume kontrolü - çok düşük volume
        quote_volume = ticker.get('quoteVolume', 0)
        if quote_volume < 10000:  # Minimum 10K USDT volume
            self.logger.debug(f"Futures {symbol} filtrelendi: volume={quote_volume} (çok düşük)")
            return True
        
        # Fiyat değişimi kontrolü - hiç hareket yok
        price_change_percent = abs(ticker.get('percentage', 0))
        if price_change_percent < 0.01:  # %0.01'den az değişim
            self.logger.debug(f"Futures {symbol} filtrelendi: price_change={price_change_percent}% (çok düşük)")
            return True
        
        # Base volume kontrolü
        base_volume = ticker.get('baseVolume', 0)
        if base_volume < 1000:  # Minimum base volume
            self.logger.debug(f"Futures {symbol} filtrelendi: base_volume={base_volume} (çok düşük)")
            return True
        
        return False
    
    def _get_smart_coins(self, tickers: Dict, count: int) -> List[str]:
        """
        Smart Liquidity + Stability Score ile coin seçimi (optimized).
        
        Args:
            tickers: Ticker bilgileri
            count: Döndürülecek coin sayısı
            
        Returns:
            Seçilen coin sembolleri
        """
        # Önce hızlı filtreleme ile top 50'yi al
        quick_candidates = self._get_quick_candidates(tickers, 50)
        
        if len(quick_candidates) <= count:
            return [symbol for symbol, _ in quick_candidates]
        
        # Sadece top 50 için smart scoring uygula
        smart_candidates = []
        
        for symbol, ticker in quick_candidates:
            # Minimum veri kontrolü
            if not self._has_sufficient_data(symbol):
                self.logger.debug(f"Smart selection {symbol}: insufficient data")
                continue
            
            # Smart scoring
            liquidity_score = self._calculate_liquidity_score(symbol, ticker)
            stability_score = self._calculate_stability_score(symbol, ticker)
            volume_pattern_score = self._analyze_volume_pattern(symbol)
            
            # Stabilite skoru 0.0 olan coinleri filtrele
            if stability_score == 0.0:
                self.logger.debug(f"Smart selection {symbol}: zero stability score")
                continue
            
            # Hibrit skor (ağırlıklı)
            total_score = (
                liquidity_score * 0.5 +      # %50 - Likidite
                stability_score * 0.3 +      # %30 - Stabilite
                volume_pattern_score * 0.2   # %20 - Volume pattern
            )
            
            # Minimum threshold
            if total_score >= 60:  # %60 minimum skor
                smart_candidates.append((symbol, total_score, liquidity_score, stability_score, volume_pattern_score))
                self.logger.debug(
                    f"Smart score {symbol}: total={total_score:.1f}, "
                    f"liquidity={liquidity_score:.1f}, stability={stability_score:.1f}, "
                    f"pattern={volume_pattern_score:.1f}"
                )
        
        # Skora göre sırala ve top N'i al
        smart_candidates.sort(key=lambda x: x[1], reverse=True)
        selected = [symbol for symbol, total, liq, stab, pat in smart_candidates[:count]]
        
        # Debug: Seçilen coinlerin skorlarını logla
        for symbol, total, liq, stab, pat in smart_candidates[:count]:
            self.logger.debug(f"Selected {symbol}: total={total:.1f}, liq={liq:.1f}, stab={stab:.1f}, pat={pat:.1f}")
        
        return selected
    
    def _has_sufficient_data(self, symbol: str) -> bool:
        """Coin'in analiz için yeterli verisi var mı kontrol eder."""
        try:
            # 21 günlük veri kontrolü
            ohlcv_1d = self.exchange.fetch_ohlcv(symbol, '1d', limit=21)
            if len(ohlcv_1d) < 21:
                self.logger.debug(f"Data sufficiency {symbol}: insufficient 1d data ({len(ohlcv_1d)} < 21)")
                return False
            
            # 24 saatlik veri kontrolü
            ohlcv_1h = self.exchange.fetch_ohlcv(symbol, '1h', limit=24)
            if len(ohlcv_1h) < 24:
                self.logger.debug(f"Data sufficiency {symbol}: insufficient 1h data ({len(ohlcv_1h)} < 24)")
                return False
                
            return True
        except Exception as e:
            self.logger.debug(f"Data sufficiency check failed for {symbol}: {e}")
            return False
    
    def _get_quick_candidates(self, tickers: Dict, limit: int) -> List[tuple]:
        """Hızlı filtreleme ile top N candidate'ı al."""
        candidates = []
        
        for symbol, ticker in tickers.items():
            # Futures sembol formatını normalize et
            normalized_symbol = symbol.replace(':USDT', '').replace(':USDC', '')
            
            # Temel filtreler (OHLCV çekmeden)
            if not self._passes_quick_filters(normalized_symbol, ticker):
                continue
            
            # Volume bazlı skor (hızlı)
            volume_score = ticker.get('quoteVolume', 0)
            candidates.append((normalized_symbol, ticker, volume_score))
        
        # Volume'a göre sırala ve top N'i al
        candidates.sort(key=lambda x: x[2], reverse=True)
        return [(symbol, ticker) for symbol, ticker, _ in candidates[:limit]]
    
    def _passes_quick_filters(self, symbol: str, ticker: Dict) -> bool:
        """Hızlı filtreler (OHLCV çekmeden)."""
        if not symbol.endswith('/USDT'):
            return False
        
        # Temel kontroller
        has_volume = ticker.get('quoteVolume') is not None
        is_leveraged = self._is_leveraged_token(symbol)
        is_stablecoin = self._is_stablecoin(symbol)
        is_excluded = self._is_futures_excluded(symbol)
        is_dead_coin = self._is_dead_coin(symbol, ticker)
        
        # Fiyat kontrolü
        price = ticker.get('last', 0)
        is_price_healthy = self._is_price_healthy(price)
        
        # Volume threshold (hızlı kontrol)
        volume = ticker.get('quoteVolume', 0)
        has_min_volume = volume >= 1000000  # 1M USDT minimum
        
        return (has_volume and not is_leveraged and not is_stablecoin and 
                not is_excluded and not is_dead_coin and is_price_healthy and has_min_volume)
    
    def _passes_basic_filters(self, symbol: str, ticker: Dict) -> bool:
        """Temel filtreleri kontrol eder."""
        if not symbol.endswith('/USDT'):
            return False
        
        # Temel kontroller
        has_volume = ticker.get('quoteVolume') is not None
        is_leveraged = self._is_leveraged_token(symbol)
        is_stablecoin = self._is_stablecoin(symbol)
        is_excluded = self._is_futures_excluded(symbol)
        is_dead_coin = self._is_dead_coin(symbol, ticker)
        
        # Fiyat kontrolü
        price = ticker.get('last', 0)
        is_price_healthy = self._is_price_healthy(price)
        
        return (has_volume and not is_leveraged and not is_stablecoin and 
                not is_excluded and not is_dead_coin and is_price_healthy)
    
    def _is_price_healthy(self, price: float) -> bool:
        """Sağlıklı fiyat aralığı kontrolü."""
        # Tüm fiyat limitleri kaldırıldı: Fiyat, coin kalitesinin göstergesi değildir.
        # Likidite, stabilite ve volume pattern skorları zaten yeterli filtreleme sağlıyor.
        # Eski limitler:
        #   - Alt limit: if price < 0.01: return False (çok düşük fiyatlı coinler)
        #   - Üst limit: if price > 50000: return False (BTC, ETH vb. yüksek fiyatlı coinler)
        # 
        # Pump&dump riski volume, stability ve dead_coin kontrolleri ile filtreleniyor.
        
        return True
    
    def _calculate_liquidity_score(self, symbol: str, ticker: Dict) -> float:
        """
        Ticker quoteVolume bazlı likidite skoru (%50 ağırlık).
        
        NOT: OHLCV volume'u Binance futures'ta tutarsız (bazen çok düşük, bazen çok yüksek).
        Ticker quoteVolume kullanılıyor çünkü doğru ve güncel 24 saatlik toplam volume'u gösteriyor.
        """
        try:
            # Ticker'dan 24 saatlik volume (doğru ve güncel)
            quote_volume = ticker.get('quoteVolume', 0)
            
            if not quote_volume or quote_volume <= 0:
                self.logger.debug(f"Liquidity score {symbol}: no quoteVolume in ticker")
                return 0
            
            # Minimum volume threshold
            if quote_volume < 100000:  # 100K USDT minimum
                self.logger.debug(f"Liquidity score {symbol}: low volume ({quote_volume:.0f} < 100K)")
                return 0
            
            # NOT: OHLCV volume'u Binance futures'ta tutarsız olduğu için consistency kontrolü kaldırıldı.
            # Ticker quoteVolume doğru ve güncel 24 saatlik toplam volume'u gösteriyor.
            # Volume consistency kontrolü yapılmıyor çünkü OHLCV volume'u güvenilir değil.
            volume_consistency = 1.0
            
            # Volume score (0-100)
            # Normalizasyon: 10M USDT = 100 puan
            # Büyük coinler (BTC, ETH) için 10M+ volume = 100 puan (max)
            volume_score = min(quote_volume / 10000000, 100)  # 10M max = 100 puan
            liquidity_score = volume_score * volume_consistency
            
            # Debug log
            self.logger.debug(f"Liquidity calculation {symbol}: quote_volume={quote_volume:.0f}, "
                            f"volume_score={volume_score:.2f}, liquidity_score={liquidity_score:.1f}")
            
            return liquidity_score
            
        except Exception as e:
            self.logger.debug(f"Liquidity score hatası {symbol}: {e}")
            return 0
    
    def _calculate_stability_score(self, symbol: str, ticker: Dict) -> float:
        """Volatilite kontrolü ile stabilite skoru (%30 ağırlık)."""
        try:
            # Son 21 günlük veri (minimum veri kontrolü)
            ohlcv_1d = self.exchange.fetch_ohlcv(symbol, '1d', limit=21)
            
            if len(ohlcv_1d) < 21:
                self.logger.debug(f"Stability score {symbol}: insufficient data ({len(ohlcv_1d)} days < 21)")
                return 0
            
            # Günlük fiyat değişimleri
            price_changes = []
            for i in range(1, len(ohlcv_1d)):
                change = abs((ohlcv_1d[i][4] - ohlcv_1d[i-1][4]) / ohlcv_1d[i-1][4])
                price_changes.append(change)
            
            # Volatilite hesaplama
            avg_volatility = sum(price_changes) / len(price_changes)
            
            # Stabilite skoru (düşük volatilite = yüksek skor)
            stability_score = max(0, 100 - (avg_volatility * 1000))
            
            # Stabilite skoru 0.0 olan coinleri filtrele
            if stability_score == 0.0:
                self.logger.debug(f"Stability score {symbol}: filtered due to zero stability (volatility={avg_volatility:.4f})")
                return 0
            
            # Debug log
            self.logger.debug(f"Stability calculation {symbol}: data_length={len(ohlcv_1d)}, "
                            f"avg_volatility={avg_volatility:.4f}, stability_score={stability_score:.1f}")
            
            return stability_score
            
        except Exception as e:
            self.logger.debug(f"Stability score hatası {symbol}: {e}")
            return 0
    
    def _analyze_volume_pattern(self, symbol: str) -> float:
        """Volume pattern analizi (%20 ağırlık)."""
        try:
            ohlcv_1h = self.exchange.fetch_ohlcv(symbol, '1h', limit=48)
            
            if len(ohlcv_1h) < 24:
                self.logger.debug(f"Volume pattern {symbol}: insufficient data ({len(ohlcv_1h)} hours < 24)")
                return 0
            
            # Binance futures OHLCV volume'u base (contract) biriminde döndürüyor.
            # Her mum için ortalama fiyatla çarparak quote (USDT) cinsine dönüştür.
            quote_volumes = []
            for candle in ohlcv_1h:
                base_volume = candle[5]
                if base_volume <= 0:
                    quote_volumes.append(0.0)
                    continue
                
                open_price, high_price, low_price, close_price = candle[1], candle[2], candle[3], candle[4]
                avg_price = (open_price + high_price + low_price + close_price) / 4
                quote_volume = base_volume * avg_price
                quote_volumes.append(max(quote_volume, 0.0))
            
            if sum(quote_volumes[-24:]) <= 0:
                self.logger.debug(f"Volume pattern {symbol}: zero quote volume after conversion")
                return 0
            
            # Volume trend analizi (USDT cinsinden)
            recent_avg = sum(quote_volumes[-12:]) / 12  # Son 12 saat
            older_avg = sum(quote_volumes[-24:-12]) / 12  # Önceki 12 saat
            
            # Volume artış trendi (normalize edilmiş)
            volume_trend_raw = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0
            
            # Volume trend'i normalize et (-1 ile +1 arasında, sonra 0-1'e çevir)
            volume_trend_normalized = max(0, min(1, (volume_trend_raw + 1) / 2))  # 0-1 aralığına çevir ve sınırla
            
            # Volume tutarlılığı (düşük std = iyi)
            mean_volume = np.mean(quote_volumes)
            if mean_volume > 0:
                volume_consistency = 1 / (1 + np.std(quote_volumes) / mean_volume)
            else:
                volume_consistency = 0
            
            pattern_score = min(volume_trend_normalized * 50 + volume_consistency * 50, 100)
            
            # Debug log
            self.logger.debug(
                f"Volume pattern {symbol}: trend_raw={volume_trend_raw:.3f}, "
                f"trend_norm={volume_trend_normalized:.3f}, consistency={volume_consistency:.3f}, "
                f"recent_avg={recent_avg:.0f}, older_avg={older_avg:.0f}, pattern_score={pattern_score:.1f}"
            )
            
            return pattern_score
            
        except Exception as e:
            self.logger.debug(f"Volume pattern hatası {symbol}: {e}")
            return 0
    
    def _get_futures_fallback_coins(self, count: int) -> List[str]:
        """
        Futures hata durumunda fallback coin listesi.
        
        Args:
            count: İstenen coin sayısı
            
        Returns:
            Varsayılan futures coin listesi
        """
        fallback = [
            'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT',
            'ADA/USDT', 'SOL/USDT', 'DOGE/USDT', 'DOT/USDT',
            'MATIC/USDT', 'LTC/USDT', 'AVAX/USDT', 'LINK/USDT',
            'UNI/USDT', 'ATOM/USDT', 'ETC/USDT', 'XLM/USDT',
            'ALGO/USDT', 'VET/USDT', 'FIL/USDT', 'TRX/USDT'
        ]
        
        self.logger.warning("Futures fallback coin listesi kullanılıyor")
        return fallback[:count]

    def _get_fallback_coins(self, count: int) -> List[str]:
        """
        Hata durumunda fallback coin listesi döndürür.
        
        Args:
            count: İstenen coin sayısı
            
        Returns:
            Varsayılan major coin listesi
        """
        fallback = [
            'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT',
            'ADA/USDT', 'SOL/USDT', 'DOGE/USDT', 'DOT/USDT',
            'MATIC/USDT', 'LTC/USDT', 'AVAX/USDT', 'LINK/USDT',
            'UNI/USDT', 'ATOM/USDT', 'ETC/USDT', 'XLM/USDT',
            'ALGO/USDT', 'VET/USDT', 'FIL/USDT', 'TRX/USDT'
        ]
        
        self.logger.warning("Fallback coin listesi kullanılıyor")
        return fallback[:count]

