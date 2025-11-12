"""
RiskManager: Risk yönetimi sınıfı.
Leverage önerisi ve pozisyon büyüklüğü hesaplaması.
"""
from typing import Dict
from utils.logger import LoggerManager


class RiskManager:
    """Risk yönetimi ve pozisyon büyüklüğü hesaplar."""
    
    def __init__(self,
                 risk_low: float = 0.01,
                 risk_medium: float = 0.03,
                 risk_high: float = 0.05,
                 leverage_min: int = 1,
                 leverage_max: int = 10):
        """
        RiskManager'ı başlatır.
        
        Args:
            risk_low: Düşük risk yüzdesi
            risk_medium: Orta risk yüzdesi
            risk_high: Yüksek risk yüzdesi
            leverage_min: Minimum leverage
            leverage_max: Maximum leverage
        """
        self.risk_levels = {
            'low': risk_low,
            'medium': risk_medium,
            'high': risk_high
        }
        self.leverage_min = leverage_min
        self.leverage_max = leverage_max
        self.logger = LoggerManager().get_logger('RiskManager')
    
    def calculate_position_size(
        self, position_info: Dict, signal_confidence: float
    ) -> Dict:
        """
        Pozisyon büyüklüğü ve leverage hesaplar.
        
        Args:
            position_info: Pozisyon bilgileri
            signal_confidence: Sinyal güvenilirliği (0-1)
            
        Returns:
            Position sizing bilgileri
        """
        # Risk seviyesini belirle
        risk_level = self._determine_risk_level(signal_confidence)
        self.logger.debug(
            f"determine_risk_level: confidence={signal_confidence:.3f} -> {risk_level}"
        )
        account_risk = self.risk_levels[risk_level]
        
        # Leverage önerisi
        leverage = self._calculate_leverage(
            signal_confidence,
            position_info.get('risk_percent', 2.0)
        )
        self.logger.debug(
            f"calculate_leverage: confidence={signal_confidence:.3f}, pos_risk={position_info.get('risk_percent', 2.0):.3f} -> leverage={leverage}"
        )
        
        # Pozisyon büyüklüğü yüzdesi
        position_size_percent = self._calculate_position_percent(
            account_risk, position_info['risk_percent'], leverage
        )
        self.logger.debug(
            f"position_percent: account_risk={account_risk:.4f}, pos_risk%={position_info['risk_percent']:.3f}, lev={leverage} -> size%={position_size_percent:.2f}"
        )
        
        return {
            'risk_level': risk_level,
            'account_risk_percent': account_risk * 100,
            'position_size_percent': position_size_percent,
            'leverage': leverage,
            'confidence': signal_confidence
        }
    
    def _determine_risk_level(self, confidence: float) -> str:
        """
        Güvenilirliğe göre risk seviyesi belirler.
        
        Args:
            confidence: Sinyal güvenilirliği
            
        Returns:
            'low', 'medium', veya 'high'
        """
        if confidence >= 0.75:
            return 'high'
        elif confidence >= 0.60:
            return 'medium'
        else:
            return 'low'
    
    def _calculate_leverage(
        self, confidence: float, risk_percent: float
    ) -> int:
        """
        Güvenilirlik ve volatiliteye göre leverage hesaplar.
        
        Args:
            confidence: Sinyal güvenilirliği
            risk_percent: Pozisyon risk yüzdesi
            
        Returns:
            Leverage değeri
        """
        # Yüksek güvenilirlik -> yüksek leverage
        base_leverage = confidence * self.leverage_max
        
        # Yüksek volatilite -> düşük leverage
        if risk_percent > 5.0:
            volatility_factor = 0.5
        elif risk_percent > 3.0:
            volatility_factor = 0.7
        else:
            volatility_factor = 1.0
        
        leverage = int(base_leverage * volatility_factor)
        
        # Min-max aralığında tut
        leverage = max(self.leverage_min, min(self.leverage_max, leverage))
        
        return leverage
    
    def _calculate_position_percent(
        self, account_risk: float, 
        position_risk: float,
        leverage: int
    ) -> float:
        """
        Pozisyon büyüklüğü yüzdesini hesaplar.
        
        Args:
            account_risk: Account risk yüzdesi (0.01 = %1)
            position_risk: Pozisyon risk yüzdesi (%)
            leverage: Kullanılacak leverage
            
        Returns:
            Pozisyon büyüklüğü yüzdesi
        """
        # Risk = (Position Size * Position Risk%) / Leverage
        # Position Size = (Account Risk * Leverage) / Position Risk%
        
        position_size = (account_risk * 100 * leverage) / position_risk
        
        # Maksimum %100 ile sınırla (leverage ile)
        max_size = 100.0
        
        return min(position_size, max_size)
    
    def format_risk_advice(self, risk_info: Dict) -> str:
        """
        Risk yönetimi tavsiyelerini Türkçe formatlar.
        
        Args:
            risk_info: Risk bilgileri
            
        Returns:
            Formatlanmış tavsiye metni
        """
        risk_level_tr = {
            'low': 'Düşük',
            'medium': 'Orta',
            'high': 'Yüksek'
        }
        
        advice = (
            f"💼 Risk Seviyesi: {risk_level_tr[risk_info['risk_level']]}\n"
            f"📊 Pozisyon Büyüklüğü: %{risk_info['position_size_percent']:.1f}\n"
            f"⚡ Önerilen Leverage: {risk_info['leverage']}x\n"
            f"🎯 Güvenilirlik: %{risk_info['confidence']*100:.0f}"
        )
        
        return advice

