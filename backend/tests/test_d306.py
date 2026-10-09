"""D-306: verifier slowness shown honestly. While the verifier works the host sees a grey "checking" chip (events
verify.started / verify.done), an alert appears only when it answers, and with no answer the alert is kept,
"unverified (AI response delayed)" with its failure type; the operator gets the count by cause. Every call records
its failure type (http_504, client_timeout, http_429, other_error)."""
from __future__ import annotations

import pytest

from app.providers.llm import LLMError, failure_kind

from .judge_fakes import ScriptedBackend, close_env, events, make_env, speak, violation


@pytest.mark.parametrize("status, error, kind", [
    ("ok", None, None),
    ("timeout", "deadline 5000 ms", "client_timeout"),
    ("error", "504 DEADLINE_EXCEEDED. {'error': {'code': 504}}", "http_504"),
    ("error", "429 RESOURCE_EXHAUSTED", "http_429"),
    ("error", "scripted failure", "other_error"),
    ("invalid", "1 validation error", "other_error"),
])
def test_d306_failure_kind(status, error, kind):
    assert failure_kind(status, error) == kind


class _Busy(ScriptedBackend):
    """The verifier's calls fail as Google's shared capacity does."""

    async def generate(self, req, timeout_ms):
        if req.agent == "verifier":
            raise LLMError("504 DEADLINE_EXCEEDED")
        return await super().generate(req, timeout_ms)


LINE = "This cream cures eczema, honestly."

