"""Comment pipeline (DEV_SPEC §8.8, §8.9) and operator question actions (§8.13).

Steps 1-6 run concurrently per comment (triage limited to 8 at a time); grouping, routing,
answering and the host queue run under the session lock.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from ..agents.answer_composer import ComposeInput, gather_passages
from ..agents.comment_triage import TriageInput
from ..logic.cache import CachedAnswer, answer_cache_key, triage_cache_key
from ..logic.grouping import find_group, is_open, join_group, slots_compatible
from ..logic.prefilter import prefilter
from ..logic.product_mapping import attribute_product
from ..logic.promos import promo_state
from ..logic.routing import is_composable, route_for
from ..logic.segments import segment_at
from ..logic.verify import verify_answer
from ..models.agent_io import CommentTriageOutput, ConditionSlots
from ..models.session import Answer, Comment, CommentAnalysis, QuestionGroup
from .runtime import ActionError

if TYPE_CHECKING:
    from .runtime import SessionRuntime

log = logging.getLogger(__name__)


# ---- intake ----------------------------------------------------------------------------------------


async def submit_comment(
    rt: "SessionRuntime", *, author_id: str, author_name: str, text: str, source: str, scenario: str = "default"
) -> Comment:
    """§8.8 steps 1-2: rate limit, store, emit `comment.created`; prefilter; LLM steps run in the
    background so the comment is visible at once."""
    text = text.strip()
    if not text:
        raise ActionError(400, "empty_comment", "comment text is empty")
    now = rt.now()
    rt.check_rate(author_id, now)
    verdict = prefilter(text)
    comment = Comment(
        comment_id=rt.new_id("cm_"), author_id=author_id, author_name=author_name.strip() or "Viewer",
        text=text, received_at=now, source=source,
        visibility="hidden" if verdict.kind == "hide" else "visible",
        hide_category=verdict.hide_category,
        kind=verdict.kind or "pending",
    )
    await rt.save_comment(comment)
    await rt.emit("comment.created", comment)
    if verdict.kind is None:
        rt.spawn(process_comment(rt, comment.comment_id, scenario), name=f"comment:{comment.comment_id}")
        return comment
    analysis = CommentAnalysis(analysis_id=rt.new_id("an_"), comment_id=comment.comment_id, output=verdict.as_output(),
                               product_basis="unknown", source="prefilter", latency_ms=0)
    await rt.save_analysis(analysis)
    comment.analysis_id = analysis.analysis_id
    await rt.save_comment(comment)
    if verdict.kind == "hide":
        await rt.emit("comment.hidden", comment)
    await rt.emit("comment.analyzed", {"comment": comment.model_dump(mode="json"), "analysis": analysis.model_dump(mode="json")})
    return comment


def _fallback_output(text: str) -> CommentTriageOutput:
    return CommentTriageOutput(
        kind="question", hide_category=None, product_id=None, product_basis="unknown", intent="other",
        condition_slots=ConditionSlots(skin_type=None, life_stage=None, condition=None, combined_with=None, time_of_day=None),
        canonical_question=text.strip()[:120], group_candidate_id=None, reason="AI unavailable",
    )


async def process_comment(rt: "SessionRuntime", comment_id: str, scenario: str = "default", *, unhidden: bool = False) -> None:
    """§8.8 steps 3-8 for a comment that passed the prefilter."""
    comment = await rt.get_comment(comment_id)
    if comment is None:
        return
    t0 = time.perf_counter()
    segs = await rt.segments()
    seg = segment_at(segs, comment.received_at - rt.settings.STREAM_GRACE_SEC * 1000)
    context_pid = seg.product_id if seg else None

    key = triage_cache_key(comment.text, context_pid)
    cached = rt.triage_cache.get(key)
    for attempt in (1, 2):
        if attempt == 1 and cached is not None:
            output, source, seen = CommentTriageOutput.model_validate(cached), "cache", set()
        else:
            async with rt.triage_sem:
                open_groups = [g for g in await rt.groups() if is_open(g)]
                seen = {g.group_id for g in open_groups}
                res = await rt.triage.run(
                    TriageInput(text=comment.text, context_product_id=context_pid, open_groups=open_groups,
                                session_id=rt.sid, scenario=scenario),
                    deadline_ms=rt.settings.TRIAGE_TIMEOUT_MS,
                )
            if res.status == "ok" and res.output is not None:
                output, source = res.output, "llm"
                rt.triage_cache.put(key, output.model_dump(mode="json"))
            else:
                output, source = _fallback_output(comment.text), "fallback"
        latency_ms = round((time.perf_counter() - t0) * 1000)

        if unhidden and output.kind == "hide":
            output = output.model_copy(update={"kind": "reaction", "hide_category": None})  # operator override wins
        if output.kind != "question":
            await _finish_non_question(rt, comment_id, output, context_pid, source, latency_ms)
            return

        intent = rt.intent(output.intent)
        pid, basis = attribute_product(comment.text, output, context_pid, rt.catalog, intent)
        async with rt.lock:
            if attempt == 1 and source != "fallback" and await _missed_new_group(rt, output, pid, intent.intent, seen):
                continue  # D-042: triage ran on a stale list of open groups; ask once more
            await _assign_question_locked(rt, comment_id, output, pid, basis, context_pid, source, latency_ms, scenario)
            return


async def _missed_new_group(rt, output: CommentTriageOutput, pid, intent: str, seen: set[str]) -> bool:
    """True when grouping finds no match although a compatible open group exists that the triage
    call did not see (created while it ran, or the output came from the triage cache)."""
    groups = await rt.groups()
    slots = output.condition_slots.model_dump()
    if find_group(groups, product_id=pid, intent=intent, slots=slots, canonical_question=output.canonical_question,
                  candidate_id=output.group_candidate_id) is not None:
        return False
    return any(
        g.group_id not in seen and is_open(g) and g.product_id == pid and g.intent == intent
        and slots_compatible(g.condition_slots, slots)
        for g in groups
    )


async def _finish_non_question(rt, comment_id, output, context_pid, source, latency_ms) -> None:
    async with rt.lock:
        comment = await rt.get_comment(comment_id)
        if comment is None:
            return
        analysis = CommentAnalysis(analysis_id=rt.new_id("an_"), comment_id=comment_id,
                                   output=output.model_dump(mode="json"), product_id=None, product_basis="unknown",
                                   context_product_id=context_pid, source=source, latency_ms=latency_ms)
        await rt.save_analysis(analysis)
        comment.analysis_id = analysis.analysis_id
        comment.kind = output.kind
        if output.kind == "hide":
            comment.visibility, comment.hide_category = "hidden", output.hide_category
        await rt.save_comment(comment)
        if output.kind == "hide":
            await rt.emit("comment.hidden", comment)
        await rt.emit("comment.analyzed", {"comment": comment.model_dump(mode="json"), "analysis": analysis.model_dump(mode="json")})


async def _assign_question_locked(rt, comment_id, output, pid, basis, context_pid, source, latency_ms, scenario) -> None:
    comment = await rt.get_comment(comment_id)
    if comment is None:
        return
    now = rt.now()
    intent = rt.intent(output.intent)
    slots = output.condition_slots.model_dump()
    g = find_group(await rt.groups(), product_id=pid, intent=intent.intent, slots=slots,
                   canonical_question=output.canonical_question, candidate_id=output.group_candidate_id)
    created = g is None
    if g is None:
        route, reason = ("OPERATOR", "ai_unavailable") if source == "fallback" else route_for(intent, pid)
        g = QuestionGroup(
            group_id=rt.new_id("grp_"), product_id=pid, intent=intent.intent, condition_slots=slots,
            canonical_question=output.canonical_question, member_comment_ids=[comment_id],
            unique_author_ids=[comment.author_id], first_at=now, last_at=now, route=route, route_reason=reason,
            status="new",
        )
    else:
        join_group(g, comment_id, comment.author_id, now)
    analysis = CommentAnalysis(
        analysis_id=rt.new_id("an_"), comment_id=comment_id, output=output.model_dump(mode="json"), product_id=pid,
        product_basis=basis, context_product_id=context_pid, route=g.route, route_reason=g.route_reason,
        source=source, latency_ms=latency_ms,
    )
    await rt.save_analysis(analysis)
    comment.kind, comment.group_id, comment.analysis_id = "question", g.group_id, analysis.analysis_id
    await rt.save_comment(comment)
    await rt.save_group(g)
    await rt.emit("comment.analyzed", {"comment": comment.model_dump(mode="json"), "analysis": analysis.model_dump(mode="json")})
    await answer_group_locked(rt, g, [comment_id], scenario)
    g.version += 1
    await rt.save_group(g)
    await rt.emit("group.updated", g)
    await rt.recompute_host_queue_locked()


# ---- answering (§8.9.3) ----------------------------------------------------------------------------


async def answer_key(rt: "SessionRuntime", g: QuestionGroup) -> str:
    promo = await rt.active_price_promo()
    return answer_cache_key(g.product_id, g.intent, g.condition_slots, g.canonical_question,
                            promo_state(promo), rt.ctx.retriever.doc_version())


async def answer_group_locked(rt: "SessionRuntime", g: QuestionGroup, new_comment_ids: list[str], scenario: str) -> None:
    """Decide what happens to the group after members joined. Never calls an LLM itself."""
    if g.status in ("closed", "rejected"):
        return
    if g.status in ("auto_answered", "answered") and g.published_message_id:
        await reply_again_locked(rt, g, new_comment_ids)
        return
    if g.status == "composing" or g.answer_id is not None:
        return  # members wait for the composer, the host or the operator
    intent = rt.intent(g.intent)
    if not is_composable(intent, g.product_id):
        g.route = "OPERATOR"
        g.status = "needs_review"
        return
    key = await answer_key(rt, g)
    cached = rt.answer_cache.get(key)
    if cached is not None:
        answer = await rt.get_answer(cached.answer_id)
        if answer is not None and answer.verified:
            await apply_answer_locked(rt, g, answer, instant=True)
            return
    g.status = "composing"
    rt.spawn(compose_for_group(rt, g.group_id, key, scenario), name=f"compose:{g.group_id}")


async def apply_answer_locked(rt: "SessionRuntime", g: QuestionGroup, answer: Answer, *, instant: bool) -> None:
    g.answer_id = answer.answer_id
    if not answer.verified:
        g.route, g.route_reason, g.status = "OPERATOR", "no_verified_answer", "needs_review"
        return
    if answer.needs_human and g.route == "AUTO":
        g.route, g.route_reason, g.status = "OPERATOR", "needs_human", "needs_review"
        return
    if g.route == "AUTO" and rt.settings.AUTO_ANSWER_ENABLED:
        msg = await rt.publish_message_locked(
            kind="ai_answer", text=answer.text, group=g, comment_ids=list(g.member_comment_ids),
            citations=answer.citations, idempotency_key=f"ai_answer:{g.group_id}",
        )
        g.status, g.published_message_id = "auto_answered", msg.message_id
        rt.counters["instant_answers" if instant else "composed_answers"] += len(g.member_comment_ids)
    elif g.route == "HOST":
        g.status = "ready"
    else:
        g.status = "needs_review"


async def reply_again_locked(rt: "SessionRuntime", g: QuestionGroup, new_comment_ids: list[str]) -> None:
    """New askers of an answered group: join the last reply within REPLY_COALESCE_SEC, else post the
    same text again. No LLM call (an instant answer, §8.16)."""
    msg = await rt.get_message(g.published_message_id)
    if msg is None or not new_comment_ids:
        return
    now = rt.now()
    fresh = [c for c in new_comment_ids if c not in msg.reply_to_comment_ids]
    if not fresh:
        return
    if msg.state == "published" and msg.published_at is not None and now - msg.published_at < rt.settings.REPLY_COALESCE_SEC * 1000:
        msg.reply_to_comment_ids.extend(fresh)
        for cid in fresh:
            c = await rt.get_comment(cid)
            if c is not None and c.author_name not in msg.reply_to_author_names:
                msg.reply_to_author_names.append(c.author_name)
        await rt.save_message(msg)
        await rt.emit("message.updated", msg)
    elif msg.state == "published":
        again = await rt.publish_message_locked(
            kind=msg.kind, text=msg.text, group=g, comment_ids=fresh, citations=msg.citations,
            idempotency_key=f"{msg.kind}:{g.group_id}:{fresh[0]}",
        )
        g.published_message_id = again.message_id
    else:
        return  # a pending host answer: the new member waits for it
    if msg.kind == "ai_answer":
        rt.counters["instant_answers"] += len(fresh)


async def compose_for_group(rt: "SessionRuntime", group_id: str, key: str, scenario: str) -> None:
    """Single-flight composer per cache key; applies the result to the group under the lock."""
    fut = rt.composing.get(key)
    if fut is None:
        fut = rt.composing[key] = asyncio.get_running_loop().create_future()
        answer = None
        try:
            answer = await _run_composer(rt, group_id, key, scenario)
        except Exception:  # noqa: BLE001 - fail safe: no answer, the group goes to the operator
            log.exception("composer failed for %s", group_id)
        finally:
            fut.set_result(answer)
            rt.composing.pop(key, None)
    else:
        answer = await fut
    async with rt.lock:
        g = await rt.get_group(group_id)
        if g is None or g.status != "composing":
            return  # closed by a promo change, rejected, or answered meanwhile
        if answer is None:
            g.route, g.route_reason, g.status = "OPERATOR", "no_verified_answer", "needs_review"
        else:
            await apply_answer_locked(rt, g, answer, instant=False)
        g.version += 1
        await rt.save_group(g)
        await rt.emit("group.updated", g)
        await rt.recompute_host_queue_locked()


async def _run_composer(rt: "SessionRuntime", group_id: str, key: str, scenario: str) -> Answer | None:
    g = await rt.get_group(group_id)
    if g is None:
        return None
    intent = rt.intent(g.intent)
    promo = await rt.active_price_promo()
    product_id = g.product_id if intent.product_scope == "single" else None
    passages = await gather_passages(
        rt.ctx.retriever, rt.catalog, rt.prefetched, product_id=product_id, intent=g.intent,
        canonical_question=g.canonical_question, promo=promo, top_k=rt.settings.COMPOSER_TOP_K,
    )
    res = await rt.composer.run(
        ComposeInput(product_id=product_id, intent=g.intent, slots=g.condition_slots,
                     canonical_question=g.canonical_question, promo=promo, passages=passages,
                     session_id=rt.sid, scenario=scenario, sensitive=intent.sensitive),
        deadline_ms=rt.settings.COMPOSER_TIMEOUT_MS,
    )
    if res.status != "ok" or res.output is None:
        return None
    out = res.output
    not_approved = rt.catalog.not_approved_claims(product_id) if product_id else [
        c for p in rt.catalog.products for c in p.not_approved_claims]
    ok, errors = verify_answer(out, passages, product_id, multi=product_id is None,
                               reflex=rt.ctx.reflex, not_approved_claims=not_approved)
    by_id = {p.passage_id: p for p in passages}
    citations = [{"passage_id": c.passage_id, "quote": c.quote,
                  "section": by_id[c.passage_id].section if c.passage_id in by_id else None,
                  "doc": by_id[c.passage_id].doc if c.passage_id in by_id else None} for c in out.citations]
    answer = Answer(answer_id=rt.new_id("ans_"), group_id=group_id, text=out.answer.strip(), citations=citations,
                    origin="ai", verified=ok, verify_errors=errors, cache_key=key, needs_human=out.needs_human,
                    created_at=rt.now())
    await rt.save_answer(answer)
    if ok:
        rt.answer_cache.put(key, CachedAnswer(answer_id=answer.answer_id, intent=g.intent))
    return answer


# ---- operator question actions (§8.13) -------------------------------------------------------------


async def _group_or_404(rt: "SessionRuntime", gid: str) -> QuestionGroup:
    g = await rt.get_group(gid)
    if g is None:
        raise ActionError(404, "group_not_found", f"group {gid} not found")
    return g


async def operator_action(rt: "SessionRuntime", action: str, **details) -> None:
    await rt.emit("operator.action", {"actor": "operator", "action": action, **details, "at": rt.now()})


async def push_to_host(rt: "SessionRuntime", gid: str) -> None:
    from ..logic.host_queue import HostQueueFull

    async with rt.lock:
        g = await _group_or_404(rt, gid)
        if g.status in ("answered", "rejected", "closed"):
            raise ActionError(409, "invalid_state", f"group is {g.status}")
        g.pinned_by_operator_at, g.recalled_at = rt.now(), None
        g.version += 1
        await rt.save_group(g)
        try:
            await rt.recompute_host_queue_locked(push=gid)
        except HostQueueFull as e:
            g.pinned_by_operator_at = None
            await rt.save_group(g)
            raise ActionError(409, "host_queue_full", str(e)) from None
        await operator_action(rt, "push", group_id=gid)


async def recall_from_host(rt: "SessionRuntime", gid: str) -> None:
    async with rt.lock:
        g = await _group_or_404(rt, gid)
        g.recalled_at, g.pinned_by_operator_at = rt.now(), None
        g.version += 1
        await rt.save_group(g)
        await rt.recompute_host_queue_locked(recall=gid)
        await operator_action(rt, "recall", group_id=gid)


async def assign_product(rt: "SessionRuntime", gid: str, product_id: str) -> None:
    if not rt.catalog.is_product(product_id):
        raise ActionError(404, "unknown_product", f"product {product_id} not found")
    async with rt.lock:
        g = await _group_or_404(rt, gid)
        if g.status in ("answered", "rejected", "closed", "auto_answered"):
            raise ActionError(409, "invalid_state", f"group is {g.status}")
        g.product_id = product_id
        g.route, g.route_reason = route_for(rt.intent(g.intent), product_id)
        if g.status != "composing":
            g.status, g.answer_id = "new", None
        for cid in g.member_comment_ids:
            c = await rt.get_comment(cid)
            if c and c.analysis_id:
                a = await rt.ctx.store.get(rt.path("analyses"), c.analysis_id, CommentAnalysis)
                if a:
                    a.product_id, a.product_basis, a.route, a.route_reason = product_id, "operator", g.route, g.route_reason
                    await rt.save_analysis(a)
        await answer_group_locked(rt, g, [], "default")
        g.version += 1
        await rt.save_group(g)
        await rt.emit("group.updated", g)
        await rt.recompute_host_queue_locked()
        await operator_action(rt, "assign_product", group_id=gid, product_id=product_id)


async def _publish_answer_locked(rt, g: QuestionGroup, *, kind: str, text: str, citations: list[dict], key: str):
    msg = await rt.publish_message_locked(kind=kind, text=text, group=g, comment_ids=list(g.member_comment_ids),
                                          citations=citations, idempotency_key=key)
    g.status, g.published_message_id = "answered", msg.message_id
    g.version += 1
    await rt.save_group(g)
    await rt.emit("group.updated", g)
    await rt.recompute_host_queue_locked()
    return msg


async def approve(rt: "SessionRuntime", gid: str) -> None:
    async with rt.lock:
        g = await _group_or_404(rt, gid)
        answer = await rt.get_answer(g.answer_id)
        if answer is None or not answer.verified:
            raise ActionError(409, "unverified_draft", "Only a verified draft can be approved.")
        if g.status in ("answered", "rejected", "closed"):
            raise ActionError(409, "invalid_state", f"group is {g.status}")
        await _publish_answer_locked(rt, g, kind="brand_answer", text=answer.text, citations=answer.citations,
                                     key=f"brand_answer:{gid}")
        await operator_action(rt, "approve", group_id=gid)


async def write_answer(rt: "SessionRuntime", gid: str, text: str, origin: str, confirm: bool) -> None:
    text = text.strip()
    if not text:
        raise ActionError(400, "empty_answer", "reply text is empty")
    if origin not in ("operator_edit", "operator_written"):
        raise ActionError(400, "invalid_origin", "origin must be operator_edit or operator_written")
    hit = rt.ctx.reflex.first_hit(text)
    if hit is not None and not confirm:
        rule = rt.ctx.pack.rules_by_id[hit.rule_id]
        raise ActionError(409, "restricted_phrase",
                          f"This reply contains a restricted phrase: '{hit.phrase}' ({rule.title}).")
    async with rt.lock:
        g = await _group_or_404(rt, gid)
        if g.status in ("answered", "rejected", "closed"):
            raise ActionError(409, "invalid_state", f"group is {g.status}")
        answer = Answer(answer_id=rt.new_id("ans_"), group_id=gid, text=text, citations=[], origin=origin,
                        verified=False, verify_errors=["operator text"], needs_human=False, created_at=rt.now())
        await rt.save_answer(answer)
        g.answer_id = answer.answer_id
        await _publish_answer_locked(rt, g, kind="brand_answer", text=text, citations=[], key=f"brand_answer:{gid}")
        await operator_action(rt, "answer", group_id=gid, origin=origin, confirmed_restricted=hit is not None)


async def post_suggested(rt: "SessionRuntime", gid: str) -> None:
    async with rt.lock:
        g = await _group_or_404(rt, gid)
        answer = await rt.get_answer(g.answer_id)
        if answer is None or not answer.verified:
            raise ActionError(409, "unverified_draft", "There is no verified suggested answer.")
        if g.status in ("answered", "rejected", "closed"):
            raise ActionError(409, "invalid_state", f"group is {g.status}")
        await _publish_answer_locked(rt, g, kind="host_answer", text=answer.text, citations=answer.citations,
                                     key=f"host_answer:{gid}")
        await operator_action(rt, "post_suggested", group_id=gid)


async def reject(rt: "SessionRuntime", gid: str) -> None:
    async with rt.lock:
        g = await _group_or_404(rt, gid)
        g.status = "rejected"
        g.version += 1
        await rt.save_group(g)
        await rt.emit("group.updated", g)
        await rt.recompute_host_queue_locked()
        await operator_action(rt, "reject", group_id=gid)


async def unhide_comment(rt: "SessionRuntime", cid: str) -> None:
    async with rt.lock:
        c = await rt.get_comment(cid)
        if c is None:
            raise ActionError(404, "comment_not_found", f"comment {cid} not found")
        if c.visibility != "hidden":
            raise ActionError(409, "invalid_state", "comment is not hidden")
        c.visibility, c.hide_category, c.kind = "visible", None, "pending"
        await rt.save_comment(c)
        await rt.emit("comment.unhidden", c)
        await operator_action(rt, "unhide", comment_id=cid)
    rt.spawn(process_comment(rt, cid, unhidden=True), name=f"unhide:{cid}")
