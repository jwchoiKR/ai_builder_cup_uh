"""SENSITIVE_APPROVAL: a sensitive question goes to the host, to the operator, or to both at once."""
from __future__ import annotations

import pytest

from app.models.session import Message
from app.pipelines import comments as ops

from .helpers import live_runtime, make_ctx, say


async def show(tmp_path, show_mode: str, mode: str = "operator", **settings):
    ctx = make_ctx(tmp_path, SENSITIVE_APPROVAL=mode, **settings)
    return ctx, await live_runtime(ctx, show_mode)


def close(ctx) -> None:
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()


async def messages(rt) -> list[Message]:
    return await rt.ctx.store.query(rt.path("messages"), Message, order_by="created_at")


def test_both_is_the_shipped_default():
    from app.config import Settings

    assert Settings.model_fields["SENSITIVE_APPROVAL"].default == "both"
