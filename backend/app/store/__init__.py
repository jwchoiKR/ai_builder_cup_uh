from __future__ import annotations

from ..config import Settings
from .base import Store
from .memory import MemoryStore


def make_store(settings: Settings, *, comments_client=None) -> Store:
    if settings.STORE == "memory":
        store: Store = MemoryStore()
    else:
        from .firestore import FirestoreStore

        store = FirestoreStore(settings)
    if settings.COMMENTS_FIRESTORE:
        # the comment collections go to Firestore whatever the main store is (docs/comments-firestore.md)
        from .comment_mirror import CommentMirrorStore, CommentWriter

        store = CommentMirrorStore(store, CommentWriter(settings.GCP_PROJECT, settings.COMMENTS_FIRESTORE_DATABASE,
                                                        comments_client))  # a client is passed by tests only
    return store
