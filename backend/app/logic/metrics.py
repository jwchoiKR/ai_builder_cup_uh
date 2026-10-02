"""Session metrics (DEV_SPEC §8.16). Pure: computed from stored documents and runtime counters."""
from __future__ import annotations

import statistics
from collections.abc import Sequence
from typing import Any

from ..models.session import AgentCall, Alert, Comment, Message, Transcript

# The judge whose latency decides the red alert path: compliance_judge in split3 (D-099).
JUDGE_AGENTS = ("compliance_judge", "utterance_judge", "judge_single")


def percentile(values: Sequence[int | float], q: float) -> int | None:
    """Nearest-rank percentile on sorted values; None when empty."""
    if not values:
        return None
    s = sorted(values)
    rank = max(1, -(-int(q * 100) * len(s) // 100))  # ceil(q * n), at least 1
    return int(s[min(rank, len(s)) - 1])


def _median(values: Sequence[int]) -> int | None:
    return int(statistics.median(values)) if values else None


def _seconds(ms: int | None) -> float | None:
    return None if ms is None else round(ms / 1000, 1)


def compute_metrics(
    *,
    alerts: Sequence[Alert],
    transcripts: Sequence[Transcript],
    agent_calls: Sequence[AgentCall],
    messages: Sequence[Message],
    comments: Sequence[Comment],
    counters: dict[str, int],
    reply_latencies: dict[str, list[int]],
    triage_hits: int,
    triage_misses: int,
) -> dict[str, Any]:
    by_transcript = {t.transcript_id: t for t in transcripts}

    # Compliance alerts that became active (shown_at is the activation time, not the chip time).
    shown = sorted((a for a in alerts if a.kind == "compliance" and a.shown_at is not None), key=lambda a: a.shown_at)
    server, render = [], []
    last_server = last_render = None
    for a in shown:
        t = by_transcript.get(a.transcript_id)
        if t is None:
            continue
        last_server = a.shown_at - t.speech_end_at
        server.append(last_server)
        if a.host_rendered_at is not None:
            last_render = a.host_rendered_at - t.speech_end_at
            render.append(last_render)
        else:
            last_render = None
    if shown and by_transcript.get(shown[-1].transcript_id) is None:
        last_server = last_render = None

    corrections = [a.resolved_at - a.shown_at for a in alerts
                   if a.kind == "compliance" and a.status == "corrected" and a.resolved_at is not None and a.shown_at is not None]

    agents: dict[str, dict[str, Any]] = {}
    for c in agent_calls:
        row = agents.setdefault(c.agent, {"latencies": [], "ok": 0, "timeout": 0, "error": 0, "invalid": 0})
        row[c.status] += 1
        if c.status == "ok":
            row["latencies"].append(c.latency_ms)
    agent_stats = {
        name: {"p50_ms": percentile(r["latencies"], 0.5), "p95_ms": percentile(r["latencies"], 0.95),
               "max_ms": max(r["latencies"]) if r["latencies"] else None,
               "ok": r["ok"], "timeout": r["timeout"], "error": r["error"], "invalid": r["invalid"]}
        for name, r in agents.items()
    }

    stt = [t.received_at - t.speech_end_at for t in transcripts if t.source == "mic" and t.is_final]

    by_kind: dict[str, int] = {}
    for m in messages:
        if m.state == "published":
            by_kind[m.kind] = by_kind.get(m.kind, 0) + 1

    instant = counters.get("instant_answers", 0)
    composed = counters.get("composed_answers", 0)
    judge_p50 = next((agent_stats[a]["p50_ms"] for a in JUDGE_AGENTS
                      if a in agent_stats and agent_stats[a]["p50_ms"] is not None), None)

    return {
        "alert": {
            "last_server_ms": last_server,
            "last_render_ms": last_render,
            "server_p50_ms": percentile(server, 0.5),
            "server_p95_ms": percentile(server, 0.95),
            "render_p50_ms": percentile(render, 0.5),
            "render_p95_ms": percentile(render, 0.95),
            "count": len(server),
        },
        "correction": {"p50_ms": percentile(corrections, 0.5), "p95_ms": percentile(corrections, 0.95),
                       "count": len(corrections)},
        "agents": agent_stats,
        "answers": {
            "instant": instant,
            "composed": composed,
            "median_reply_ms": {"instant": _median(reply_latencies.get("instant", [])),
                                "composed": _median(reply_latencies.get("composed", []))},
        },
        "triage_cache": {"hits": triage_hits, "misses": triage_misses},
        "messages_by_kind": by_kind,
        "stt_final_latency_ms": {"p50_ms": percentile(stt, 0.5), "p95_ms": percentile(stt, 0.95), "count": len(stt)},
        "header": {
            "alert_in_s": _seconds(last_render if last_render is not None else last_server),
            "judge_p50_s": _seconds(judge_p50),
            "instant_answers": instant,
            "answers_total": instant + composed,
        },
        "comments": len(comments),
        # flat keys kept for P1 clients
        "instant_answers": instant,
        "composed_answers": composed,
        "triage_cache_hits": triage_hits,
        "triage_cache_misses": triage_misses,
    }
