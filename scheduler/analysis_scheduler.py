"""
AnalysisScheduler: Saatlik otomatik analiz scheduler.
Her saat başı piyasa analizini yapıp kanala gönderir.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from typing import List
from utils.logger import LoggerManager
from bot.telegram_bot_manager import TelegramBotManager
from bot.command_handler import CommandHandler
from bot.message_formatter import MessageFormatter
from data.coin_filter import CoinFilter
from scheduler.components.hourly_analyzer import HourlyAnalyzer
from scheduler.components.signal_ranker import SignalRanker
from scheduler.components.channel_notifier import ChannelNotifier


class AnalysisScheduler:
    """Saatlik otomatik analiz scheduler."""
    
    def __init__(self,
                 bot_manager: TelegramBotManager,
                 command_handler: CommandHandler,
                 formatter: MessageFormatter,
                 coin_filter: CoinFilter,
                 market_data,
                 channel_id: str,
                 top_count: int = 20,
                 top_signals: int = 5):
        """
        AnalysisScheduler'ı başlatır.
        
        Args:
            bot_manager: Telegram bot manager
            command_handler: Komut handler
            formatter: Mesaj formatter
            coin_filter: Coin filter
            market_data: Market data manager
            channel_id: Telegram kanal ID
            top_count: Analiz edilecek coin sayısı
            top_signals: Raporlanacak top sinyal sayısı
        """
        self.bot_mgr = bot_manager
        self.cmd_handler = command_handler
        self.formatter = formatter
        self.coin_filter = coin_filter
        self.market_data = market_data
        self.channel_id = channel_id
        self.top_count = top_count
        self.top_signals = top_signals
        self.scheduler = BackgroundScheduler()
        self.logger = LoggerManager().get_logger('Scheduler')
        
        # Bileşenleri initialize et
        self._initialize_components()
    
    def _initialize_components(self) -> None:
        """Scheduler bileşenlerini initialize eder."""
        self.hourly_analyzer = HourlyAnalyzer(self.coin_filter, self.cmd_handler)
        self.signal_ranker = SignalRanker()
        self.channel_notifier = ChannelNotifier(self.bot_mgr, self.formatter, self.market_data)
    
    def run_hourly_analysis(self) -> None:
        """
        Saatlik analizi çalıştırır ve kanala gönderir.
        """
        try:
            self.logger.info("Saatlik analiz başlatıldı")
            
            # Top coinleri analiz et
            all_signals = self.hourly_analyzer.analyze_top_coins(self.top_count)
            
            if not all_signals:
                self.logger.warning("Hiç sinyal üretilemedi")
                return
            
            # Sinyalleri sırala ve filtrele
            top_signals = self.signal_ranker.rank_signals(all_signals, self.top_signals)
            
            if not top_signals:
                self.logger.warning("Filtrelenmiş sinyal bulunamadı")
                return
            
            # Kanala gönder
            success = self.channel_notifier.send_hourly_analysis(top_signals, self.channel_id)
            
            if success:
                self.logger.info("Saatlik analiz başarıyla tamamlandı")
            else:
                self.logger.error("Saatlik analiz kanala gönderilemedi")
            
        except Exception as e:
            self.logger.error(f"Saatlik analiz hatası: {str(e)}", exc_info=True)
    
    def start(self) -> None:
        """
        Scheduler'ı başlatır.
        Her saat başı (XX:00) analiz çalıştırır.
        """
        # Her saat başı trigger
        # self.scheduler.add_job(
        #     self.run_hourly_analysis,
        #     trigger=CronTrigger(minute=0),
        #     id='hourly_analysis',
        #     name='Saatlik Piyasa Analizi',
        #     replace_existing=True
        # )
        
        self.scheduler.start()
        self.logger.info("Scheduler başlatıldı - Her saat başı analiz")
    
    def stop(self) -> None:
        """Scheduler'ı durdurur."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            self.logger.info("Scheduler durduruldu")
