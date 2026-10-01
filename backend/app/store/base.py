"""Store interface (DEV_SPEC §6.3). `memory` and `firestore` implement the same protocol, so
pipelines never know which one is used. Paths follow the Firestore layout:
`sessions` and `sessions/{sid}/<collection>`."""
from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any, Literal, Protocol, TypeVar

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)

Op = Literal["==", "!=", "<", "<=", ">", ">=", "in"]
Filter = tuple[str, Op, Any]

SESSIONS = "sessions"
AGENT_CALLS_GLOBAL = "agent_calls"  # calls made outside a session (e.g. Brief Agent on /setup)
SUBCOLLECTIONS = (
    "segments", "transcripts", "alerts", "comments", "analyses", "groups",
    "answers", "messages", "agent_calls", "events",
)


def sub(session_id: str, name: str) -> str:
    if name not in SUBCOLLECTIONS:
        raise ValueError(f"unknown session collection {name!r}")
    return f"{SESSIONS}/{session_id}/{name}"


def event_doc_id(seq: int) -> str:
    # Zero-padded so lexical order equals numeric order.
    return f"{seq:010d}"


class Transaction(Protocol):
    """Reads see committed data; writes are buffered and applied atomically on exit."""

    async def get(self, path: str, doc_id: str, model: type[M]) -> M | None: ...
    def put(self, path: str, doc_id: str, doc: BaseModel) -> None: ...
    def delete(self, path: str, doc_id: str) -> None: ...


class Store(Protocol):
    name: str

    async def get(self, path: str, doc_id: str, model: type[M]) -> M | None: ...
    async def put(self, path: str, doc_id: str, doc: BaseModel) -> None: ...
    async def delete(self, path: str, doc_id: str) -> None: ...
    async def query(
        self,
        path: str,
        model: type[M],
        *,
        where: Sequence[Filter] = (),
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[M]: ...
    def transaction(self) -> AbstractAsyncContextManager[Transaction]: ...
    async def delete_session(self, session_id: str) -> None:
        """Delete a session document and all its subcollections (demo reset)."""
        ...
