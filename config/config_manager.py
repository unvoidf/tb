"""
ConfigManager: Uygulama konfigürasyonunu yöneten sınıf.
.env dosyasından environment variables okur ve sabit parametreleri tutar.
"""
import os
from typing import Dict, List
from dotenv import load_dotenv


class ConfigManager:
    """Merkezi konfigürasyon yöneticisi."""
    
    def __init__(self):
        """ConfigManager'ı başlatır ve .env dosyasını yükler."""
        load_dotenv()
        self._validate_env_variables()
        self._load_exchange_env()
        self._load_phase0_thresholds()
        self._load_phase1_env()
        self._load_technical_parameters()
        self._load_risk_parameters()
        self._load_fibonacci_levels()
        
    def _validate_env_variables(self) -> None:
        """Gerekli environment variable'ların varlığını kontrol eder."""
        required_vars = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHANNEL_ID']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            raise ValueError(
                f"Eksik environment variables: {', '.join(missing_vars)}"
            )

    def _load_exchange_env(self) -> None:
        """Binance/Futures ortam değişkenlerini ve mod anahtarını yükler."""
        self.binance_mode = os.getenv('BINANCE_MODE', 'testnet').lower()  # testnet|mainnet
        self.binance_api_key = os.getenv('BINANCE_API_KEY', '')
        self.binance_api_secret = os.getenv('BINANCE_API_SECRET', '')
        # Phase 0'da emir yok; anahtarlar boş olabilir. Phase 3'te zorunlu olacak.

        # HTTP ayarları
        try:
            self.recv_window_ms = int(os.getenv('BINANCE_RECV_WINDOW_MS', '5000'))
        except Exception:
            self.recv_window_ms = 5000
        try:
            self.http_timeout_ms = int(os.getenv('HTTP_TIMEOUT_MS', '10000'))
        except Exception:
            self.http_timeout_ms = 10000

    def _load_phase0_thresholds(self) -> None:
        """Phase 0 için latency ve clock drift eşikleri."""
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
        """Teknik analiz parametrelerini yükler."""
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
        """Risk yönetimi parametrelerini yükler."""
        self.risk_low = 0.01  # %1
        self.risk_medium = 0.03  # %3
        self.risk_high = 0.05  # %5
        self.leverage_min = 1
        self.leverage_max = 10
        
    def _load_fibonacci_levels(self) -> None:
        """Fibonacci seviyelerini yükler."""
        self.fib_levels = [0.236, 0.382, 0.618, 0.786]
        self.fib_extensions = [1.0, 1.618, 2.618]
        self.swing_lookback = 100
        
    @property
    def telegram_token(self) -> str:
        """Telegram bot token'ını döndürür."""
        return os.getenv('TELEGRAM_BOT_TOKEN')
    
    @property
    def telegram_channel_id(self) -> str:
        """Telegram kanal ID'sini döndürür."""
        return os.getenv('TELEGRAM_CHANNEL_ID')

    @property
    def confidence_threshold(self) -> float:
        """Sinyal eşiği (.env -> CONFIDENCE_THRESHOLD), yoksa 0.69.

        Örnek .env:
            CONFIDENCE_THRESHOLD=0.69
        """
        try:
            val = os.getenv('CONFIDENCE_THRESHOLD')
            return float(val) if val is not None else 0.69
        except Exception:
            return 0.69
    
    @property
    def cooldown_hours(self) -> int:
        """Cooldown süresi (.env -> COOLDOWN_HOURS), yoksa 1 saat.

        Örnek .env:
            COOLDOWN_HOURS=1
        """
        try:
            val = os.getenv('COOLDOWN_HOURS')
            return int(val) if val is not None else 1
        except Exception:
            return 1
    
    @property
    def signal_tracker_interval_minutes(self) -> int:
        """Signal tracker kontrol interval'i (.env -> SIGNAL_TRACKER_INTERVAL_MINUTES), yoksa 1 dakika.

        Örnek .env:
            SIGNAL_TRACKER_INTERVAL_MINUTES=1
        """
        try:
            val = os.getenv('SIGNAL_TRACKER_INTERVAL_MINUTES')
            return int(val) if val is not None else 1
        except Exception:
            return 1
    
    @property
    def timeframes(self) -> List[str]:
        """Analiz edilecek timeframe listesini döndürür."""
        return ['1h', '4h', '1d']
    
    @property
    def timeframe_weights(self) -> Dict[str, float]:
        """Timeframe ağırlıklarını döndürür."""
        return {'1h': 0.40, '4h': 0.35, '1d': 0.25}
    
    @property
    def top_coins_count(self) -> int:
        """Analiz edilecek top coin sayısını döndürür."""
        return 20
    
    @property
    def top_signals_count(self) -> int:
        """Raporlanacak top sinyal sayısını döndürür."""
        return 5
    
    @property
    def volume_spike_threshold(self) -> float:
        """Hacim spike eşiğini döndürür."""
        return 1.5
    
    @property
    def adx_thresholds(self) -> Dict[str, float]:
        """ADX eşiklerini döndürür."""
        return {'weak': 20, 'strong': 40}
    
    @property
    def retry_config(self) -> Dict[str, any]:
        """API retry konfigürasyonunu döndürür."""
        return {
            'max_attempts': 5,
            'backoff_base': 2,
            'initial_delay': 1
        }
    
    @property
    def log_config(self) -> Dict[str, any]:
        """Log konfigürasyonunu döndürür."""
        return {
            'max_bytes': 10 * 1024 * 1024,  # 10MB
            'backup_count': 5,
            'log_dir': 'logs'
        }

    def _load_phase1_env(self) -> None:
        """Phase 1 için mod ve kaldıraç ayarlarını .env'den okur."""
        self.position_mode = (os.getenv('POSITION_MODE', 'oneway').lower())  # oneway|hedge
        self.margin_mode = (os.getenv('MARGIN_MODE', 'isolated').lower())    # isolated|cross
        # Kaldıraç sabitleri
        try:
            self.leverage_global = int(os.getenv('LEVERAGE_GLOBAL', '5'))
        except Exception:
            self.leverage_global = 5
        # Sembol bazlı override: BTCUSDT:10,ETHUSDT:8
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
        """Whitelist user ID'lerini döndürür."""
        whitelist_str = os.getenv('WHITELIST_IDS', '')
        if not whitelist_str:
            return []  # Boş liste = tüm kullanıcılar
        
        try:
            return [int(uid.strip()) for uid in whitelist_str.split(',')]
        except ValueError:
            return []
    
    @property
    def admin_user_ids(self) -> List[int]:
        """Admin user ID'lerini döndürür (error notifications için)."""
        admin_str = os.getenv('ADMIN_USER_IDS', '')
        if not admin_str:
            return []
        
        try:
            return [int(uid.strip()) for uid in admin_str.split(',')]
        except ValueError:
            return []

