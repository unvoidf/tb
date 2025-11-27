"""
AnalysisScheduler: Hourly automatic analysis scheduler.
Performs market analysis every hour and sends to channel.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from typing import List
from utils.logger import LoggerManager
from bot.telegram_bot_manager import TelegramBotManager
from analysis.signal_generator import SignalGenerator
from bot.message_formatter import MessageFormatter
from data.coin_filter import CoinFilter
from scheduler.components.hourly_analyzer import HourlyAnalyzer
from scheduler.components.signal_ranker import SignalRanker
from scheduler.components.channel_notifier import ChannelNotifier


class AnalysisScheduler:
    """Hourly automatic analysis scheduler."""
    
    def __init__(self,
                 bot_manager: TelegramBotManager,
                 signal_generator: SignalGenerator,
                 formatter: MessageFormatter,
                 coin_filter: CoinFilter,
                 market_data,
                 channel_id: str,
                 top_count: int = 20,
                 top_signals: int = 5):
        """
        Initializes AnalysisScheduler.
        
        Args:
            bot_manager: Telegram bot manager
            signal_generator: Signal generator
            formatter: Message formatter
            coin_filter: Coin filter
            market_data: Market data manager
            channel_id: Telegram channel ID
            top_count: Number of coins to analyze
            top_signals: Number of top signals to report
        """
        self.bot_mgr = bot_manager
        self.signal_gen = signal_generator
        self.formatter = formatter
        self.coin_filter = coin_filter
        self.market_data = market_data
        self.channel_id = channel_id
        self.top_count = top_count
        self.top_signals = top_signals
        self.scheduler = BackgroundScheduler()
        self.logger = LoggerManager().get_logger('Scheduler')
        
        # Initialize components
        self._initialize_components()
    
    def _initialize_components(self) -> None:
        """Initializes scheduler components."""
        self.hourly_analyzer = HourlyAnalyzer(self.coin_filter, self.market_data, self.signal_gen)
        self.signal_ranker = SignalRanker()
        self.channel_notifier = ChannelNotifier(self.bot_mgr, self.formatter, self.market_data)
    
    def run_hourly_analysis(self) -> None:
        """
        Runs hourly analysis and sends to channel.
        """
        try:
            self.logger.info("Hourly analysis started")
            
            # Analyze top coins
            all_signals = self.hourly_analyzer.analyze_top_coins(self.top_count)
            
            if not all_signals:
                self.logger.warning("No signals generated")
                return
            
            # Rank and filter signals
            top_signals = self.signal_ranker.rank_signals(all_signals, self.top_signals)
            
            if not top_signals:
                self.logger.warning("No filtered signals found")
                return
            
            # Send to channel
            success = self.channel_notifier.send_hourly_analysis(top_signals, self.channel_id)
            
            if success:
                self.logger.info("Hourly analysis completed successfully")
            else:
                self.logger.error("Hourly analysis could not be sent to channel")
            
        except Exception as e:
            self.logger.error(f"Hourly analysis error: {str(e)}", exc_info=True)
    
    def start(self) -> None:
        """
        Starts the scheduler.
        Runs analysis every hour (XX:00).
        """
        # Trigger every hour
        # self.scheduler.add_job(
        #     self.run_hourly_analysis,
        #     trigger=CronTrigger(minute=0),
        #     id='hourly_analysis',
        #     name='Hourly Market Analysis',
        #     replace_existing=True
        # )
        
        self.scheduler.start()
        self.logger.info("Scheduler started - Hourly analysis")
    
    def stop(self) -> None:
        """Stops the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            self.logger.info("Scheduler stopped")
