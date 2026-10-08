"""Post-broadcast summary statistics (DEV_SPEC §8.14). Computed by code; the BroadcastSummary
agent only writes prose around these numbers, and every number it uses must appear here."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..models.session import (
    AgentCall,
    Alert,
    Comment,
    CommentAnalysis,
    Event,
    Message,
    QuestionGroup,
    Segment,
    Session,
    Transcript,
)
from .catalog import Catalog
from .metrics import percentile

ANSWER_KINDS = ("ai_answer", "host_answer", "brand_answer")


def _sec(ms: int | None) -> int | None:
    return None if ms is None else round(ms / 1000)


def compute_summary_stats(
    *,
    session: Session,
    segments: Sequence[Segment],
    catalog: Catalog,
    comments: Sequence[Comment],
    analyses: Sequence[CommentAnalysis],
    groups: Sequence[QuestionGroup],
    messages: Sequence[Message],
    alerts: Sequence[Alert],
    transcripts: Sequence[Transcript],
    events: Sequence[Event],
    agent_calls: Sequence[AgentCall],
    counters: dict[str, int],
    triage_hits: int,
    triage_misses: int,
    now: int,
) -> dict[str, Any]:
    end = session.ended_at or now
    grace_ms = int((session.settings_snapshot or {}).get("STREAM_GRACE_SEC", 2)) * 1000
    by_transcript = {t.transcript_id: t for t in transcripts}
    published = [m for m in messages if m.state == "published"]
    analysis_by_comment = {a.comment_id: a for a in analyses}

    # ---- per product ---------------------------------------------------------------------------
    products = []
    for item in sorted(catalog.runsheet.items, key=lambda i: i.order):
        pid = item.product_id
        product = catalog.get_product(pid)
        segs = [s for s in segments if s.product_id == pid]
        duration_ms = sum((s.ended_at if s.ended_at is not None else end) - s.started_at for s in segs)
        covered = {p for s in segs for p in s.covered_point_ids}
        texts = {p.point_id: p.text for p in product.prompter_points}
        missing = [p for p in item.required_point_ids if p not in covered]

        def in_segment(t: int) -> bool:
            at = t - grace_ms
            return any(s.started_at <= at < (s.ended_at if s.ended_at is not None else end + 1) for s in segs)

        seg_comments = [c for c in comments if in_segment(c.received_at)]
        questions = [c for c in seg_comments if c.kind == "question"]
        product_groups = [g for g in groups if g.product_id == pid]
        answered = {k: 0 for k in ANSWER_KINDS}
        unanswered = []
        for g in product_groups:
            kinds = {m.kind for m in published if m.group_id == g.group_id}
            for k in ANSWER_KINDS:
                answered[k] += k in kinds
            if not kinds and g.status != "rejected":
                unanswered.append({"group_id": g.group_id, "canonical_question": g.canonical_question,
                                   "unique_askers": len(g.unique_author_ids), "status": g.status})
        products.append({
            "product_id": pid,
            "name": product.name,
            "duration_sec": _sec(duration_ms) if segs else 0,
            "planned_duration_sec": item.planned_duration_sec,
            "required_points_covered": len(item.required_point_ids) - len(missing),
            "required_points_total": len(item.required_point_ids),
            "missing_points": [{"point_id": p, "text": texts.get(p, "")} for p in missing],
            "comments": len(seg_comments),
            "questions": len(questions),
            "groups": len(product_groups),
            "answered_groups": answered,
            "unanswered_groups": unanswered,
        })

    general = [g for g in groups if g.product_id is None]
    general_unanswered = [
        {"group_id": g.group_id, "canonical_question": g.canonical_question, "unique_askers": len(g.unique_author_ids),
         "intent": g.intent, "status": g.status}
        for g in general if g.status != "rejected" and not any(m.group_id == g.group_id for m in published)
    ]

    # ---- alerts ---------------------------------------------------------------------------------
    # D-403: a cleared alert (replaced by a merged line's verdict, or a provisional one never confirmed) is not an
    # alert of the show: left out, never counted as uncorrected
    compliance = []
    for a in sorted((a for a in alerts if a.kind == "compliance" and a.shown_at is not None and a.status != "cleared"),
                    key=lambda a: a.shown_at):
        t = by_transcript.get(a.transcript_id)
        rule = catalog.pack.rules_by_id.get(a.rule_id or "")
        if a.status == "corrected" and a.resolved_at is not None:
            outcome: int | str = a.resolved_at - a.shown_at
        elif a.status == "dismissed":
            outcome = "dismissed"
        else:
            outcome = "uncorrected"
        compliance.append({
            "alert_id": a.alert_id, "rule_id": a.rule_id, "rule_title": rule.title if rule else None,
            "severity": a.severity, "span": a.span, "shown_at": a.shown_at,
            "speech_end_to_shown_ms": (a.shown_at - t.speech_end_at) if t else None,
            "shown_to_corrected_ms": outcome, "corrected_text": a.corrected_text, "unverified": a.unverified,
        })
    facts = []
    for a in sorted((a for a in alerts if a.kind == "fact" and a.status != "cleared"), key=lambda a: a.created_at):
        corrected = a.status == "corrected"
        t = by_transcript.get(a.transcript_id)
        shown = a.shown_at if a.shown_at is not None else a.created_at
        # D-096: the same columns as the compliance log (time, what was said, latency, outcome, correction)
        outcome = ((a.resolved_at - shown) if corrected and a.resolved_at is not None
                   else "dismissed" if a.status == "dismissed" else "uncorrected")
        facts.append({
            "alert_id": a.alert_id, "field": a.field, "stated_value": a.stated_value, "correct_value": a.correct_value,
            "corrected": corrected,
            "time_to_correction_ms": (a.resolved_at - a.shown_at) if corrected and a.resolved_at and a.shown_at else None,
            "span": a.span, "shown_at": shown,
            "speech_end_to_shown_ms": (shown - t.speech_end_at) if t else None,
            "shown_to_corrected_ms": outcome, "corrected_text": a.corrected_text,
        })

    # ---- promos ---------------------------------------------------------------------------------
    promos: dict[str, dict] = {}
    order: list[str] = []
    for ev in sorted(events, key=lambda e: e.seq):
        pid = ev.payload.get("promo_id")
        if ev.type == "promo.started" and pid:
            key = f"{pid}#{ev.seq}"
            promo = catalog.pack.promos_by_id.get(pid)
            promos[key] = {"promo_id": pid, "title": promo.title if promo else pid,
                           "started_at": ev.payload.get("started_at", ev.at), "ended_at": None}
            order.append(key)
        elif ev.type == "promo.ended" and pid:
            for key in reversed(order):
                if promos[key]["promo_id"] == pid and promos[key]["ended_at"] is None:
                    promos[key]["ended_at"] = ev.payload.get("ended_at", ev.at)
                    break
    promo_rows = []
    for key in order:
        row = promos[key]
        stop = row["ended_at"] if row["ended_at"] is not None else end
        promo_rows.append({**row, "duration_sec": _sec(stop - row["started_at"])})

    # ---- agents and caches ------------------------------------------------------------------------
    # D-202 (full review P1): latency of the successful calls, next to every attempt, its failures and the share
    # that finished within its deadline (a timeout is the deadline missed), so failures cannot look fast
    latencies: dict[str, list[int]] = {}
    attempts: dict[str, list[str]] = {}
    for c in agent_calls:
        attempts.setdefault(c.agent, []).append(c.status)
        if c.status == "ok":
            latencies.setdefault(c.agent, []).append(c.latency_ms)
    agents = {}
    for name, statuses in sorted(attempts.items()):
        v, n = latencies.get(name, []), len(statuses)
        failures = sum(st != "ok" for st in statuses)
        agents[name] = {"p50_ms": percentile(v, 0.5), "p95_ms": percentile(v, 0.95), "calls": len(v),
                        "attempts": n, "failures": failures, "timeouts": statuses.count("timeout"),
                        "failure_rate": round(failures / n, 4),
                        "deadline_attainment": round((n - statuses.count("timeout")) / n, 4)}

    questions_total = sum(1 for c in comments if c.kind == "question")
    return {
        "title": session.title,
        "session_id": session.session_id,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "duration_sec": _sec(end - session.started_at) if session.started_at else 0,
        "products": products,
        "totals": {
            "comments": len(comments),
            "questions": questions_total,
            "hidden_comments": sum(1 for c in comments if c.visibility == "hidden"),
            "groups": len(groups),
            "messages_by_kind": {k: sum(1 for m in published if m.kind == k) for k in
                                 ("ai_answer", "host_answer", "brand_answer", "notice", "correction_notice")},
            "analysed_comments": sum(1 for c in comments if c.comment_id in analysis_by_comment),
        },
        "general_unanswered_groups": general_unanswered,
        "compliance_alerts": compliance,
        "fact_alerts": facts,
        "promos": promo_rows,
        "agent_latency": agents,
        "cache": {
            "instant_answers": counters.get("instant_answers", 0),
            "composed_answers": counters.get("composed_answers", 0),
            "triage_hits": triage_hits,
            "triage_misses": triage_misses,
        },
    }
