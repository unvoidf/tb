"""
BaseRepository: Repository helper metodları.
JSON temizleme ve row-to-dict dönüşüm fonksiyonları.
"""
import json
import sqlite3
from typing import Dict
from utils.logger import LoggerManager


class BaseRepository:
    """Repository için temel helper sınıfı."""
    
    def __init__(self):
        self.logger = LoggerManager().get_logger('BaseRepository')
    
    def clean_for_json(self, obj):
        """
        Dict'i JSON serialization için temizler.
        Numpy/pandas bool, int, float'ları Python native tiplerine çevirir.
        
        Args:
            obj: Temizlenecek obje (dict, list, veya primitive)
            
        Returns:
            Temizlenmiş obje
        """
        if isinstance(obj, dict):
            return {key: self.clean_for_json(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self.clean_for_json(item) for item in obj]
        elif isinstance(obj, (bool, int, float, str, type(None))):
            # Python native tipler zaten JSON serializable
            return obj
        else:
            # Numpy/pandas tipleri Python native'e çevir
            try:
                import numpy as np
                # Numpy bool tipleri (np.bool8 yeni versiyonlarda yok)
                if isinstance(obj, np.bool_):
                    return bool(obj)
                # Numpy bool8 kontrolü (eski versiyonlar için)
                if hasattr(np, 'bool8') and isinstance(obj, np.bool8):
                    return bool(obj)
                # Numpy integer tipleri
                if isinstance(obj, (np.integer, np.int_, np.intc, np.intp, np.int8,
                                     np.int16, np.int32, np.int64, np.uint8, np.uint16,
                                     np.uint32, np.uint64)):
                    return int(obj)
                # Numpy floating tipleri
                if isinstance(obj, (np.floating, np.float_, np.float16, np.float32, np.float64)):
                    return float(obj)
                # Numpy array
                if isinstance(obj, np.ndarray):
                    return obj.tolist()
            except (ImportError, AttributeError):
                pass
            
            # Pandas tipleri
            try:
                import pandas as pd
                if isinstance(obj, pd.Series):
                    return obj.tolist()
                elif isinstance(obj, pd.DataFrame):
                    return obj.to_dict('records')
            except ImportError:
                pass
            
            # Son çare: string'e çevir
            return str(obj)
    
    def row_to_dict(self, row: sqlite3.Row) -> Dict:
        """
        SQLite Row'u dict'e çevirir.
        
        Args:
            row: SQLite Row
            
        Returns:
            Dict
        """
        result = dict(row)
        
        # JSON string'leri parse et
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
        
        # signal_log JSON parse
        if result.get('signal_log'):
            try:
                result['signal_log'] = json.loads(result['signal_log'])
            except Exception:
                result['signal_log'] = []
        else:
            result['signal_log'] = []
        
        return result

