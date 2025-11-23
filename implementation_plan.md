# Implementation Plan - Internationalization (i18n)

## Goal Description
Convert the entire project from Turkish to English to support international developers and users. This involves translating code comments, docstrings, and user-facing Telegram messages.

## User Review Required
> [!IMPORTANT]
> **Decision Point:** Should we implement a multi-language system (support both TR/EN) or switch completely to English?
> *   **Recommendation:** Switch completely to English for the codebase (comments/docstrings) to adhere to global standards. For the UI, we can either hard-switch to EN or implement a localization system.
> *   **Current Plan:** I will assume a complete switch to English for simplicity and maintainability unless requested otherwise.

## Proposed Changes

### Phase 1: Codebase Translation (Developer Experience)
Translate all Python docstrings, inline comments, and log messages to English.

#### [MODIFY] Core & Config
*   `main.py`
*   `core/application_factory.py`
*   `config/config_manager.py`
*   `config/constants.py`

#### [MODIFY] Data Layer
*   `data/signal_database.py`
*   `data/signal_repository.py`
*   `data/market_data_manager.py`

#### [MODIFY] Strategy Layer
*   `strategy/position_calculator.py`
*   `strategy/risk_manager.py`
*   `strategy/liquidation_safety_filter.py`
*   `strategy/dynamic_entry_calculator.py`
*   `analysis/ranging_strategy_analyzer.py`

#### [MODIFY] Bot & Scheduler
*   `bot/telegram_bot_manager.py`
*   `scheduler/components/signal_scanner_manager.py`

### Phase 2: UI Translation (User Experience)
Translate Telegram messages and formatting logic.

#### [MODIFY] `bot/formatters/signal_formatter.py`
*   Translate `DIRECTION_TR` dictionary (e.g., `'LONG': 'YÜKSELİŞ'` -> `'LONG': 'LONG'`).
*   Translate message templates (e.g., `"Güncel Fiyat"` -> `"Current Price"`).
*   Translate emoji mappings if necessary.

#### [MODIFY] `bot/formatters/base_formatter.py`
*   Translate helper methods for date/time formatting if they use Turkish locale.

## Verification Plan

### Automated Tests
*   Run existing tests to ensure no logic was broken during translation.
*   `pytest tests/`

### Manual Verification
*   Review generated Telegram messages to ensure English text is correctly formatted.
*   Check logs to verify English log messages.
