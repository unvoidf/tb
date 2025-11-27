
import pytest
from bot.message_formatter import MessageFormatter

def test_format_signal_alert_simulation(mocker):
    """Tests format_signal_alert method with simulated signal data."""
    mocker.patch('bot.message_formatter.LoggerManager')
    formatter = MessageFormatter()

    symbol = "TEST/USDT"
    current_price = 100.0
    signal_data = {
        'direction': 'LONG',
        'confidence': 0.85
    }
    entry_levels = {
        'atr': 5.0,
        'timeframe': '1h',
        'immediate': {
            'price': 100.1,
            'risk_level': 'Orta',
            'expectation': 'Hızlı hareket',
            'explanation_detail': 'Güncel Fiyat + %0.1 = 100.000000 x 1.001 = 100.100000',
            'price_change_pct': 0.1
        },
        'optimal': {
            'price': 95.0,
            'risk_level': 'Düşük',
            'expectation': 'ATR bazlı düzeltme',
            'explanation_detail': 'ATR (1h) = 5.000000, Formül: Güncel Fiyat - ATR = 100.000000 - 5.000000 = 95.000000',
            'price_change_pct': -5.0
        },
        'conservative': {
            'price': 90.0,
            'risk_level': 'Çok Düşük',
            'expectation': 'ATR bazlı güvenli seviye',
            'explanation_detail': 'ATR (1h) = 5.000000, Formül: Güncel Fiyat - 2 x ATR = 100.000000 - 2 x 5.000000 = 90.000000',
            'price_change_pct': -10.0
        }
    }

    created_at = 1_700_000_000
    current_price_timestamp = created_at + 60
    signal_id = "20251107-074546-TESTUSDT"

    message = formatter.format_signal_alert(
        symbol=symbol,
        signal_data=signal_data,
        entry_levels=entry_levels,
        signal_price=current_price,
        now_price=current_price,
        tp_hits={1: False, 2: False, 3: False},
        sl_hits={'1': False, '1.5': False, '2': False},
        created_at=created_at,
        current_price_timestamp=current_price_timestamp,
        tp_hit_times={1: None, 2: None, 3: None},
        sl_hit_times={'1': None, '1.5': None, '2': None},
        signal_id=signal_id
    )
    
    print("--- SIMULATED MESSAGE ---")
    print(message)
    print("--- END SIMULATED MESSAGE ---")

    assert "*Giriş:*" in message
    assert "*Durum:*" in message
    assert "🎯 *HEDEFLER*" in message
    assert "🛡 *STOP LOSS*" in message
    assert "📊 *Teknik Detay*" in message
    assert f"`{signal_id}`" not in message  # ID escape edilmiyor


def test_escape_handles_plus_inside_bold(mocker):
    """Tests that markdown escape correctly handles plus sign inside bold text."""
    mocker.patch('bot.message_formatter.LoggerManager')
    formatter = MessageFormatter()
    
    raw_text = "*+0.44%*"
    escaped = formatter._escape_markdown_v2_selective(raw_text)
    
    assert escaped == "*\\+0\\.44%*"
