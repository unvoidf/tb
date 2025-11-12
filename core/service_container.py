"""
ServiceContainer: Dependency injection container.
Servisleri yönetir ve bağımlılıkları çözer.
"""
from typing import Dict, Type, Any, Callable, Optional
from utils.logger import LoggerManager


class ServiceContainer:
    """Dependency injection container."""
    
    def __init__(self):
        """ServiceContainer'ı başlatır."""
        self._services: Dict[Type, Any] = {}
        self._factories: Dict[Type, Callable] = {}
        self._singletons: Dict[Type, Any] = {}
        self.logger = LoggerManager().get_logger('ServiceContainer')
    
    def register_singleton(self, service_type: Type, instance: Any) -> None:
        """
        Singleton servis kaydeder.
        
        Args:
            service_type: Servis tipi
            instance: Servis instance'ı
        """
        self._singletons[service_type] = instance
        self.logger.debug(f"Singleton registered: {service_type.__name__}")
    
    def register_factory(self, service_type: Type, factory: Callable) -> None:
        """
        Factory servis kaydeder.
        
        Args:
            service_type: Servis tipi
            factory: Factory fonksiyonu
        """
        self._factories[service_type] = factory
        self.logger.debug(f"Factory registered: {service_type.__name__}")
    
    def register_instance(self, service_type: Type, instance: Any) -> None:
        """
        Instance servis kaydeder.
        
        Args:
            service_type: Servis tipi
            instance: Servis instance'ı
        """
        self._services[service_type] = instance
        self.logger.debug(f"Instance registered: {service_type.__name__}")
    
    def get(self, service_type: Type) -> Any:
        """
        Servis instance'ını döndürür.
        
        Args:
            service_type: Servis tipi
            
        Returns:
            Servis instance'ı
            
        Raises:
            ValueError: Servis bulunamadığında
        """
        # Singleton kontrolü
        if service_type in self._singletons:
            return self._singletons[service_type]
        
        # Instance kontrolü
        if service_type in self._services:
            return self._services[service_type]
        
        # Factory kontrolü
        if service_type in self._factories:
            instance = self._factories[service_type]()
            self.logger.debug(f"Factory created: {service_type.__name__}")
            return instance
        
        raise ValueError(f"Service not found: {service_type.__name__}")
    
    def get_optional(self, service_type: Type) -> Optional[Any]:
        """
        Opsiyonel servis instance'ını döndürür.
        
        Args:
            service_type: Servis tipi
            
        Returns:
            Servis instance'ı veya None
        """
        try:
            return self.get(service_type)
        except ValueError:
            return None
    
    def is_registered(self, service_type: Type) -> bool:
        """
        Servisin kayıtlı olup olmadığını kontrol eder.
        
        Args:
            service_type: Servis tipi
            
        Returns:
            Kayıtlı mı
        """
        return (service_type in self._services or 
                service_type in self._factories or 
                service_type in self._singletons)
    
    def clear(self) -> None:
        """Tüm servisleri temizler."""
        self._services.clear()
        self._factories.clear()
        self._singletons.clear()
        self.logger.debug("All services cleared")
