
import sqlite3

def simulate_trades():
    initial_capital = 100.0
    capital = initial_capital
    stop_loss_pct = 0.05

    conn = sqlite3.connect('signals.db')
    cursor = conn.cursor()

    cursor.execute("SELECT signal_id, direction, signal_price, tp1_price FROM signals ORDER BY created_at ASC")
    signals = cursor.fetchall()

    for signal in signals:
        signal_id, direction, signal_price, tp1_price = signal
        sl_price = 0

        if direction == 'LONG':
            sl_price = signal_price * (1 - stop_loss_pct)
        else: # SHORT
            sl_price = signal_price * (1 + stop_loss_pct)

        cursor.execute("SELECT price FROM signal_price_snapshots WHERE signal_id = ? ORDER BY timestamp ASC", (signal_id,))
        price_snapshots = cursor.fetchall()

        trade_closed = False
        for snapshot in price_snapshots:
            price = snapshot[0]
            if direction == 'LONG':
                if price >= tp1_price:
                    profit = (tp1_price - signal_price) / signal_price
                    capital *= (1 + profit)
                    print(f"Trade {signal_id}: TP hit. Capital: {capital:.2f}")
                    trade_closed = True
                    break
                elif price <= sl_price:
                    capital *= (1 - stop_loss_pct)
                    print(f"Trade {signal_id}: SL hit. Capital: {capital:.2f}")
                    trade_closed = True
                    break
            else: # SHORT
                if price <= tp1_price:
                    profit = (signal_price - tp1_price) / signal_price
                    capital *= (1 + profit)
                    print(f"Trade {signal_id}: TP hit. Capital: {capital:.2f}")
                    trade_closed = True
                    break
                elif price >= sl_price:
                    capital *= (1 - stop_loss_pct)
                    print(f"Trade {signal_id}: SL hit. Capital: {capital:.2f}")
                    trade_closed = True
                    break
        
        if not trade_closed and price_snapshots:
            last_price = price_snapshots[-1][0]
            if direction == 'LONG':
                profit = (last_price - signal_price) / signal_price
                capital *= (1 + profit)
            else: #SHORT
                profit = (signal_price - last_price) / signal_price
                capital *= (1 + profit)
            print(f"Trade {signal_id}: Still open. Current capital: {capital:.2f}")


    conn.close()

    print(f"\nInitial capital: ${initial_capital:.2f}")
    print(f"Final capital: ${capital:.2f}")
    print(f"Profit/Loss: ${capital - initial_capital:.2f}")

if __name__ == "__main__":
    simulate_trades()
