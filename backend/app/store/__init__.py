from __future__ import annotations

from ..config import Settings
from .base import Store
from .memory import MemoryStore


def make_store(settings: Settings, *, firestore_client=None) -> Store:
    if settings.STORE == "firestore":
        from .firestore import FirestoreStore

        return FirestoreStore(settings)
    store: Store = MemoryStore()
    if settings.SESSIONS_FIRESTORE:
        # memory for the shows being worked on, Firestore for all of them (docs/comments-firestore.md)
        from .session_mirror import MirrorWriter, SessionMirrorStore

        store = SessionMirrorStore(store, MirrorWriter(settings.GCP_PROJECT, settings.SESSIONS_FIRESTORE_DATABASE,
                                                       firestore_client))  # a client is passed by tests only
    return store
