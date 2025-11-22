"""
Simulation Utilities
--------------------
Helper functions for simulation module.
"""
from datetime import datetime
from typing import Dict, List


def format_timestamp(ts: int) -> str:
    """Formats Unix timestamp to readable date string."""
    return datetime.fromtimestamp(ts).strftime('%d/%m/%Y %H:%M:%S')


def format_duration_str(seconds: int) -> str:
    """Formats duration in seconds to readable string."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}s {minutes}dk"


def interpret_results(metrics: Dict) -> List[str]:
    """Generates human-readable insights based on simulation metrics."""
    insights = []
    
    # Liquidation Warning
    if metrics['liquidations'] > 0:
        insights.append(
            f"💀 **LİKİDASYON UYARISI:** {metrics['liquidations']} işlem likit oldu! "
            f"Kaldıraç çok yüksek veya SL çok uzak."
        )

    # 1. Profitability & Efficiency
    pf = metrics['profit_factor']
    if pf > 2.0:
        insights.append(
            f"✅ **Mükemmel Verimlilik:** Profit Factor {pf:.2f} "
            f"(Her 1$ kayba karşılık {pf:.2f}$ kazanç)."
        )
    elif pf > 1.5:
        insights.append(f"✅ **İyi Verimlilik:** Profit Factor {pf:.2f}. Sistem sürdürülebilir.")
    elif pf > 1.0:
        insights.append(
            f"⚠️ **Düşük Verimlilik:** Profit Factor {pf:.2f}. "
            f"Kâr ediyor ama riskli sınırda."
        )
    else:
        insights.append(f"❌ **Zarar:** Sistem para kaybediyor (PF: {pf:.2f}).")

    # 2. Risk & Drawdown
    mdd = metrics['max_drawdown']
    if mdd < 10:
        insights.append(f"🛡️ **Düşük Risk:** Max Drawdown sadece %{mdd:.2f}. Sermaye güvende.")
    elif mdd < 20:
        insights.append(
            f"⚠️ **Orta Risk:** Max Drawdown %{mdd:.2f}. "
            f"Kabul edilebilir ama dikkatli olunmalı."
        )
    else:
        insights.append(
            f"🚨 **YÜKSEK RİSK:** Max Drawdown %{mdd:.2f}! "
            f"Sermayenin ciddi kısmı erime riski taşıyor."
        )

    # 3. Streaks
    loss_streak = metrics['max_loss_streak']
    if loss_streak >= 5:
        insights.append(
            f"🔥 **Psikolojik Baskı:** Arka arkaya {loss_streak} kayıp yaşanmış. "
            f"Sabırlı olunmalı."
        )
        
    # 4. Duration
    avg_dur = metrics['avg_duration_seconds']
    hours = avg_dur / 3600
    if hours < 1:
        insights.append(f"⚡ **Scalper:** İşlemler ortalama {hours*60:.0f} dakika sürüyor.")
    elif hours < 24:
        insights.append(f"📅 **Day Trader:** İşlemler ortalama {hours:.1f} saat sürüyor.")
    else:
        insights.append(f"🗓️ **Swing Trader:** İşlemler ortalama {hours/24:.1f} gün sürüyor.")
    
    return insights

