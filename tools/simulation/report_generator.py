"""
Report Generator
----------------
Generates formatted reports for simulation results.
"""
from typing import Dict, List, Callable, Optional
from .utils import format_timestamp, interpret_results


class ReportGenerator:
    """Generates formatted reports for simulation results."""
    
    def __init__(self, log_callback: Optional[Callable[[str, bool], None]] = None):
        """
        Initialize report generator.
        
        Args:
            log_callback: Function to call for logging messages.
                         Signature: log(message: str, detail: bool = True)
        """
        self.log_callback = log_callback or (lambda msg, detail=True: print(msg))
        self.report_buffer: List[str] = []
    
    def log(self, message: str = "", detail: bool = True):
        """Logs a message and adds to report buffer."""
        self.log_callback(message, detail)
        if message:
            self.report_buffer.append(message)
    
    def generate_summary_report(
        self,
        summary: Dict,
        portfolio,
        auto_optimized: Optional[Dict] = None,
        manual_config: Optional[Dict] = None
    ):
        """Generates comprehensive summary report."""
        # Add simulation duration to summary
        if 'simulation_duration' not in summary:
            summary['simulation_duration'] = summary.get('last_signal_time', 0) - summary.get('first_signal_time', 0)
        
        # Visual header (Mobile-friendly Telegram format)
        self.log("📊 *SİMÜLASYON RAPORU (İzole Margin)*", detail=False)
        self.log("", detail=False)  # Empty line for spacing
        
        # Add auto-optimization info if applicable
        if auto_optimized:
            self.log("🔍 Optimizasyon Modu: Otomatik", detail=False)
            self.log(
                f"✅ En iyi konfigürasyon: Risk %{auto_optimized['risk']} | "
                f"Kaldıraç {auto_optimized['leverage']}x",
                detail=False
            )
            self.log("", detail=False)  # Empty line after optimization info
        elif manual_config:
            self.log("📊 Manuel Konfigürasyon", detail=False)
            min_sl_liq_buffer = manual_config.get('min_sl_liq_buffer', 0.01)
            self.log(
                f"⚙️  Parametreler: Risk %{manual_config['risk']} | "
                f"Kaldıraç {manual_config['leverage']}x | "
                f"Likidite Buffer %{min_sl_liq_buffer*100:.1f}",
                detail=False
            )
            self.log("", detail=False)  # Empty line after config info
        
        # Financials with emojis
        self.log("💰 *FİNANSAL ÖZET*", detail=False)
        
        pnl_emoji = (
            "📈" if summary['pnl_amount'] > 0 
            else "📉" if summary['pnl_amount'] < 0 
            else "➡️"
        )
        self.log(f"💵 Başlangıç  : ${summary['initial_balance']:>10,.2f}", detail=False)
        self.log(f"{pnl_emoji} Final      : ${summary['final_balance']:>10,.2f}", detail=False)
        
        pnl_sign = "+" if summary['pnl_amount'] > 0 else ""
        pnl_color = (
            "🟢" if summary['pnl_amount'] > 0 
            else "🔴" if summary['pnl_amount'] < 0 
            else "⚪"
        )
        self.log(
            f"{pnl_color} Net PnL    : {pnl_sign}${summary['pnl_amount']:>9,.2f} "
            f"({summary['pnl_percent']:+.2f}%)",
            detail=False
        )

        # Detailed Statistics
        self.log("\n📈 *İSTATİSTİKLER*", detail=False)
        
        win_rate_emoji = (
            "🟢" if summary['win_rate'] >= 60 
            else "🟡" if summary['win_rate'] >= 50 
            else "🔴"
        )
        self.log(
            f"{win_rate_emoji} Win Rate   : %{summary['win_rate']:.1f} "
            f"({summary['wins']}W-{summary['losses']}L)",
            detail=False
        )
        
        dd_risk_level = (
            "Orta" if summary['max_drawdown'] > 10 
            else "Düşük" if summary['max_drawdown'] < 5 
            else "Yüksek" if summary['max_drawdown'] > 20 
            else "Makul"
        )
        dd_emoji = (
            "🟢" if summary['max_drawdown'] < 10 
            else "🟡" if summary['max_drawdown'] < 20 
            else "🔴"
        )
        self.log(
            f"{dd_emoji} Max DD     : %{summary['max_drawdown']:.2f} ({dd_risk_level})",
            detail=False
        )
        
        pf_emoji = (
            "🟢" if summary['profit_factor'] > 1.5 
            else "🟡" if summary['profit_factor'] > 1.0 
            else "🔴"
        )
        self.log(f"{pf_emoji} Profit F.  : {summary['profit_factor']:.2f}", detail=False)
        
        self.log(f"📊 Toplam     : {summary['total_trades']} işlem", detail=False)
        self.log(
            f"💸 Ödenen Kom.: ${portfolio.total_commission_paid:,.2f}",
            detail=False
        )
        
        if summary['liquidations'] > 0:
            self.log(f"💀 Likidasyon  : {summary['liquidations']} adet ⚠️", detail=False)
        
        # Detailed Analysis
        self.log("\n🔍 *DETAYLI ANALİZ*", detail=False)
        
        # Average Win/Loss
        if summary['wins'] > 0:
            self.log(f"💚 Ort. Kazanç : ${summary['avg_win']:>10,.2f}", detail=False)
        if summary['losses'] > 0:
            self.log(f"❌ Ort. Kayıp  : ${summary['avg_loss']:>10,.2f}", detail=False)
        
        # Win/Loss Ratio
        if summary['avg_loss'] > 0:
            win_loss_ratio = summary['avg_win'] / summary['avg_loss']
            self.log(f"⚖️  K/Z Oranı  : {win_loss_ratio:.2f}x", detail=False)
        
        # Streaks
        streak_emoji = "🔥" if summary['max_win_streak'] >= 5 else "✅"
        self.log(
            f"{streak_emoji} Max Seri    : {summary['max_win_streak']}W/"
            f"{summary['max_loss_streak']}L",
            detail=False
        )
        
        # Long/Short Stats
        if summary['long_stats']['total'] > 0:
            long_emoji = (
                "🟢" if summary['long_stats']['win_rate'] >= 50 
                else "🔴"
            )
            self.log(
                f"📊 LONG        : {summary['long_stats']['wins']}W/"
                f"{summary['long_stats']['total']}T "
                f"(%{summary['long_stats']['win_rate']:.1f})",
                detail=False
            )
        
        if summary['short_stats']['total'] > 0:
            short_emoji = (
                "🟢" if summary['short_stats']['win_rate'] >= 50 
                else "🔴"
            )
            self.log(
                f"📉 SHORT       : {summary['short_stats']['wins']}W/"
                f"{summary['short_stats']['total']}T "
                f"(%{summary['short_stats']['win_rate']:.1f})",
                detail=False
            )

        # AI Insights with visual formatting
        pf = summary['profit_factor']
        if pf > 2.0:
            verim = "Verim: Mükemmel 🎯"
            verim_emoji = "🌟"
        elif pf > 1.5:
            verim = "Verim: İyi 👍"
            verim_emoji = "✅"
        elif pf > 1.0:
            verim = "Verim: Düşük, risk sınırda"
            verim_emoji = "⚠️"
        else:
            verim = "Verim: Zarar"
            verim_emoji = "❌"
        self.log(f"{verim_emoji} {verim}", detail=False)
        
        ls = summary['max_loss_streak']
        if ls >= 5:
            psikoloji = f"{ls} ardışık kayıp riski"
            psikoloji_emoji = "😰"
        else:
            psikoloji = "Psikoloji: Kontrol altında"
            psikoloji_emoji = "😊"
        self.log(f"{psikoloji_emoji} {psikoloji}", detail=False)
        
        avg_dur = summary['avg_duration_seconds']
        hours = avg_dur / 3600
        minutes = (avg_dur % 3600) / 60
        if avg_dur < 3600:
            style = "Scalper (<1 saat)"
            style_emoji = "⚡"
        elif avg_dur < 86400:
            style = f"Day Trader ({int(hours)}sa {int(minutes)}dk)"
            style_emoji = "📅"
        else:
            style = "Swing Trader (>1 gün)"
            style_emoji = "🗓️"
        self.log(f"{style_emoji} {style}", detail=False)
        
        # Time Range
        if summary.get('simulation_duration', 0) > 0:
            duration_days = summary['simulation_duration'] / 86400
            start_date = format_timestamp(
                summary.get('first_signal_time', 0)
            ).split()[0]
            end_date = format_timestamp(
                summary.get('last_signal_time', 0)
            ).split()[0]
            
            if duration_days < 1:
                duration_str = f"{duration_days * 24:.1f} saat"
            elif duration_days < 30:
                duration_str = f"{duration_days:.1f} gün"
            else:
                duration_str = f"{duration_days / 30:.1f} ay"
            
            self.log(f"\n📆 {start_date} - {end_date}", detail=False)
            self.log(f"⏱️  Süre: {duration_str}", detail=False)
        
        # Açık pozisyon sayısı (her zaman göster)
        open_trades = summary.get('open_trades', 0)
        open_signals_from_db = summary.get('open_signals_from_db', 0)
        
        # Show both simulated open positions and actual open signals from DB
        if open_signals_from_db > 0:
            if open_trades != open_signals_from_db:
                # Mismatch: some signals were skipped
                self.log(
                    f"📊 Açık Pozisyon: {open_trades} adet "
                    f"(DB'de {open_signals_from_db} açık sinyal)",
                    detail=False
                )
            else:
                self.log(f"📊 Açık Pozisyon: {open_trades} adet", detail=False)
        else:
            self.log(f"📊 Açık Pozisyon: 0 adet", detail=False)
    
    def get_report_text(self) -> str:
        """Returns the full report as text."""
        return "\n".join(self.report_buffer)
    
    def clear_buffer(self):
        """Clears the report buffer."""
        self.report_buffer.clear()

