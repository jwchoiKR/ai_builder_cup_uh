"""Firestore store (STORE=firestore). Implemented in phase P6 (DEV_SPEC §15)."""
from __future__ import annotations


class FirestoreStore:
    name = "firestore"

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError("STORE=firestore is implemented in phase P6; use STORE=memory")
