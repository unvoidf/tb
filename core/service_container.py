"""
ServiceContainer: Dependency injection container.
Manages services and resolves dependencies.
"""
from typing import Dict, Type, Any, Callable, Optional
from utils.logger import LoggerManager


class ServiceContainer:
    """Dependency injection container."""
    
    def __init__(self):
        """Initializes ServiceContainer."""
        self._services: Dict[Type, Any] = {}
        self._factories: Dict[Type, Callable] = {}
        self._singletons: Dict[Type, Any] = {}
        self.logger = LoggerManager().get_logger('ServiceContainer')
    
    def register_singleton(self, service_type: Type, instance: Any) -> None:
        """
        Registers a singleton service.
        
        Args:
            service_type: Service type
            instance: Service instance
        """
        self._singletons[service_type] = instance
        self.logger.debug(f"Singleton registered: {service_type.__name__}")
    
    def register_factory(self, service_type: Type, factory: Callable) -> None:
        """
        Registers a factory service.
        
        Args:
            service_type: Service type
            factory: Factory function
        """
        self._factories[service_type] = factory
        self.logger.debug(f"Factory registered: {service_type.__name__}")
    
    def register_instance(self, service_type: Type, instance: Any) -> None:
        """
        Registers an instance service.
        
        Args:
            service_type: Service type
            instance: Service instance
        """
        self._services[service_type] = instance
        self.logger.debug(f"Instance registered: {service_type.__name__}")
    
    def get(self, service_type: Type) -> Any:
        """
        Returns service instance.
        
        Args:
            service_type: Service type
            
        Returns:
            Service instance
            
        Raises:
            ValueError: When service is not found
        """
        # Singleton check
        if service_type in self._singletons:
            return self._singletons[service_type]
        
        # Instance check
        if service_type in self._services:
            return self._services[service_type]
        
        # Factory check
        if service_type in self._factories:
            instance = self._factories[service_type]()
            self.logger.debug(f"Factory created: {service_type.__name__}")
            return instance
        
        raise ValueError(f"Service not found: {service_type.__name__}")
    
    def get_optional(self, service_type: Type) -> Optional[Any]:
        """
        Returns optional service instance.
        
        Args:
            service_type: Service type
            
        Returns:
            Service instance or None
        """
        try:
            return self.get(service_type)
        except ValueError:
            return None
    
    def is_registered(self, service_type: Type) -> bool:
        """
        Checks if service is registered.
        
        Args:
            service_type: Service type
            
        Returns:
            Whether registered
        """
        return (service_type in self._services or 
                service_type in self._factories or 
                service_type in self._singletons)
    
    def clear(self) -> None:
        """Clears all services."""
        self._services.clear()
        self._factories.clear()
        self._singletons.clear()
        self.logger.debug("All services cleared")
