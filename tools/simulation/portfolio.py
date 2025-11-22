"""
Portfolio Manager
-----------------
Manages portfolio balance, margin, and trade statistics.
"""
from typing import List, Dict


class Portfolio:
    """Manages portfolio state during simulation."""
    
    def __init__(self, balance: float, commission_rate: float):
        self.initial_balance = balance
        self.balance = balance  # Total Balance (Free + Locked)
        self.free_balance = balance  # Available for new trades
        self.peak_balance = balance
        self.max_drawdown_pct = 0.0
        self.equity = balance
        self.commission_rate = commission_rate
        self.trades: List[Dict] = []
        self.balance_history: List[float] = [balance]
        
        # Stats
        self.wins = 0
        self.losses = 0
        self.liquidations = 0
        self.gross_profit = 0.0
        self.gross_loss = 0.0
        self.total_commission_paid = 0.0
        
        # Streaks
        self.current_win_streak = 0
        self.current_loss_streak = 0
        self.max_win_streak = 0
        self.max_loss_streak = 0
        
        # Duration
        self.total_duration_seconds = 0
        
        # Directional Stats
        self.long_wins = 0
        self.long_losses = 0
        self.short_wins = 0
        self.short_losses = 0
        
        self.open_trades = 0
        self.locked_margin = 0.0

    def update_drawdown(self):
        """Updates maximum drawdown percentage."""
        if self.balance > self.peak_balance:
            self.peak_balance = self.balance
        
        drawdown = (self.peak_balance - self.balance) / self.peak_balance * 100
        if drawdown > self.max_drawdown_pct:
            self.max_drawdown_pct = drawdown

    def lock_margin(self, amount: float):
        """Locks margin for a new trade (Isolated Margin)."""
        self.free_balance -= amount
        self.locked_margin += amount

    def release_margin(self, amount: float, pnl: float):
        """Releases margin and adds PnL (Isolated Margin)."""
        self.locked_margin -= amount
        self.free_balance += amount + pnl
        self.balance = self.free_balance + self.locked_margin
        self.update_drawdown()
        self.balance_history.append(self.balance)
    
    def pay_commission(self, amount: float):
        """Deducts commission from balance."""
        self.free_balance -= amount
        self.balance = self.free_balance + self.locked_margin
        self.update_drawdown()

    def add_trade_result(self, trade_result: Dict):
        """Records trade result and updates portfolio statistics."""
        self.trades.append(trade_result)
        
        # Commission Calculation (Entry + Exit)
        position_size = trade_result['position_size']
        entry_comm = position_size * (self.commission_rate / 100)
        exit_comm = position_size * (self.commission_rate / 100)
        total_comm = entry_comm + exit_comm
        self.total_commission_paid += total_comm
        
        # Gross PnL (komisyonsuz)
        gross_pnl = trade_result['pnl']
        
        # Net PnL for statistics (gross_pnl - total_comm)
        net_pnl = gross_pnl - total_comm
        
        # Update Balances: First add gross PnL, then deduct commission
        margin_used = trade_result['margin_used']
        self.release_margin(margin_used, gross_pnl)  # Gross PnL ekleniyor
        self.pay_commission(total_comm)  # Komisyon bakiyeden düşülüyor
        
        direction = trade_result['direction']
        duration = trade_result['duration']
        self.total_duration_seconds += duration
        
        if trade_result['status'] == 'LIQUIDATED':
            self.liquidations += 1
            self.gross_loss += abs(net_pnl)
            self.losses += 1  # Count as loss too
            self.current_loss_streak += 1
            self.current_win_streak = 0
            if self.current_loss_streak > self.max_loss_streak:
                self.max_loss_streak = self.current_loss_streak
            if direction == 'LONG':
                self.long_losses += 1
            else:
                self.short_losses += 1

        elif net_pnl > 0:
            self.gross_profit += net_pnl
            self.wins += 1
            self.current_win_streak += 1
            self.current_loss_streak = 0
            if self.current_win_streak > self.max_win_streak:
                self.max_win_streak = self.current_win_streak
                
            if direction == 'LONG':
                self.long_wins += 1
            else:
                self.short_wins += 1
        else:
            self.gross_loss += abs(net_pnl)
            self.losses += 1
            self.current_loss_streak += 1
            self.current_win_streak = 0
            if self.current_loss_streak > self.max_loss_streak:
                self.max_loss_streak = self.current_loss_streak
                
            if direction == 'LONG':
                self.long_losses += 1
            else:
                self.short_losses += 1

    def get_summary(self) -> Dict:
        """Returns comprehensive portfolio summary."""
        total_trades = self.wins + self.losses  # Liquidations included in losses
        win_rate = (self.wins / total_trades * 100) if total_trades > 0 else 0
        pnl_percent = ((self.balance - self.initial_balance) / self.initial_balance) * 100
        
        profit_factor = (
            (self.gross_profit / self.gross_loss) 
            if self.gross_loss > 0 
            else float('inf')
        )
        
        avg_win = (self.gross_profit / self.wins) if self.wins > 0 else 0
        avg_loss = (self.gross_loss / self.losses) if self.losses > 0 else 0
        
        avg_duration = self.total_duration_seconds / total_trades if total_trades > 0 else 0
        
        long_total = self.long_wins + self.long_losses
        short_total = self.short_wins + self.short_losses
        long_win_rate = (self.long_wins / long_total * 100) if long_total > 0 else 0
        short_win_rate = (self.short_wins / short_total * 100) if short_total > 0 else 0

        return {
            'initial_balance': self.initial_balance,
            'final_balance': self.balance,
            'pnl_amount': self.balance - self.initial_balance,
            'pnl_percent': pnl_percent,
            'total_trades': total_trades,
            'wins': self.wins,
            'losses': self.losses,
            'liquidations': self.liquidations,
            'win_rate': win_rate,
            'open_trades': self.open_trades,
            'locked_margin': self.locked_margin,
            'free_balance': self.free_balance,
            'max_drawdown': self.max_drawdown_pct,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'total_commission': self.total_commission_paid,
            'max_win_streak': self.max_win_streak,
            'max_loss_streak': self.max_loss_streak,
            'avg_duration_seconds': avg_duration,
            'long_stats': {
                'total': long_total, 
                'wins': self.long_wins, 
                'win_rate': long_win_rate
            },
            'short_stats': {
                'total': short_total, 
                'wins': self.short_wins, 
                'win_rate': short_win_rate
            },
            'balance_history': self.balance_history
        }

