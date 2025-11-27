"""
CoinFilter: Volume-based coin filtering class.
Selects USDT pairs with the highest volume in the last 1 hour.
"""
import ccxt
import numpy as np
from typing import List, Dict
from utils.logger import LoggerManager
from utils.retry_handler import RetryHandler
from utils.exchange_factory import ExchangeFactory
from data.filters.coin_scorer import CoinScorer


class CoinFilter:
    """Performs volume-based coin filtering from Binance."""
    
    def __init__(self, retry_handler: RetryHandler):
        """
        Initializes CoinFilter.
        
        Args:
            retry_handler: Retry mechanism instance
        """
        self.exchange = ExchangeFactory.create_binance_futures()
        self.retry_handler = retry_handler
        self.logger = LoggerManager().get_logger('CoinFilter')
        self.coin_scorer = CoinScorer()
    
    def get_top_volume_coins(self, count: int = 20) -> List[str]:
        """
        Returns USDT pairs with the highest volume in the last 1 hour.
        
        Args:
            count: Number of coins to return
            
        Returns:
            List of symbols (e.g., ['BTC/USDT', 'ETH/USDT', ...])
        """
        try:
            # Fetch all tickers
            tickers = self.retry_handler.execute(
                self.exchange.fetch_tickers
            )
            self.logger.debug(f"tickers_count={len(tickers)}")
            
            # Filter USDT pairs
            usdt_pairs = self._filter_usdt_pairs(tickers)
            self.logger.debug(f"usdt_pairs_count={len(usdt_pairs)}")
            
            # Sort by volume and get top N
            sorted_pairs = self._sort_by_volume(usdt_pairs, count)
            self.logger.debug(f"sorted_pairs_topN={sorted_pairs[:3]}")
            
            symbols = [item['symbol'] for item in sorted_pairs]
            
            self.logger.info(
                f"Top {count} volume coins selected: {', '.join(symbols[:5])}..."
            )
            
            return symbols
            
        except Exception as e:
            self.logger.error(
                f"Coin filtering error: {str(e)}",
                exc_info=True
            )
            return self._get_fallback_coins(count)
    
    def _filter_usdt_pairs(self, tickers: Dict) -> List[Dict]:
        """
        Filters only USDT pairs.
        
        Args:
            tickers: All ticker info
            
        Returns:
            List of USDT pairs
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
        Leverage token check (UP, DOWN, BULL, BEAR etc.).
        
        Args:
            symbol: Trading pair
            
        Returns:
            True if leverage token
        """
        leverage_keywords = ['UP/', 'DOWN/', 'BULL/', 'BEAR/']
        return any(keyword in symbol for keyword in leverage_keywords)
    
    def _is_stablecoin(self, symbol: str) -> bool:
        """
        Stablecoin check (USDC, USDT, BUSD, DAI etc.).
        
        Args:
            symbol: Trading pair
            
        Returns:
            True if stablecoin
        """
        # Filter only real stablecoins
        stablecoins = ['USDC/USDT', 'BUSD/USDT', 'DAI/USDT', 'TUSD/USDT', 
                       'USDD/USDT', 'USDP/USDT', 'FDUSD/USDT', 'USDE/USDT']
        return symbol in stablecoins
    
    def _sort_by_volume(self, pairs: List[Dict], 
                       count: int) -> List[Dict]:
        """
        Sorts pairs by volume and returns top N.
        
        Args:
            pairs: List of coin pairs
            count: Number to return
            
        Returns:
            Sorted list
        """
        sorted_pairs = sorted(
            pairs,
            key=lambda x: x['volume'],
            reverse=True
        )
        return sorted_pairs[:count]
    
    def get_top_futures_coins(self, count: int = 50) -> List[str]:
        """
        Selects coins with Hybrid Dynamic Scan (Majors + Momentum).
        
        Args:
            count: Total number of coins to return (Default: 50)
            
        Returns:
            Futures coin symbol list (Majors + Momentum)
        """
        try:
            # Create futures exchange instance
            futures_exchange = ExchangeFactory.create_binance_futures()
            
            # Fetch futures tickers
            tickers = self.retry_handler.execute(
                futures_exchange.fetch_tickers
            )
            self.logger.debug(f"futures_tickers_count={len(tickers)}")
            
            # 1. Majors (Blue Chips) - Limit: 15
            # Most reliable coins with Smart Liquidity + Stability Score
            major_count = 15
            major_coins = self._get_smart_coins(tickers, major_count)
            self.logger.info(
                f"🏰 Majors ({len(major_coins)}): {', '.join(major_coins)}"
            )
            
            # 2. Momentum (Radar) - Limit: Remaining (e.g., 35)
            # "Active" coins with Price Change (Volatility) and Volume
            momentum_count = max(0, count - len(major_coins))
            momentum_coins = self._get_momentum_coins(tickers, momentum_count, exclude=major_coins)
            self.logger.info(
                f"📡 Radar ({len(momentum_coins)}): {', '.join(momentum_coins)}"
            )
            
            # Combine two lists
            combined_coins = list(set(major_coins + momentum_coins))
            
            self.logger.info(
                f"Hybrid Scan Total {len(combined_coins)} coins: {', '.join(combined_coins)}"
            )
            
            return combined_coins
            
        except Exception as e:
            self.logger.error(
                f"Hybrid coin filtering error: {str(e)}",
                exc_info=True
            )
            return self._get_futures_fallback_coins(count)

    def _get_momentum_coins(self, tickers: Dict, count: int, exclude: List[str] = []) -> List[str]:
        """
        Momentum (Radar) Filter: Selects active coins with high price change.
        
        Args:
            tickers: Ticker info
            count: Number of coins requested
            exclude: Coins to exclude (Majors list)
            
        Returns:
            Momentum coin symbol list
        """
        momentum_candidates = []
        
        for symbol, ticker in tickers.items():
            # Normalize futures symbol format
            normalized_symbol = symbol.replace(':USDT', '').replace(':USDC', '')
            
            # Skip if already in Majors list
            if normalized_symbol in exclude:
                continue
                
            # Basic filters (Leverage token, stablecoin, dead coin etc.)
            if not self._passes_quick_filters(normalized_symbol, ticker):
                continue
            
            # Momentum Criterion: Price Change (Absolute Value)
            # Captures both big drops (Oversold opportunity) and big pumps (Trend opportunity)
            price_change_percent = abs(float(ticker.get('percentage', 0) or 0))
            
            # Extra Criterion: Sufficient Volume (to avoid Pump/Dump traps)
            # Doesn't need to be as high as Majors but at least 5M USDT
            quote_volume = float(ticker.get('quoteVolume', 0) or 0)
            if quote_volume < 5000000: # 5M USDT
                continue
                
            momentum_candidates.append((normalized_symbol, price_change_percent))
            
        # Sort by price change (Most active on top)
        momentum_candidates.sort(key=lambda x: x[1], reverse=True)
        
        selected = [symbol for symbol, pct in momentum_candidates[:count]]
        return selected
    
    def _filter_futures_usdt_pairs(self, tickers: Dict) -> List[Dict]:
        """
        Filters Futures USDT pairs (without stablecoins).
        
        Args:
            tickers: Futures ticker info
            
        Returns:
            List of Futures USDT pairs
        """
        futures_pairs = []
        usdt_count = 0
        filtered_count = 0
        
        for symbol, ticker in tickers.items():
            # Normalize futures symbol format (LQTY/USDT:USDT -> LQTY/USDT)
            normalized_symbol = symbol.replace(':USDT', '').replace(':USDC', '')
            
            # Debug: Count USDT pairs
            if normalized_symbol.endswith('/USDT'):
                usdt_count += 1
                
                # Debug: Check filtering steps
                has_volume = ticker.get('quoteVolume') is not None
                is_leveraged = self._is_leveraged_token(normalized_symbol)
                is_stablecoin = self._is_stablecoin(normalized_symbol)
                is_excluded = self._is_futures_excluded(normalized_symbol)
                
                # Add dead coin check
                is_dead_coin = self._is_dead_coin(normalized_symbol, ticker)
                
                if (has_volume and 
                    not is_leveraged and 
                    not is_stablecoin and 
                    not is_excluded and
                    not is_dead_coin):  # Dead coin check added
                    
                    futures_pairs.append({
                        'symbol': normalized_symbol,  # Use normalized symbol
                        'volume': ticker['quoteVolume'],
                        'price': ticker.get('last', 0)
                    })
                    filtered_count += 1
                else:
                    # Debug: Log why filtered
                    self.logger.debug(
                        f"Futures {normalized_symbol} filtered: "
                        f"volume={has_volume}, leveraged={is_leveraged}, "
                        f"stablecoin={is_stablecoin}, excluded={is_excluded}, "
                        f"dead_coin={is_dead_coin}"
                    )
        
        self.logger.debug(f"Futures filtering: {usdt_count} USDT pairs, {filtered_count} passed filters")
        return futures_pairs
    
    def _is_futures_excluded(self, symbol: str) -> bool:
        """
        Coins to exclude in Futures.
        
        Args:
            symbol: Trading pair
            
        Returns:
            True if excluded
        """
        # Coins not in Futures or problematic
        excluded = [
            'LUNA/USDT', 'UST/USDT', 'FTT/USDT',  # Problematic coins
            'BUSD/USDT', 'USDC/USDT',  # Stablecoins
        ]
        return any(excluded_symbol in symbol for excluded_symbol in excluded)
    
    def _is_dead_coin(self, symbol: str, ticker: Dict) -> bool:
        """
        Checks for dead coins.
        
        Args:
            symbol: Coin symbol
            ticker: Ticker info
            
        Returns:
            True if dead coin
        """
        # Volume check - very low volume
        quote_volume = ticker.get('quoteVolume', 0)
        if quote_volume < 10000:  # Minimum 10K USDT volume
            self.logger.debug(f"Futures {symbol} filtered: volume={quote_volume} (too low)")
            return True
        
        # Price change check - no movement
        price_change_percent = abs(ticker.get('percentage', 0))
        if price_change_percent < 0.01:  # Less than 0.01% change
            self.logger.debug(f"Futures {symbol} filtered: price_change={price_change_percent}% (too low)")
            return True
        
        # Base volume check
        base_volume = ticker.get('baseVolume', 0)
        if base_volume < 1000:  # Minimum base volume
            self.logger.debug(f"Futures {symbol} filtered: base_volume={base_volume} (too low)")
            return True
        
        return False
    
    def _get_smart_coins(self, tickers: Dict, count: int) -> List[str]:
        """
        Coin selection with Smart Liquidity + Stability Score (optimized).
        
        Args:
            tickers: Ticker info
            count: Number of coins to return
            
        Returns:
            Selected coin symbols
        """
        # Get top 50 with quick filtering first
        quick_candidates = self._get_quick_candidates(tickers, 50)
        
        if len(quick_candidates) <= count:
            return [symbol for symbol, _ in quick_candidates]
        
        # Apply smart scoring only for top 50
        smart_candidates = []
        
        for symbol, ticker in quick_candidates:
            # Minimum data check
            if not self._has_sufficient_data(symbol):
                self.logger.debug(f"Smart selection {symbol}: insufficient data")
                continue
            
            # Smart scoring (using CoinScorer)
            liquidity_score = self.coin_scorer.calculate_liquidity_score(ticker)
            stability_score = self.coin_scorer.calculate_stability_score(ticker)
            # Volume pattern uses old method (requires OHLCV)
            volume_pattern_score = self._analyze_volume_pattern(symbol)
            
            # Filter coins with 0.0 stability score
            if stability_score == 0.0:
                self.logger.debug(f"Smart selection {symbol}: zero stability score")
                continue
            
            # Hybrid score (weighted)
            total_score = (
                liquidity_score * 0.5 +      # 50% - Liquidity
                stability_score * 0.3 +      # 30% - Stability
                volume_pattern_score * 0.2   # 20% - Volume pattern
            )
            
            # Minimum threshold
            if total_score >= 60:  # 60% minimum score
                smart_candidates.append((symbol, total_score, liquidity_score, stability_score, volume_pattern_score))
                self.logger.debug(
                    f"Smart score {symbol}: total={total_score:.1f}, "
                    f"liquidity={liquidity_score:.1f}, stability={stability_score:.1f}, "
                    f"pattern={volume_pattern_score:.1f}"
                )
        
        # Sort by score and get top N
        smart_candidates.sort(key=lambda x: x[1], reverse=True)
        selected = [symbol for symbol, total, liq, stab, pat in smart_candidates[:count]]
        
        # Debug: Log scores of selected coins
        for symbol, total, liq, stab, pat in smart_candidates[:count]:
            self.logger.debug(f"Selected {symbol}: total={total:.1f}, liq={liq:.1f}, stab={stab:.1f}, pat={pat:.1f}")
        
        return selected
    
    def _has_sufficient_data(self, symbol: str) -> bool:
        """Checks if coin has sufficient data for analysis."""
        try:
            # 21 days data check
            ohlcv_1d = self.exchange.fetch_ohlcv(symbol, '1d', limit=21)
            if len(ohlcv_1d) < 21:
                self.logger.debug(f"Data sufficiency {symbol}: insufficient 1d data ({len(ohlcv_1d)} < 21)")
                return False
            
            # 24 hours data check
            ohlcv_1h = self.exchange.fetch_ohlcv(symbol, '1h', limit=24)
            if len(ohlcv_1h) < 24:
                self.logger.debug(f"Data sufficiency {symbol}: insufficient 1h data ({len(ohlcv_1h)} < 24)")
                return False
                
            return True
        except Exception as e:
            self.logger.debug(f"Data sufficiency check failed for {symbol}: {e}")
            return False
    
    def _get_quick_candidates(self, tickers: Dict, limit: int) -> List[tuple]:
        """Get top N candidates with quick filtering."""
        candidates = []
        
        for symbol, ticker in tickers.items():
            # Normalize futures symbol format
            normalized_symbol = symbol.replace(':USDT', '').replace(':USDC', '')
            
            # Basic filters (without fetching OHLCV)
            if not self._passes_quick_filters(normalized_symbol, ticker):
                continue
            
            # Volume based score (quick)
            volume_score = ticker.get('quoteVolume', 0)
            candidates.append((normalized_symbol, ticker, volume_score))
        
        # Sort by volume and get top N
        candidates.sort(key=lambda x: x[2], reverse=True)
        return [(symbol, ticker) for symbol, ticker, _ in candidates[:limit]]
    
    def _passes_quick_filters(self, symbol: str, ticker: Dict) -> bool:
        """Quick filters (without fetching OHLCV)."""
        if not symbol.endswith('/USDT'):
            return False
        
        # Basic checks
        has_volume = ticker.get('quoteVolume') is not None
        is_leveraged = self._is_leveraged_token(symbol)
        is_stablecoin = self._is_stablecoin(symbol)
        is_excluded = self._is_futures_excluded(symbol)
        is_dead_coin = self._is_dead_coin(symbol, ticker)
        
        # Price check
        price = ticker.get('last', 0)
        is_price_healthy = self._is_price_healthy(price)
        
        # Volume threshold (quick check)
        volume = ticker.get('quoteVolume', 0)
        has_min_volume = volume >= 1000000  # 1M USDT minimum
        
        return (has_volume and not is_leveraged and not is_stablecoin and 
                not is_excluded and not is_dead_coin and is_price_healthy and has_min_volume)
    
    def _passes_basic_filters(self, symbol: str, ticker: Dict) -> bool:
        """Checks basic filters."""
        if not symbol.endswith('/USDT'):
            return False
        
        # Basic checks
        has_volume = ticker.get('quoteVolume') is not None
        is_leveraged = self._is_leveraged_token(symbol)
        is_stablecoin = self._is_stablecoin(symbol)
        is_excluded = self._is_futures_excluded(symbol)
        is_dead_coin = self._is_dead_coin(symbol, ticker)
        
        # Price check
        price = ticker.get('last', 0)
        is_price_healthy = self._is_price_healthy(price)
        
        return (has_volume and not is_leveraged and not is_stablecoin and 
                not is_excluded and not is_dead_coin and is_price_healthy)
    
    def _is_price_healthy(self, price: float) -> bool:
        """Healthy price range check."""
        # All price limits removed: Price is not an indicator of coin quality.
        # Liquidity, stability and volume pattern scores already provide sufficient filtering.
        # Old limits:
        #   - Lower limit: if price < 0.01: return False (very low priced coins)
        #   - Upper limit: if price > 50000: return False (BTC, ETH etc. high priced coins)
        # 
        # Pump&dump risk is filtered by volume, stability and dead_coin checks.
        
        return True
    
    def _analyze_volume_pattern(self, symbol: str) -> float:
        """Volume pattern analysis (20% weight)."""
        try:
            ohlcv_1h = self.exchange.fetch_ohlcv(symbol, '1h', limit=48)
            
            if len(ohlcv_1h) < 24:
                self.logger.debug(f"Volume pattern {symbol}: insufficient data ({len(ohlcv_1h)} hours < 24)")
                return 0
            
            # Binance futures OHLCV returns volume in base (contract) unit.
            # Convert to quote (USDT) by multiplying with average price for each candle.
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
            
            # Volume trend analysis (in USDT)
            recent_avg = sum(quote_volumes[-12:]) / 12  # Last 12 hours
            older_avg = sum(quote_volumes[-24:-12]) / 12  # Previous 12 hours
            
            # Volume increase trend (normalized)
            volume_trend_raw = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0
            
            # Normalize volume trend (between -1 and +1, then convert to 0-1)
            volume_trend_normalized = max(0, min(1, (volume_trend_raw + 1) / 2))  # Convert to 0-1 range and limit
            
            # Volume consistency (low std = good)
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
            self.logger.debug(f"Volume pattern error {symbol}: {e}")
            return 0
    
    def _get_futures_fallback_coins(self, count: int) -> List[str]:
        """
        Fallback coin list in case of Futures error.
        
        Args:
            count: Number of coins requested
            
        Returns:
            Default futures coin list
        """
        fallback = [
            'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT',
            'ADA/USDT', 'SOL/USDT', 'DOGE/USDT', 'DOT/USDT',
            'MATIC/USDT', 'LTC/USDT', 'AVAX/USDT', 'LINK/USDT',
            'UNI/USDT', 'ATOM/USDT', 'ETC/USDT', 'XLM/USDT',
            'ALGO/USDT', 'VET/USDT', 'FIL/USDT', 'TRX/USDT'
        ]
        
        self.logger.warning("Using futures fallback coin list")
        return fallback[:count]

    def _get_fallback_coins(self, count: int) -> List[str]:
        """
        Returns fallback coin list in case of error.
        
        Args:
            count: Number of coins requested
            
        Returns:
            Default major coin list
        """
        fallback = [
            'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT',
            'ADA/USDT', 'SOL/USDT', 'DOGE/USDT', 'DOT/USDT',
            'MATIC/USDT', 'LTC/USDT', 'AVAX/USDT', 'LINK/USDT',
            'UNI/USDT', 'ATOM/USDT', 'ETC/USDT', 'XLM/USDT',
            'ALGO/USDT', 'VET/USDT', 'FIL/USDT', 'TRX/USDT'
        ]
        
        self.logger.warning("Using fallback coin list")
        return fallback[:count]

