"""
Unit Tests for Simulation Database Manager
------------------------------------------
Tests for DatabaseManager class.
"""
import pytest
import sqlite3
import os
import tempfile
from tools.simulation.database_manager import DatabaseManager


class TestDatabaseManager:
    """Test suite for DatabaseManager class."""
    
    def test_database_manager_initialization_default(self):
        """Test database manager initialization with default path."""
        manager = DatabaseManager()
        
        assert manager.db_path == "data/signals.db"
    
    def test_database_manager_initialization_custom_path(self):
        """Test database manager initialization with custom path."""
        custom_path = "custom/path.db"
        manager = DatabaseManager(db_path=custom_path)
        
        assert manager.db_path == custom_path
    
    def test_load_all_signals_empty_database(self, tmp_path):
        """Test loading signals from empty database."""
        # Create temporary database
        db_path = os.path.join(tmp_path, "test_signals.db")
        
        # Create database with signals table
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE signals (
                signal_id TEXT PRIMARY KEY,
                created_at INTEGER,
                symbol TEXT,
                direction TEXT,
                signal_price REAL
            )
        """)
        conn.commit()
        conn.close()
        
        # Test loading
        manager = DatabaseManager(db_path=db_path)
        signals = manager.load_all_signals()
        
        assert isinstance(signals, list)
        assert len(signals) == 0
    
    def test_load_all_signals_with_data(self, tmp_path):
        """Test loading signals from database with data."""
        # Create temporary database
        db_path = os.path.join(tmp_path, "test_signals.db")
        
        # Create database with signals table and data
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE signals (
                signal_id TEXT PRIMARY KEY,
                created_at INTEGER,
                symbol TEXT,
                direction TEXT,
                signal_price REAL
            )
        """)
        cursor.execute("""
            INSERT INTO signals (signal_id, created_at, symbol, direction, signal_price)
            VALUES ('TEST1', 1000000000, 'BTC/USDT', 'LONG', 50000.0)
        """)
        cursor.execute("""
            INSERT INTO signals (signal_id, created_at, symbol, direction, signal_price)
            VALUES ('TEST2', 1000000100, 'ETH/USDT', 'SHORT', 3000.0)
        """)
        conn.commit()
        conn.close()
        
        # Test loading
        manager = DatabaseManager(db_path=db_path)
        signals = manager.load_all_signals()
        
        assert isinstance(signals, list)
        assert len(signals) == 2
        assert signals[0]['signal_id'] == 'TEST1'
        assert signals[1]['signal_id'] == 'TEST2'
        # Should be sorted by created_at
        assert signals[0]['created_at'] <= signals[1]['created_at']
    
    def test_load_all_signals_deep_copy(self, tmp_path):
        """Test that loaded signals are deep copies."""
        # Create temporary database
        db_path = os.path.join(tmp_path, "test_signals.db")
        
        # Create database with signals table and data
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE signals (
                signal_id TEXT PRIMARY KEY,
                created_at INTEGER,
                symbol TEXT,
                direction TEXT,
                signal_price REAL
            )
        """)
        cursor.execute("""
            INSERT INTO signals (signal_id, created_at, symbol, direction, signal_price)
            VALUES ('TEST1', 1000000000, 'BTC/USDT', 'LONG', 50000.0)
        """)
        conn.commit()
        conn.close()
        
        # Test loading
        manager = DatabaseManager(db_path=db_path)
        signals = manager.load_all_signals()
        
        # Modify signal
        signals[0]['symbol'] = 'MODIFIED'
        
        # Reload should not be affected
        signals2 = manager.load_all_signals()
        assert signals2[0]['symbol'] == 'BTC/USDT'  # Original value

