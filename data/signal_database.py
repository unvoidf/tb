"""
SignalDatabase: SQLite database management.
Database connection and schema creation for signal tracking system.
"""
import sqlite3
import os
import threading
import contextlib
from typing import Optional, Generator
from utils.logger import LoggerManager


class SignalDatabase:
    """SQLite database management."""
    
    def __init__(self, db_path: str = "data/signals.db"):
        """
        Initializes SignalDatabase.
        
        Args:
            db_path: Database file path
        """
        self.db_path = db_path
        self.logger = LoggerManager().get_logger('SignalDatabase')
        self._lock = threading.RLock()
        self._connection: Optional[sqlite3.Connection] = None
        
        # Create data/ directory
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            self.logger.info(f"Database directory created: {db_dir}")
        
        # Database connection and table creation
        self._initialize_database()
    
    def _get_persistent_connection(self) -> sqlite3.Connection:
        """
        Returns or creates persistent connection.
        Not thread-safe, caller must acquire lock.
        """
        if self._connection is None:
            try:
                # check_same_thread=False: Allow access from different threads (protected by lock)
                self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
                self._connection.row_factory = sqlite3.Row
                # WAL mode is good for performance and concurrency
                self._connection.execute("PRAGMA journal_mode=WAL;")
            except Exception as e:
                self.logger.error(f"Database connection error: {str(e)}", exc_info=True)
                raise
        return self._connection

    def _initialize_database(self) -> None:
        """Initializes database and creates tables."""
        try:
            with self.get_db_context() as conn:
                cursor = conn.cursor()
                
                # Create signals table
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
                        tp1_hit INTEGER DEFAULT 0,
                        tp2_hit INTEGER DEFAULT 0,
                        tp1_hit_at INTEGER,
                        tp2_hit_at INTEGER,
                        sl_price REAL,
                        sl_hit INTEGER DEFAULT 0,
                        sl_hit_at INTEGER,
                        signal_data TEXT,
                        entry_levels TEXT,
                        message_deleted INTEGER DEFAULT 0
                    )
                """)
                
                # Migration: Add message_deleted column if not exists
                try:
                    cursor.execute("ALTER TABLE signals ADD COLUMN message_deleted INTEGER DEFAULT 0")
                    self.logger.info("message_deleted column added (migration)")
                except sqlite3.OperationalError:
                    pass
                
                # Migration: Add signal_log column if not exists
                try:
                    cursor.execute("ALTER TABLE signals ADD COLUMN signal_log TEXT")
                    self.logger.info("signal_log column added (migration)")
                except sqlite3.OperationalError:
                    pass
                
                # Migration: MFE/MAE tracking columns
                for col in ['mfe_price REAL', 'mfe_at INTEGER', 'mae_price REAL', 'mae_at INTEGER', 'final_price REAL', 'final_outcome TEXT']:
                    try:
                        cursor.execute(f"ALTER TABLE signals ADD COLUMN {col}")
                        self.logger.info(f"{col.split()[0]} column added (migration)")
                    except sqlite3.OperationalError:
                        pass
                
                # Migration: Score breakdown column
                try:
                    cursor.execute("ALTER TABLE signals ADD COLUMN signal_score_breakdown TEXT")
                    self.logger.info("signal_score_breakdown column added (migration)")
                except sqlite3.OperationalError:
                    pass
                
                # Migration: Market context column
                try:
                    cursor.execute("ALTER TABLE signals ADD COLUMN market_context TEXT")
                    self.logger.info("market_context column added (migration)")
                except sqlite3.OperationalError:
                    pass
                
                # Migration: R-based distances columns
                for col in ['tp1_distance_r REAL', 'tp2_distance_r REAL', 'sl_distance_r REAL']:
                    try:
                        cursor.execute(f"ALTER TABLE signals ADD COLUMN {col}")
                        self.logger.info(f"{col.split()[0]} column added (migration)")
                    except sqlite3.OperationalError:
                        pass
                
                # Migration: Alternative entry columns
                for col in ['optimal_entry_price REAL', 'conservative_entry_price REAL', 'optimal_entry_hit INTEGER DEFAULT 0', 'optimal_entry_hit_at INTEGER', 'conservative_entry_hit INTEGER DEFAULT 0', 'conservative_entry_hit_at INTEGER']:
                    try:
                        cursor.execute(f"ALTER TABLE signals ADD COLUMN {col}")
                        self.logger.info(f"{col.split()[0]} column added (migration)")
                    except sqlite3.OperationalError:
                        pass
                
                # signal_price_snapshots table
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
                
                # rejected_signals table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS rejected_signals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        signal_id TEXT,
                        symbol TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        signal_price REAL NOT NULL,
                        created_at INTEGER NOT NULL,
                        rejection_reason TEXT NOT NULL,
                        rejected_reason TEXT,
                        score_breakdown TEXT,
                        market_context TEXT
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_rejected_symbol ON rejected_signals(symbol)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_rejected_created_at ON rejected_signals(created_at)")
                
                # signal_metrics_summary table
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
                        sl_hit_rate REAL,
                        avg_mfe_percent REAL,
                        avg_mae_percent REAL,
                        avg_time_to_first_target_hours REAL,
                        market_regime TEXT,
                        metrics_json TEXT
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_summary_period ON signal_metrics_summary(period_start, period_end)")
                
                # Create indexes
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
                    CREATE INDEX IF NOT EXISTS idx_active_signals ON signals(tp1_hit, tp2_hit, sl_hit)
                """)
                
                conn.commit()
                
                self.logger.info(f"Database initialized: {self.db_path}")
            
        except Exception as e:
            self.logger.error(f"Database initialization error: {str(e)}", exc_info=True)
            raise
    
    def get_connection(self) -> sqlite3.Connection:
        """
        Legacy support: Returns a new connection.
        NOTE: This method opens a new connection every time it is called.
        Use get_db_context() for optimized usage.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            self.logger.error(f"Database connection error: {str(e)}", exc_info=True)
            raise

    @contextlib.contextmanager
    def get_db_context(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Thread-safe database connection context manager.
        Uses persistent connection and lock.
        
        Usage:
            with db.get_db_context() as conn:
                cursor = conn.cursor()
                ...
        """
        with self._lock:
            conn = self._get_persistent_connection()
            yield conn
            # Commit/Rollback might be caller's responsibility but
            # usually commit is done within repository.
            # We do NOT close the connection here.
    
    def close(self) -> None:
        """Closes database connection."""
        with self._lock:
            if self._connection:
                try:
                    self._connection.close()
                    self._connection = None
                    self.logger.info("Database connection closed.")
                except Exception as e:
                    self.logger.error(f"Database closing error: {str(e)}", exc_info=True)

