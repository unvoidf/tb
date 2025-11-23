"""
MarketDataManager: Class that fetches market data from Binance.
Provides OHLCV data for different timeframes.
"""
import ccxt
import pandas as pd
import time
from typing import Optional, List, Dict, Tuple
from utils.logger import LoggerManager
from utils.retry_handler import RetryHandler
from utils.exchange_factory import ExchangeFactory


class MarketDataManager:
    """Manages market data from Binance API."""
    
    def __init__(self, retry_handler: RetryHandler):
        """
        Initializes MarketDataManager.
        
        Args:
            retry_handler: Retry mechanism instance
        """
        self.exchange = ExchangeFactory.create_binance_futures()
        self.retry_handler = retry_handler
        self.logger = LoggerManager().get_logger('MarketData')

        # Whitelist for valid symbols (exchange markets)
        try:
            markets = self.exchange.load_markets()
            self.valid_symbols = set(markets.keys())  # e.g. 'BTC/USDT'
        except Exception as e:
            self.logger.error(
                f"Markets could not be loaded: {str(e)}",
                exc_info=True
            )
            self.valid_symbols = set()

        # OHLCV cache: {(symbol, timeframe): (timestamp, df)}
        self._ohlcv_cache: Dict[Tuple[str, str], Tuple[float, pd.DataFrame]] = {}
        self._ohlcv_ttl_seconds: int = 300  # 5 minutes cache

    def is_valid_symbol(self, symbol: str) -> bool:
        """Checks symbol whitelist."""
        valid_symbols = getattr(self, 'valid_symbols', set())
        
        if not valid_symbols:
            self.logger.warning("valid_symbols is empty! Markets might not be loaded.")
            return False
        
        # Direct check
        if symbol in valid_symbols:
            return True
        
        # If symbol is already in futures format (BTC/USDT:USDT), 
        # check normal format too (BTC/USDT)
        if ':USDT' in symbol or ':USDC' in symbol:
            normalized = symbol.split(':')[0]  # BTC/USDT:USDT -> BTC/USDT
            if normalized in valid_symbols:
                return True
            
        # Normalize futures symbol format and check
        # (BTC/USDT -> BTC/USDT:USDT)
        futures_symbol = f"{symbol}:USDT"
        if futures_symbol in valid_symbols:
            return True
            
        return False
    
    def fetch_ohlcv(self, symbol: str, timeframe: str, 
                    limit: int = 200) -> Optional[pd.DataFrame]:
        """
        Fetches OHLCV data for the specified symbol.
        
        Args:
            symbol: Trading pair (e.g. 'BTC/USDT')
            timeframe: Timeframe ('1h', '4h', '1d')
            limit: Number of candles to fetch
            
        Returns:
            DataFrame containing OHLCV data or None
        """
        # Sembol whitelist kontrolü
        if not self.is_valid_symbol(symbol):
            self.logger.warning(
                f"Invalid symbol (not in whitelist): symbol={symbol} timeframe={timeframe}"
            )
            return None

        # Short-lived cache check
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
                self.logger.warning(f"Data not found for {symbol}")
                return None
            
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            self.logger.info(
                f"{symbol} - {timeframe}: {len(df)} candles fetched"
            )
            self.logger.debug(
                f"{symbol} - {timeframe}: head=\n{df.head(3)}"
            )
            
            # Write to cache
            self._ohlcv_cache[cache_key] = (now_ts, df)
            return df
            
        except ccxt.BadSymbol as e:
            # Do not retry on BadSymbol, log warning
            self.logger.warning(
                f"Invalid symbol: symbol={symbol} error={str(e)}"
            )
            return None
        except Exception as e:
            self.logger.error(
                f"Error fetching data for {symbol}: {str(e)}",
                exc_info=True
            )
            return None
    
    def fetch_multi_timeframe(self, symbol: str, 
                             timeframes: List[str],
                             limit: int = 200) -> Dict[str, pd.DataFrame]:
        """
        Fetches OHLCV data for multiple timeframes.
        Applies adaptive limit for 1d timeframe.
        
        Args:
            symbol: Trading pair
            timeframes: List of timeframes
            limit: Number of candles to fetch for each timeframe
            
        Returns:
            Dict of DataFrames by timeframe
        """
        result = {}
        
        for tf in timeframes:
            # Adaptive limit for 1d timeframe
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
        Fetches adaptive OHLCV data for 1d timeframe.
        Tries with ideal limit first, uses available data if not enough.
        
        Args:
            symbol: Trading pair
            timeframe: Timeframe (1d)
            ideal_limit: Ideal number of candles (200)
            
        Returns:
            OHLCV DataFrame or None
        """
        try:
            # Try with ideal limit first
            ohlcv = self.retry_handler.execute(
                self.exchange.fetch_ohlcv,
                symbol,
                timeframe,
                limit=ideal_limit
            )
            
            if not ohlcv:
                self.logger.warning(f"Data not found for {symbol} {timeframe}")
                return None
            
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Data quality check
            if not self._validate_ohlcv_quality(df, symbol, timeframe):
                self.logger.warning(f"{symbol} {timeframe} low data quality, skipping analysis")
                return None
            
            data_count = len(df)
            
            # Log message based on data amount
            if data_count >= ideal_limit:
                self.logger.info(
                    f"{symbol} - {timeframe}: {data_count} candles fetched (ideal)"
                )
            else:
                self.logger.info(
                    f"{symbol} - {timeframe}: {data_count} candles fetched "
                    f"(adaptive - {ideal_limit - data_count} days missing)"
                )
                
                # Coin age info
                first_date = df['timestamp'].iloc[0]
                days_old = (pd.Timestamp.now() - first_date).days
                self.logger.debug(
                    f"{symbol} futures age: {days_old} days "
                    f"(first date: {first_date.strftime('%Y-%m-%d')})"
                )
            
            self.logger.debug(
                f"{symbol} - {timeframe}: head=\n{df.head(3)}"
            )
            
            # Write to cache
            cache_key = (symbol, timeframe)
            now_ts = time.time()
            self._ohlcv_cache[cache_key] = (now_ts, df)
            
            return df
            
        except ccxt.BadSymbol as e:
            self.logger.warning(
                f"Invalid symbol: symbol={symbol} error={str(e)}"
            )
            return None
        except Exception as e:
            self.logger.error(
                f"Error fetching adaptive data for {symbol}: {str(e)}",
                exc_info=True
            )
            return None
    
    def _validate_ohlcv_quality(self, df: pd.DataFrame, symbol: str, timeframe: str) -> bool:
        """
        Validates OHLCV data quality.
        
        Args:
            df: OHLCV DataFrame
            symbol: Trading pair
            timeframe: Timeframe
            
        Returns:
            True if data is quality
        """
        try:
            # Empty data check
            if df.empty:
                self.logger.debug(f"{symbol} {timeframe}: Empty data")
                return False
            
            # NaN check
            nan_count = df.isnull().sum().sum()
            if nan_count > 0:
                self.logger.debug(f"{symbol} {timeframe}: {nan_count} NaN values found")
                return False
            
            # Zero price check
            zero_prices = ((df['open'] <= 0) | (df['high'] <= 0) | 
                          (df['low'] <= 0) | (df['close'] <= 0)).sum()
            if zero_prices > 0:
                self.logger.debug(f"{symbol} {timeframe}: {zero_prices} zero prices found")
                return False
            
            # Volume check
            zero_volume_count = (df['volume'] <= 0).sum()
            if zero_volume_count > len(df) * 0.5:  # More than 50% zero volume
                self.logger.debug(f"{symbol} {timeframe}: {zero_volume_count} zero volume ({len(df)} candles)")
                return False
            
            # OHLC logic check
            invalid_ohlc = ((df['high'] < df['low']) | 
                           (df['high'] < df['open']) | 
                           (df['high'] < df['close']) |
                           (df['low'] > df['open']) | 
                           (df['low'] > df['close'])).sum()
            if invalid_ohlc > 0:
                self.logger.debug(f"{symbol} {timeframe}: {invalid_ohlc} invalid OHLC")
                return False
            
            # Very low price change check (dead coin)
            price_changes = df['close'].pct_change().abs()
            low_volatility_count = (price_changes < 0.001).sum()  # Less than 0.1% change
            if low_volatility_count > len(df) * 0.8:  # More than 80% low volatility
                self.logger.debug(f"{symbol} {timeframe}: {low_volatility_count} low volatility ({len(df)} candles)")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"{symbol} {timeframe} data quality check error: {str(e)}")
            return False
    
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Returns current price of the symbol.
        
        Args:
            symbol: Trading pair
            
        Returns:
            Current price or None
        """
        # Symbol whitelist check
        if not self.is_valid_symbol(symbol):
            self.logger.warning(
                f"Invalid symbol (price): symbol={symbol}"
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
                f"Error fetching price for {symbol}: {str(e)}"
            )
            return None
    
    def get_latest_price_with_timestamp(self, symbol: str) -> Tuple[Optional[float], Optional[int]]:
        """
        Returns current price of the symbol with timestamp.
        
        Args:
            symbol: Trading pair
            
        Returns:
            (Current price, timestamp) or (None, None)
        """
        # Symbol whitelist check
        if not self.is_valid_symbol(symbol):
            self.logger.warning(
                f"Invalid symbol (price): symbol={symbol}"
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
                f"Error fetching price for {symbol}: {str(e)}"
            )
            return None, None
    
    def get_ticker_info(self, symbol: str) -> Optional[Dict]:
        """
        Returns detailed ticker info for the symbol.
        
        Args:
            symbol: Trading pair
            
        Returns:
            Ticker info dict or None
        """
        # Symbol whitelist check
        if not self.is_valid_symbol(symbol):
            self.logger.warning(
                f"Invalid symbol (ticker): symbol={symbol}"
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
                f"Error fetching ticker info for {symbol}: {str(e)}"
            )
            return None
    
    def get_historical_price(self, symbol: str, target_timestamp: int) -> Optional[float]:
        """
        Returns price at a specific point in time.
        
        Args:
            symbol: Trading pair
            target_timestamp: Unix timestamp (seconds)
            
        Returns:
            Price at that time point or None
        """
        # Symbol whitelist check
        if not self.is_valid_symbol(symbol):
            self.logger.warning(
                f"Invalid symbol (historical): symbol={symbol}"
            )
            return None

        try:
            # Fetch 1 hour of data (fewer API calls)
            df = self.fetch_ohlcv(symbol, '1h', limit=50)
            if df is None or df.empty:
                return None
            
            # Convert target timestamp to datetime
            target_dt = pd.to_datetime(target_timestamp, unit='s')
            
            # Find the closest candle
            df_sorted = df.sort_values('timestamp')
            
            # Find the last candle before target time
            before_target = df_sorted[df_sorted['timestamp'] <= target_dt]
            
            if before_target.empty:
                # Get the first candle after target time
                after_target = df_sorted[df_sorted['timestamp'] > target_dt]
                if not after_target.empty:
                    return float(after_target.iloc[0]['close'])
                return None
            
            # Return close price of the closest candle
            closest_mum = before_target.iloc[-1]
            price = float(closest_mum['close'])
            
            self.logger.info(
                f"{symbol} - {target_dt.strftime('%Y-%m-%d %H:%M')} price: ${price:,.2f}"
            )
            self.logger.debug(
                f"get_historical_price: target={target_dt}, chosen_close={price}, before_rows={len(before_target)}"
            )
            
            return price
            
        except Exception as e:
            self.logger.error(
                f"Error fetching historical price for {symbol}: {str(e)}"
            )
            return None
    
    def get_historical_price_with_timestamp(self, symbol: str, target_timestamp: int) -> Tuple[Optional[float], Optional[int]]:
        """
        Returns price at a specific point in time with timestamp.
        
        Args:
            symbol: Trading pair
            target_timestamp: Unix timestamp (seconds)
            
        Returns:
            (Price at that time point, timestamp) or (None, None)
        """
        # Symbol whitelist check
        if not self.is_valid_symbol(symbol):
            self.logger.warning(
                f"Invalid symbol (historical): symbol={symbol}"
            )
            return None, None

        try:
            # Fetch 1 hour of data (fewer API calls)
            df = self.fetch_ohlcv(symbol, '1h', limit=50)
            if df is None or df.empty:
                return None, None
            
            # Convert target timestamp to datetime
            target_dt = pd.to_datetime(target_timestamp, unit='s')
            
            # Find the closest candle
            df_sorted = df.sort_values('timestamp')
            
            # Find the last candle before target time
            before_target = df_sorted[df_sorted['timestamp'] <= target_dt]
            
            if before_target.empty:
                # Get the first candle after target time
                after_target = df_sorted[df_sorted['timestamp'] > target_dt]
                if not after_target.empty:
                    price = float(after_target.iloc[0]['close'])
                    # Get candle timestamp
                    mum_timestamp = int(after_target.iloc[0]['timestamp'].timestamp())
                    return price, mum_timestamp
                return None, None
            
            # Return close price of the closest candle
            closest_mum = before_target.iloc[-1]
            price = float(closest_mum['close'])
            # Get candle timestamp
            mum_timestamp = int(closest_mum['timestamp'].timestamp())
            
            self.logger.info(
                f"{symbol} - {target_dt.strftime('%Y-%m-%d %H:%M')} price: ${price:,.2f}"
            )
            
            return price, mum_timestamp
            
        except Exception as e:
            self.logger.error(
                f"Error fetching historical price for {symbol}: {str(e)}"
            )
            return None, None

