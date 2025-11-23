"""
Optimization Engine
-------------------
Parameter optimization engine for simulation.
"""
from typing import Dict, List
from .simulation_engine import SimulationEngine, DEFAULT_MAINTENANCE_MARGIN_RATE


class OptimizationEngine:
    """Handles parameter optimization for simulations."""
    
    def __init__(
        self,
        initial_balance: float,
        commission_rate: float,
        mmr: float = DEFAULT_MAINTENANCE_MARGIN_RATE
    ):
        self.initial_balance = initial_balance
        self.commission_rate = commission_rate
        self.mmr = mmr
    
    def run_optimization(
        self,
        silent: bool = False,
        show_all_rankings: bool = False,
        top_n: int = 10
    ) -> Dict[str, float]:
        """
        Runs optimization across risk and leverage combinations.
        
        Returns:
            Best configuration: {'risk': float, 'leverage': int}
        """
        if not silent:
            print(f"🧪 OPTİMİZASYON MODU BAŞLATILIYOR...")
            print(f"💰 Başlangıç Bakiyesi: ${self.initial_balance:,.2f}")
            print(f"💸 Komisyon Oranı: %{self.commission_rate}")
            print("-" * 60)
        
        risk_ranges = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
        leverage_ranges = [
            1, 2, 3, 4, 5, 7, 10, 12, 15, 20, 25, 30, 35, 40, 45, 50
        ]
        
        results = []
        total_combinations = len(risk_ranges) * len(leverage_ranges)
        count = 0
        
        if not silent:
            print(f"⏳ Toplam {total_combinations} kombinasyon test ediliyor...")
        
        for risk in risk_ranges:
            for lev in leverage_ranges:
                count += 1
                # Print progress every 10 steps
                if not silent and count % 10 == 0:
                    print(f"   ... {count}/{total_combinations} tamamlandı")
                
                # Run simulation silently
                engine = SimulationEngine(
                    initial_balance=self.initial_balance,
                    risk_per_trade=risk,
                    leverage=lev,
                    commission_rate=self.commission_rate,
                    mmr=self.mmr
                )
                
                summary = engine.run(
                    send_telegram=False,
                    summary_only=True,
                    silent=True
                )
                
                # Calculate risk-adjusted return and composite score
                if summary['max_drawdown'] > 0:
                    risk_adj_return = summary['pnl_percent'] / summary['max_drawdown']
                    composite_score = (
                        (summary['pnl_percent'] * summary['profit_factor']) 
                        / summary['max_drawdown']
                    )
                elif summary['pnl_percent'] > 0:
                    # No drawdown with positive return = perfect scenario
                    risk_adj_return = float('inf')
                    composite_score = float('inf')
                else:
                    # No drawdown, no profit = neutral
                    risk_adj_return = 0
                    composite_score = 0
                
                results.append({
                    'risk': risk,
                    'leverage': lev,
                    'pnl_amount': summary['pnl_amount'],
                    'pnl_percent': summary['pnl_percent'],
                    'max_drawdown': summary['max_drawdown'],
                    'profit_factor': summary['profit_factor'],
                    'trades': summary['total_trades'],
                    'liquidations': summary['liquidations'],
                    'risk_adj_return': risk_adj_return,
                    'composite_score': composite_score
                })
        
        # Filter results to only configurations with sufficient data
        MIN_TRADES = 5  # Minimum trades for statistical significance
        valid_results = [r for r in results if r['trades'] >= MIN_TRADES]
        
        if show_all_rankings and not silent:
            self._show_all_rankings(valid_results, MIN_TRADES)
        elif not silent:
            self._show_default_rankings(valid_results, MIN_TRADES, top_n)
            results = sorted(valid_results, key=lambda x: x['pnl_amount'], reverse=True)
        else:
            # Silent mode - filter and sort by PnL
            MIN_TRADES = 5
            valid_results = [r for r in results if r['trades'] >= MIN_TRADES]
            results = sorted(valid_results, key=lambda x: x['pnl_amount'], reverse=True)
        
        # Return best configuration
        if len(results) == 0:
            # Fallback: no config with 5+ trades, use all results
            all_results = sorted(
                results if 'results' in locals() else [],
                key=lambda x: x.get('profit_factor', 0),
                reverse=True
            )
            results = all_results
        
        best = results[0] if results else {'risk': 1.0, 'leverage': 1}
        return {'risk': best['risk'], 'leverage': best['leverage']}
    
    def _show_all_rankings(
        self, 
        valid_results: List[Dict], 
        min_trades: int
    ) -> None:
        """Shows all ranking methods."""
        print("\n" + "="*90)
        print("📊 ÇOKLU ANALİZ SONUÇLARI")
        print(f"ℹ️  Minimum {min_trades} trade olan konfigürasyonlar gösteriliyor "
              f"(istatistiksel güvenilirlik)")
        print("="*90)
        
        # 1. Risk-Adjusted Return
        sorted_rar = sorted(
            valid_results, 
            key=lambda x: x['risk_adj_return'], 
            reverse=True
        )
        print("\n🎯 EN İYİ 5 KONFİGÜRASYON (Risk-Adjusted Return)")
        print("-" * 90)
        for i, res in enumerate(sorted_rar[:5]):
            pnl_str = (
                f"+${res['pnl_amount']:,.0f}" 
                if res['pnl_amount'] > 0 
                else f"${res['pnl_amount']:,.0f}"
            )
            print(
                f"{i+1}. Risk {res['risk']}% | {res['leverage']}x → "
                f"R/R: {res['risk_adj_return']:.2f} | PnL: {pnl_str} | "
                f"DD: {res['max_drawdown']:.1f}%"
            )
        
        # 2. Maximum PnL
        sorted_pnl = sorted(
            valid_results, 
            key=lambda x: x['pnl_amount'], 
            reverse=True
        )
        print("\n💰 EN İYİ 5 KONFİGÜRASYON (Maksimum PnL)")
        print("-" * 90)
        for i, res in enumerate(sorted_pnl[:5]):
            pnl_str = (
                f"+${res['pnl_amount']:,.0f}" 
                if res['pnl_amount'] > 0 
                else f"${res['pnl_amount']:,.0f}"
            )
            print(
                f"{i+1}. Risk {res['risk']}% | {res['leverage']}x → "
                f"PnL: {pnl_str} ({res['pnl_percent']:.1f}%) | "
                f"DD: {res['max_drawdown']:.1f}% | PF: {res['profit_factor']:.2f}"
            )
        
        # 3. Profit Factor
        valid_results_pf = [r for r in valid_results if r['trades'] > 0]
        sorted_pf = sorted(
            valid_results_pf, 
            key=lambda x: x['profit_factor'], 
            reverse=True
        )
        print("\n🎯 EN İYİ 5 KONFİGÜRASYON (Profit Factor - Tutarlılık)")
        print("-" * 90)
        for i, res in enumerate(sorted_pf[:5]):
            pnl_str = (
                f"+${res['pnl_amount']:,.0f}" 
                if res['pnl_amount'] > 0 
                else f"${res['pnl_amount']:,.0f}"
            )
            print(
                f"{i+1}. Risk {res['risk']}% | {res['leverage']}x → "
                f"PF: {res['profit_factor']:.2f} | PnL: {pnl_str} | "
                f"DD: {res['max_drawdown']:.1f}%"
            )
        
        # 4. Composite Score
        sorted_comp = sorted(
            valid_results, 
            key=lambda x: x['composite_score'], 
            reverse=True
        )
        print("\n⚖️ EN İYİ 5 KONFİGÜRASYON (Composite Score)")
        print("-" * 90)
        for i, res in enumerate(sorted_comp[:5]):
            pnl_str = (
                f"+${res['pnl_amount']:,.0f}" 
                if res['pnl_amount'] > 0 
                else f"${res['pnl_amount']:,.0f}"
            )
            print(
                f"{i+1}. Risk {res['risk']}% | {res['leverage']}x → "
                f"Score: {res['composite_score']:.2f} | PnL: {pnl_str} | "
                f"PF: {res['profit_factor']:.2f}"
            )
        
        print("\n" + "="*90)
        print("ℹ️  Profit Factor (PF) varsayılan sıralama kriteri olarak kullanılacak.")
        print("="*90)
    
    def _show_default_rankings(
        self, 
        valid_results: List[Dict], 
        min_trades: int, 
        top_n: int
    ) -> None:
        """Shows default rankings (PnL + Profit Factor + Max Drawdown)."""
        # 1. Maximum PnL Ranking (primary)
        sorted_pnl = sorted(
            valid_results, 
            key=lambda x: x['pnl_amount'], 
            reverse=True
        )
        print("\n" + "="*90)
        print(f"💰 EN İYİ {top_n} KONFİGÜRASYON (Maksimum PnL) - Min {min_trades} trade")
        print("="*90)
        print(
            f"{'Rank':<5} | {'Risk':<6} | {'Lev':<5} | {'PnL ($)':<12} | "
            f"{'PnL (%)':<8} | {'MaxDD':<8} | {'PF':<6} | {'R/R':<6} | {'Liq':<4}"
        )
        print("-" * 90)
        
        for i, res in enumerate(sorted_pnl[:top_n]):
            rank = i + 1
            pnl_str = f"${res['pnl_amount']:,.2f}"
            if res['pnl_amount'] > 0:
                pnl_str = "+" + pnl_str
            
            print(
                f"{rank:<5} | {res['risk']:<4}% | {res['leverage']:<3}x  | "
                f"{pnl_str:<12} | {res['pnl_percent']:>6.2f}% | "
                f"{res['max_drawdown']:>6.2f}% | {res['profit_factor']:>4.2f} | "
                f"{res['risk_adj_return']:>4.2f} | {res['liquidations']:<4}"
            )
        
        print("="*90)
        
        # 2. Profit Factor Ranking (secondary)
        sorted_pf = sorted(
            valid_results, 
            key=lambda x: x['profit_factor'], 
            reverse=True
        )
        print("\n" + "="*90)
        print(f"🏆 EN İYİ {top_n} KONFİGÜRASYON (Profit Factor) - Min {min_trades} trade")
        print("="*90)
        print(
            f"{'Rank':<5} | {'Risk':<6} | {'Lev':<5} | {'PnL ($)':<12} | "
            f"{'PnL (%)':<8} | {'MaxDD':<8} | {'PF':<6} | {'R/R':<6} | {'Liq':<4}"
        )
        print("-" * 90)
        
        for i, res in enumerate(sorted_pf[:top_n]):
            rank = i + 1
            pnl_str = f"${res['pnl_amount']:,.2f}"
            if res['pnl_amount'] > 0:
                pnl_str = "+" + pnl_str
            
            print(
                f"{rank:<5} | {res['risk']:<4}% | {res['leverage']:<3}x  | "
                f"{pnl_str:<12} | {res['pnl_percent']:>6.2f}% | "
                f"{res['max_drawdown']:>6.2f}% | {res['profit_factor']:>4.2f} | "
                f"{res['risk_adj_return']:>4.2f} | {res['liquidations']:<4}"
            )
        
        print("="*90)
        
        # 3. Minimum Max Drawdown Ranking (tertiary - lower is better)
        sorted_dd = sorted(
            valid_results, 
            key=lambda x: x['max_drawdown'], 
            reverse=False
        )
        print("\n" + "="*90)
        print(f"📉 EN İYİ {top_n} KONFİGÜRASYON (Minimum Max Drawdown) - Min {min_trades} trade")
        print("="*90)
        print(
            f"{'Rank':<5} | {'Risk':<6} | {'Lev':<5} | {'PnL ($)':<12} | "
            f"{'PnL (%)':<8} | {'MaxDD':<8} | {'PF':<6} | {'R/R':<6} | {'Liq':<4}"
        )
        print("-" * 90)
        
        for i, res in enumerate(sorted_dd[:top_n]):
            rank = i + 1
            pnl_str = f"${res['pnl_amount']:,.2f}"
            if res['pnl_amount'] > 0:
                pnl_str = "+" + pnl_str
            
            print(
                f"{rank:<5} | {res['risk']:<4}% | {res['leverage']:<3}x  | "
                f"{pnl_str:<12} | {res['pnl_percent']:>6.2f}% | "
                f"{res['max_drawdown']:>6.2f}% | {res['profit_factor']:>4.2f} | "
                f"{res['risk_adj_return']:>4.2f} | {res['liquidations']:<4}"
            )
        
        print("="*90)

