from unittest.mock import MagicMock

import pytest

from scheduler.components.signal_scanner_manager import SignalScannerManager


@pytest.fixture(autouse=True)
def mock_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    from utils import logger as logger_module

    monkeypatch.setattr(logger_module.LoggerManager, "_instance", None)
    monkeypatch.setattr(logger_module.LoggerManager, "_initialized", False)

    monkeypatch.setattr(
        logger_module.LoggerManager,
        "_setup_log_directory",
        lambda self: None,
    )

    def _fake_setup(self, all_real_handlers=None) -> None:
        self.logger = MagicMock()

    monkeypatch.setattr(logger_module.LoggerManager, "_setup_logger", _fake_setup)

    yield

    logger_module.LoggerManager._instance = None
    logger_module.LoggerManager._initialized = False


def _build_manager(repository: MagicMock) -> SignalScannerManager:
    return SignalScannerManager(
        coin_filter=MagicMock(),
        market_data=MagicMock(),
        signal_generator=MagicMock(),
        entry_calculator=MagicMock(),
        message_formatter=MagicMock(),
        bot_manager=MagicMock(),
        channel_id="channel",
        signal_repository=repository,
        confidence_threshold=0.7,
    )


def test_cache_warmup_populates_cache() -> None:
    repo = MagicMock()
    repo.get_recent_signal_summaries.return_value = [
        {
            "symbol": "MINA/USDT",
            "direction": "LONG",
            "confidence": 0.78,
            "created_at": 1_700_000_000,
        }
    ]
    repo.get_latest_active_signal_by_symbol.return_value = None

    manager = _build_manager(repo)

    assert "MINA/USDT" in manager.signal_cache
    cache_entry = manager.signal_cache["MINA/USDT"]
    assert cache_entry["has_active_signal"] is True
    assert cache_entry["direction"] == "LONG"
    assert cache_entry["confidence"] == 0.78


def test_should_send_notification_uses_db_when_cache_empty() -> None:
    repo = MagicMock()
    repo.get_recent_signal_summaries.return_value = []

    # Aktif sinyal var
    repo.get_latest_active_signal_by_symbol.return_value = {
        "symbol": "MINA/USDT",
        "direction": "LONG",
        "confidence": 0.81,
        "created_at": 1_700_000_000,
        "signal_id": "TEST_001",
    }

    manager = _build_manager(repo)
    manager.market_data.get_latest_price.return_value = 100.0

    signal_data = {"confidence": 0.75, "score_breakdown": {}, "market_context": {}}
    should_send = manager._should_send_notification("MINA/USDT", "LONG", signal_data)

    assert should_send is False
    cache_entry = manager.signal_cache["MINA/USDT"]
    assert cache_entry["has_active_signal"] is True
    assert cache_entry["direction"] == "LONG"


def test_should_send_notification_blocks_when_active_signal_exists() -> None:
    repo = MagicMock()
    repo.get_recent_signal_summaries.return_value = []

    # Aktif sinyal var
    repo.get_latest_active_signal_by_symbol.return_value = {
        "symbol": "MINA/USDT",
        "direction": "LONG",
        "confidence": 0.65,
        "created_at": 1_700_000_000,
        "signal_id": "TEST_001",
    }

    manager = _build_manager(repo)
    manager.market_data.get_latest_price.return_value = 100.0

    signal_data = {"confidence": 0.75, "score_breakdown": {}, "market_context": {}}
    
    # Aktif sinyal var, yeni sinyal reddedilmeli (yön fark etmez)
    assert manager._should_send_notification("MINA/USDT", "LONG", signal_data) is False
    assert manager._should_send_notification("MINA/USDT", "SHORT", signal_data) is False


def test_should_send_notification_neutral_direction() -> None:
    repo = MagicMock()
    repo.get_recent_signal_summaries.return_value = []

    manager = _build_manager(repo)
    manager.market_data.get_latest_price.return_value = 100.0

    signal_data = {"confidence": 0.75, "score_breakdown": {}, "market_context": {}}
    
    # NEUTRAL yönlü sinyaller her zaman reddedilir
    assert manager._should_send_notification("TA/USDT", "NEUTRAL", signal_data) is False


def test_neutral_signal_not_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = MagicMock()
    repo.get_recent_signal_summaries.return_value = []
    repo.get_latest_active_signal_by_symbol.return_value = None

    manager = _build_manager(repo)
    manager.market_data.get_latest_price.return_value = 100.0
    
    def fake_generate_signal(multi_tf_data, symbol=None, return_reason=False):
        return {
            "direction": "NEUTRAL",
            "confidence": 0.75,
            "timeframe_signals": {},
        }

    monkeypatch.setattr(manager.signal_gen, "generate_signal", fake_generate_signal)
    send_mock = MagicMock()
    monkeypatch.setattr(manager, "_send_signal_notification", send_mock)

    manager._check_symbol_signal("TA/USDT")

    send_mock.assert_not_called()


