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

    def _fake_setup(self) -> None:
        self.logger = MagicMock()

    monkeypatch.setattr(logger_module.LoggerManager, "_setup_logger", _fake_setup)

    yield

    logger_module.LoggerManager._instance = None
    logger_module.LoggerManager._initialized = False


def _build_manager(repository: MagicMock, cooldown_hours: int = 1) -> SignalScannerManager:
    return SignalScannerManager(
        coin_filter=MagicMock(),
        command_handler=MagicMock(),
        entry_calculator=MagicMock(),
        message_formatter=MagicMock(),
        bot_manager=MagicMock(),
        channel_id="channel",
        signal_repository=repository,
        confidence_threshold=0.7,
        cooldown_hours=cooldown_hours,
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
    repo.get_last_signal_summary.return_value = None

    manager = _build_manager(repo)

    assert "MINA/USDT" in manager.signal_cache
    cache_entry = manager.signal_cache["MINA/USDT"]
    assert cache_entry["last_direction"] == "LONG"
    assert cache_entry["last_signal_time"] == 1_700_000_000
    assert cache_entry["confidence"] == 0.78


def test_should_send_notification_uses_db_when_cache_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = MagicMock()
    repo.get_recent_signal_summaries.return_value = []

    fixed_now = 2_000_000_000
    last_signal_time = fixed_now - 600

    repo.get_last_signal_summary.return_value = {
        "symbol": "MINA/USDT",
        "direction": "LONG",
        "confidence": 0.81,
        "created_at": last_signal_time,
    }

    manager = _build_manager(repo)

    monkeypatch.setattr(
        "scheduler.components.signal_scanner_manager.time.time",
        lambda: fixed_now,
    )

    should_send = manager._should_send_notification("MINA/USDT", "LONG")

    assert should_send is False
    cache_entry = manager.signal_cache["MINA/USDT"]
    assert cache_entry["last_signal_time"] == last_signal_time
    assert cache_entry["last_direction"] == "LONG"


def test_should_send_notification_allows_direction_change(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = MagicMock()
    repo.get_recent_signal_summaries.return_value = []

    fixed_now = 2_000_000_000
    last_signal_time = fixed_now - 300

    repo.get_last_signal_summary.return_value = {
        "symbol": "MINA/USDT",
        "direction": "LONG",
        "confidence": 0.65,
        "created_at": last_signal_time,
    }

    manager = _build_manager(repo)

    monkeypatch.setattr(
        "scheduler.components.signal_scanner_manager.time.time",
        lambda: fixed_now,
    )

    # İlk kontrol: aynı yön, cooldown devrede
    assert manager._should_send_notification("MINA/USDT", "LONG") is False

    # Yön değişince cooldown bypass edilmeli
    assert manager._should_send_notification("MINA/USDT", "SHORT") is True


def test_should_send_notification_neutral_direction() -> None:
    repo = MagicMock()
    repo.get_recent_signal_summaries.return_value = []

    manager = _build_manager(repo)
    manager.signal_cache["TA/USDT"] = {
        "last_direction": "LONG",
        "last_signal_time": 0,
        "confidence": 0.8,
    }

    assert manager._should_send_notification("TA/USDT", "NEUTRAL") is False


def test_neutral_signal_not_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = MagicMock()
    repo.get_recent_signal_summaries.return_value = []

    manager = _build_manager(repo)
    manager.cmd_handler._analyze_symbol.return_value = {
        "direction": "NEUTRAL",
        "confidence": 0.75,
        "timeframe_signals": {},
    }

    def fake_rank(signals, top_count):
        return [
            {
                "symbol": signals[0]["symbol"],
                "signal": signals[0]["signal"],
                "_ranking_info": {
                    "total_score": 0.8,
                    "base_score": 0.8,
                    "rsi_bonus": 0.0,
                    "volume_bonus": 0.0,
                },
            }
        ]

    monkeypatch.setattr(manager.signal_ranker, "rank_signals", fake_rank)
    send_mock = MagicMock()
    monkeypatch.setattr(manager, "_send_signal_notification", send_mock)

    manager._check_symbol_signal("TA/USDT")

    send_mock.assert_not_called()


