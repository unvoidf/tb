"""
Unit Tests for Simulation Portfolio
-----------------------------------
Tests for Portfolio class in simulation module.
"""
import pytest
from tools.simulation.portfolio import Portfolio


class TestPortfolio:
    """Test suite for Portfolio class."""
    
    def test_portfolio_initialization(self):
        """Test portfolio initialization."""
        portfolio = Portfolio(balance=10000.0, commission_rate=0.075)
        
        assert portfolio.initial_balance == 10000.0
        assert portfolio.balance == 10000.0
        assert portfolio.free_balance == 10000.0
        assert portfolio.commission_rate == 0.075
        assert portfolio.open_trades == 0
        assert portfolio.locked_margin == 0.0
        assert portfolio.wins == 0
        assert portfolio.losses == 0
    
    def test_lock_margin(self):
        """Test margin locking."""
        portfolio = Portfolio(balance=10000.0, commission_rate=0.075)
        
        portfolio.lock_margin(1000.0)
        
        assert portfolio.free_balance == 9000.0
        assert portfolio.locked_margin == 1000.0
        assert portfolio.balance == 10000.0
    
    def test_release_margin_with_profit(self):
        """Test margin release with profit."""
        portfolio = Portfolio(balance=10000.0, commission_rate=0.075)
        
        # Lock margin first
        portfolio.lock_margin(1000.0)
        assert portfolio.free_balance == 9000.0
        
        # Release with profit: margin (1000) + profit (500) = 1500 added to free
        portfolio.release_margin(1000.0, 500.0)
        
        # Free balance: 9000 (locked) + 1000 (margin returned) + 500 (profit) = 10500
        assert portfolio.free_balance == 10500.0
        assert portfolio.locked_margin == 0.0
        assert portfolio.balance == 10500.0
    
    def test_release_margin_with_loss(self):
        """Test margin release with loss."""
        portfolio = Portfolio(balance=10000.0, commission_rate=0.075)
        
        # Lock margin first
        portfolio.lock_margin(1000.0)
        assert portfolio.free_balance == 9000.0
        
        # Release with loss: margin (1000) + loss (-300) = 700 added to free
        portfolio.release_margin(1000.0, -300.0)
        
        # Free balance: 9000 (locked) + 1000 (margin returned) - 300 (loss) = 9700
        assert portfolio.free_balance == 9700.0
        assert portfolio.locked_margin == 0.0
        assert portfolio.balance == 9700.0
    
    def test_pay_commission(self):
        """Test commission payment."""
        portfolio = Portfolio(balance=10000.0, commission_rate=0.075)
        
        portfolio.pay_commission(50.0)
        
        assert portfolio.free_balance == 9950.0
        assert portfolio.balance == 9950.0
    
    def test_add_winning_trade(self):
        """Test adding a winning trade."""
        portfolio = Portfolio(balance=10000.0, commission_rate=0.075)
        
        trade_result = {
            'symbol': 'BTC/USDT',
            'direction': 'LONG',
            'status': 'WIN',
            'pnl': 500.0,  # Gross PnL
            'margin_used': 1000.0,
            'position_size': 5000.0,
            'duration': 3600
        }
        
        # Lock margin first (as it would be in real simulation)
        portfolio.lock_margin(1000.0)
        
        portfolio.add_trade_result(trade_result)
        
        assert portfolio.wins == 1
        assert portfolio.losses == 0
        assert portfolio.long_wins == 1
        assert portfolio.long_losses == 0
        assert portfolio.current_win_streak == 1
        assert portfolio.current_loss_streak == 0
    
    def test_add_losing_trade(self):
        """Test adding a losing trade."""
        portfolio = Portfolio(balance=10000.0, commission_rate=0.075)
        
        trade_result = {
            'symbol': 'BTC/USDT',
            'direction': 'SHORT',
            'status': 'LOSS',
            'pnl': -300.0,  # Gross PnL
            'margin_used': 1000.0,
            'position_size': 5000.0,
            'duration': 1800
        }
        
        # Lock margin first
        portfolio.lock_margin(1000.0)
        
        portfolio.add_trade_result(trade_result)
        
        assert portfolio.wins == 0
        assert portfolio.losses == 1
        assert portfolio.short_wins == 0
        assert portfolio.short_losses == 1
        assert portfolio.current_win_streak == 0
        assert portfolio.current_loss_streak == 1
    
    def test_add_liquidated_trade(self):
        """Test adding a liquidated trade."""
        portfolio = Portfolio(balance=10000.0, commission_rate=0.075)
        
        trade_result = {
            'symbol': 'BTC/USDT',
            'direction': 'LONG',
            'status': 'LIQUIDATED',
            'pnl': -1000.0,  # Full margin loss
            'margin_used': 1000.0,
            'position_size': 5000.0,
            'duration': 900
        }
        
        # Lock margin first
        portfolio.lock_margin(1000.0)
        
        portfolio.add_trade_result(trade_result)
        
        assert portfolio.liquidations == 1
        assert portfolio.losses == 1  # Liquidation counts as loss
        assert portfolio.wins == 0
    
    def test_drawdown_calculation(self):
        """Test maximum drawdown calculation."""
        portfolio = Portfolio(balance=10000.0, commission_rate=0.075)
        
        # Initial peak
        assert portfolio.peak_balance == 10000.0
        assert portfolio.max_drawdown_pct == 0.0
        
        # Loss reduces balance
        portfolio.lock_margin(1000.0)
        portfolio.release_margin(1000.0, -2000.0)  # Big loss
        portfolio.pay_commission(50.0)
        
        # Drawdown should be calculated
        assert portfolio.balance < portfolio.initial_balance
        assert portfolio.max_drawdown_pct > 0
    
    def test_get_summary(self):
        """Test portfolio summary generation."""
        portfolio = Portfolio(balance=10000.0, commission_rate=0.075)
        
        # Add some trades
        portfolio.lock_margin(1000.0)
        portfolio.add_trade_result({
            'symbol': 'BTC/USDT',
            'direction': 'LONG',
            'status': 'WIN',
            'pnl': 500.0,
            'margin_used': 1000.0,
            'position_size': 5000.0,
            'duration': 3600
        })
        
        summary = portfolio.get_summary()
        
        assert 'initial_balance' in summary
        assert 'final_balance' in summary
        assert 'pnl_amount' in summary
        assert 'pnl_percent' in summary
        assert 'total_trades' in summary
        assert 'wins' in summary
        assert 'losses' in summary
        assert 'win_rate' in summary
        assert 'profit_factor' in summary
        assert summary['wins'] == 1
        assert summary['total_trades'] == 1

