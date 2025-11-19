"""
SignalRepository: Sinyal veritabanı işlemleri.
CRUD işlemleri ve sinyal ID generation.
"""
import json
import sqlite3
import time
from datetime import datetime
from typing import Dict, List, Optional
from data.signal_database import SignalDatabase
from utils.logger import LoggerManager


class SignalRepository:
    """Sinyal veritabanı repository."""
    
    def __init__(self, database: SignalDatabase):
        """
        SignalRepository'yi başlatır.
        
        Args:
            database: SignalDatabase instance
        """
        self.db = database
        self.logger = LoggerManager().get_logger('SignalRepository')
    
    def generate_signal_id(self, symbol: str) -> str:
        """
        Timestamp-based unique signal ID oluşturur.
        
        Format: YYYYMMDD-HHMMSS-SYMBOL
        Örnek: 20241215-143022-BTCUSDT
        
        Args:
            symbol: Trading pair (örn: BTC/USDT)
            
        Returns:
            Unique signal ID
        """
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        symbol_clean = symbol.replace('/', '').replace(':', '').upper()
        signal_id = f"{timestamp}-{symbol_clean}"
        return signal_id
    
    def save_signal(
        self,
        signal_id: str,
        symbol: str,
        direction: str,
        signal_price: float,
        confidence: float,
        atr: Optional[float],
        timeframe: Optional[str],
        telegram_message_id: int,
        telegram_channel_id: str,
        tp1_price: Optional[float],
        tp2_price: Optional[float],
        tp3_price: Optional[float],
        sl1_price: Optional[float],
        sl1_5_price: Optional[float],
        sl2_price: Optional[float],
        signal_data: Dict,
        entry_levels: Dict,
        signal_score_breakdown: Optional[str] = None,
        market_context: Optional[str] = None,
        tp1_distance_r: Optional[float] = None,
        tp2_distance_r: Optional[float] = None,
        tp3_distance_r: Optional[float] = None,
        sl1_distance_r: Optional[float] = None,
        sl2_distance_r: Optional[float] = None,
        optimal_entry_price: Optional[float] = None,
        conservative_entry_price: Optional[float] = None
    ) -> bool:
        """
        Yeni sinyal kaydeder.
        
        Args:
            signal_id: Unique signal ID
            symbol: Trading pair
            direction: LONG/SHORT
            signal_price: Sinyal fiyatı
            confidence: Güven skoru
            atr: ATR değeri
            timeframe: Timeframe
            telegram_message_id: Telegram mesaj ID
            telegram_channel_id: Telegram kanal ID
            tp1_price, tp2_price, tp3_price: TP seviyeleri
            sl1_price, sl1_5_price, sl2_price: SL seviyeleri
            signal_data: Sinyal verisi dict (JSON'a çevrilecek)
            entry_levels: Entry levels dict (JSON'a çevrilecek)
            
        Returns:
            True ise başarılı
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            created_at = int(time.time())
            # JSON serialization için dict'leri temizle (numpy/pandas bool'ları Python bool'a çevir)
            signal_data_clean = self._clean_for_json(signal_data)
            entry_levels_clean = self._clean_for_json(entry_levels)
            signal_data_json = json.dumps(signal_data_clean)
            entry_levels_json = json.dumps(entry_levels_clean)
            
            cursor.execute("""
                INSERT INTO signals (
                    signal_id, symbol, direction, signal_price, confidence,
                    atr, timeframe, telegram_message_id, telegram_channel_id,
                    created_at, tp1_price, tp2_price, tp3_price,
                    sl1_price, sl1_5_price, sl2_price,
                    signal_data, entry_levels,
                    signal_score_breakdown, market_context,
                    tp1_distance_r, tp2_distance_r, tp3_distance_r,
                    sl1_distance_r, sl2_distance_r,
                    optimal_entry_price, conservative_entry_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal_id, symbol, direction, signal_price, confidence,
                atr, timeframe, telegram_message_id, telegram_channel_id,
                created_at, tp1_price, tp2_price, tp3_price,
                sl1_price, sl1_5_price, sl2_price,
                signal_data_json, entry_levels_json,
                signal_score_breakdown, market_context,
                tp1_distance_r, tp2_distance_r, tp3_distance_r,
                sl1_distance_r, sl2_distance_r,
                optimal_entry_price, conservative_entry_price
            ))
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Sinyal kaydedildi: {signal_id} - {symbol} {direction}")
            return True
            
        except Exception as e:
            self.logger.error(f"Sinyal kaydetme hatası: {str(e)}", exc_info=True)
            return False
    
    def get_signal(self, signal_id: str) -> Optional[Dict]:
        """
        Sinyal getirir.
        
        Args:
            signal_id: Signal ID
            
        Returns:
            Sinyal dict veya None
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM signals WHERE signal_id = ?
            """, (signal_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return self._row_to_dict(row)
            return None
            
        except Exception as e:
            self.logger.error(f"Sinyal getirme hatası: {str(e)}", exc_info=True)
            return None
    
    def get_active_signals(self) -> List[Dict]:
        """
        Aktif sinyalleri getirir (72 saatten yeni sinyaller).
        TP/SL durumuna bakılmaksızın, sadece 72 saat kontrolü yapılır.
        
        Returns:
            Aktif sinyal listesi
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # 72 saat = 259200 saniye
            hours_72_seconds = 72 * 3600
            
            # UTC timestamp al (sistem saatinden bağımsız)
            current_time_utc = int(time.time())
            threshold_time = current_time_utc - hours_72_seconds
            
            # 72 saatten yeni sinyaller (TP/SL durumundan bağımsız)
            # Mesaj silinmemiş sinyaller (message_deleted = 0)
            # Python'dan UTC timestamp kullanarak sistem saatinden bağımsız çalışır
            cursor.execute("""
                SELECT * FROM signals
                WHERE created_at > ? AND (message_deleted = 0 OR message_deleted IS NULL)
                ORDER BY created_at DESC
            """, (threshold_time,))
            
            rows = cursor.fetchall()
            active_count = len(rows)
            
            # 72 saatten eski sinyalleri say (logger için)
            cursor.execute("""
                SELECT COUNT(*) FROM signals
                WHERE created_at <= ?
            """, (threshold_time,))
            expired_count = cursor.fetchone()[0]
            
            conn.close()
            
            # Logger mesajları
            self.logger.debug(f"Aktif sinyal sorgusu: {active_count} aktif, {expired_count} eski (72 saatten eski, UTC timestamp: {current_time_utc})")
            if expired_count > 0:
                self.logger.info(f"{expired_count} sinyal 72 saatten eski olduğu için aktif listeden çıkarıldı")
            
            return [self._row_to_dict(row) for row in rows]
            
        except Exception as e:
            self.logger.error(f"Aktif sinyal getirme hatası: {str(e)}", exc_info=True)
            return []
    
    def get_last_signal_summary(self, symbol: str) -> Optional[Dict]:
        """Belirtilen sembol için en son aktif (mesajı silinmemiş) sinyalin özet bilgilerini döndürür."""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT symbol, direction, confidence, created_at
                FROM signals
                WHERE symbol = ?
                  AND (message_deleted = 0 OR message_deleted IS NULL)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (symbol,)
            )

            row = cursor.fetchone()
            conn.close()

            if row:
                summary = {
                    'symbol': row['symbol'],
                    'direction': row['direction'],
                    'confidence': row['confidence'],
                    'created_at': row['created_at']
                }
                self.logger.debug(
                    "Son sinyal özeti alındı: %s %s @ %s",
                    summary['symbol'],
                    summary['direction'],
                    summary['created_at']
                )
                return summary

            self.logger.debug("%s için sinyal özeti bulunamadı", symbol)
            return None

        except Exception as e:
            self.logger.error(f"Son sinyal özeti alma hatası: {str(e)}", exc_info=True)
            return None

    def get_recent_signal_summaries(self, lookback_hours: int) -> List[Dict]:
        """Belirtilen saat aralığında her sembol için en güncel sinyal özetini döndürür.
        
        Sadece aktif (mesajı silinmemiş) sinyalleri döndürür.
        """
        if lookback_hours <= 0:
            lookback_hours = 24

        try:
            threshold = int(time.time()) - (lookback_hours * 3600)
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT symbol, direction, confidence, created_at
                FROM signals
                WHERE created_at >= ? 
                  AND (message_deleted = 0 OR message_deleted IS NULL)
                ORDER BY created_at DESC
                """,
                (threshold,)
            )

            rows = cursor.fetchall()
            conn.close()

            summaries: List[Dict] = []
            processed_symbols = set()

            for row in rows:
                symbol = row['symbol']
                if symbol in processed_symbols:
                    continue

                summaries.append({
                    'symbol': symbol,
                    'direction': row['direction'],
                    'confidence': row['confidence'],
                    'created_at': row['created_at']
                })
                processed_symbols.add(symbol)

            self.logger.debug(
                "Cache warmup için %d sembol bulundu (lookback=%dh)",
                len(summaries),
                lookback_hours
            )
            return summaries

        except Exception as e:
            self.logger.error(f"Cache warmup verisi alma hatası: {str(e)}", exc_info=True)
            return []

    def update_tp_hit(
        self,
        signal_id: str,
        tp_level: int,
        hit_at: Optional[int] = None
    ) -> bool:
        """
        TP hit durumunu günceller.
        
        Args:
            signal_id: Signal ID
            tp_level: TP seviyesi (1, 2, veya 3)
            hit_at: Hit zamanı (Unix timestamp, None ise şu an)
            
        Returns:
            True ise başarılı
        """
        try:
            if hit_at is None:
                hit_at = int(time.time())
            
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            if tp_level == 1:
                cursor.execute("""
                    UPDATE signals
                    SET tp1_hit = 1, tp1_hit_at = ?
                    WHERE signal_id = ? AND tp1_hit = 0
                """, (hit_at, signal_id))
            elif tp_level == 2:
                cursor.execute("""
                    UPDATE signals
                    SET tp2_hit = 1, tp2_hit_at = ?
                    WHERE signal_id = ? AND tp2_hit = 0
                """, (hit_at, signal_id))
            elif tp_level == 3:
                cursor.execute("""
                    UPDATE signals
                    SET tp3_hit = 1, tp3_hit_at = ?
                    WHERE signal_id = ? AND tp3_hit = 0
                """, (hit_at, signal_id))
            else:
                self.logger.warning(f"Geçersiz TP level: {tp_level}")
                conn.close()
                return False
            
            conn.commit()
            rows_affected = cursor.rowcount
            conn.close()
            
            if rows_affected > 0:
                self.logger.info(f"TP{tp_level} hit güncellendi: {signal_id}")
                return True
            else:
                self.logger.debug(f"TP{tp_level} zaten hit veya sinyal bulunamadı: {signal_id}")
                return False
            
        except Exception as e:
            self.logger.error(f"TP hit güncelleme hatası: {str(e)}", exc_info=True)
            return False
    
    def update_sl_hit(
        self,
        signal_id: str,
        sl_level: str,
        hit_at: Optional[int] = None
    ) -> bool:
        """
        SL hit durumunu günceller.
        
        Args:
            signal_id: Signal ID
            sl_level: SL seviyesi ('1', '1.5', veya '2')
            hit_at: Hit zamanı (Unix timestamp, None ise şu an)
            
        Returns:
            True ise başarılı
        """
        try:
            if hit_at is None:
                hit_at = int(time.time())
            
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            if sl_level == '1':
                cursor.execute("""
                    UPDATE signals
                    SET sl1_hit = 1, sl1_hit_at = ?
                    WHERE signal_id = ? AND sl1_hit = 0
                """, (hit_at, signal_id))
            elif sl_level == '1.5':
                cursor.execute("""
                    UPDATE signals
                    SET sl1_5_hit = 1, sl1_5_hit_at = ?
                    WHERE signal_id = ? AND sl1_5_hit = 0
                """, (hit_at, signal_id))
            elif sl_level == '2':
                cursor.execute("""
                    UPDATE signals
                    SET sl2_hit = 1, sl2_hit_at = ?
                    WHERE signal_id = ? AND sl2_hit = 0
                """, (hit_at, signal_id))
            else:
                self.logger.warning(f"Geçersiz SL level: {sl_level}")
                conn.close()
                return False
            
            conn.commit()
            rows_affected = cursor.rowcount
            conn.close()
            
            if rows_affected > 0:
                self.logger.info(f"SL{sl_level} hit güncellendi: {signal_id}")
                return True
            else:
                self.logger.debug(f"SL{sl_level} zaten hit veya sinyal bulunamadı: {signal_id}")
                return False
            
        except Exception as e:
            self.logger.error(f"SL hit güncelleme hatası: {str(e)}", exc_info=True)
            return False
    
    def mark_message_deleted(self, signal_id: str) -> bool:
        """
        Sinyalin Telegram mesajının silindiğini işaretler.
        Bu sinyal artık aktif listede görünmeyecek.
        
        Args:
            signal_id: Signal ID
            
        Returns:
            True ise başarılı
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE signals
                SET message_deleted = 1
                WHERE signal_id = ?
            """, (signal_id,))
            
            conn.commit()
            rows_affected = cursor.rowcount
            conn.close()
            
            if rows_affected > 0:
                self.logger.info(f"Sinyal mesajı silindi olarak işaretlendi: {signal_id}")
                return True
            else:
                self.logger.warning(f"Sinyal bulunamadı (message_deleted): {signal_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Message deleted işaretleme hatası: {str(e)}", exc_info=True)
            return False
    
    def _clean_for_json(self, obj):
        """
        Dict'i JSON serialization için temizler.
        Numpy/pandas bool, int, float'ları Python native tiplerine çevirir.
        
        Args:
            obj: Temizlenecek obje (dict, list, veya primitive)
            
        Returns:
            Temizlenmiş obje
        """
        if isinstance(obj, dict):
            return {key: self._clean_for_json(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._clean_for_json(item) for item in obj]
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
    
    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
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
    
    def get_latest_active_signal_by_symbol_direction(
        self, symbol: str, direction: str
    ) -> Optional[Dict]:
        """
        Belirtilen sembol ve yön için en son aktif sinyali bulur.
        
        Args:
            symbol: Trading pair (örn: BTC/USDT)
            direction: LONG/SHORT
            
        Returns:
            Sinyal dict veya None
        """
        try:
            import time
            hours_72_seconds = 72 * 3600
            current_time_utc = int(time.time())
            threshold_time = current_time_utc - hours_72_seconds
            
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM signals
                WHERE symbol = ? 
                  AND direction = ?
                  AND created_at > ?
                  AND (message_deleted = 0 OR message_deleted IS NULL)
                ORDER BY created_at DESC
                LIMIT 1
            """, (symbol, direction, threshold_time))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                signal = self._row_to_dict(row)
                self.logger.debug(
                    "Aktif sinyal bulundu: %s %s @ %s (signal_id: %s)",
                    symbol, direction, signal.get('created_at'), signal.get('signal_id')
                )
                return signal
            
            self.logger.debug("%s %s için aktif sinyal bulunamadı", symbol, direction)
            return None
            
        except Exception as e:
            self.logger.error(
                f"Aktif sinyal bulma hatası ({symbol} {direction}): {str(e)}",
                exc_info=True
            )
            return None
    
    def add_signal_log_entry(
        self,
        signal_id: str,
        price: float,
        confidence: float,
        old_confidence: float,
        min_log_interval_seconds: int = 600,  # 10 dakika default
        min_confidence_change: float = 0.05  # %5 default
    ) -> bool:
        """
        Sinyal günlüğüne yeni entry ekler (cooldown sırasında yeni sinyal tespit edildiğinde).
        Flood'u önlemek için filtreleme uygular:
        - Son log entry'den en az min_log_interval_seconds geçmişse VEYA
        - Confidence değişikliği min_confidence_change eşiğini geçmişse
        - O zaman log ekler
        
        Args:
            signal_id: Aktif sinyal ID
            price: Yeni sinyal fiyatı
            confidence: Yeni sinyal güven skoru
            old_confidence: Aktif sinyalin güven skoru
            min_log_interval_seconds: Minimum log ekleme aralığı (saniye, default: 600 = 10 dakika)
            min_confidence_change: Minimum confidence değişikliği eşiği (default: 0.05 = %5)
            
        Returns:
            True ise başarılı, False ise filtreleme nedeniyle eklenmedi
        """
        try:
            import time
            current_time = int(time.time())
            # Floating point precision sorunlarını önlemek için yuvarlama yap
            # 6 decimal place'e yuvarla, ama çok küçük farkları da yakala
            raw_change = confidence - old_confidence
            confidence_change = round(raw_change, 6)
            
            # Eğer yuvarlama sonrası 0.0 olduysa ama raw_change 0 değilse,
            # çok küçük bir fark var demektir, onu koru
            if confidence_change == 0.0 and abs(raw_change) > 1e-10:
                # Çok küçük farkları da kaydet (örn: 0.76 - 0.759 = 0.001)
                confidence_change = raw_change
            
            # Mevcut sinyal bilgilerini al
            signal = self.get_signal(signal_id)
            if not signal:
                self.logger.warning(f"Sinyal bulunamadı (log ekleme): {signal_id}")
                return False
            
            # Mevcut signal_log'u al veya boş liste oluştur
            signal_log = signal.get('signal_log', [])
            if not isinstance(signal_log, list):
                signal_log = []
            
            # Flood önleme: Son log entry'yi kontrol et
            if signal_log:
                # Son entry'yi al (en son eklenen)
                last_entry = signal_log[-1]
                last_timestamp = last_entry.get('timestamp', 0)
                time_since_last = current_time - last_timestamp
                
                # Confidence değişikliğinin mutlak değerini al
                abs_confidence_change = abs(confidence_change)
                
                # Filtreleme: Sadece önemli değişikliklerde veya zaman aralığı dolduysa log ekle
                should_log = (
                    time_since_last >= min_log_interval_seconds or  # Zaman aralığı doldu
                    abs_confidence_change >= min_confidence_change  # Önemli confidence değişikliği
                )
                
                if not should_log:
                    # Log eklenmedi (filtreleme nedeniyle)
                    self.logger.debug(
                        f"Sinyal günlüğü entry'si atlandı (filtreleme): {signal_id} - "
                        f"son_log={time_since_last}s, confidence_change={confidence_change:+.3f}, "
                        f"min_interval={min_log_interval_seconds}s, min_change={min_confidence_change}"
                    )
                    return False
            
            # Yeni entry oluştur
            new_entry = {
                "timestamp": current_time,
                "event_type": "new_signal",
                "price": float(price),
                "confidence": float(confidence),
                "confidence_change": float(confidence_change)
            }
            
            # Entry'yi ekle
            signal_log.append(new_entry)
            
            # JSON'a çevir ve güncelle
            signal_log_json = json.dumps(signal_log)
            
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE signals
                SET signal_log = ?
                WHERE signal_id = ?
            """, (signal_log_json, signal_id))
            
            conn.commit()
            rows_affected = cursor.rowcount
            conn.close()
            
            if rows_affected > 0:
                self.logger.info(
                    f"Sinyal günlüğüne entry eklendi: {signal_id} - "
                    f"price={price}, confidence={confidence:.3f}, change={confidence_change:+.3f}"
                )
                return True
            else:
                self.logger.warning(f"Sinyal güncellenemedi (log ekleme): {signal_id}")
                return False
                
        except Exception as e:
            self.logger.error(
                f"Sinyal günlüğü entry ekleme hatası: {str(e)}",
                exc_info=True
            )
            return False
    
    def get_latest_confidence_change(self, signal_id: str) -> Optional[float]:
        """
        Signal log'dan en son confidence_change değerini döndürür.
        
        Args:
            signal_id: Sinyal ID
            
        Returns:
            En son confidence_change değeri veya None
        """
        try:
            signal = self.get_signal(signal_id)
            if not signal:
                return None
            
            signal_log = signal.get('signal_log', [])
            if not isinstance(signal_log, list) or not signal_log:
                return None
            
            # En son entry'yi al (timestamp'e göre sıralanmış olmalı)
            # Veya en son eklenen entry'yi al
            latest_entry = signal_log[-1]
            
            if latest_entry.get('event_type') == 'new_signal':
                confidence_change = latest_entry.get('confidence_change')
                if confidence_change is not None:
                    return float(confidence_change)
            
            return None
            
        except Exception as e:
            self.logger.error(
                f"En son confidence_change getirme hatası: {str(e)}",
                exc_info=True
            )
            return None
    
    def update_mfe_mae(
        self,
        signal_id: str,
        mfe_price: Optional[float],
        mfe_at: Optional[int],
        mae_price: Optional[float],
        mae_at: Optional[int]
    ) -> bool:
        """
        MFE/MAE günceller.
        
        Args:
            signal_id: Signal ID
            mfe_price: Maximum Favorable Excursion fiyatı
            mfe_at: MFE zamanı (unix timestamp)
            mae_price: Maximum Adverse Excursion fiyatı
            mae_at: MAE zamanı (unix timestamp)
            
        Returns:
            True ise başarılı
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE signals
                SET mfe_price = ?, mfe_at = ?, mae_price = ?, mae_at = ?
                WHERE signal_id = ?
            """, (mfe_price, mfe_at, mae_price, mae_at, signal_id))
            
            conn.commit()
            conn.close()
            
            self.logger.debug(f"MFE/MAE güncellendi: {signal_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"MFE/MAE güncelleme hatası: {str(e)}", exc_info=True)
            return False
    
    def update_alternative_entry_hit(
        self,
        signal_id: str,
        entry_type: str,
        hit_at: int
    ) -> bool:
        """
        optimal/conservative entry hit kaydeder.
        
        Args:
            signal_id: Signal ID
            entry_type: 'optimal' veya 'conservative'
            hit_at: Hit zamanı (unix timestamp)
            
        Returns:
            True ise başarılı
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            if entry_type == 'optimal':
                cursor.execute("""
                    UPDATE signals
                    SET optimal_entry_hit = 1, optimal_entry_hit_at = ?
                    WHERE signal_id = ?
                """, (hit_at, signal_id))
            elif entry_type == 'conservative':
                cursor.execute("""
                    UPDATE signals
                    SET conservative_entry_hit = 1, conservative_entry_hit_at = ?
                    WHERE signal_id = ?
                """, (hit_at, signal_id))
            else:
                self.logger.warning(f"Geçersiz entry_type: {entry_type}")
                return False
            
            conn.commit()
            conn.close()
            
            self.logger.debug(f"Alternative entry hit: {signal_id} - {entry_type}")
            return True
            
        except Exception as e:
            self.logger.error(f"Alternative entry hit güncelleme hatası: {str(e)}", exc_info=True)
            return False
    
    def finalize_signal(
        self,
        signal_id: str,
        final_price: float,
        final_outcome: str
    ) -> bool:
        """
        Sinyal kapanışı kaydeder.
        
        Args:
            signal_id: Signal ID
            final_price: Sinyal kapatma fiyatı
            final_outcome: 'tp1_reached', 'tp2_reached', 'tp3_reached',
                          'sl1_hit', 'sl2_hit', 'expired_no_target'
            
        Returns:
            True ise başarılı
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE signals
                SET final_price = ?, final_outcome = ?
                WHERE signal_id = ?
            """, (final_price, final_outcome, signal_id))
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Sinyal finalized: {signal_id} - {final_outcome} @ {final_price}")
            return True
            
        except Exception as e:
            self.logger.error(f"Sinyal finalize hatası: {str(e)}", exc_info=True)
            return False
    
    def save_price_snapshot(
        self,
        signal_id: str,
        timestamp: int,
        price: float,
        source: str
    ) -> bool:
        """
        Snapshot kaydeder.
        
        Args:
            signal_id: Signal ID
            timestamp: Unix timestamp
            price: Fiyat
            source: 'tracker_tick', 'manual_update', 'finalize'
            
        Returns:
            True ise başarılı
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO signal_price_snapshots (signal_id, timestamp, price, source)
                VALUES (?, ?, ?, ?)
            """, (signal_id, timestamp, price, source))
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Snapshot kayıt hatası: {str(e)}", exc_info=True)
            return False
    
    def save_rejected_signal(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        signal_price: float,
        rejection_reason: str,
        score_breakdown: Optional[str],
        market_context: Optional[str]
    ) -> bool:
        """
        Reddedilen sinyal kaydeder.
        
        Args:
            symbol: Trading pair
            direction: LONG/SHORT/NEUTRAL
            confidence: Güven skoru
            signal_price: Sinyal fiyatı
            rejection_reason: 'direction_neutral', 'cooldown_active', 'confidence_below_threshold'
            score_breakdown: JSON string
            market_context: JSON string
            
        Returns:
            True ise başarılı
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            created_at = int(time.time())
            
            cursor.execute("""
                INSERT INTO rejected_signals (
                    symbol, direction, confidence, signal_price,
                    created_at, rejection_reason, score_breakdown, market_context
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, direction, confidence, signal_price,
                  created_at, rejection_reason, score_breakdown, market_context))
            
            conn.commit()
            conn.close()
            
            self.logger.debug(f"Rejected signal kaydedildi: {symbol} - {rejection_reason}")
            return True
            
        except Exception as e:
            self.logger.error(f"Rejected signal kayıt hatası: {str(e)}", exc_info=True)
            return False
    
    def get_price_snapshots(self, signal_id: str) -> List[Dict]:
        """
        Sinyale ait tüm snapshot'ları döner.
        
        Args:
            signal_id: Signal ID
            
        Returns:
            Snapshot listesi
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM signal_price_snapshots
                WHERE signal_id = ?
                ORDER BY timestamp
            """, (signal_id,))
            
            rows = cursor.fetchall()
            conn.close()
            
            snapshots = [dict(row) for row in rows]
            return snapshots
            
        except Exception as e:
            self.logger.error(f"Snapshot getirme hatası: {str(e)}", exc_info=True)
            return []
    
    def save_metrics_summary(
        self,
        period_start: int,
        period_end: int,
        metrics: Dict
    ) -> bool:
        """
        Özet metrik kaydeder.
        
        Args:
            period_start: Dönem başlangıcı (unix timestamp)
            period_end: Dönem sonu (unix timestamp)
            metrics: Metrikler dict
            
        Returns:
            True ise başarılı
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO signal_metrics_summary (
                    period_start, period_end,
                    total_signals, long_signals, short_signals, neutral_filtered,
                    avg_confidence, tp1_hit_rate, tp2_hit_rate, tp3_hit_rate,
                    sl1_hit_rate, sl2_hit_rate,
                    avg_mfe_percent, avg_mae_percent,
                    avg_time_to_first_target_hours, market_regime
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                period_start, period_end,
                metrics.get('total_signals', 0),
                metrics.get('long_signals', 0),
                metrics.get('short_signals', 0),
                metrics.get('neutral_filtered', 0),
                metrics.get('avg_confidence', 0.0),
                metrics.get('tp1_hit_rate', 0.0),
                metrics.get('tp2_hit_rate', 0.0),
                metrics.get('tp3_hit_rate', 0.0),
                metrics.get('sl1_hit_rate', 0.0),
                metrics.get('sl2_hit_rate', 0.0),
                metrics.get('avg_mfe_percent', 0.0),
                metrics.get('avg_mae_percent', 0.0),
                metrics.get('avg_time_to_first_target_hours', 0.0),
                metrics.get('market_regime', 'unknown')
            ))
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Metrics summary kaydedildi: {period_start} - {period_end}")
            return True
            
        except Exception as e:
            self.logger.error(f"Metrics summary kayıt hatası: {str(e)}", exc_info=True)
            return False
    
    def get_signals_by_time_range(self, start_ts: int, end_ts: int) -> List[Dict]:
        """
        Belirli zaman aralığındaki sinyalleri döner.
        
        Args:
            start_ts: Başlangıç timestamp
            end_ts: Bitiş timestamp
            
        Returns:
            Sinyal listesi
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM signals
                WHERE created_at >= ? AND created_at <= ?
                ORDER BY created_at
            """, (start_ts, end_ts))
            
            rows = cursor.fetchall()
            conn.close()
            
            signals = []
            for row in rows:
                signal = dict(row)
                # Parse JSON fields
                if signal.get('signal_data'):
                    try:
                        signal['signal_data'] = json.loads(signal['signal_data'])
                    except:
                        pass
                if signal.get('entry_levels'):
                    try:
                        signal['entry_levels'] = json.loads(signal['entry_levels'])
                    except:
                        pass
                if signal.get('signal_log'):
                    try:
                        signal['signal_log'] = json.loads(signal['signal_log'])
                    except:
                        pass
                signals.append(signal)
            
            return signals
            
        except Exception as e:
            self.logger.error(f"Time range signals getirme hatası: {str(e)}", exc_info=True)
            return []

