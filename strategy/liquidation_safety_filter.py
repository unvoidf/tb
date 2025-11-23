"""
Liquidation Safety Filter
-------------------------
Hızlı liquidation risk kontrolü için utility fonksiyonları.
Bir sinyal için farklı risk/kaldıraç kombinasyonlarını test eder ve
SL ile liquidation arasında çok az fark olanları filtreler.
"""
import os
from typing import List, Dict, Tuple, Optional
from tools.simulation.position_manager import calculate_liquidation_price
from utils.logger import LoggerManager


class LiquidationSafetyFilter:
    """Liquidation risk kontrolü için filtre."""
    
    def __init__(self, mmr: float = 0.004, min_sl_liq_buffer: Optional[float] = None):
        """
        LiquidationSafetyFilter'ı başlatır.
        
        Args:
            mmr: Maintenance Margin Rate (default: 0.004 = 0.4%)
            min_sl_liq_buffer: SL ile liquidation arası minimum buffer (default: .env'den okunur veya 0.01 = %1)
        """
        self.mmr = mmr
        self.min_sl_liq_buffer = min_sl_liq_buffer or self._load_min_sl_liq_buffer()
        self.logger = LoggerManager().get_logger('LiquidationSafetyFilter')
    
    def filter_unsafe_combinations(
        self,
        entry_price: float,
        sl_price: float,
        direction: str,
        balance: float,
        risk_ranges: List[float],
        leverage_ranges: List[int]
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Risk/kaldıraç kombinasyonlarını test eder ve güvenli olanları döndürür.
        
        Args:
            entry_price: Entry fiyatı
            sl_price: Stop loss fiyatı
            direction: LONG veya SHORT
            balance: Hesap bakiyesi
            risk_ranges: Test edilecek risk oranları listesi (örn: [0.5, 1.0, 1.5, ...])
            leverage_ranges: Test edilecek kaldıraç değerleri listesi (örn: [1, 2, 3, ...])
            
        Returns:
            (safe_combinations, unsafe_combinations) tuple
            Her kombinasyon: {'risk': float, 'leverage': int, 'liq_price': float, 'sl_liq_diff_pct': float}
        """
        safe_combinations = []
        unsafe_combinations = []
        
        # SL mesafesi
        sl_distance_pct = abs(entry_price - sl_price) / entry_price
        if sl_distance_pct == 0:
            self.logger.warning("SL distance is 0, cannot calculate liquidation")
            return safe_combinations, unsafe_combinations
        
        for risk_percent in risk_ranges:
            for leverage in leverage_ranges:
                # Pozisyon büyüklüğü hesapla
                risk_amount = balance * (risk_percent / 100)
                position_size_usd = risk_amount / sl_distance_pct
                margin_required = position_size_usd / leverage
                quantity = position_size_usd / entry_price
                
                # Liquidation price hesapla
                liq_price = calculate_liquidation_price(
                    direction=direction,
                    entry_price=entry_price,
                    quantity=quantity,
                    margin=margin_required,
                    mmr=self.mmr
                )
                
                if liq_price <= 0:
                    continue
                
                # SL ile liquidation arasındaki farkı hesapla
                if direction == 'LONG':
                    # LONG: SL < Entry, Liq < Entry
                    # SL ile Liq arasındaki fark
                    sl_liq_diff = abs(sl_price - liq_price)
                    sl_liq_diff_pct = (sl_liq_diff / entry_price) * 100
                else:
                    # SHORT: SL > Entry, Liq > Entry
                    sl_liq_diff = abs(sl_price - liq_price)
                    sl_liq_diff_pct = (sl_liq_diff / entry_price) * 100
                
                combination = {
                    'risk': risk_percent,
                    'leverage': leverage,
                    'liq_price': liq_price,
                    'sl_liq_diff_pct': sl_liq_diff_pct,
                    'margin_required': margin_required,
                    'position_size_usd': position_size_usd
                }
                
                # Buffer kontrolü: SL ile liquidation arasında minimum %1 fark olmalı
                if sl_liq_diff_pct < (self.min_sl_liq_buffer * 100):
                    unsafe_combinations.append(combination)
                    self.logger.debug(
                        f"Unsafe: Risk {risk_percent}% | Leverage {leverage}x | "
                        f"SL-Liq diff: {sl_liq_diff_pct:.2f}% < {self.min_sl_liq_buffer*100:.1f}%"
                    )
                else:
                    safe_combinations.append(combination)
        
        return safe_combinations, unsafe_combinations
    
    def find_optimal_safe_combination(
        self,
        entry_price: float,
        sl_price: float,
        direction: str,
        balance: float,
        risk_ranges: Optional[List[float]] = None,
        leverage_ranges: Optional[List[int]] = None
    ) -> Optional[Dict]:
        """
        Güvenli kombinasyonlar arasından en iyisini bulur.
        
        Args:
            entry_price: Entry fiyatı
            sl_price: Stop loss fiyatı
            direction: LONG veya SHORT
            balance: Hesap bakiyesi
            risk_ranges: Test edilecek risk oranları (default: [0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
            leverage_ranges: Test edilecek kaldıraç değerleri (default: [1, 2, 3, 4, 5, 7, 10])
            
        Returns:
            En iyi güvenli kombinasyon veya None
        """
        if risk_ranges is None:
            # Load from .env or use defaults
            risk_ranges = self._load_risk_ranges()
        
        if leverage_ranges is None:
            # Load from .env or use defaults
            leverage_ranges = self._load_leverage_ranges()
        
        safe_combinations, unsafe_combinations = self.filter_unsafe_combinations(
            entry_price=entry_price,
            sl_price=sl_price,
            direction=direction,
            balance=balance,
            risk_ranges=risk_ranges,
            leverage_ranges=leverage_ranges
        )
        
        if not safe_combinations:
            self.logger.warning(
                f"No safe combinations found for {direction} signal "
                f"(Entry: ${entry_price:.4f}, SL: ${sl_price:.4f})"
            )
            return None
        
        # En iyi kombinasyonu seç: En yüksek leverage, en yüksek risk (ama güvenli)
        # Öncelik: SL-Liq farkı yeterince büyük olanlar, sonra yüksek leverage
        best = max(
            safe_combinations,
            key=lambda x: (x['sl_liq_diff_pct'], x['leverage'], x['risk'])
        )
        
        self.logger.info(
            f"Optimal safe combination: Risk {best['risk']}% | Leverage {best['leverage']}x | "
            f"SL-Liq diff: {best['sl_liq_diff_pct']:.2f}%"
        )
        
        return best
    
    def calculate_liquidation_risk_percentage(
        self,
        entry_price: float,
        sl_price: float,
        direction: str,
        balance: float,
        risk_ranges: Optional[List[float]] = None,
        leverage_ranges: Optional[List[int]] = None
    ) -> float:
        """
        Likidite risk yüzdesini hesaplar.
        
        Args:
            entry_price: Entry fiyatı
            sl_price: Stop loss fiyatı
            direction: LONG veya SHORT
            balance: Hesap bakiyesi
            risk_ranges: Test edilecek risk oranları (default: .env'den okunur)
            leverage_ranges: Test edilecek kaldıraç değerleri (default: .env'den okunur)
            
        Returns:
            Likidite risk yüzdesi (0-100 arası): (Unsafe kombinasyonlar / Tüm kombinasyonlar) * 100
        """
        if risk_ranges is None:
            risk_ranges = self._load_risk_ranges()
        
        if leverage_ranges is None:
            leverage_ranges = self._load_leverage_ranges()
        
        safe_combinations, unsafe_combinations = self.filter_unsafe_combinations(
            entry_price=entry_price,
            sl_price=sl_price,
            direction=direction,
            balance=balance,
            risk_ranges=risk_ranges,
            leverage_ranges=leverage_ranges
        )
        
        total_combinations = len(safe_combinations) + len(unsafe_combinations)
        
        if total_combinations == 0:
            return 0.0
        
        risk_percentage = (len(unsafe_combinations) / total_combinations) * 100
        return round(risk_percentage, 2)
    
    def _load_risk_ranges(self) -> List[float]:
        """Load risk ranges from .env or use defaults."""
        default = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
        val = os.getenv('SAFETYFILTER_RISK_RANGES')
        if not val:
            return default
        try:
            return [float(x.strip()) for x in val.split(',') if x.strip()]
        except Exception:
            return default
    
    def _load_leverage_ranges(self) -> List[int]:
        """Load leverage ranges from .env or use defaults."""
        default = [1, 2, 3, 4, 5, 7, 10, 12, 15, 20]
        val = os.getenv('SAFETYFILTER_LEVERAGE_RANGES')
        if not val:
            return default
        try:
            return [int(x.strip()) for x in val.split(',') if x.strip()]
        except Exception:
            return default
    
    def _load_min_sl_liq_buffer(self) -> float:
        """Load minimum SL-Liq buffer from .env or use default."""
        try:
            val = os.getenv('SAFETYFILTER_MIN_SL_LIQ_BUFFER')
            return float(val) if val is not None else 0.01
        except Exception:
            return 0.01

