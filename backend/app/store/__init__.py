from __future__ import annotations

from ..config import Settings
from .base import Store
from .memory import MemoryStore


def make_store(settings: Settings) -> Store:
    if settings.STORE == "memory":
        return MemoryStore()
    from .firestore import FirestoreStore

    return FirestoreStore(settings)
