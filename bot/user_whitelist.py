"""
UserWhitelist: User access control.
Checks authorized user IDs.
"""
from typing import List, Set
from utils.logger import LoggerManager


class UserWhitelist:
    """Performs bot access control."""
    
    def __init__(self, whitelist_ids: List[int] = None):
        """
        Initializes UserWhitelist.
        
        Args:
            whitelist_ids: List of authorized user IDs
        """
        self.whitelist: Set[int] = set(whitelist_ids or [])
        self.logger = LoggerManager().get_logger('UserWhitelist')
    
    def is_authorized(self, user_id: int) -> bool:
        """
        Checks if the user is authorized.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if authorized
        """
        # If whitelist is empty, allow all users
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
                f"Unauthorized access attempt: User ID {user_id}"
            )
        
        return is_auth
    
    def add_user(self, user_id: int) -> None:
        """
        Adds user to whitelist.
        
        Args:
            user_id: Telegram user ID
        """
        self.whitelist.add(user_id)
        self.logger.info(f"User ID {user_id} added to whitelist")
    
    def remove_user(self, user_id: int) -> None:
        """
        Removes user from whitelist.
        
        Args:
            user_id: Telegram user ID
        """
        self.whitelist.discard(user_id)
        self.logger.info(f"User ID {user_id} removed from whitelist")
    
    def get_whitelist(self) -> List[int]:
        """
        Returns whitelist.
        
        Returns:
            List of authorized user IDs
        """
        return list(self.whitelist)
    
    def get_unauthorized_message(self) -> str:
        """
        Unauthorized user message.
        
        Returns:
            Error message
        """
        return (
            "⛔ Unauthorized Access\n\n"
            "You are not authorized to use this bot.\n"
            "Please contact the bot administrator for access."
        )

