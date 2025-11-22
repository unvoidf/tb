#!/usr/bin/env python3
"""
Historical Simulator for TrendBot (Event-Driven) v2
------------------------------------------------
Replays past signals from signals.db to simulate portfolio performance.
Uses a strict chronological event stream (Entry -> Exit) to manage margin and PnL.
Implements ISOLATED MARGIN logic with Liquidation checks.

Usage:
    python tools/simulate.py [--send-telegram] [--summary] [--risk 1.0] [--leverage 5] [--balance 10000] [--commission 0.075]
"""
import os
import sys
import argparse

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.simulation import SimulationEngine, OptimizationEngine

# Default Configuration (can be overridden by CLI args)
DEFAULT_INITIAL_BALANCE = 10000.0
DEFAULT_RISK_PER_TRADE_PERCENT = 1.0
DEFAULT_LEVERAGE = 5
DEFAULT_COMMISSION_RATE = 0.075  # % per side (Binance default)
DEFAULT_MAINTENANCE_MARGIN_RATE = 0.004  # %0.4 (Binance default for small positions)


def main():
    """Main entry point for simulation CLI."""
    parser = argparse.ArgumentParser(description='TrendBot Event-Driven Simulator')
    parser.add_argument(
        '--send-telegram', 
        action='store_true', 
        help='Send report to Telegram Admin'
    )
    parser.add_argument(
        '--summary', 
        action='store_true', 
        help='Only output condensed summary report'
    )
    parser.add_argument(
        '--opt', 
        action='store_true', 
        help='Run optimization mode (parameter sweep)'
    )
    parser.add_argument(
        '--balance', 
        type=float, 
        default=DEFAULT_INITIAL_BALANCE, 
        help='Initial Balance (USDT)'
    )
    parser.add_argument(
        '--risk', 
        type=float, 
        default=DEFAULT_RISK_PER_TRADE_PERCENT, 
        help='Risk per trade (%)'
    )
    parser.add_argument(
        '--leverage', 
        type=int, 
        default=DEFAULT_LEVERAGE, 
        help='Leverage (x)'
    )
    parser.add_argument(
        '--commission', 
        type=float, 
        default=DEFAULT_COMMISSION_RATE, 
        help='Commission rate per side (%)'
    )
    parser.add_argument(
        '--mmr', 
        type=float, 
        default=DEFAULT_MAINTENANCE_MARGIN_RATE, 
        help='Maintenance Margin Rate (default: 0.004 = 0.4%)'
    )
    
    args = parser.parse_args()
    
    if args.send_telegram:
        # Check if user provided explicit risk/leverage parameters
        if (args.risk != DEFAULT_RISK_PER_TRADE_PERCENT or 
            args.leverage != DEFAULT_LEVERAGE):
            # User provided explicit parameters, use them instead of optimization
            print(
                f"📊 Belirtilen parametrelerle simülasyon çalıştırılıyor: "
                f"Risk %{args.risk} | Kaldıraç {args.leverage}x\n"
            )
            engine = SimulationEngine(
                initial_balance=args.balance,
                risk_per_trade=args.risk,
                leverage=args.leverage,
                commission_rate=args.commission,
                mmr=args.mmr
            )
            engine.run(
                send_telegram=True,
                summary_only=True,  # Always send summary when using --send-telegram
                manual_config={'risk': args.risk, 'leverage': args.leverage}
            )
        else:
            # Auto-optimize before sending to Telegram (only if no explicit params)
            print("🔍 Otomatik optimizasyon çalıştırılıyor...")
            opt_engine = OptimizationEngine(
                initial_balance=args.balance,
                commission_rate=args.commission,
                mmr=args.mmr
            )
            best_config = opt_engine.run_optimization(silent=True)
            print(
                f"✅ En iyi konfigürasyon bulundu: "
                f"Risk %{best_config['risk']} | Kaldıraç {best_config['leverage']}x\n"
            )
            
            # Run simulation with best parameters and send to Telegram
            engine = SimulationEngine(
                initial_balance=args.balance,
                risk_per_trade=best_config['risk'],
                leverage=best_config['leverage'],
                commission_rate=args.commission,
                mmr=args.mmr
            )
            engine.run(
                send_telegram=True,
                summary_only=True,
                auto_optimized=best_config
            )
    elif args.opt:
        # Explicit --opt flag: Show all rankings (top 10)
        opt_engine = OptimizationEngine(
            initial_balance=args.balance,
            commission_rate=args.commission,
            mmr=args.mmr
        )
        opt_engine.run_optimization(show_all_rankings=True, top_n=10)
    elif (args.risk != DEFAULT_RISK_PER_TRADE_PERCENT or 
          args.leverage != DEFAULT_LEVERAGE or 
          args.summary):
        # Explicit simulation parameters provided: Run normal simulation
        engine = SimulationEngine(
            initial_balance=args.balance,
            risk_per_trade=args.risk,
            leverage=args.leverage,
            commission_rate=args.commission,
            mmr=args.mmr
        )
        engine.run(
            send_telegram=False,
            summary_only=args.summary
        )
    else:
        # Default behavior: Run optimization with top 5 results
        opt_engine = OptimizationEngine(
            initial_balance=args.balance,
            commission_rate=args.commission,
            mmr=args.mmr
        )
        opt_engine.run_optimization(show_all_rankings=False, top_n=5)


if __name__ == "__main__":
    main()
