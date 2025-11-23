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
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

# Add project root to path
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

from tools.simulation import SimulationEngine, OptimizationEngine

# Default Configuration (can be overridden by CLI args)
DEFAULT_INITIAL_BALANCE = 10000.0
DEFAULT_RISK_PER_TRADE_PERCENT = 1.0
DEFAULT_LEVERAGE = 5
DEFAULT_COMMISSION_RATE = 0.075  # % per side (Binance default)
DEFAULT_MAINTENANCE_MARGIN_RATE = 0.004  # %0.4 (Binance default for small positions)


def _add_flag_arguments(parser: ArgumentParser) -> None:
    """Add boolean flag arguments to parser.

    Args:
        parser: Argument parser instance.
    """
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


def _add_parameter_arguments(parser: ArgumentParser) -> None:
    """Add parameter arguments to parser.

    Args:
        parser: Argument parser instance.
    """
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
    parser.add_argument(
        '--top',
        type=int,
        default=10,
        help='Number of top results to show in optimization mode (default: 10, ignored if --risk or --leverage is used)'
    )


def _parse_arguments() -> Namespace:
    """Parse command line arguments.

    Returns:
        Parsed command line arguments.
    """
    parser = ArgumentParser(description='TrendBot Event-Driven Simulator')
    _add_flag_arguments(parser)
    _add_parameter_arguments(parser)
    return parser.parse_args()


def _create_simulation_engine(
    balance: float,
    risk: float,
    leverage: int,
    commission: float,
    mmr: float
) -> SimulationEngine:
    """Create SimulationEngine with given parameters.

    Args:
        balance: Initial balance in USDT.
        risk: Risk per trade percentage.
        leverage: Leverage multiplier.
        commission: Commission rate per side (%).
        mmr: Maintenance margin rate.

    Returns:
        Configured SimulationEngine instance.
    """
    return SimulationEngine(
        initial_balance=balance,
        risk_per_trade=risk,
        leverage=leverage,
        commission_rate=commission,
        mmr=mmr
    )


def _create_optimization_engine(
    balance: float,
    commission: float,
    mmr: float
) -> OptimizationEngine:
    """Create OptimizationEngine with given parameters.

    Args:
        balance: Initial balance in USDT.
        commission: Commission rate per side (%).
        mmr: Maintenance margin rate.

    Returns:
        Configured OptimizationEngine instance.
    """
    return OptimizationEngine(
        initial_balance=balance,
        commission_rate=commission,
        mmr=mmr
    )


def _has_explicit_parameters(args: Namespace) -> bool:
    """Check if user provided explicit risk/leverage parameters.

    Args:
        args: Parsed command line arguments.

    Returns:
        True if explicit parameters were provided.
    """
    return (
        args.risk != DEFAULT_RISK_PER_TRADE_PERCENT or
        args.leverage != DEFAULT_LEVERAGE
    )


def _run_telegram_with_explicit_params(args: Namespace) -> None:
    """Run Telegram mode with explicit parameters.

    Args:
        args: Parsed command line arguments.
    """
    print(
        f"📊 Belirtilen parametrelerle simülasyon çalıştırılıyor: "
        f"Risk %{args.risk} | Kaldıraç {args.leverage}x\n"
    )
    engine = _create_simulation_engine(
        balance=args.balance,
        risk=args.risk,
        leverage=args.leverage,
        commission=args.commission,
        mmr=args.mmr
    )
    engine.run(
        send_telegram=True,
        summary_only=True,
        manual_config={'risk': args.risk, 'leverage': args.leverage}
    )


def _run_telegram_with_optimization(args: Namespace) -> None:
    """Run Telegram mode with auto-optimization.

    Args:
        args: Parsed command line arguments.
    """
    print("🔍 Otomatik optimizasyon çalıştırılıyor...")
    opt_engine = _create_optimization_engine(
        balance=args.balance,
        commission=args.commission,
        mmr=args.mmr
    )
    best_config = opt_engine.run_optimization(silent=True)
    print(
        f"✅ En iyi konfigürasyon bulundu: "
        f"Risk %{best_config['risk']} | Kaldıraç {best_config['leverage']}x\n"
    )

    engine = _create_simulation_engine(
        balance=args.balance,
        risk=best_config['risk'],
        leverage=best_config['leverage'],
        commission=args.commission,
        mmr=args.mmr
    )
    engine.run(
        send_telegram=True,
        summary_only=True,
        auto_optimized=best_config
    )


def _run_telegram_mode(args: Namespace) -> None:
    """Run simulation with Telegram notification mode.

    Args:
        args: Parsed command line arguments.
    """
    if _has_explicit_parameters(args):
        _run_telegram_with_explicit_params(args)
    else:
        _run_telegram_with_optimization(args)


def _run_optimization_mode(args: Namespace) -> None:
    """Run optimization mode with full rankings.

    Args:
        args: Parsed command line arguments.
    """
    opt_engine = _create_optimization_engine(
        balance=args.balance,
        commission=args.commission,
        mmr=args.mmr
    )
    # In --opt mode, always use --top parameter
    opt_engine.run_optimization(show_all_rankings=True, top_n=args.top)


def _run_simulation_mode(args: Namespace) -> None:
    """Run normal simulation with explicit parameters.

    Args:
        args: Parsed command line arguments.
    """
    engine = _create_simulation_engine(
        balance=args.balance,
        risk=args.risk,
        leverage=args.leverage,
        commission=args.commission,
        mmr=args.mmr
    )
    engine.run(
        send_telegram=False,
        summary_only=args.summary
    )


def _run_default_mode(args: Namespace) -> None:
    """Run default optimization mode with top N results.

    Args:
        args: Parsed command line arguments.
    """
    opt_engine = _create_optimization_engine(
        balance=args.balance,
        commission=args.commission,
        mmr=args.mmr
    )
    # Use --top parameter (defaults to 10 if not specified)
    # This is only used in default mode, so no need to check explicit params
    opt_engine.run_optimization(show_all_rankings=False, top_n=args.top)


def main() -> None:
    """Main entry point for simulation CLI."""
    args = _parse_arguments()

    if args.send_telegram:
        _run_telegram_mode(args)
    elif args.opt:
        _run_optimization_mode(args)
    elif _has_explicit_parameters(args) or args.summary:
        # Explicit parameters override --top, run normal simulation
        _run_simulation_mode(args)
    else:
        # Default mode: use --top parameter (defaults to 10)
        _run_default_mode(args)


if __name__ == "__main__":
    main()
