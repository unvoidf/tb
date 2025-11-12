"""
UserWhitelist: Kullanıcı erişim kontrolü.
Yetkili user ID'leri kontrol eder.
"""
from typing import List, Set
from utils.logger import LoggerManager


class UserWhitelist:
    """Bot erişim kontrolü yapar."""
    
    def __init__(self, whitelist_ids: List[int] = None):
        """
        UserWhitelist'i başlatır.
        
        Args:
            whitelist_ids: Yetkili user ID listesi
        """
        self.whitelist: Set[int] = set(whitelist_ids or [])
        self.logger = LoggerManager().get_logger('UserWhitelist')
    
    def is_authorized(self, user_id: int) -> bool:
        """
        Kullanıcının yetkili olup olmadığını kontrol eder.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True ise yetkili
        """
        # Whitelist boşsa tüm kullanıcılara izin ver
        if not self.whitelist:
            try:
                self.logger.debug(f"auth check: user={user_id} -> open access (empty whitelist)")
            except Exception:
                pass
            return True
        
        is_auth = user_id in self.whitelist
        try:
            self.logger.debug(f"auth check: user={user_id} -> {is_auth}")
        except Exception:
            pass
        
        if not is_auth:
            self.logger.warning(
                f"Yetkisiz erişim denemesi: User ID {user_id}"
            )
        
        return is_auth
    
    def add_user(self, user_id: int) -> None:
        """
        Whitelist'e user ekler.
        
        Args:
            user_id: Telegram user ID
        """
        self.whitelist.add(user_id)
        self.logger.info(f"User ID {user_id} whitelist'e eklendi")
    
    def remove_user(self, user_id: int) -> None:
        """
        Whitelist'den user çıkarır.
        
        Args:
            user_id: Telegram user ID
        """
        self.whitelist.discard(user_id)
        self.logger.info(f"User ID {user_id} whitelist'den çıkarıldı")
    
    def get_whitelist(self) -> List[int]:
        """
        Whitelist'i döndürür.
        
        Returns:
            Yetkili user ID listesi
        """
        return list(self.whitelist)
    
    def get_unauthorized_message(self) -> str:
        """
        Yetkisiz kullanıcı mesajı.
        
        Returns:
            Türkçe hata mesajı
        """
        return (
            "⛔ Yetkisiz Erişim\n\n"
            "Bu botu kullanma yetkiniz bulunmamaktadır.\n"
            "Erişim için bot yöneticisiyle iletişime geçiniz."
        )

