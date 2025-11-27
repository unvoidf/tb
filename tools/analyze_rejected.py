import os
import pandas as pd
import glob
from datetime import datetime
import json
import argparse
from typing import List, Dict

def load_rejected_signals(archive_dir: str, months: int = 1) -> pd.DataFrame:
    """
    Loads rejected signals from Parquet archives.
    
    Args:
        archive_dir: Root archive directory
        months: Number of recent months to load
        
    Returns:
        DataFrame containing rejected signals
    """
    rejected_dir = os.path.join(archive_dir, "rejected_signals")
    if not os.path.exists(rejected_dir):
        print(f"No rejected signals archive found at {rejected_dir}")
        return pd.DataFrame()
    
    # Get all parquet files
    files = sorted(glob.glob(os.path.join(rejected_dir, "*.parquet")), reverse=True)
    
    # Take recent files
    files_to_load = files[:months]
    
    dfs = []
    for f in files_to_load:
        try:
            df = pd.read_parquet(f)
            dfs.append(df)
        except Exception as e:
            print(f"Error reading {f}: {e}")
            
    if not dfs:
        return pd.DataFrame()
        
    return pd.concat(dfs, ignore_index=True)

def analyze_rejections(df: pd.DataFrame):
    """
    Analyzes rejection reasons and statistics.
    """
    if df.empty:
        print("No data to analyze.")
        return

    print("\n=== REJECTED SIGNALS ANALYSIS ===")
    print(f"Total Rejected Signals: {len(df)}")
    print(f"Time Range: {datetime.fromtimestamp(df['created_at'].min().astype(int))} to {datetime.fromtimestamp(df['created_at'].max().astype(int))}")
    
    print("\n--- Top Rejection Reasons ---")
    reason_counts = df['rejection_reason'].value_counts()
    print(reason_counts.head(10))
    
    print("\n--- Rejection by Direction ---")
    print(df['direction'].value_counts())
    
    # Parse JSON columns if they are strings
    if isinstance(df['score_breakdown'].iloc[0], str):
        # Sample analysis of score breakdown for a specific reason
        top_reason = reason_counts.index[0]
        print(f"\n--- Analysis for Top Reason: '{top_reason}' ---")
        
        subset = df[df['rejection_reason'] == top_reason]
        
        # Extract some metrics from JSON
        rsi_values = []
        adx_values = []
        
        for _, row in subset.iterrows():
            try:
                score = json.loads(row['score_breakdown'])
                if 'rsi_value' in score:
                    rsi_values.append(score['rsi_value'])
                if 'adx_value' in score:
                    adx_values.append(score['adx_value'])
            except:
                pass
                
        if rsi_values:
            avg_rsi = sum(rsi_values) / len(rsi_values)
            print(f"Average RSI for '{top_reason}': {avg_rsi:.2f}")
            
        if adx_values:
            avg_adx = sum(adx_values) / len(adx_values)
            print(f"Average ADX for '{top_reason}': {avg_adx:.2f}")

def main():
    parser = argparse.ArgumentParser(description="Analyze rejected signals from archive.")
    parser.add_argument("--dir", default="data/archive", help="Archive directory path")
    parser.add_argument("--months", type=int, default=1, help="Number of months to analyze")
    
    args = parser.parse_args()
    
    df = load_rejected_signals(args.dir, args.months)
    analyze_rejections(df)

if __name__ == "__main__":
    main()
