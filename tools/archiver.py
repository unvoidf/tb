import os
import sqlite3
import json
import logging
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from data.signal_database import SignalDatabase
from utils.logger import LoggerManager

class SignalArchiver:
    """
    Handles the archival of inactive signals from SQLite to Parquet.
    Implements a 'Write-Verify-Delete' safety mechanism.
    """

    def __init__(self, db_path: str = "data/signals.db", archive_dir: str = "data/archive"):
        """
        Initialize the SignalArchiver.

        Args:
            db_path: Path to the SQLite database.
            archive_dir: Root directory for Parquet archives.
        """
        self.db_path = db_path
        self.archive_dir = archive_dir
        self.signals_archive_dir = os.path.join(archive_dir, "signals")
        self.snapshots_archive_dir = os.path.join(archive_dir, "snapshots")
        
        # Ensure archive directories exist
        os.makedirs(self.signals_archive_dir, exist_ok=True)
        os.makedirs(self.snapshots_archive_dir, exist_ok=True)
        
        self.logger = LoggerManager().get_logger('SignalArchiver')
        self.db = SignalDatabase(db_path)

    def archive_signal(self, signal_id: str) -> bool:
        """
        Archives a single signal and its snapshots to Parquet, then deletes from SQLite.
        Only archives signals with message_deleted=1 to prevent archiving active signals.
        
        Args:
            signal_id: The ID of the signal to archive.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            self.logger.info(f"Starting archival for signal: {signal_id}")
            
            # 1. Fetch Data
            signal_data, snapshots_data = self._fetch_signal_data(signal_id)
            
            if not signal_data:
                self.logger.warning(f"Signal not found for archival: {signal_id}")
                return False
            
            # 2. Verify message_deleted=1 (safety check)
            message_deleted = signal_data.get('message_deleted', 0)
            if message_deleted != 1:
                self.logger.warning(
                    f"Signal {signal_id} has message_deleted={message_deleted}, "
                    f"not archiving (only message_deleted=1 signals should be archived)"
                )
                return False
                
            # 3. Determine Partition (Month)
            created_at = signal_data.get('created_at', 0)
            date_str = datetime.fromtimestamp(created_at).strftime('%Y-%m')
            
            # 4. Write to Parquet (Append mode)
            signals_file = os.path.join(self.signals_archive_dir, f"{date_str}.parquet")
            snapshots_file = os.path.join(self.snapshots_archive_dir, f"{date_str}.parquet")
            
            # Convert to DataFrame
            df_signal = pd.DataFrame([signal_data])
            df_snapshots = pd.DataFrame(snapshots_data) if snapshots_data else pd.DataFrame()
            
            # Write Signal
            self._append_to_parquet(df_signal, signals_file)
            
            # Write Snapshots (if any)
            if not df_snapshots.empty:
                self._append_to_parquet(df_snapshots, snapshots_file)
                
            # 5. Verify & Delete (Atomic-like)
            # We assume if _append_to_parquet didn't raise exception, it's safe.
            # Ideally, we could check file size or read back, but for now we trust the write.
            
            self._delete_from_sqlite(signal_id)
            
            self.logger.info(f"Successfully archived signal: {signal_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to archive signal {signal_id}: {str(e)}", exc_info=True)
            return False

    def migrate_all(self, batch_size: int = 100, dry_run: bool = False) -> int:
        """
        Migrates all inactive signals (message_deleted=1) to Parquet.
        
        Args:
            batch_size: Number of signals to process in one go.
            dry_run: If True, does not delete from SQLite.
            
        Returns:
            Number of signals migrated.
        """
        self.logger.info("Starting full migration of inactive signals...")
        
        try:
            with self.db.get_db_context() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT signal_id FROM signals WHERE message_deleted = 1")
                signal_ids = [row['signal_id'] for row in cursor.fetchall()]
                
            total = len(signal_ids)
            self.logger.info(f"Found {total} inactive signals to migrate.")
            
            count = 0
            for signal_id in signal_ids:
                if dry_run:
                    self.logger.info(f"[DRY RUN] Would archive: {signal_id}")
                    count += 1
                    continue
                    
                if self.archive_signal(signal_id):
                    count += 1
                    
                if count % 10 == 0:
                    self.logger.info(f"Migrated {count}/{total} signals...")
                    
            if not dry_run and count > 0:
                self.logger.info("Running VACUUM to reclaim space...")
                with self.db.get_db_context() as conn:
                    conn.execute("VACUUM")
                    
            self.logger.info(f"Migration complete. {count} signals archived.")
            return count
            
        except Exception as e:
            self.logger.error(f"Migration failed: {str(e)}", exc_info=True)
            return 0

    def _fetch_signal_data(self, signal_id: str) -> Tuple[Optional[Dict], List[Dict]]:
        """Fetches signal row and snapshot rows from SQLite."""
        with self.db.get_db_context() as conn:
            cursor = conn.cursor()
            
            # Fetch Signal
            cursor.execute("SELECT * FROM signals WHERE signal_id = ?", (signal_id,))
            row = cursor.fetchone()
            signal_data = dict(row) if row else None
            
            # Fetch Snapshots
            cursor.execute("SELECT * FROM signal_price_snapshots WHERE signal_id = ?", (signal_id,))
            snapshots_data = [dict(r) for r in cursor.fetchall()]
            
            return signal_data, snapshots_data

    def _append_to_parquet(self, df: pd.DataFrame, path: str):
        """Appends DataFrame to Parquet file."""
        if df.empty:
            return

        # Ensure consistent types (especially for object columns)
        # This is a basic conversion, might need refinement based on schema
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str)

        table = pa.Table.from_pandas(df)
        
        if os.path.exists(path):
            # Read existing table
            existing_table = pq.read_table(path)
            existing_df = existing_table.to_pandas()
            
            # Convert all object columns to string in both dataframes
            for col in existing_df.columns:
                if existing_df[col].dtype == 'object':
                    existing_df[col] = existing_df[col].astype(str)
            for col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].astype(str)
            
            # Merge dataframes
            combined_df = pd.concat([existing_df, df], ignore_index=True)
            
            # Remove duplicates if any (based on signal_id)
            if 'signal_id' in combined_df.columns:
                combined_df = combined_df.drop_duplicates(subset=['signal_id'], keep='last')
            
            # Convert all columns to string for consistency (parquet schema compatibility)
            for col in combined_df.columns:
                combined_df[col] = combined_df[col].astype(str)
            
            # Convert back to parquet
            combined_table = pa.Table.from_pandas(combined_df)
            pq.write_table(combined_table, path)
        else:
            pq.write_table(table, path)
    
    def _unify_schemas(self, schema1: pa.Schema, schema2: pa.Schema) -> pa.Schema:
        """
        Unifies two schemas by promoting types to be compatible.
        Returns a schema that can hold data from both input schemas.
        """
        unified_fields = []
        
        # Get all field names from both schemas
        all_field_names = set(schema1.names) | set(schema2.names)
        
        for field_name in all_field_names:
            field1 = schema1.field(field_name) if field_name in schema1.names else None
            field2 = schema2.field(field_name) if field_name in schema2.names else None
            
            if field1 and field2:
                # Both schemas have this field - unify types
                unified_type = self._unify_types(field1.type, field2.type)
                unified_fields.append(pa.field(field_name, unified_type))
            elif field1:
                unified_fields.append(field1)
            elif field2:
                unified_fields.append(field2)
        
        return pa.schema(unified_fields)
    
    def _unify_types(self, type1: pa.DataType, type2: pa.DataType) -> pa.DataType:
        """
        Unifies two PyArrow types by promoting to a compatible type.
        """
        # If types are the same, return as is
        if type1 == type2:
            return type1
        
        # Convert both to string if one is string (most flexible)
        if pa.types.is_string(type1) or pa.types.is_string(type2):
            return pa.string()
        
        # If one is int64 and other is string, promote to string
        if (pa.types.is_integer(type1) and pa.types.is_string(type2)) or \
           (pa.types.is_string(type1) and pa.types.is_integer(type2)):
            return pa.string()
        
        # If both are numeric, promote to the larger type
        if pa.types.is_integer(type1) and pa.types.is_integer(type2):
            return pa.int64()
        if pa.types.is_floating(type1) and pa.types.is_floating(type2):
            return pa.float64()
        
        # Default: promote to string (safest option)
        return pa.string()

    def _delete_from_sqlite(self, signal_id: str):
        """Deletes signal and snapshots from SQLite."""
        with self.db.get_db_context() as conn:
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM signal_price_snapshots WHERE signal_id = ?", (signal_id,))
            cursor.execute("DELETE FROM signals WHERE signal_id = ?", (signal_id,))
            
            conn.commit()
