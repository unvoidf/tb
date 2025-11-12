"""
MarketDataManager: Binance'den piyasa verilerini çeken sınıf.
OHLCV verilerini farklı timeframe'ler için sağlar.
"""
import ccxt
import pandas as pd
import time
from typing import Optional, List, Dict, Tuple
from utils.logger import LoggerManager
from utils.retry_handler import RetryHandler


class MarketDataManager:
    """Binance API'den piyasa verilerini yönetir."""
    
    def __init__(self, retry_handler: RetryHandler):
        """
        MarketDataManager'ı başlatır.
        
        Args:
            retry_handler: Retry mekanizması instance
        """
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        self.retry_handler = retry_handler
        self.logger = LoggerManager().get_logger('MarketData')

        # Geçerli semboller için whitelist (exchange markets)
        try:
            markets = self.exchange.load_markets()
            self.valid_symbols = set(markets.keys())  # örn: 'BTC/USDT'
        except Exception as e:
            self.logger.error(
                f"Markets yüklenemedi: {str(e)}",
                exc_info=True
            )
            self.valid_symbols = set()

        # OHLCV cache: {(symbol, timeframe): (timestamp, df)}
        self._ohlcv_cache: Dict[Tuple[str, str], Tuple[float, pd.DataFrame]] = {}
        self._ohlcv_ttl_seconds: int = 300  # 5 dakika cache

    def is_valid_symbol(self, symbol: str) -> bool:
        """Sembol whitelist kontrolü yapar."""
        valid_symbols = getattr(self, 'valid_symbols', set())
        
        if not valid_symbols:
            self.logger.warning("valid_symbols boş! Markets yüklenmemiş olabilir.")
            return False
        
        # Direkt kontrol
        if symbol in valid_symbols:
            return True
        
        # Eğer symbol zaten futures formatındaysa (BTC/USDT:USDT), 
        # normal formatını da kontrol et (BTC/USDT)
        if ':USDT' in symbol or ':USDC' in symbol:
            normalized = symbol.split(':')[0]  # BTC/USDT:USDT -> BTC/USDT
            if normalized in valid_symbols:
                return True
            
        # Futures sembol formatını normalize et ve kontrol et
        # (BTC/USDT -> BTC/USDT:USDT)
        futures_symbol = f"{symbol}:USDT"
        if futures_symbol in valid_symbols:
            return True
            
        return False
    
    def fetch_ohlcv(self, symbol: str, timeframe: str, 
                    limit: int = 200) -> Optional[pd.DataFrame]:
        """
        Belirtilen sembol için OHLCV verisi çeker.
        
        Args:
            symbol: Trading pair (örn: 'BTC/USDT')
            timeframe: Zaman dilimi ('1h', '4h', '1d')
            limit: Çekilecek mum sayısı
            
        Returns:
            OHLCV verisi içeren DataFrame veya None
        """
        # Sembol whitelist kontrolü
        if not self.is_valid_symbol(symbol):
            self.logger.warning(
                f"Geçersiz sembol (whitelist dışı): symbol={symbol} timeframe={timeframe}"
            )
            return None

        # Kısa ömürlü cache kontrolü
        cache_key = (symbol, timeframe)
        now_ts = time.time()
        cached = self._ohlcv_cache.get(cache_key)
        if cached:
            cached_ts, cached_df = cached
            if now_ts - cached_ts <= self._ohlcv_ttl_seconds:
                return cached_df

        try:
            ohlcv = self.retry_handler.execute(
                self.exchange.fetch_ohlcv,
                symbol,
                timeframe,
                limit=limit
            )
            
            if not ohlcv:
                self.logger.warning(f"{symbol} için veri bulunamadı")
                return None
            
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            self.logger.info(
                f"{symbol} - {timeframe}: {len(df)} mum verisi çekildi"
            )
            self.logger.debug(
                f"{symbol} - {timeframe}: head=\n{df.head(3)}"
            )
            
            # Cache'e yaz
            self._ohlcv_cache[cache_key] = (now_ts, df)
            return df
            
        except ccxt.BadSymbol as e:
            # BadSymbol durumunda retry yapma, uyarı logla
            self.logger.warning(
                f"Geçersiz sembol: symbol={symbol} error={str(e)}"
            )
            return None
        except Exception as e:
            self.logger.error(
                f"{symbol} verisi çekilirken hata: {str(e)}",
                exc_info=True
            )
            return None
    
    def fetch_multi_timeframe(self, symbol: str, 
                             timeframes: List[str],
                             limit: int = 200) -> Dict[str, pd.DataFrame]:
        """
        Birden fazla timeframe için OHLCV verisi çeker.
        1d timeframe için adaptive limit uygular.
        
        Args:
            symbol: Trading pair
            timeframes: Timeframe listesi
            limit: Her timeframe için çekilecek mum sayısı
            
        Returns:
            Timeframe'lere göre DataFrame dict
        """
        result = {}
        
        for tf in timeframes:
            # 1d timeframe için adaptive limit
            if tf == '1d':
                df = self._fetch_adaptive_ohlcv(symbol, tf, limit)
            else:
                df = self.fetch_ohlcv(symbol, tf, limit)
            
            if df is not None:
                result[tf] = df
        
        return result
    
    def _fetch_adaptive_ohlcv(self, symbol: str, timeframe: str, 
                             ideal_limit: int = 200) -> Optional[pd.DataFrame]:
        """
        1d timeframe için adaptive OHLCV verisi çeker.
        Önce ideal limit ile dener, yeterli veri yoksa mevcut veriyi kullanır.
        
        Args:
            symbol: Trading pair
            timeframe: Timeframe (1d)
            ideal_limit: İdeal mum sayısı (200)
            
        Returns:
            OHLCV DataFrame veya None
        """
        try:
            # Önce ideal limit ile dene
            ohlcv = self.retry_handler.execute(
                self.exchange.fetch_ohlcv,
                symbol,
                timeframe,
                limit=ideal_limit
            )
            
            if not ohlcv:
                self.logger.warning(f"{symbol} için {timeframe} veri bulunamadı")
                return None
            
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Veri kalitesi kontrolü
            if not self._validate_ohlcv_quality(df, symbol, timeframe):
                self.logger.warning(f"{symbol} {timeframe} veri kalitesi düşük, analiz edilmiyor")
                return None
            
            data_count = len(df)
            
            # Veri miktarına göre log mesajı
            if data_count >= ideal_limit:
                self.logger.info(
                    f"{symbol} - {timeframe}: {data_count} mum verisi çekildi (ideal)"
                )
            else:
                self.logger.info(
                    f"{symbol} - {timeframe}: {data_count} mum verisi çekildi "
                    f"(adaptive - {ideal_limit - data_count} gün eksik)"
                )
                
                # Coin yaşı bilgisi
                first_date = df['timestamp'].iloc[0]
                days_old = (pd.Timestamp.now() - first_date).days
                self.logger.debug(
                    f"{symbol} futures yaşı: {days_old} gün "
                    f"(ilk tarih: {first_date.strftime('%Y-%m-%d')})"
                )
            
            self.logger.debug(
                f"{symbol} - {timeframe}: head=\n{df.head(3)}"
            )
            
            # Cache'e yaz
            cache_key = (symbol, timeframe)
            now_ts = time.time()
            self._ohlcv_cache[cache_key] = (now_ts, df)
            
            return df
            
        except ccxt.BadSymbol as e:
            self.logger.warning(
                f"Geçersiz sembol: symbol={symbol} error={str(e)}"
            )
            return None
        except Exception as e:
            self.logger.error(
                f"{symbol} adaptive verisi çekilirken hata: {str(e)}",
                exc_info=True
            )
            return None
    
    def _validate_ohlcv_quality(self, df: pd.DataFrame, symbol: str, timeframe: str) -> bool:
        """
        OHLCV veri kalitesini kontrol eder.
        
        Args:
            df: OHLCV DataFrame
            symbol: Trading pair
            timeframe: Zaman dilimi
            
        Returns:
            True ise kaliteli veri
        """
        try:
            # Boş veri kontrolü
            if df.empty:
                self.logger.debug(f"{symbol} {timeframe}: Boş veri")
                return False
            
            # NaN kontrolü
            nan_count = df.isnull().sum().sum()
            if nan_count > 0:
                self.logger.debug(f"{symbol} {timeframe}: {nan_count} NaN değer var")
                return False
            
            # Sıfır fiyat kontrolü
            zero_prices = ((df['open'] <= 0) | (df['high'] <= 0) | 
                          (df['low'] <= 0) | (df['close'] <= 0)).sum()
            if zero_prices > 0:
                self.logger.debug(f"{symbol} {timeframe}: {zero_prices} sıfır fiyat var")
                return False
            
            # Volume kontrolü
            zero_volume_count = (df['volume'] <= 0).sum()
            if zero_volume_count > len(df) * 0.5:  # %50'den fazla sıfır volume
                self.logger.debug(f"{symbol} {timeframe}: {zero_volume_count} sıfır volume ({len(df)} mum)")
                return False
            
            # OHLC mantık kontrolü
            invalid_ohlc = ((df['high'] < df['low']) | 
                           (df['high'] < df['open']) | 
                           (df['high'] < df['close']) |
                           (df['low'] > df['open']) | 
                           (df['low'] > df['close'])).sum()
            if invalid_ohlc > 0:
                self.logger.debug(f"{symbol} {timeframe}: {invalid_ohlc} geçersiz OHLC")
                return False
            
            # Çok düşük fiyat değişimi kontrolü (ölü coin)
            price_changes = df['close'].pct_change().abs()
            low_volatility_count = (price_changes < 0.001).sum()  # %0.1'den az değişim
            if low_volatility_count > len(df) * 0.8:  # %80'den fazla düşük volatilite
                self.logger.debug(f"{symbol} {timeframe}: {low_volatility_count} düşük volatilite ({len(df)} mum)")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"{symbol} {timeframe} veri kalitesi kontrolü hatası: {str(e)}")
            return False
    
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Sembolün güncel fiyatını döndürür.
        
        Args:
            symbol: Trading pair
            
        Returns:
            Güncel fiyat veya None
        """
        # Sembol whitelist kontrolü
        if not self.is_valid_symbol(symbol):
            self.logger.warning(
                f"Geçersiz sembol (price): symbol={symbol}"
            )
            return None

        try:
            ticker = self.retry_handler.execute(
                self.exchange.fetch_ticker,
                symbol
            )
            last = ticker['last']
            self.logger.debug(f"get_latest_price {symbol} -> {last}")
            return last
            
        except Exception as e:
            self.logger.error(
                f"{symbol} fiyatı çekilirken hata: {str(e)}"
            )
            return None
    
    def get_latest_price_with_timestamp(self, symbol: str) -> Tuple[Optional[float], Optional[int]]:
        """
        Sembolün güncel fiyatını timestamp ile döndürür.
        
        Args:
            symbol: Trading pair
            
        Returns:
            (Güncel fiyat, timestamp) veya (None, None)
        """
        # Sembol whitelist kontrolü
        if not self.is_valid_symbol(symbol):
            self.logger.warning(
                f"Geçersiz sembol (price): symbol={symbol}"
            )
            return None, None

        try:
            ticker = self.retry_handler.execute(
                self.exchange.fetch_ticker,
                symbol
            )
            current_timestamp = int(time.time())
            return ticker['last'], current_timestamp
            
        except Exception as e:
            self.logger.error(
                f"{symbol} fiyatı çekilirken hata: {str(e)}"
            )
            return None, None
    
    def get_ticker_info(self, symbol: str) -> Optional[Dict]:
        """
        Sembol için detaylı ticker bilgisi döndürür.
        
        Args:
            symbol: Trading pair
            
        Returns:
            Ticker bilgisi dict veya None
        """
        # Sembol whitelist kontrolü
        if not self.is_valid_symbol(symbol):
            self.logger.warning(
                f"Geçersiz sembol (ticker): symbol={symbol}"
            )
            return None

        try:
            ticker = self.retry_handler.execute(
                self.exchange.fetch_ticker,
                symbol
            )
            return ticker
            
        except Exception as e:
            self.logger.error(
                f"{symbol} ticker bilgisi alınırken hata: {str(e)}"
            )
            return None
    
    def get_historical_price(self, symbol: str, target_timestamp: int) -> Optional[float]:
        """
        Belirli bir zaman noktasındaki fiyatı döndürür.
        
        Args:
            symbol: Trading pair
            target_timestamp: Unix timestamp (saniye)
            
        Returns:
            O zaman noktasındaki fiyat veya None
        """
        # Sembol whitelist kontrolü
        if not self.is_valid_symbol(symbol):
            self.logger.warning(
                f"Geçersiz sembol (historical): symbol={symbol}"
            )
            return None

        try:
            # 1 saatlik veri çek (daha az API çağrısı)
            df = self.fetch_ohlcv(symbol, '1h', limit=50)
            if df is None or df.empty:
                return None
            
            # Target timestamp'i datetime'a çevir
            target_dt = pd.to_datetime(target_timestamp, unit='s')
            
            # En yakın mum'u bul
            df_sorted = df.sort_values('timestamp')
            
            # Target time'dan önceki en son mum'u bul
            before_target = df_sorted[df_sorted['timestamp'] <= target_dt]
            
            if before_target.empty:
                # Target time'dan sonraki ilk mum'u al
                after_target = df_sorted[df_sorted['timestamp'] > target_dt]
                if not after_target.empty:
                    return float(after_target.iloc[0]['close'])
                return None
            
            # En yakın mum'un close fiyatını döndür
            closest_mum = before_target.iloc[-1]
            price = float(closest_mum['close'])
            
            self.logger.info(
                f"{symbol} - {target_dt.strftime('%Y-%m-%d %H:%M')} fiyatı: ${price:,.2f}"
            )
            self.logger.debug(
                f"get_historical_price: target={target_dt}, chosen_close={price}, before_rows={len(before_target)}"
            )
            
            return price
            
        except Exception as e:
            self.logger.error(
                f"{symbol} tarihsel fiyat alınırken hata: {str(e)}"
            )
            return None
    
    def get_historical_price_with_timestamp(self, symbol: str, target_timestamp: int) -> Tuple[Optional[float], Optional[int]]:
        """
        Belirli bir zaman noktasındaki fiyatı timestamp ile döndürür.
        
        Args:
            symbol: Trading pair
            target_timestamp: Unix timestamp (saniye)
            
        Returns:
            (O zaman noktasındaki fiyat, timestamp) veya (None, None)
        """
        # Sembol whitelist kontrolü
        if not self.is_valid_symbol(symbol):
            self.logger.warning(
                f"Geçersiz sembol (historical): symbol={symbol}"
            )
            return None, None

        try:
            # 1 saatlik veri çek (daha az API çağrısı)
            df = self.fetch_ohlcv(symbol, '1h', limit=50)
            if df is None or df.empty:
                return None, None
            
            # Target timestamp'i datetime'a çevir
            target_dt = pd.to_datetime(target_timestamp, unit='s')
            
            # En yakın mum'u bul
            df_sorted = df.sort_values('timestamp')
            
            # Target time'dan önceki en son mum'u bul
            before_target = df_sorted[df_sorted['timestamp'] <= target_dt]
            
            if before_target.empty:
                # Target time'dan sonraki ilk mum'u al
                after_target = df_sorted[df_sorted['timestamp'] > target_dt]
                if not after_target.empty:
                    price = float(after_target.iloc[0]['close'])
                    # Mum'un timestamp'ini al
                    mum_timestamp = int(after_target.iloc[0]['timestamp'].timestamp())
                    return price, mum_timestamp
                return None, None
            
            # En yakın mum'un close fiyatını döndür
            closest_mum = before_target.iloc[-1]
            price = float(closest_mum['close'])
            # Mum'un timestamp'ini al
            mum_timestamp = int(closest_mum['timestamp'].timestamp())
            
            self.logger.info(
                f"{symbol} - {target_dt.strftime('%Y-%m-%d %H:%M')} fiyatı: ${price:,.2f}"
            )
            
            return price, mum_timestamp
            
        except Exception as e:
            self.logger.error(
                f"{symbol} tarihsel fiyat alınırken hata: {str(e)}"
            )
            return None, None

