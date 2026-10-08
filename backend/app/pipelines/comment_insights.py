"""What viewers asked, for the summary page: one analysis of a finished broadcast's comments.

Nothing is classified into topics while the show runs (a question is answered by itself or waits for a person). After
`End broadcast` the stored comment documents of the session are read once: with COMMENTS_FIRESTORE from Firestore
(the durable copy, after the write queue is flushed), otherwise from the app's store. The CommentInsights agent sorts
the questions into topics; every number is counted here from the stored records. When the agent fails or returns
nothing usable, the topics are the labels triage stored with each question.
"""
from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING, Any

from ..agents.comment_insights import CommentInsights, InsightsInput
from ..models.session import Comment, Message, QuestionGroup

if TYPE_CHECKING:
    from .runtime import SessionRuntime

log = logging.getLogger(__name__)

MAX_QUESTIONS = 300  # questions offered to the agent; the rest are counted under their stored label
MAX_TOPICS = 10
MAX_NOTES = 3
OTHER = "Other"
OUTCOMES = ("auto_answered", "answered_by_person", "unanswered")
_DIGIT = re.compile(r"\d")


async def stored_comment_docs(rt: "SessionRuntime") -> tuple[str, list[Comment], list[QuestionGroup], list[Message]]:
    """The session's comments, questions and posted messages, and where they were read from."""
    store = rt.ctx.store
    writer = getattr(store, "writer", None)
    if writer is not None:
        try:
            await writer.flush(10)
            docs = await writer.read(rt.sid, ("comments", "groups", "messages"))
            if docs["comments"]:
                return ("firestore", [Comment.model_validate(d) for d in docs["comments"]],
                        [QuestionGroup.model_validate(d) for d in docs["groups"]],
                        [Message.model_validate(d) for d in docs["messages"]])
        except Exception:  # noqa: BLE001 - the durable copy is unreachable or unreadable: the app's own copy
            log.exception("comment insights: reading Firestore failed for %s; using the app's store", rt.sid)
    return ("store", await store.query(rt.path("comments"), Comment), await rt.groups(),
            await store.query(rt.path("messages"), Message))


def outcome_of(g: QuestionGroup, kinds: set[str]) -> str:
    if "ai_answer" in kinds:
        return "auto_answered"
    return "answered_by_person" if kinds & {"host_answer", "brand_answer"} else "unanswered"


def label_of(intent: str) -> str:
    words = intent.replace("_", " ").strip()
    return (words[:1].upper() + words[1:]) if words else OTHER


BUYING_INTENTS = frozenset({"price", "set_price", "promo", "shipping", "payment"})  # labels fallback


def _percentile(values: list[int], q: float) -> float | None:
    """Nearest-rank percentile in seconds, one decimal; None without values."""
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))] / 1000, 1)


def timeline(comments: list[Comment], started_at: int | None, ended_at: int | None,
             on_air=lambda at: None) -> dict[str, Any] | None:
    """Comments and questions per slice of the broadcast, and the busiest slice for questions. Slices are 1 minute
    up to 20 minutes of show, 5 minutes beyond. `on_air(at)` names the product presented at a time."""
    if not comments:
        return None
    start = started_at if started_at is not None else min(c.received_at for c in comments)
    end = max(ended_at or 0, max(c.received_at for c in comments))
    size = 60_000 if end - start <= 20 * 60_000 else 300_000
    bins = [{"start_sec": i * size // 1000, "comments": 0, "questions": 0,
             "product": on_air(start + i * size + size // 2)} for i in range(max(1, math.ceil((end - start + 1) / size)))]
    for c in comments:
        b = bins[min(len(bins) - 1, max(0, (c.received_at - start) // size))]
        b["comments"] += 1
        b["questions"] += c.kind == "question"
    peak = max(bins, key=lambda b: (b["questions"], b["comments"]))
    return {"bin_sec": size // 1000, "bins": bins, "peak": peak if peak["questions"] else None}


def build_insights(comments: list[Comment], groups: list[QuestionGroup], messages: list[Message],
                   topics_by_key: dict[str, str] | None, notes: list[str], *, source: str,
                   product_name=lambda pid: None, buying_labels: set[str] | None = None,
                   started_at: int | None = None, ended_at: int | None = None,
                   on_air=lambda at: None) -> dict[str, Any]:
    """The summary block. `topics_by_key` maps a question's key (its group id) to the agent's topic label; None, or a
    question without one, uses the label stored with the question. `buying_labels` are the topics the agent marked
    as buying questions. All counts are made here."""
    by_id = {c.comment_id: c for c in comments}
    published: dict[str, set[str]] = {}
    waits: dict[str, list[int]] = {"auto": [], "person": []}  # a viewer's wait from comment to reply, ms
    for m in messages:
        if m.state == "published" and m.group_id:
            published.setdefault(m.group_id, set()).add(m.kind)
            if m.published_at is not None and m.kind in ("ai_answer", "host_answer", "brand_answer"):
                for cid in m.reply_to_comment_ids:
                    if (c := by_id.get(cid)) is not None and m.published_at >= c.received_at:
                        waits["auto" if m.kind == "ai_answer" else "person"].append(m.published_at - c.received_at)
    no_source: list[QuestionGroup] = []
    rows: dict[str, dict[str, Any]] = {}
    totals = dict.fromkeys(OUTCOMES, 0)
    reasons: dict[str, int] = {}
    for g in sorted(groups, key=lambda g: g.first_at):
        label = (topics_by_key or {}).get(g.group_id) or (label_of(g.intent) if topics_by_key is None else OTHER)
        n = len(g.member_comment_ids) or 1
        outcome = outcome_of(g, published.get(g.group_id, set()))
        buying = label in buying_labels if buying_labels is not None else g.intent in BUYING_INTENTS
        row = rows.setdefault(label, {"label": label, "buying": buying, "questions": 0, "askers": set(),
                                      **dict.fromkeys(OUTCOMES, 0), "examples": [], "products": set()})
        if g.route_reason == "no_verified_answer":
            no_source.append(g)
        row["questions"] += n
        row[outcome] += n
        row["askers"].update(g.unique_author_ids)
        totals[outcome] += n
        if g.needs_approval:
            reasons[g.approval_reason or "unclear"] = reasons.get(g.approval_reason or "unclear", 0) + n
        if (name := product_name(g.product_id)) is not None:
            row["products"].add(name)
        for cid in g.member_comment_ids:  # the viewers' own words; a hidden comment is never quoted
            c = by_id.get(cid)
            if c is not None and c.visibility == "visible" and len(row["examples"]) < 2 and c.text not in row["examples"]:
                row["examples"].append(c.text[:160])
    topics = sorted(({**r, "askers": len(r["askers"]), "products": sorted(r["products"])} for r in rows.values()),
                    key=lambda r: (r["label"] == OTHER, -r["questions"], -r["askers"], r["label"]))
    languages: dict[str, int] = {}
    for c in comments:
        if c.kind == "question":
            languages[c.language or "unknown"] = languages.get(c.language or "unknown", 0) + 1
    buying_rows = [r for r in topics if r["buying"]]
    return {
        "source": source,  # firestore: read from the stored documents; store: the app's own copy
        "comments": len(comments),
        "viewers": len({c.author_id for c in comments}),  # who wrote at least one comment
        "askers": len({a for g in groups for a in g.unique_author_ids}),
        "questions": sum(totals.values()),
        # a viewer's wait from their comment to the reply: answered by itself, or by the host or the team
        "reply_time_sec": {k: {"n": len(v), "p50": _percentile(v, 0.5), "p95": _percentile(v, 0.95)}
                           for k, v in waits.items()},
        # questions viewers ask while deciding to buy, and how many of them got no reply
        "buying": {"questions": sum(r["questions"] for r in buying_rows),
                   "topics": [r["label"] for r in buying_rows],
                   "unanswered": sum(r["unanswered"] for r in buying_rows)},
        # questions the product information did not answer: what to add to the product sheet
        "not_in_product_information": {
            "questions": sum(len(g.member_comment_ids) or 1 for g in no_source),
            "examples": [g.canonical_question for g in sorted(no_source, key=lambda g: -len(g.unique_author_ids))[:6]],
        },
        "reactions": sum(c.kind == "reaction" for c in comments),
        "hidden": sum(c.visibility == "hidden" for c in comments),
        "stream_reports": sum(c.signal == "stream_issue" for c in comments),
        "outcomes": totals,
        # when viewers wrote and asked, per slice of the broadcast
        "timeline": timeline(comments, started_at, ended_at, on_air),
        "waited_for_a_person_by_reason": dict(sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))),
        "question_languages": dict(sorted(languages.items(), key=lambda kv: (-kv[1], kv[0]))),
        "topics": topics,
        "notes": notes,
    }


def accept(output, offered: dict[str, str]) -> tuple[dict[str, str], list[str], set[str]]:
    """The agent's topics as {group id: label}: only offered keys, each once (the first topic that names it wins),
    at most MAX_TOPICS labels (later ones fall under "Other"). Notes: at most MAX_NOTES, none with a digit."""
    by_group: dict[str, str] = {}
    labels: list[str] = []
    buying: set[str] = set()
    for t in output.topics:
        label = " ".join(t.label.split())[:60] or OTHER
        if _DIGIT.search(label):
            label = OTHER
        if label not in labels:
            labels.append(label)
        if labels.index(label) >= MAX_TOPICS:
            label = OTHER
        if t.buying and label != OTHER:
            buying.add(label)
        for key in t.keys:
            gid = offered.get(key)
            if gid is not None and gid not in by_group:
                by_group[gid] = label
    notes = [" ".join(n.split())[:240] for n in output.notes if n.strip() and not _DIGIT.search(n)][:MAX_NOTES]
    return by_group, notes, buying


async def run_comment_insights(rt: "SessionRuntime", *, scenario: str = "S14") -> dict[str, Any] | None:
    """The block for the summary document, or None when it cannot be built. Never raises."""
    try:
        source, comments, groups, messages = await stored_comment_docs(rt)

        def product_name(pid):
            return rt.catalog.get_product(pid).name if pid and rt.catalog.is_product(pid) else None

        session, segments = await rt.load_session(), await rt.segments()

        def on_air(at: int):
            seg = next((s for s in segments if s.started_at is not None and s.started_at <= at
                        and (s.ended_at is None or at < s.ended_at)), None)
            return product_name(seg.product_id) if seg is not None else None

        when = {"started_at": session.started_at, "ended_at": session.ended_at, "on_air": on_air}
        if not groups:
            return {**build_insights(comments, groups, messages, None, [], source=source, **when),
                    "topic_source": "none"}
        by_id = {c.comment_id: c for c in comments}
        offered: dict[str, str] = {}
        rows = []
        for i, g in enumerate(sorted(groups, key=lambda g: g.first_at)[:MAX_QUESTIONS], start=1):
            offered[f"q{i}"] = g.group_id
            said = [by_id[cid].text for cid in g.member_comment_ids
                    if cid in by_id and by_id[cid].visibility == "visible"]
            rows.append({"key": f"q{i}", "question": g.canonical_question, "comments": said,
                         "product": product_name(g.product_id)})
        res = await CommentInsights(rt.ctx.llm, rt.ctx.prompts["comment_insights"]).run(
            InsightsInput(questions=rows, session_id=rt.sid, scenario=scenario),
            deadline_ms=rt.settings.SUMMARY_TIMEOUT_MS)
        by_group, notes, buying = (accept(res.output, offered) if res.status == "ok" and res.output is not None
                                   else ({}, [], set()))
        if not by_group:  # the agent failed or sorted nothing: the labels stored with the questions
            return {**build_insights(comments, groups, messages, None, [], source=source, product_name=product_name,
                                     **when), "topic_source": "labels"}
        return {**build_insights(comments, groups, messages, by_group, notes, source=source,
                                 product_name=product_name, buying_labels=buying, **when),
                "topic_source": "analysis"}
    except Exception:  # noqa: BLE001 - the summary page works without this block
        log.exception("comment insights failed for %s", rt.sid)
        return None
