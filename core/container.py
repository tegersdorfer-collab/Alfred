"""
Leichter Service-Locator für gemeinsam genutzte Infrastruktur.

Kein vollständiges DI-Framework — aber alle Module können Abhängigkeiten
hier registrieren und abrufen, statt sie als Modul-Globals zu halten.

Verwendung:
    # beim Start (orchestrator.py):
    from core.container import services
    services.register("lzg", lzg_instance)

    # in einer Domain-Funktion:
    from core.container import services
    lzg = services.get("lzg")
"""
from __future__ import annotations
import logging
from typing import Any, TypeVar, Type

log = logging.getLogger(__name__)

T = TypeVar("T")


class ServiceContainer:
    def __init__(self) -> None:
        self._registry: dict[str, Any] = {}

    def register(self, name: str, instance: Any) -> None:
        if name in self._registry:
            log.debug(f"ServiceContainer: '{name}' wird überschrieben")
        self._registry[name] = instance

    def get(self, name: str, default: Any = None) -> Any:
        return self._registry.get(name, default)

    def require(self, name: str) -> Any:
        """Wie get(), aber wirft KeyError wenn nicht registriert."""
        if name not in self._registry:
            raise KeyError(
                f"Service '{name}' nicht registriert. "
                f"Verfügbar: {sorted(self._registry)}"
            )
        return self._registry[name]

    def typed(self, name: str, typ: Type[T]) -> T:
        """Type-safe get mit isinstance-Check."""
        obj = self.require(name)
        if not isinstance(obj, typ):
            raise TypeError(f"Service '{name}' ist {type(obj).__name__}, erwartet {typ.__name__}")
        return obj

    def registered(self) -> list[str]:
        return sorted(self._registry)

    def __contains__(self, name: str) -> bool:
        return name in self._registry


# Singleton — globaler Service-Locator
services = ServiceContainer()
