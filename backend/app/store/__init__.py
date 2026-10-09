from __future__ import annotations

from ..config import Settings
from .base import Store
from .memory import MemoryStore


def make_store(settings: Settings, *, firestore_client=None) -> Store:
    """D-428: one Firestore writer (STORE=firestore); the comments team's session mirror was merged into it."""
    if settings.STORE == "firestore":
        from .firestore import FirestoreStore

        return FirestoreStore(settings, client=firestore_client)  # a client is passed by tests only
    return MemoryStore()
