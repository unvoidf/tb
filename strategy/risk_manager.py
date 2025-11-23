"""
RiskManager: Risk management class.
Leverage suggestion and position size calculation.
"""
from typing import Dict
from utils.logger import LoggerManager


class RiskManager:
    """Calculates risk management and position size."""
    
    def __init__(self,
                 risk_low: float = 0.01,
                 risk_medium: float = 0.03,
                 risk_high: float = 0.05,
                 leverage_min: int = 1,
                 leverage_max: int = 10):
        """
        Initializes RiskManager.
        
        Args:
            risk_low: Low risk percentage
            risk_medium: Medium risk percentage
            risk_high: High risk percentage
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
        Calculates position size and leverage.
        
        Args:
            position_info: Position information
            signal_confidence: Signal confidence (0-1)
            
        Returns:
            Position sizing information
        """
        # Determine risk level
        risk_level = self._determine_risk_level(signal_confidence)
        self.logger.debug(
            f"determine_risk_level: confidence={signal_confidence:.3f} -> {risk_level}"
        )
        account_risk = self.risk_levels[risk_level]
        
        # Leverage suggestion
        leverage = self._calculate_leverage(
            signal_confidence,
            position_info.get('risk_percent', 2.0)
        )
        self.logger.debug(
            f"calculate_leverage: confidence={signal_confidence:.3f}, pos_risk={position_info.get('risk_percent', 2.0):.3f} -> leverage={leverage}"
        )
        
        # Position size percentage
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
        Determines risk level based on confidence.
        
        Args:
            confidence: Signal confidence
            
        Returns:
            'low', 'medium', or 'high'
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
        Calculates leverage based on confidence and volatility.
        
        Args:
            confidence: Signal confidence
            risk_percent: Position risk percentage
            
        Returns:
            Leverage value
        """
        # High confidence -> high leverage
        base_leverage = confidence * self.leverage_max
        
        # High volatility -> low leverage
        if risk_percent > 5.0:
            volatility_factor = 0.5
        elif risk_percent > 3.0:
            volatility_factor = 0.7
        else:
            volatility_factor = 1.0
        
        leverage = int(base_leverage * volatility_factor)
        
        # Keep within min-max range
        leverage = max(self.leverage_min, min(self.leverage_max, leverage))
        
        return leverage
    
    def _calculate_position_percent(
        self, account_risk: float, 
        position_risk: float,
        leverage: int
    ) -> float:
        """
        Calculates position size percentage.
        
        Args:
            account_risk: Account risk percentage (0.01 = 1%)
            position_risk: Position risk percentage (%)
            leverage: Leverage to use
            
        Returns:
            Position size percentage
        """
        # Risk = (Position Size * Position Risk%) / Leverage
        # Position Size = (Account Risk * Leverage) / Position Risk%
        
        position_size = (account_risk * 100 * leverage) / position_risk
        
        # Limit to maximum 100% (with leverage)
        max_size = 100.0
        
        return min(position_size, max_size)
    
    def format_risk_advice(self, risk_info: Dict) -> str:
        """
        Formats risk management advice in Turkish.
        
        Args:
            risk_info: Risk information
            
        Returns:
            Formatted advice text
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

