"""
HourlyAnalyzer: Hourly analysis component.
Analyzes top coins and generates signals.
"""
from typing import List, Dict
from utils.logger import LoggerManager
from data.coin_filter import CoinFilter
from data.coin_filter import CoinFilter
from analysis.signal_generator import SignalGenerator
from data.market_data_manager import MarketDataManager


class HourlyAnalyzer:
    """Hourly analysis component."""
    
    def __init__(self, coin_filter: CoinFilter, market_data: MarketDataManager, signal_generator: SignalGenerator):
        """
        Initializes HourlyAnalyzer.
        
        Args:
            coin_filter: Coin filter
            market_data: Market data manager
            signal_generator: Signal generator
        """
        self.coin_filter = coin_filter
        self.market_data = market_data
        self.signal_gen = signal_generator
        self.logger = LoggerManager().get_logger('HourlyAnalyzer')
    
    def analyze_top_coins(self, top_count: int = 20) -> List[Dict]:
        """
        Analyzes top coins.
        
        Args:
            top_count: Number of coins to analyze
            
        Returns:
            List of analysis results
        """
        try:
            self.logger.info(f"Analyzing top {top_count} coins")
            
            # Get top volume coins
            symbols = self.coin_filter.get_top_volume_coins(top_count)
            
            if not symbols:
                self.logger.warning("Coin list could not be retrieved")
                return []
            
            # Generate signal for each coin
            all_signals = []
            
            for symbol in symbols:
                try:
                    # Fetch multi-timeframe data
                    timeframes = ['1h', '4h', '1d']
                    multi_tf_data = self.market_data.fetch_multi_timeframe(symbol, timeframes)
                    
                    if multi_tf_data:
                        signal_data = self.signal_gen.generate_signal(multi_tf_data, symbol=symbol)
                    else:
                        signal_data = None

                    if signal_data:
                        all_signals.append({
                            'symbol': symbol,
                            'signal': signal_data
                        })
                except Exception as e:
                    self.logger.error(f"{symbol} analysis error: {str(e)}")
            
            self.logger.info(f"Total {len(all_signals)} coins analyzed")
            return all_signals
            
        except Exception as e:
            self.logger.error(f"Hourly analysis error: {str(e)}", exc_info=True)
            return []
