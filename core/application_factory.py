"""
ApplicationFactory: Factory creating application components.
Initializes all services and resolves dependencies.
"""
from typing import Dict, Any, Optional
from core.service_container import ServiceContainer
from config.config_manager import ConfigManager
from utils.logger import LoggerManager
from utils.retry_handler import RetryHandler
from data.market_data_manager import MarketDataManager
from data.coin_filter import CoinFilter
from analysis.technical_indicators import TechnicalIndicatorCalculator
from analysis.volume_analyzer import VolumeAnalyzer
from analysis.fibonacci_calculator import FibonacciCalculator
from analysis.adaptive_thresholds import AdaptiveThresholdManager
from analysis.signal_generator import SignalGenerator
from analysis.ranging_strategy_analyzer import RangingStrategyAnalyzer
from strategy.position_calculator import PositionCalculator
from strategy.risk_manager import RiskManager
from strategy.risk_reward_calculator import RiskRewardCalculator
from strategy.liquidation_safety_filter import LiquidationSafetyFilter
from bot.user_whitelist import UserWhitelist
from bot.message_formatter import MessageFormatter
from bot.telegram_bot_manager import TelegramBotManager
from scheduler.analysis_scheduler import AnalysisScheduler
from strategy.dynamic_entry_calculator import DynamicEntryCalculator
from scheduler.components.signal_scanner_manager import SignalScannerManager
from scheduler.components.signal_scanner_scheduler import SignalScannerScheduler
from data.signal_database import SignalDatabase
from data.signal_repository import SignalRepository
from scheduler.components.signal_tracker import SignalTracker
from scheduler.components.signal_tracker_scheduler import SignalTrackerScheduler


class ApplicationFactory:
    """Factory creating application components."""
    
    def __init__(self):
        """Initializes ApplicationFactory."""
        self.container = ServiceContainer()
        self.logger = LoggerManager().get_logger('ApplicationFactory')
    
    def create_application(self) -> Dict[str, Any]:
        """
        Creates all application components.
        
        Returns:
            Application components dict
        """
        self.logger.info("Creating application components...")
        
        # Config
        config = self._create_config()
        self.container.register_singleton(ConfigManager, config)
        
        # Logger
        logger = self._create_logger(config)
        self.container.register_singleton(LoggerManager, logger)
        
        # Retry Handler
        retry_handler = self._create_retry_handler(config)
        self.container.register_singleton(RetryHandler, retry_handler)
        
        # Data Layer
        market_data = self._create_market_data_manager(retry_handler)
        coin_filter = self._create_coin_filter(retry_handler)
        
        # Analysis Layer
        indicator_calc = self._create_technical_indicators(config)
        volume_analyzer = self._create_volume_analyzer(config)
        fib_calculator = self._create_fibonacci_calculator(config)
        threshold_manager = self._create_adaptive_thresholds(config)
        signal_generator = self._create_signal_generator(
            indicator_calc, volume_analyzer, threshold_manager, config, market_data
        )
        
        # Strategy Layer
        position_calc = self._create_position_calculator(fib_calculator)
        risk_manager = self._create_risk_manager(config)
        # Dynamic Entry Calculator
        dynamic_entry_calc = self._create_dynamic_entry_calculator(fib_calculator, position_calc)
        
        # Bot Layer
        user_whitelist = self._create_user_whitelist(config)
        message_formatter = self._create_message_formatter()
        
        # Command Handler removed
        
        # Create Telegram bot first (without reminder_manager)
        telegram_bot = self._create_telegram_bot(config)
        
        # Configure lifecycle notifications (channel + cache)
        try:
            telegram_bot.configure_lifecycle_notifications(config.telegram_channel_id, None)
        except Exception:
            pass
        
        # Signal Database System
        signal_database = self._create_signal_database()
        signal_repository = self._create_signal_repository(signal_database)
        
        # Signal Tracker System (Create before SignalScannerManager, will be injected)
        signal_tracker = self._create_signal_tracker(
            signal_repository, market_data, telegram_bot, message_formatter
        )
        signal_tracker_scheduler = self._create_signal_tracker_scheduler(signal_tracker, config)
        
        # Set SignalTracker to TelegramBotManager (for callback handler)
        telegram_bot.set_signal_tracker(signal_tracker)
        
        # Risk Reward Calculator
        risk_reward_calc = RiskRewardCalculator()
        self.container.register_singleton(RiskRewardCalculator, risk_reward_calc)
        
        # Liquidation Safety Filter
        liquidation_safety_filter = self._create_liquidation_safety_filter(config)
        
        # Signal Scanner System (Inject SignalTracker)
        signal_scanner_manager = self._create_signal_scanner_manager(
            coin_filter, market_data, signal_generator, dynamic_entry_calc, 
            message_formatter, telegram_bot, signal_repository, config,
            risk_reward_calc, liquidation_safety_filter, signal_tracker=signal_tracker
        )
        signal_scanner_scheduler = self._create_signal_scanner_scheduler(signal_scanner_manager)
        
        # Scheduler
        scheduler = self._create_analysis_scheduler(
            telegram_bot, signal_generator, message_formatter, 
            coin_filter, market_data, config
        )
        
        return {
            'config': config,
            'logger': logger,
            'retry_handler': retry_handler,
            'market_data': market_data,
            'coin_filter': coin_filter,
            'indicator_calc': indicator_calc,
            'volume_analyzer': volume_analyzer,
            'fib_calculator': fib_calculator,
            'threshold_manager': threshold_manager,
            'signal_generator': signal_generator,
            'position_calc': position_calc,
            'risk_manager': risk_manager,
            'dynamic_entry_calc': dynamic_entry_calc,
            'user_whitelist': user_whitelist,
            'message_formatter': message_formatter,
            'telegram_bot': telegram_bot,
            'scheduler': scheduler,
            'signal_scanner_manager': signal_scanner_manager,
            'signal_scanner_scheduler': signal_scanner_scheduler,
            'signal_database': signal_database,
            'signal_repository': signal_repository,
            'signal_tracker': signal_tracker,
            'signal_tracker_scheduler': signal_tracker_scheduler
        }
    
    def _create_config(self) -> ConfigManager:
        """Creates config manager."""
        return ConfigManager()
    
    def _create_logger(self, config: ConfigManager) -> LoggerManager:
        """Creates logger manager."""
        log_cfg = config.log_config
        return LoggerManager(
            log_dir=log_cfg['log_dir'],
            max_bytes=log_cfg['max_bytes'],
            backup_count=log_cfg['backup_count'],
            async_enabled=log_cfg['async_enabled'],
            rotation_type=log_cfg['rotation_type'],
            rotation_when=log_cfg['rotation_when'],
            rotation_interval=log_cfg['rotation_interval']
        )
    
    def _create_retry_handler(self, config: ConfigManager) -> RetryHandler:
        """Creates retry handler."""
        retry_cfg = config.retry_config
        return RetryHandler(
            max_attempts=retry_cfg['max_attempts'],
            backoff_base=retry_cfg['backoff_base'],
            initial_delay=retry_cfg['initial_delay']
        )
    
    def _create_market_data_manager(self, retry_handler: RetryHandler) -> MarketDataManager:
        """Creates market data manager."""
        return MarketDataManager(retry_handler)
    
    def _create_coin_filter(self, retry_handler: RetryHandler) -> CoinFilter:
        """Creates coin filter."""
        return CoinFilter(retry_handler)
    
    def _create_technical_indicators(self, config: ConfigManager) -> TechnicalIndicatorCalculator:
        """Creates technical indicators."""
        return TechnicalIndicatorCalculator(
            rsi_period=config.rsi_period,
            macd_fast=config.macd_fast,
            macd_slow=config.macd_slow,
            macd_signal=config.macd_signal,
            ema_short=config.ema_short,
            ema_medium=config.ema_medium,
            ema_long=config.ema_long,
            bb_period=config.bb_period,
            bb_std=config.bb_std,
            atr_period=config.atr_period,
            adx_period=config.adx_period
        )
    
    def _create_volume_analyzer(self, config: ConfigManager) -> VolumeAnalyzer:
        """Creates volume analyzer."""
        return VolumeAnalyzer(
            volume_ma_period=config.volume_ma_period,
            spike_threshold=config.volume_spike_threshold
        )
    
    def _create_fibonacci_calculator(self, config: ConfigManager) -> FibonacciCalculator:
        """Creates Fibonacci calculator."""
        return FibonacciCalculator(
            fib_levels=config.fib_levels,
            swing_lookback=config.swing_lookback
        )
    
    def _create_adaptive_thresholds(self, config: ConfigManager) -> AdaptiveThresholdManager:
        """Creates adaptive thresholds."""
        return AdaptiveThresholdManager(
            adx_weak_threshold=config.adx_thresholds['weak'],
            adx_strong_threshold=config.adx_thresholds['strong']
        )
    
    def _create_ranging_strategy_analyzer(self, config: ConfigManager) -> RangingStrategyAnalyzer:
        """Creates ranging strategy analyzer."""
        logger_manager = self.container.get_optional(LoggerManager)
        min_sl_percent = config.ranging_min_sl_percent
        
        # Debug: Log value from config
        if logger_manager:
            logger = logger_manager.get_logger("ApplicationFactory")
            logger.debug(
                f"Creating RangingStrategyAnalyzer with min_stop_distance_percent={min_sl_percent}% "
                f"(from config.ranging_min_sl_percent)"
            )
            return RangingStrategyAnalyzer(logger_manager, min_stop_distance_percent=min_sl_percent)
        return RangingStrategyAnalyzer(min_stop_distance_percent=min_sl_percent)
    
    def _create_signal_generator(self, indicator_calc: TechnicalIndicatorCalculator,
                                volume_analyzer: VolumeAnalyzer,
                                threshold_manager: AdaptiveThresholdManager,
                                config: ConfigManager,
                                market_data: MarketDataManager = None) -> SignalGenerator:
        """Creates signal generator."""
        ranging_analyzer = self._create_ranging_strategy_analyzer(config)
        self.container.register_singleton(RangingStrategyAnalyzer, ranging_analyzer)
        return SignalGenerator(
            indicator_calculator=indicator_calc,
            volume_analyzer=volume_analyzer,
            threshold_manager=threshold_manager,
            timeframe_weights=config.timeframe_weights,
            ranging_analyzer=ranging_analyzer,
            market_data_manager=market_data
        )
    
    def _create_position_calculator(self, fib_calculator: FibonacciCalculator) -> PositionCalculator:
        """Creates position calculator."""
        return PositionCalculator(fib_calculator)
    
    def _create_risk_manager(self, config: ConfigManager) -> RiskManager:
        """Creates risk manager."""
        return RiskManager(
            risk_low=config.risk_low,
            risk_medium=config.risk_medium,
            risk_high=config.risk_high,
            leverage_min=config.leverage_min,
            leverage_max=config.leverage_max
        )
    
    def _create_user_whitelist(self, config: ConfigManager) -> UserWhitelist:
        """Creates user whitelist."""
        return UserWhitelist(config.whitelist_ids)
    
    def _create_message_formatter(self) -> MessageFormatter:
        """Creates message formatter."""
        return MessageFormatter()
    
    # Command Handler creator removed
    
    def _create_telegram_bot(self, config: ConfigManager, 
                           reminder_manager: Optional[Any] = None) -> TelegramBotManager:
        """Creates Telegram bot."""
        return TelegramBotManager(
            token=config.telegram_token,
            reminder_manager=reminder_manager
        )
    
    def _create_analysis_scheduler(self, telegram_bot: TelegramBotManager,
                                 signal_generator: SignalGenerator,
                                 message_formatter: MessageFormatter,
                                 coin_filter: CoinFilter,
                                 market_data: MarketDataManager,
                                 config: ConfigManager) -> AnalysisScheduler:
        """Creates analysis scheduler."""
        return AnalysisScheduler(
            bot_manager=telegram_bot,
            signal_generator=signal_generator,
            formatter=message_formatter,
            coin_filter=coin_filter,
            market_data=market_data,
            channel_id=config.telegram_channel_id,
            top_count=config.top_coins_count,
            top_signals=config.top_signals_count
        )
    
    def _create_dynamic_entry_calculator(self, fib_calculator: FibonacciCalculator, 
                                       position_calc: PositionCalculator) -> DynamicEntryCalculator:
        """Creates dynamic entry calculator."""
        return DynamicEntryCalculator(fib_calculator, position_calc)
    
    def _create_signal_database(self) -> SignalDatabase:
        """Creates signal database."""
        return SignalDatabase()
    
    def _create_signal_repository(self, database: SignalDatabase) -> SignalRepository:
        """Creates signal repository."""
        return SignalRepository(database)
    
    def _create_liquidation_safety_filter(self, config: ConfigManager) -> LiquidationSafetyFilter:
        """Creates liquidation safety filter."""
        return LiquidationSafetyFilter(
            mmr=config.mmr,
            min_sl_liq_buffer=None  # will be read from .env (SAFETYFILTER_MIN_SL_LIQ_BUFFER)
        )
    
    def _create_signal_scanner_manager(self, coin_filter: CoinFilter,
                                     market_data: MarketDataManager,
                                     signal_generator: SignalGenerator,
                                     entry_calculator: DynamicEntryCalculator,
                                     message_formatter: MessageFormatter,
                                     bot_manager: TelegramBotManager,
                                     signal_repository: SignalRepository,
                                     config: ConfigManager,
                                     risk_reward_calc: RiskRewardCalculator,
                                     liquidation_safety_filter: LiquidationSafetyFilter,
                                     signal_tracker: Optional[SignalTracker] = None) -> SignalScannerManager:
        """Creates signal scanner manager."""
        return SignalScannerManager(
            coin_filter=coin_filter,
            market_data=market_data,
            signal_generator=signal_generator,
            entry_calculator=entry_calculator,
            message_formatter=message_formatter,
            bot_manager=bot_manager,
            channel_id=config.telegram_channel_id,
            signal_repository=signal_repository,
            confidence_threshold=config.confidence_threshold,  # from .env or default 0.69
            cooldown_hours=config.cooldown_hours,  # from .env or default 1
            risk_reward_calc=risk_reward_calc,  # Risk/Reward calculator
            ranging_min_sl_percent=config.ranging_min_sl_percent,
            liquidation_safety_filter=liquidation_safety_filter,  # Liquidation safety filter
            signal_tracker=signal_tracker  # SignalTracker instance (optional, for cooldown log updates)
        )
    
    def _create_signal_scanner_scheduler(self, scanner_manager: SignalScannerManager) -> SignalScannerScheduler:
        """Creates signal scanner scheduler."""
        return SignalScannerScheduler(scanner_manager)
    
    def _create_signal_tracker(self, signal_repository: SignalRepository,
                               market_data: MarketDataManager,
                               bot_manager: TelegramBotManager,
                               message_formatter: MessageFormatter) -> SignalTracker:
        """Creates signal tracker."""
        return SignalTracker(
            signal_repository=signal_repository,
            market_data=market_data,
            bot_manager=bot_manager,
            message_formatter=message_formatter
        )
    
    def _create_signal_tracker_scheduler(
        self, 
        signal_tracker: SignalTracker, 
        config: ConfigManager
    ) -> SignalTrackerScheduler:
        """Creates signal tracker scheduler."""
        interval_minutes = config.signal_tracker_interval_minutes
        return SignalTrackerScheduler(signal_tracker, interval_minutes=interval_minutes)
