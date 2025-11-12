#!/usr/bin/env python3
"""
Test script: Aktif sinyalleri manuel olarak günceller (keyboard butonu testi için).
Bot çalışırken güvenli şekilde çalıştırılabilir.
"""
import sys
import os
import time

# Proje root'unu path'e ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.signal_database import SignalDatabase
from data.signal_repository import SignalRepository
from data.market_data_manager import MarketDataManager
from bot.telegram_bot_manager import TelegramBotManager
from bot.message_formatter import MessageFormatter
from config.config_manager import ConfigManager
from utils.retry_handler import RetryHandler
from utils.logger import LoggerManager


def update_active_signals_with_keyboard():
    """Aktif sinyalleri günceller ve keyboard butonu ekler."""
    try:
        print("=" * 60)
        print("Aktif Sinyalleri Manuel Güncelleme (Keyboard Test)")
        print("=" * 60)
        
        # Logger
        logger = LoggerManager().get_logger('TestUpdateSignals')
        
        # Config
        config = ConfigManager()
        logger.info("Config yüklendi")
        
        # Database ve Repository
        # SignalDatabase varsayılan path kullanır: data/signals.db
        signal_db = SignalDatabase()
        signal_repo = SignalRepository(signal_db)
        logger.info("Signal repository hazır")
        
        # Market Data
        # RetryHandler'ı config'den oluştur
        retry_cfg = config.retry_config
        retry_handler = RetryHandler(
            max_attempts=retry_cfg['max_attempts'],
            backoff_base=retry_cfg['backoff_base'],
            initial_delay=retry_cfg['initial_delay']
        )
        market_data = MarketDataManager(retry_handler)
        logger.info("Market data manager hazır")
        
        # Message Formatter
        message_formatter = MessageFormatter()
        logger.info("Message formatter hazır")
        
        # Telegram Bot Manager (sadece mesaj göndermek için, bot çalışmıyor olabilir)
        # Bu durumda direkt Telegram API kullanacağız
        import asyncio
        from telegram import Bot
        from telegram.error import TelegramError
        
        bot = Bot(token=config.telegram_token)
        logger.info("Telegram bot instance hazır")
        
        # Aktif sinyalleri al (72 saatten yeni)
        active_signals = signal_repo.get_active_signals()
        logger.info(f"{len(active_signals)} aktif sinyal bulundu")
        
        if not active_signals:
            print("⚠️  Aktif sinyal bulunamadı!")
            return
        
        print(f"\n📊 {len(active_signals)} aktif sinyal bulundu")
        print("=" * 60)
        
        updated_count = 0
        error_count = 0
        
        for i, signal in enumerate(active_signals, 1):
            signal_id = signal.get('signal_id')
            symbol = signal.get('symbol')
            message_id = signal.get('telegram_message_id')
            channel_id = signal.get('telegram_channel_id')
            
            if not all([signal_id, symbol, message_id, channel_id]):
                logger.warning(f"Sinyal {i}: Eksik bilgi - {signal_id}")
                continue
            
            print(f"\n[{i}/{len(active_signals)}] {symbol} - {signal_id}")
            print(f"  Message ID: {message_id}")
            
            try:
                # Güncel fiyatı al
                current_price, current_price_ts = market_data.get_latest_price_with_timestamp(symbol)
                if not current_price:
                    logger.warning(f"{symbol} güncel fiyat alınamadı")
                    print(f"  ⚠️  Fiyat alınamadı")
                    continue
                
                print(f"  💰 Güncel fiyat: ${current_price}")
                
                # Sinyal verilerini hazırla
                signal_data = signal.get('signal_data', {})
                entry_levels = signal.get('entry_levels', {})
                signal_price = signal.get('signal_price')
                created_at = signal.get('created_at')
                
                # TP/SL hit durumlarını al
                tp_hits_dict = {
                    1: signal.get('tp1_hit', 0) == 1,
                    2: signal.get('tp2_hit', 0) == 1,
                    3: signal.get('tp3_hit', 0) == 1
                }
                tp_hit_times = {
                    1: signal.get('tp1_hit_at'),
                    2: signal.get('tp2_hit_at'),
                    3: signal.get('tp3_hit_at')
                }
                
                sl_hits_dict = {
                    '1': signal.get('sl1_hit', 0) == 1,
                    '1.5': signal.get('sl1_5_hit', 0) == 1,
                    '2': signal.get('sl2_hit', 0) == 1
                }
                sl_hit_times = {
                    '1': signal.get('sl1_hit_at'),
                    '1.5': signal.get('sl1_5_hit_at'),
                    '2': signal.get('sl2_hit_at')
                }
                
                # Confidence change'i al
                confidence_change = signal_repo.get_latest_confidence_change(signal_id)
                
                # Mesajı formatla
                message = message_formatter.format_signal_alert(
                    symbol=symbol,
                    signal_data=signal_data,
                    entry_levels=entry_levels,
                    signal_price=signal_price,
                    now_price=current_price,
                    tp_hits=tp_hits_dict,
                    sl_hits=sl_hits_dict,
                    created_at=created_at,
                    current_price_timestamp=current_price_ts,
                    tp_hit_times=tp_hit_times,
                    sl_hit_times=sl_hit_times,
                    signal_id=signal_id,
                    confidence_change=confidence_change
                )
                
                # Keyboard oluştur
                keyboard = message_formatter.create_signal_keyboard(signal_id)
                
                # Telegram mesajını güncelle (keyboard ile) - ASYNC
                try:
                    # edit_message_text async bir fonksiyon, asyncio.run ile çalıştır
                    async def update_message():
                        return await bot.edit_message_text(
                            chat_id=channel_id,
                            message_id=message_id,
                            text=message,
                            reply_markup=keyboard
                        )
                    
                    result = asyncio.run(update_message())
                    updated_count += 1
                    print(f"  ✅ Mesaj güncellendi (keyboard eklendi)")
                    print(f"     Button: {keyboard.inline_keyboard[0][0].text}")
                    print(f"     Callback: {keyboard.inline_keyboard[0][0].callback_data}")
                    
                    # Rate limiting: Her mesaj arasında 0.6 saniye bekle
                    if i < len(active_signals):
                        time.sleep(0.6)
                        
                except TelegramError as e:
                    error_msg = str(e).lower()
                    if "message to edit not found" in error_msg or "message not found" in error_msg:
                        logger.warning(f"{signal_id} mesajı bulunamadı (silinmiş olabilir)")
                        print(f"  ⚠️  Mesaj bulunamadı (silinmiş)")
                    else:
                        logger.error(f"{signal_id} mesaj güncelleme hatası: {e}")
                        print(f"  ❌ Hata: {str(e)}")
                        error_count += 1
                    
            except Exception as e:
                logger.error(f"{signal_id} işleme hatası: {e}", exc_info=True)
                print(f"  ❌ İşleme hatası: {str(e)}")
                error_count += 1
                continue
        
        print("\n" + "=" * 60)
        print(f"✅ Başarılı: {updated_count} sinyal")
        print(f"❌ Hatalı: {error_count} sinyal")
        print(f"📊 Toplam: {len(active_signals)} sinyal")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Kritik hata: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    update_active_signals_with_keyboard()

