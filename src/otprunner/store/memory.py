from __future__ import annotations

from .base import Store


class MemoryStore(Store):
    """Almacén en memoria, para tests."""

    backend = "memory"

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def _load(self) -> dict[str, str]:
        return dict(self.data)

    async def _write(self, name: str, uri: str) -> None:
        self.data[name] = uri

    async def _remove(self, name: str) -> bool:
        return self.data.pop(name, None) is not None
