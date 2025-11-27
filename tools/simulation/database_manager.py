"""
Archive Manager
---------------
Manages parquet archive file reading for simulation.
Loads signals from parquet archive files instead of SQLite database.
"""
import os
import sys
import glob
from typing import List, Dict, Any
import copy
import pandas as pd
import pyarrow.parquet as pq

ARCHIVE_DIR = "data/archive/signals"


class DatabaseManager:
    """Manages archive operations for simulation (reads from parquet files)."""
    
    def __init__(self, archive_dir: str = ARCHIVE_DIR):
        """
        Initialize Archive Manager.
        
        Args:
            archive_dir: Directory containing parquet archive files.
        """
        self.archive_dir = archive_dir
    
    def _get_parquet_files(self) -> List[str]:
        """
        Gets all parquet files from archive directory.
        
        Returns:
            List of parquet file paths, sorted by filename (chronological).
        """
        if not os.path.exists(self.archive_dir):
            print(f"❌ Archive directory not found at {self.archive_dir}")
            sys.exit(1)
        
        pattern = os.path.join(self.archive_dir, "*.parquet")
        files = glob.glob(pattern)
        files.sort()  # Sort by filename (YYYY-MM.parquet format ensures chronological order)
        return files
    
    def _convert_row_to_dict(self, row: pd.Series) -> Dict[str, Any]:
        """
        Converts pandas Series to dict with proper type conversion.
        
        Args:
            row: Pandas Series row from parquet file.
            
        Returns:
            Dictionary with properly typed values.
        """
        result = {}
        for key, value in row.items():
            # Convert string representations back to proper types
            if pd.isna(value) or value == 'None' or value == '':
                result[key] = None
            elif key in ['created_at', 'tp1_hit_at', 'tp2_hit_at', 'sl_hit_at', 
                         'mfe_at', 'mae_at', 'optimal_entry_hit_at', 'conservative_entry_hit_at']:
                # Timestamp fields - convert to int
                try:
                    result[key] = int(float(str(value))) if value else None
                except (ValueError, TypeError):
                    result[key] = None
            elif key in ['tp1_hit', 'tp2_hit', 'sl_hit', 'optimal_entry_hit', 
                         'conservative_entry_hit', 'message_deleted']:
                # Boolean/flag fields - convert to int
                try:
                    result[key] = int(float(str(value))) if value else 0
                except (ValueError, TypeError):
                    result[key] = 0
            elif key in ['signal_price', 'confidence', 'atr', 'tp1_price', 'tp2_price', 
                         'sl_price', 'mfe_price', 'mae_price', 'final_price',
                         'tp1_distance_r', 'tp2_distance_r', 'sl_distance_r',
                         'optimal_entry_price', 'conservative_entry_price']:
                # Numeric fields - convert to float
                try:
                    result[key] = float(str(value)) if value else None
                except (ValueError, TypeError):
                    result[key] = None
            elif key == 'telegram_message_id':
                # Integer field
                try:
                    result[key] = int(float(str(value))) if value else 0
                except (ValueError, TypeError):
                    result[key] = 0
            else:
                # String fields - keep as string
                result[key] = str(value) if value else None
        
        return result
    
    def load_all_signals(self) -> List[Dict[str, Any]]:
        """
        Loads all signals from parquet archive files as immutable snapshot.
        Combines all monthly parquet files and returns sorted by created_at.
        Returns deep-copied list of signals to prevent race conditions.
        
        Returns:
            List of signal dictionaries, sorted by created_at.
        """
        parquet_files = self._get_parquet_files()
        
        if not parquet_files:
            print(f"⚠️  No parquet files found in {self.archive_dir}")
            return []
        
        all_signals = []
        
        for file_path in parquet_files:
            try:
                # Read parquet file
                df = pd.read_parquet(file_path)
                
                # Convert each row to dict with proper type conversion
                for _, row in df.iterrows():
                    signal_dict = self._convert_row_to_dict(row)
                    all_signals.append(signal_dict)
                
            except Exception as e:
                print(f"⚠️  Error reading {file_path}: {str(e)}")
                continue
        
        # Sort by created_at (ascending)
        all_signals.sort(key=lambda x: x.get('created_at', 0) or 0)
        
        # Deep copy for immutability
        signals = [copy.deepcopy(signal) for signal in all_signals]
        
        return signals

