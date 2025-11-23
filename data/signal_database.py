"""
SignalDatabase: SQLite veritabanı yönetimi.
Sinyal takip sistemi için veritabanı bağlantısı ve şema oluşturma.
"""
import sqlite3
import os
import threading
import contextlib
from typing import Optional, Generator
from utils.logger import LoggerManager


class SignalDatabase:
    """SQLite veritabanı yönetimi."""
    
    def __init__(self, db_path: str = "data/signals.db"):
        """
        SignalDatabase'i başlatır.
        
        Args:
            db_path: Veritabanı dosya yolu
        """
        self.db_path = db_path
        self.logger = LoggerManager().get_logger('SignalDatabase')
        self._lock = threading.RLock()
        self._connection: Optional[sqlite3.Connection] = None
        
        # data/ klasörünü oluştur
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            self.logger.info(f"Veritabanı klasörü oluşturuldu: {db_dir}")
        
        # Veritabanı bağlantısı ve tablo oluşturma
        self._initialize_database()
    
    def _get_persistent_connection(self) -> sqlite3.Connection:
        """
        Persistent bağlantıyı döndürür veya oluşturur.
        Thread-safe değildir, caller lock almalı.
        """
        if self._connection is None:
            try:
                # check_same_thread=False: Farklı thread'lerden erişime izin ver (lock ile koruyacağız)
                self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
                self._connection.row_factory = sqlite3.Row
                # WAL mode performans ve concurrency için iyidir
                self._connection.execute("PRAGMA journal_mode=WAL;")
            except Exception as e:
                self.logger.error(f"Veritabanı bağlantı hatası: {str(e)}", exc_info=True)
                raise
        return self._connection

    def _initialize_database(self) -> None:
        """Veritabanını initialize eder ve tabloları oluşturur."""
        try:
            with self.get_db_context() as conn:
                cursor = conn.cursor()
                
                # signals tablosunu oluştur
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS signals (
                        signal_id TEXT PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        signal_price REAL NOT NULL,
                        confidence REAL NOT NULL,
                        atr REAL,
                        timeframe TEXT,
                        telegram_message_id INTEGER NOT NULL,
                        telegram_channel_id TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        tp1_price REAL,
                        tp2_price REAL,
                        tp3_price REAL,
                        tp1_hit INTEGER DEFAULT 0,
                        tp2_hit INTEGER DEFAULT 0,
                        tp3_hit INTEGER DEFAULT 0,
                        tp1_hit_at INTEGER,
                        tp2_hit_at INTEGER,
                        tp3_hit_at INTEGER,
                        sl1_price REAL,
                        sl1_5_price REAL,
                        sl2_price REAL,
                        sl1_hit INTEGER DEFAULT 0,
                        sl1_5_hit INTEGER DEFAULT 0,
                        sl2_hit INTEGER DEFAULT 0,
                        sl1_hit_at INTEGER,
                        sl1_5_hit_at INTEGER,
                        sl2_hit_at INTEGER,
                        signal_data TEXT,
                        entry_levels TEXT,
                        message_deleted INTEGER DEFAULT 0
                    )
                """)
                
                # Migration: Eğer message_deleted kolonu yoksa ekle
                try:
                    cursor.execute("ALTER TABLE signals ADD COLUMN message_deleted INTEGER DEFAULT 0")
                    self.logger.info("message_deleted kolonu eklendi (migration)")
                except sqlite3.OperationalError:
                    pass
                
                # Migration: Eğer signal_log kolonu yoksa ekle
                try:
                    cursor.execute("ALTER TABLE signals ADD COLUMN signal_log TEXT")
                    self.logger.info("signal_log kolonu eklendi (migration)")
                except sqlite3.OperationalError:
                    pass
                
                # Migration: MFE/MAE tracking kolonları
                for col in ['mfe_price REAL', 'mfe_at INTEGER', 'mae_price REAL', 'mae_at INTEGER', 'final_price REAL', 'final_outcome TEXT']:
                    try:
                        cursor.execute(f"ALTER TABLE signals ADD COLUMN {col}")
                        self.logger.info(f"{col.split()[0]} kolonu eklendi (migration)")
                    except sqlite3.OperationalError:
                        pass
                
                # Migration: Score breakdown kolonu
                try:
                    cursor.execute("ALTER TABLE signals ADD COLUMN signal_score_breakdown TEXT")
                    self.logger.info("signal_score_breakdown kolonu eklendi (migration)")
                except sqlite3.OperationalError:
                    pass
                
                # Migration: Market context kolonu
                try:
                    cursor.execute("ALTER TABLE signals ADD COLUMN market_context TEXT")
                    self.logger.info("market_context kolonu eklendi (migration)")
                except sqlite3.OperationalError:
                    pass
                
                # Migration: R-based distances kolonları
                for col in ['tp1_distance_r REAL', 'tp2_distance_r REAL', 'tp3_distance_r REAL', 'sl1_distance_r REAL', 'sl2_distance_r REAL']:
                    try:
                        cursor.execute(f"ALTER TABLE signals ADD COLUMN {col}")
                        self.logger.info(f"{col.split()[0]} kolonu eklendi (migration)")
                    except sqlite3.OperationalError:
                        pass
                
                # Migration: Alternative entry kolonları
                for col in ['optimal_entry_price REAL', 'conservative_entry_price REAL', 'optimal_entry_hit INTEGER DEFAULT 0', 'optimal_entry_hit_at INTEGER', 'conservative_entry_hit INTEGER DEFAULT 0', 'conservative_entry_hit_at INTEGER']:
                    try:
                        cursor.execute(f"ALTER TABLE signals ADD COLUMN {col}")
                        self.logger.info(f"{col.split()[0]} kolonu eklendi (migration)")
                    except sqlite3.OperationalError:
                        pass
                
                # signal_price_snapshots tablosu
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS signal_price_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        signal_id TEXT NOT NULL,
                        timestamp INTEGER NOT NULL,
                        price REAL NOT NULL,
                        source TEXT,
                        FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_signal_id ON signal_price_snapshots(signal_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON signal_price_snapshots(timestamp)")
                
                # rejected_signals tablosu
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS rejected_signals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        signal_price REAL NOT NULL,
                        created_at INTEGER NOT NULL,
                        rejection_reason TEXT NOT NULL,
                        score_breakdown TEXT,
                        market_context TEXT
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_rejected_symbol ON rejected_signals(symbol)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_rejected_created_at ON rejected_signals(created_at)")
                
                # signal_metrics_summary tablosu
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS signal_metrics_summary (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        period_start INTEGER NOT NULL,
                        period_end INTEGER NOT NULL,
                        total_signals INTEGER,
                        long_signals INTEGER,
                        short_signals INTEGER,
                        neutral_filtered INTEGER,
                        avg_confidence REAL,
                        tp1_hit_rate REAL,
                        tp2_hit_rate REAL,
                        tp3_hit_rate REAL,
                        sl1_hit_rate REAL,
                        sl2_hit_rate REAL,
                        avg_mfe_percent REAL,
                        avg_mae_percent REAL,
                        avg_time_to_first_target_hours REAL,
                        market_regime TEXT
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_summary_period ON signal_metrics_summary(period_start, period_end)")
                
                # İndeksler oluştur
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_symbol ON signals(symbol)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_created_at ON signals(created_at)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_telegram_message_id ON signals(telegram_message_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_active_signals ON signals(tp1_hit, tp2_hit, tp3_hit, sl1_hit, sl1_5_hit, sl2_hit)
                """)
                
                conn.commit()
                
                self.logger.info(f"Veritabanı initialize edildi: {self.db_path}")
            
        except Exception as e:
            self.logger.error(f"Veritabanı initialize hatası: {str(e)}", exc_info=True)
            raise
    
    def get_connection(self) -> sqlite3.Connection:
        """
        Legacy support: Yeni bir bağlantı döndürür.
        NOT: Bu metod her çağrıldığında yeni connection açar.
        Optimize edilmiş kullanım için get_db_context() kullanın.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            self.logger.error(f"Veritabanı bağlantı hatası: {str(e)}", exc_info=True)
            raise

    @contextlib.contextmanager
    def get_db_context(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Thread-safe veritabanı bağlantısı context manager.
        Persistent connection ve lock kullanır.
        
        Usage:
            with db.get_db_context() as conn:
                cursor = conn.cursor()
                ...
        """
        with self._lock:
            conn = self._get_persistent_connection()
            yield conn
            # Commit/Rollback caller sorumluluğunda olabilir ama
            # genelde repository içinde commit yapılıyor.
            # Burada connection'ı KAPATMIYORUZ.
    
    def close(self) -> None:
        """Veritabanı bağlantısını kapatır."""
        with self._lock:
            if self._connection:
                try:
                    self._connection.close()
                    self._connection = None
                    self.logger.info("Veritabanı bağlantısı kapatıldı.")
                except Exception as e:
                    self.logger.error(f"Veritabanı kapatma hatası: {str(e)}", exc_info=True)

