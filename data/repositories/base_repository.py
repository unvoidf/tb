"""
BaseRepository: Repository helper methods.
JSON cleaning and row-to-dict conversion functions.
"""
import json
import sqlite3
from typing import Dict
from utils.logger import LoggerManager


class BaseRepository:
    """Base helper class for repositories."""
    
    def __init__(self):
        self.logger = LoggerManager().get_logger('BaseRepository')
    
    def clean_for_json(self, obj):
        """
        Cleans dict for JSON serialization.
        Converts Numpy/pandas bool, int, float to Python native types.
        
        Args:
            obj: Object to clean (dict, list, or primitive)
            
        Returns:
            Cleaned object
        """
        if isinstance(obj, dict):
            return {key: self.clean_for_json(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self.clean_for_json(item) for item in obj]
        elif isinstance(obj, (bool, int, float, str, type(None))):
            # Python native types are already JSON serializable
            return obj
        else:
            # Convert Numpy/pandas types to Python native
            try:
                import numpy as np
                # Numpy bool types (np.bool8 is missing in new versions)
                if isinstance(obj, np.bool_):
                    return bool(obj)
                # Numpy bool8 check (for older versions)
                if hasattr(np, 'bool8') and isinstance(obj, np.bool8):
                    return bool(obj)
                # Numpy integer types
                if isinstance(obj, (np.integer, np.int_, np.intc, np.intp, np.int8,
                                     np.int16, np.int32, np.int64, np.uint8, np.uint16,
                                     np.uint32, np.uint64)):
                    return int(obj)
                # Numpy floating types
                if isinstance(obj, (np.floating, np.float_, np.float16, np.float32, np.float64)):
                    return float(obj)
                # Numpy array
                if isinstance(obj, np.ndarray):
                    return obj.tolist()
            except (ImportError, AttributeError):
                pass
            
            # Pandas types
            try:
                import pandas as pd
                if isinstance(obj, pd.Series):
                    return obj.tolist()
                elif isinstance(obj, pd.DataFrame):
                    return obj.to_dict('records')
            except ImportError:
                pass
            
            # Last resort: convert to string
            return str(obj)
    
    def row_to_dict(self, row: sqlite3.Row) -> Dict:
        """
        Converts SQLite Row to dict.
        
        Args:
            row: SQLite Row
            
        Returns:
            Dict
        """
        result = dict(row)
        
        # Parse JSON strings
        if result.get('signal_data'):
            try:
                result['signal_data'] = json.loads(result['signal_data'])
            except Exception:
                result['signal_data'] = {}
        
        if result.get('entry_levels'):
            try:
                result['entry_levels'] = json.loads(result['entry_levels'])
            except Exception:
                result['entry_levels'] = {}
        
        # Keep backwards-compatible alias for score_breakdown
        if result.get('signal_score_breakdown') and 'score_breakdown' not in result:
            result['score_breakdown'] = result['signal_score_breakdown']
        
        r_aliases = {
            'tp1_distance_r': 'tp1_r',
            'tp2_distance_r': 'tp2_r',
            'sl_distance_r': 'sl_r'
        }
        for src, alias in r_aliases.items():
            if src in result and alias not in result:
                result[alias] = result[src]
        
        # signal_log JSON parse
        if result.get('signal_log'):
            try:
                result['signal_log'] = json.loads(result['signal_log'])
            except Exception:
                result['signal_log'] = []
        else:
            result['signal_log'] = []
        
        return result

