"""
Database Manager
----------------
Manages database connections and signal queries for simulation.
"""
import sqlite3
import os
import sys
from typing import List, Dict, Any
import copy

DB_PATH = "data/signals.db"


class DatabaseManager:
    """Manages database operations for simulation."""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
    
    def get_connection(self):
        """Creates and returns a database connection."""
        if not os.path.exists(self.db_path):
            print(f"❌ Database not found at {self.db_path}")
            sys.exit(1)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def load_all_signals(self) -> List[Dict[str, Any]]:
        """
        Loads all signals from database as immutable snapshot.
        Returns deep-copied list of signals to prevent race conditions.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM signals ORDER BY created_at ASC")
        signals_raw = cursor.fetchall()
        conn.close()
        
        # Convert sqlite3.Row to dict, then deep copy for immutability
        signals = [copy.deepcopy(dict(signal)) for signal in signals_raw]
        return signals

