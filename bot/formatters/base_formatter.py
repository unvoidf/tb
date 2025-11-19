"""
BaseFormatter: Temel formatlama utility'leri.
Markdown escape ve timestamp formatlama fonksiyonları.
"""
import os
import time
from typing import Optional, List
from datetime import datetime, timezone
from utils.logger import LoggerManager


class BaseFormatter:
    """Temel formatlama işlevlerini sağlar."""
    
    def __init__(self):
        self.logger = LoggerManager().get_logger('BaseFormatter')
    
    @staticmethod
    def escape_markdown_v2(text: str) -> str:
        """
        Telegram MarkdownV2 için özel karakterleri escape eder.
        
        MarkdownV2'de escape edilmesi GEREKEN karakterler (sadece bunlar):
        _ * [ ] ( ) ~ ` 
        
        Not: Diğer karakterler (+, -, =, |, {, }, ., !, >, #) normal metinde 
        escape edilmemeli, sadece özel bağlamlarda gerekli.
        
        Args:
            text: Escape edilecek metin
            
        Returns:
            Escape edilmiş metin
        """
        if not text:
            return text
        
        # MarkdownV2'de MUTLAKA escape edilmesi gereken karakterler
        # Sadece bu karakterler escape edilmeli
        # Not: () parantezler sadece link formatında kullanılıyor, normal metinde escape edilmemeli
        special_chars = ['_', '*', '[', ']', '~', '`']
        
        # Her özel karakteri escape et
        escaped = text
        for char in special_chars:
            escaped = escaped.replace(char, f'\\{char}')
        
        return escaped

    @staticmethod
    def escape_markdown_v2_chars(
        text: str,
        special_chars: Optional[List[str]] = None
    ) -> str:
        """
        MarkdownV2 formatında belirtilen karakterleri escape eder.
        
        Args:
            text: İşlenecek metin
            special_chars: Escape edilecek özel karakter listesi
            
        Returns:
            Escape edilmiş metin
        """
        if not text:
            return text
        
        chars = special_chars or [
            '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|',
            '{', '}', '.', '!'
        ]
        
        escaped = text
        for char in chars:
            escaped = escaped.replace(char, f'\\{char}')
        return escaped
    
    @staticmethod
    def escape_markdown_v2_smart(text: str, preserve_code_blocks: bool = True) -> str:
        """
        Akıllı Markdown escape: Code block ve bold/italic içindeki karakterleri korur.
        
        Telegram'ın MarkdownV2 formatı için:
        - *bold* -> korunur (tek yıldız) - ESCAPE EDİLMEZ
        - _italic_ -> korunur - ESCAPE EDİLMEZ
        - `code` -> korunur - ESCAPE EDİLMEZ
        
        Args:
            text: Escape edilecek metin
            preserve_code_blocks: True ise code block içindeki karakterleri escape etmez
            
        Returns:
            Escape edilmiş metin
        """
        if not text:
            return text
        
        import re
        
        if not preserve_code_blocks:
            return BaseFormatter.escape_markdown_v2_selective(text)
        
        # Code block pattern: `...` (backtick ile çevrili)
        parts = []
        last_end = 0
        
        # Tüm code block'ları bul (backtick ile çevrili)
        pattern = r'`([^`]*)`'
        matches = list(re.finditer(pattern, text))
        
        for match in matches:
            # Code block öncesi kısmı escape et (bold/italic KORUNARAK)
            before = text[last_end:match.start()]
            before_escaped = BaseFormatter.escape_markdown_v2_selective(before)
            parts.append(before_escaped)
            
            # Code block içeriğini olduğu gibi bırak (ESCAPE ETME!)
            # Code block içinde özel karakterler (nokta, köşeli parantez vs.) escape edilmemeli
            code_content = match.group(1)
            # Code block içeriğini hiç escape etme - Telegram zaten code block içinde parse etmez
            parts.append(f'`{code_content}`')
            
            last_end = match.end()
        
        # Kalan kısmı escape et (bold/italic KORUNARAK)
        if last_end < len(text):
            remaining = text[last_end:]
            # Kalan kısımda da code block olabilir, tekrar kontrol et
            remaining_escaped = BaseFormatter.escape_markdown_v2_selective(remaining)
            parts.append(remaining_escaped)
        
        return ''.join(parts)
    
    @staticmethod
    def escape_markdown_v2_selective(text: str) -> str:
        """
        Seçici Markdown escape: Bold (*) ve italic (_) formatlarını korur,
        diğer özel karakterleri escape eder.
        
        Telegram'ın MarkdownV2 formatında:
        - *bold* -> korunur (tek yıldız)
        - _italic_ -> korunur
        - Diğer özel karakterler escape edilir
        
        Args:
            text: Escape edilecek metin
            
        Returns:
            Escape edilmiş metin
        """
        if not text:
            return text
        
        import re
        import uuid
        
        # Bold ve italic pattern'lerini koru
        # *text* -> korunur (MarkdownV2 için tek yıldız)
        # _text_ -> korunur
        
        # Önce bold ve italic pattern'lerini işaretle
        # Sonra diğer özel karakterleri escape et
        # En son bold/italic işaretlerini geri getir
        
        # Geçici placeholder'lar - benzersiz olmalı
        placeholders = {}
        
        # Bold pattern: *text* (MarkdownV2 için tek yıldız)
        def bold_replacer(match):
            unique_id = str(uuid.uuid4())[:8]
            placeholder = f"__BOLD_{unique_id}__"
            content = match.group(1)
            escaped_content = BaseFormatter.escape_markdown_v2_chars(content)
            placeholders[placeholder] = f"*{escaped_content}*"
            return placeholder
        
        # Italic pattern: _text_ (ama * içinde değilse)
        def italic_replacer(match):
            unique_id = str(uuid.uuid4())[:8]
            placeholder = f"__ITALIC_{unique_id}__"
            content = match.group(1)
            escaped_content = BaseFormatter.escape_markdown_v2_chars(content)
            placeholders[placeholder] = f"_{escaped_content}_"
            return placeholder
        
        # Bold'u koru (*text* - tek yıldız, MarkdownV2)
        # Basit pattern: * ile başlayıp * ile biten (ama ** değil)
        text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', bold_replacer, text)
        
        # Italic'i koru (_text_ - alt çizgi)
        text = re.sub(r'(?<!_)_([^_\s]+(?:\s+[^_\s]+)*)_(?!_)', italic_replacer, text)
        
        # Diğer özel karakterleri escape et (bold/italic dışında)
        # Telegram MarkdownV2 dokümantasyonuna göre:
        # "In all other places characters '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!' must be escaped"
        # NOT: Backtick (`) escape edilmemeli çünkü _escape_markdown_v2_smart fonksiyonu
        # code block'ları zaten koruyor. Burada escape edersek code block pattern'i bozulur.
        # Bold/italic pattern'leri placeholder'a çevrildiği için içlerindeki karakterler escape edilmiyor
        # 
        # ÖNEMLİ: Telegram dokümantasyonuna TAMAMEN uymalıyız!
        # Parantezler de dahil tüm özel karakterler escape edilmeli
        # Placeholder mekanizması sayesinde bold/italic içindeki karakterler korunuyor
        text = BaseFormatter.escape_markdown_v2_chars(text)
        
        # Placeholder'ları geri getir (ters sırada - en son eklenenler önce)
        for placeholder, original in reversed(list(placeholders.items())):
            text = text.replace(placeholder, original)
        
        return text
    
    def format_timestamp(self, timestamp: int) -> str:
        """
        Unix timestamp'i Türkiye saatine (UTC+3) formatlar.
        TZ environment variable varsa onu kullanır, yoksa varsayılan olarak Europe/Istanbul kullanır.
        
        Args:
            timestamp: Unix timestamp (saniye, UTC)
            
        Returns:
            Formatlanmış tarih/saat string (Türkiye saati - UTC+3)
        """
        try:
            # Unix timestamp'i UTC datetime'a çevir
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            
            # TZ environment variable kontrolü (esneklik için)
            tz_name = os.getenv('TZ')
            if not tz_name:
                # Varsayılan timezone: Türkiye saati (UTC+3)
                tz_name = 'Europe/Istanbul'
            
            try:
                from zoneinfo import ZoneInfo
                local_dt = dt.astimezone(ZoneInfo(tz_name))
            except ImportError:
                # zoneinfo modülü yoksa (Python < 3.9) UTC kullan
                local_dt = dt
            except Exception:
                # ZoneInfo hata verirse UTC kullan
                local_dt = dt
            
            formatted = local_dt.strftime('%d/%m/%Y %H:%M:%S')
            try:
                self.logger.debug(f"format_timestamp: ts={timestamp} -> {formatted} (timezone: {tz_name})")
            except Exception:
                pass
            return formatted
        except Exception as e:
            # Son çare: basit datetime formatı (sistem saatine göre)
            try:
                return datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y %H:%M:%S')
            except Exception:
                return "Tarih alınamadı"
    
    def format_timestamp_with_seconds(self, timestamp: Optional[int]) -> str:
        """Opsiyonel timestamp'i formatlar."""
        if timestamp is None:
            return "-"
        return self.format_timestamp(timestamp)
    
    def format_time_elapsed(self, start_timestamp: Optional[int], end_timestamp: Optional[int]) -> str:
        """
        İki timestamp arasındaki geçen süreyi human readable formatında döndürür.
        
        Args:
            start_timestamp: Başlangıç timestamp (saniye)
            end_timestamp: Bitiş timestamp (saniye, None ise şu anki zaman)
            
        Returns:
            Human readable zaman farkı (örn: "2 saat 11 dakika", "1 gün 3 saat", "45 dakika")
        """
        try:
            if start_timestamp is None:
                return "-"
            
            if end_timestamp is None:
                end_timestamp = int(time.time())
            
            elapsed_seconds = end_timestamp - start_timestamp
            
            if elapsed_seconds < 0:
                return "-"
            
            # Gün, saat, dakika hesapla
            days = elapsed_seconds // 86400
            hours = (elapsed_seconds % 86400) // 3600
            minutes = (elapsed_seconds % 3600) // 60
            
            # Formatla
            parts = []
            if days > 0:
                parts.append(f"{days} gün" if days == 1 else f"{days} gün")
            if hours > 0:
                parts.append(f"{hours} saat" if hours == 1 else f"{hours} saat")
            if minutes > 0:
                parts.append(f"{minutes} dakika" if minutes == 1 else f"{minutes} dakika")
            
            # Eğer hiçbir şey yoksa (çok kısa süre)
            if not parts:
                if elapsed_seconds > 0:
                    return "1 dakikadan az"
                return "0 dakika"
            
            return " ".join(parts)
            
        except Exception:
            return "-"

    def format_price_with_timestamp(self, price: float, timestamp: Optional[int] = None) -> str:
        """
        Fiyatı tarih/saat bilgisi ile formatlar.
        
        Args:
            price: Fiyat
            timestamp: Unix timestamp (opsiyonel)
            
        Returns:
            Formatlanmış fiyat string
        """
        if price is None:
            return "💰 Fiyat alınamadı"
        
        price_str = f"💰 ${price:,.4f}"
        
        if timestamp:
            time_str = self.format_timestamp(timestamp)
            price_str += f" ({time_str})"
        
        try:
            self.logger.debug(f"format_price_with_timestamp: price={price}, ts={timestamp} -> {price_str}")
        except Exception:
            pass
        return price_str
    
    # Emoji ve string mapping constants
    DIRECTION_EMOJI = {
        'LONG': '📈',
        'SHORT': '📉',
        'NEUTRAL': '➡️'
    }
    
    DIRECTION_TR = {
        'LONG': 'LONG (Alış)',
        'SHORT': 'SHORT (Satış)',
        'NEUTRAL': 'NEUTRAL (Nötr)'
    }

    DIRECTION_TITLE = {
        'LONG': 'LONG',
        'SHORT': 'SHORT',
        'NEUTRAL': 'NEUTRAL'
    }

    DIRECTION_FORECAST = {
        'LONG': 'Yükseliş',
        'SHORT': 'Düşüş',
        'NEUTRAL': 'Nötr'
    }

