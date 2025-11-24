"""
ConfigManager: Class managing application configuration.
Reads environment variables from .env file and holds constant parameters.
"""
import os
from typing import Dict, List
from dotenv import load_dotenv


class ConfigManager:
    """Central configuration manager."""
    
    def __init__(self):
        """Initializes ConfigManager and loads .env file."""
        load_dotenv()
        self._validate_env_variables()
        self._load_exchange_env()
        self._load_phase0_thresholds()
        self._load_phase1_env()
        self._load_technical_parameters()
        self._load_risk_parameters()
        self._load_fibonacci_levels()
        
    def _validate_env_variables(self) -> None:
        """Checks for existence of required environment variables."""
        required_vars = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHANNEL_ID']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            raise ValueError(
                f"Missing environment variables: {', '.join(missing_vars)}"
            )

    def _load_exchange_env(self) -> None:
        """Loads Binance/Futures environment variables and mode key."""
        self.binance_mode = os.getenv('BINANCE_MODE', 'testnet').lower()  # testnet|mainnet
        self.binance_api_key = os.getenv('BINANCE_API_KEY', '')
        self.binance_api_secret = os.getenv('BINANCE_API_SECRET', '')
        # No orders in Phase 0; keys can be empty. Will be mandatory in Phase 3.

        # HTTP settings
        try:
            self.recv_window_ms = int(os.getenv('BINANCE_RECV_WINDOW_MS', '5000'))
        except Exception:
            self.recv_window_ms = 5000
        try:
            self.http_timeout_ms = int(os.getenv('HTTP_TIMEOUT_MS', '10000'))
        except Exception:
            self.http_timeout_ms = 10000

    def _load_phase0_thresholds(self) -> None:
        """Latency and clock drift thresholds for Phase 0."""
        try:
            self.clock_drift_warn_ms = int(os.getenv('CLOCK_DRIFT_WARN_MS', '1000'))
        except Exception:
            self.clock_drift_warn_ms = 1000
        try:
            self.clock_drift_crit_ms = int(os.getenv('CLOCK_DRIFT_CRIT_MS', '2000'))
        except Exception:
            self.clock_drift_crit_ms = 2000
        try:
            self.latency_warn_ms = int(os.getenv('LATENCY_WARN_MS', '300'))
        except Exception:
            self.latency_warn_ms = 300
        try:
            self.latency_crit_ms = int(os.getenv('LATENCY_CRIT_MS', '800'))
        except Exception:
            self.latency_crit_ms = 800
    
    def _load_technical_parameters(self) -> None:
        """Loads technical analysis parameters."""
        self.rsi_period = 14
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        self.ema_short = 20
        self.ema_medium = 50
        self.ema_long = 200
        self.bb_period = 20
        self.bb_std = 2
        self.atr_period = 14
        self.adx_period = 14
        self.volume_ma_period = 20
        
    def _load_risk_parameters(self) -> None:
        """Loads risk management parameters."""
        self.risk_low = 0.01  # %1
        self.risk_medium = 0.03  # %3
        self.risk_high = 0.05  # %5
        self.leverage_min = 1
        self.leverage_max = 10
    
    def _parse_float_list(self, env_var: str, default: List[float]) -> List[float]:
        """Parse comma-separated float list from environment variable."""
        val = os.getenv(env_var)
        if not val:
            return default
        try:
            return [float(x.strip()) for x in val.split(',') if x.strip()]
        except Exception:
            return default
    
    def _parse_int_list(self, env_var: str, default: List[int]) -> List[int]:
        """Parse comma-separated int list from environment variable."""
        val = os.getenv(env_var)
        if not val:
            return default
        try:
            return [int(x.strip()) for x in val.split(',') if x.strip()]
        except Exception:
            return default
    
    @property
    def optimize_risk_ranges(self) -> List[float]:
        """Risk ranges for Optimization engine."""
        default = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
        return self._parse_float_list('OPTIMIZE_RISK_RANGES', default)
    
    @property
    def optimize_leverage_ranges(self) -> List[int]:
        """Leverage ranges for Optimization engine."""
        default = [1, 2, 3, 4, 5, 7, 10, 12, 15, 20, 25, 30, 35, 40, 45, 50]
        return self._parse_int_list('OPTIMIZE_LEVERAGE_RANGES', default)
    
    @property
    def optimize_min_sl_liq_buffer(self) -> float:
        """Minimum buffer between SL and liquidation for Simulation engine (default: 0.01 = 1%)."""
        try:
            val = os.getenv('OPTIMIZE_MIN_SL_LIQ_BUFFER')
            return float(val) if val is not None else 0.01
        except Exception:
            return 0.01
    
    @property
    def safetyfilter_risk_ranges(self) -> List[float]:
        """Risk ranges for Liquidation safety filter."""
        default = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
        return self._parse_float_list('SAFETYFILTER_RISK_RANGES', default)
    
    @property
    def safetyfilter_leverage_ranges(self) -> List[int]:
        """Leverage ranges for Liquidation safety filter."""
        default = [1, 2, 3, 4, 5, 7, 10, 12, 15, 20]
        return self._parse_int_list('SAFETYFILTER_LEVERAGE_RANGES', default)
    
    @property
    def safetyfilter_min_sl_liq_buffer(self) -> float:
        """Minimum buffer between SL and liquidation (default: 0.01 = 1%)."""
        try:
            val = os.getenv('SAFETYFILTER_MIN_SL_LIQ_BUFFER')
            return float(val) if val is not None else 0.01
        except Exception:
            return 0.01
    
    @property
    def mmr(self) -> float:
        """Maintenance Margin Rate (default: 0.004 = 0.4%)."""
        try:
            val = os.getenv('MAINTENANCE_MARGIN_RATE')
            return float(val) if val is not None else 0.004
        except Exception:
            return 0.004
        
    def _load_fibonacci_levels(self) -> None:
        """Loads Fibonacci levels."""
        self.fib_levels = [0.236, 0.382, 0.618, 0.786]
        self.fib_extensions = [1.0, 1.618, 2.618]
        self.swing_lookback = 100
        
    @property
    def telegram_token(self) -> str:
        """Returns Telegram bot token."""
        return os.getenv('TELEGRAM_BOT_TOKEN')
    
    @property
    def telegram_channel_id(self) -> str:
        """Returns Telegram channel ID."""
        return os.getenv('TELEGRAM_CHANNEL_ID')
    
    @property
    def confidence_threshold(self) -> float:
        """Signal threshold (.env -> CONFIDENCE_THRESHOLD), else 0.69.
        
        DEPRECATED: Use confidence_threshold_long and confidence_threshold_short instead.
        This property is kept for backwards compatibility.

        Example .env:
            CONFIDENCE_THRESHOLD=0.69
        """
        try:
            val = os.getenv('CONFIDENCE_THRESHOLD')
            return float(val) if val is not None else 0.69
        except Exception:
            return 0.69
    
    @property
    def confidence_threshold_long(self) -> float:
        """LONG signal threshold (.env -> CONFIDENCE_THRESHOLD_LONG), else 0.90.
        
        LONG signals require higher confidence due to poor historical performance.
        Data: LONG 6.67% WR vs SHORT 36.84% WR

        Example .env:
            CONFIDENCE_THRESHOLD_LONG=0.90
        """
        try:
            val = os.getenv('CONFIDENCE_THRESHOLD_LONG')
            return float(val) if val is not None else 0.90
        except Exception:
            return 0.90
    
    @property
    def confidence_threshold_short(self) -> float:
        """SHORT signal threshold (.env -> CONFIDENCE_THRESHOLD_SHORT), else 0.69.

        Example .env:
            CONFIDENCE_THRESHOLD_SHORT=0.69
        """
        try:
            val = os.getenv('CONFIDENCE_THRESHOLD_SHORT')
            return float(val) if val is not None else 0.69
        except Exception:
            return 0.69
    
    @property
    def cooldown_hours(self) -> int:
        """Cooldown duration (.env -> COOLDOWN_HOURS), else 1 hour.

        Example .env:
            COOLDOWN_HOURS=1
        """
        try:
            val = os.getenv('COOLDOWN_HOURS')
            return int(val) if val is not None else 1
        except Exception:
            return 1
    
    @property
    def min_atr_percent(self) -> float:
        """Minimum ATR percentage (.env -> MIN_ATR_PERCENT), else 2.0.
        
        Signals with ATR below this threshold are rejected to avoid low-volatility
        false positives. Data shows 51.7% failure rate for ATR <2%.

        Example .env:
            MIN_ATR_PERCENT=2.0
        """
        try:
            val = os.getenv('MIN_ATR_PERCENT')
            return float(val) if val is not None else 2.0
        except Exception:
            return 2.0
    
    @property
    def signal_tracker_interval_minutes(self) -> int:
        """Signal tracker check interval (.env -> SIGNAL_TRACKER_INTERVAL_MINUTES), else 1 minute.

        Example .env:
            SIGNAL_TRACKER_INTERVAL_MINUTES=1
        """
        try:
            val = os.getenv('SIGNAL_TRACKER_INTERVAL_MINUTES')
            return int(val) if val is not None else 1
        except Exception:
            return 1
    
    @property
    def timeframes(self) -> List[str]:
        """Returns list of timeframes to analyze."""
        return ['1h', '4h', '1d']
    
    @property
    def timeframe_weights(self) -> Dict[str, float]:
        """Returns timeframe weights."""
        return {'1h': 0.40, '4h': 0.35, '1d': 0.25}
    
    @property
    def top_coins_count(self) -> int:
        """Returns number of top coins to analyze."""
        return 20
    
    @property
    def top_signals_count(self) -> int:
        """Returns number of top signals to report."""
        return 5
    
    @property
    def volume_spike_threshold(self) -> float:
        """Returns volume spike threshold."""
        return 1.5
    
    @property
    def adx_thresholds(self) -> Dict[str, float]:
        """Returns ADX thresholds."""
        return {'weak': 20, 'strong': 40}
    
    @property
    def retry_config(self) -> Dict[str, any]:
        """Returns API retry configuration."""
        return {
            'max_attempts': 5,
            'backoff_base': 2,
            'initial_delay': 1
        }

    @property
    def ranging_min_sl_percent(self) -> float:
        """
        Minimum stop distance for ranging strategy (as %).

        .env -> RANGING_MIN_SL_PERCENT (e.g., 0.5 -> 0.5%, 1 -> 1%)
        """
        try:
            val = os.getenv('RANGING_MIN_SL_PERCENT')
            if val is None:
                return 0.5
            parsed = float(val)
            return max(parsed, 0.1)  # at least 0.1%
        except Exception:
            return 0.5
    
    @property
    def log_config(self) -> Dict[str, any]:
        """Returns log configuration (reads from .env)."""
        # LOG_MAX_BYTES (default: 10MB)
        try:
            max_bytes_str = os.getenv('LOG_MAX_BYTES')
            max_bytes = int(max_bytes_str) if max_bytes_str else (10 * 1024 * 1024)  # 10MB default
        except (ValueError, TypeError):
            max_bytes = 10 * 1024 * 1024  # 10MB default
        
        # LOG_BACKUP_COUNT (default: 5)
        try:
            backup_count_str = os.getenv('LOG_BACKUP_COUNT')
            backup_count = int(backup_count_str) if backup_count_str else 5
        except (ValueError, TypeError):
            backup_count = 5
        
        # LOG_DIR (default: 'logs')
        log_dir = os.getenv('LOG_DIR', 'logs')
        
        # LOG_ASYNC_ENABLED (default: True)
        async_str = os.getenv('LOG_ASYNC_ENABLED', 'true').lower()
        async_enabled = async_str in ('true', '1', 'yes')
        
        # LOG_ROTATION_TYPE (default: 'both')
        rotation_type = os.getenv('LOG_ROTATION_TYPE', 'both').lower()
        if rotation_type not in ('size', 'time', 'both'):
            rotation_type = 'both'
        
        # LOG_ROTATION_WHEN (default: 'midnight')
        rotation_when = os.getenv('LOG_ROTATION_WHEN', 'midnight').lower()
        
        # LOG_ROTATION_INTERVAL (default: 1)
        try:
            rotation_interval_str = os.getenv('LOG_ROTATION_INTERVAL', '1')
            rotation_interval = int(rotation_interval_str)
        except (ValueError, TypeError):
            rotation_interval = 1
        
        return {
            'max_bytes': max_bytes,
            'backup_count': backup_count,
            'log_dir': log_dir,
            'async_enabled': async_enabled,
            'rotation_type': rotation_type,
            'rotation_when': rotation_when,
            'rotation_interval': rotation_interval
        }

    def _load_phase1_env(self) -> None:
        """Reads mode and leverage settings from .env for Phase 1."""
        self.position_mode = (os.getenv('POSITION_MODE', 'oneway').lower())  # oneway|hedge
        self.margin_mode = (os.getenv('MARGIN_MODE', 'isolated').lower())    # isolated|cross
        # Leverage constants
        try:
            self.leverage_global = int(os.getenv('LEVERAGE_GLOBAL', '5'))
        except Exception:
            self.leverage_global = 5
        # Symbol based override: BTCUSDT:10,ETHUSDT:8
        overrides_str = os.getenv('LEVERAGE_SYMBOL_OVERRIDES', '')
        self.leverage_symbol_overrides = {}
        if overrides_str:
            try:
                parts = [p.strip() for p in overrides_str.split(',') if p.strip()]
                for part in parts:
                    sym, val = part.split(':')
                    self.leverage_symbol_overrides[sym.strip().upper()] = int(val.strip())
            except Exception:
                self.leverage_symbol_overrides = {}
    
    @property
    def whitelist_ids(self) -> List[int]:
        """Returns whitelist user IDs."""
        whitelist_str = os.getenv('WHITELIST_IDS', '')
        if not whitelist_str:
            return []  # Empty list = all users
        
        try:
            return [int(uid.strip()) for uid in whitelist_str.split(',')]
        except ValueError:
            return []
    
    @property
    def admin_user_ids(self) -> List[int]:
        """Returns Admin user IDs (for error notifications)."""
        admin_str = os.getenv('ADMIN_USER_IDS', '')
        if not admin_str:
            return []
        
        try:
            return [int(uid.strip()) for uid in admin_str.split(',')]
        except ValueError:
            return []

