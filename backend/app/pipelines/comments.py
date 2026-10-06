"""Comment pipeline (DEV_SPEC §8.8, §8.9) and operator question actions (§8.13).

Steps 1-6 run concurrently per comment (triage through `TriageQueue`, D-102); grouping, routing,
answering and the host queue run under the session lock.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
import logging
import re
import time
from typing import TYPE_CHECKING

from ..agents import arms, file_tools, inputs
from ..agents.answer_composer import ComposeInput, gather_passages
from ..agents.comment_triage import TriageInput
from ..logic.cache import CachedAnswer, answer_cache_key, triage_cache_key
from ..logic.grouping import find_group, is_open, join_group, slots_compatible
from ..logic.prefilter import PrefilterVerdict, mask_links, prefilter
from ..logic.product_mapping import attribute_product, set_question
from ..logic.promos import promo_passage, promo_state
from ..logic.routing import is_composable, route_for
from ..logic.pd import ShoutOut
from ..logic.segments import segment_at
from ..logic.shoutout import shout_kind
from ..agents.draft_verifier import DraftCheckInput, cited_passages
from ..logic.verify import number_set, verify_answer
from ..providers.armor import screen as armor_screen
from ..models.agent_io import CommentTriageOutput, ConditionSlots
from ..models.session import Answer, Comment, CommentAnalysis, QuestionGroup
from .runtime import ActionError

if TYPE_CHECKING:
    from .runtime import SessionRuntime

log = logging.getLogger(__name__)
SHORT_COMMENT_WORDS = 5  # D-157: a comment this short is triaged with the host's last line
HOST_LINE_MAX_AGE_MS = 30_000


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
    # D-191 arms D and E: no prefilter beyond Model Armor; triage decides every comment
    text = mask_links(text)  # D-234: the link itself never shows in chat or reaches a model; the question does
    verdict = (PrefilterVerdict(None) if arms.agents_decide(rt.settings.DESIGN_ARM)
               else prefilter(text, rt.catalog.lexicon, rt.settings.PREFILTER))
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
    if verdict.kind == "reaction":
        note_shoutout(rt, comment)
    if verdict.kind == "hide":
        await rt.emit("comment.hidden", comment)
    await rt.emit("comment.analyzed", {"comment": comment.model_dump(mode="json"), "analysis": analysis.model_dump(mode="json")})
    return comment


async def _finish_armored(rt, comment_id: str, verdict: str, detail: str, latency_ms: int) -> None:
    """Blocked: hidden from chat, no LLM call; in the operator's hidden list (team) or only counted (solo);
    never a host card. Unscreened: stays in chat as a plain comment, never triaged, answered or carded."""
    async with rt.lock:
        comment = await rt.get_comment(comment_id)
        if comment is None:
            return
        analysis = CommentAnalysis(analysis_id=rt.new_id("an_"), comment_id=comment_id,
                                   output={"kind": "armor", "verdict": verdict, "detail": detail},
                                   product_basis="unknown", source="armor", latency_ms=latency_ms)
        await rt.save_analysis(analysis)
        comment.armor, comment.analysis_id = verdict, analysis.analysis_id
        if verdict == "blocked":
            comment.kind, comment.visibility, comment.hide_category = "hide", "hidden", "armor_blocked"
        else:
            comment.kind = "reaction"
        await rt.save_comment(comment)
        rt.counters[f"armor_{verdict}"] += 1
        if verdict == "blocked":
            await rt.emit("comment.hidden", comment)
        await rt.emit("comment.analyzed", {"comment": comment.model_dump(mode="json"),
                                           "analysis": analysis.model_dump(mode="json")})


def note_shoutout(rt: "SessionRuntime", comment: Comment, label: str | None = None) -> None:
    """D-113: a purchase, first-time or compliment reaction the AI PD may read out with the name. D-187 arm B: the
    kind is triage's label, never a regex (a reaction the prefilter settles has none)."""
    kind = label if arms.meaning_to_llm(rt.settings.DESIGN_ARM) else shout_kind(comment.text)
    if kind is not None:
        rt.shoutouts.append(ShoutOut(comment.comment_id, comment.author_name, kind, comment.received_at))


def _fallback_output(text: str) -> CommentTriageOutput:
    return CommentTriageOutput(
        kind="question", hide_category=None, product_id=None, product_basis="unknown", intent="other",
        condition_slots=ConditionSlots(person_type=None, life_stage=None, condition=None, combined_with=None, time_of_day=None),
        canonical_question=text.strip()[:120], group_candidate_id=None, reason="AI unavailable",
    )


async def process_comment(rt: "SessionRuntime", comment_id: str, scenario: str = "default", *, unhidden: bool = False) -> None:
    """§8.8 steps 3-8 for a comment that passed the prefilter."""
    if not rt.assistant:
        return  # D-139: the comment stays in chat; nobody triages, groups or answers it
    comment = await rt.get_comment(comment_id)
    if comment is None:
        return
    t0 = time.perf_counter()
    # D-125: Model Armor before triage, on every comment the prefilter let through (no cache bypass)
    verdict, detail = await armor_screen(rt.ctx.armor, comment.text, rt.settings.MODEL_ARMOR_TIMEOUT_MS)
    if verdict == "unscreened":  # D-206: once more, then the operator
        verdict, detail = await armor_screen(rt.ctx.armor, comment.text, rt.settings.MODEL_ARMOR_TIMEOUT_MS)
    if verdict == "blocked":
        await _finish_armored(rt, comment_id, verdict, detail, round((time.perf_counter() - t0) * 1000))
        return
    unscreened = verdict != "pass"
    if unscreened:
        # D-206 (full review P2): an unscreened comment never reaches a model; it goes to the operator as an
        # "other" question (OPERATOR route, nothing drafted) instead of being dropped as a reaction
        async with rt.lock:
            comment.armor = "unscreened"
            await rt.save_comment(comment)
            rt.counters["armor_unscreened"] += 1
    segs = await rt.segments()
    seg = segment_at(segs, comment.received_at - rt.settings.STREAM_GRACE_SEC * 1000)
    # D-135: before the first segment, the host screen already shows the first run-sheet product as NOW.
    # D-152 (comment-flow CF10): in the first seconds of a session the grace lookup finds no segment although
    # one is on air; take the product on air then, not the first of the run sheet
    if seg is None:
        seg = await rt.current_segment()
    context_pid = seg.product_id if seg else (rt.catalog.order[0] if rt.catalog.order else None)
    # D-157 (00007 show replays): "Over 60 how", "Pouch for set?" and "Tingling?" answer what the host just said;
    # a short comment is triaged with the host's last line
    host_line = (rt.utterances.recent_host_line(comment.received_at, HOST_LINE_MAX_AGE_MS, seg.segment_id if seg else None)
                 if len(comment.text.split()) <= SHORT_COMMENT_WORDS else None)

    key = triage_cache_key(comment.text, context_pid, host_line)
    cached = rt.triage_cache.get(key)
    for attempt in (1, 2):
        if unscreened:
            output, source, seen = _fallback_output(comment.text), "unscreened", set()
        elif attempt == 1 and cached is not None:
            output, source, seen = CommentTriageOutput.model_validate(cached), "cache", set()
        else:
            inp = TriageInput(text=comment.text, context_product_id=context_pid, session_id=rt.sid, scenario=scenario,
                              host_line=host_line)
            res, seen = await rt.triage_queue.classify(inp)
            if res.status != "ok" or res.output is None:
                # D-176 (comment flow CF11): one triage timeout lost an answerable question; once more
                res, seen = await rt.triage_queue.classify(replace(inp, open_groups=[]))
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

        if set_question(output.intent, comment.text, rt.catalog):
            output = output.model_copy(update={"intent": "set_price"})
        intent = rt.intent(output.intent)
        pid, basis = attribute_product(comment.text, output, context_pid, rt.catalog, intent)
        async with rt.lock:
            if attempt == 1 and source not in ("fallback", "unscreened") and await _missed_new_group(
                    rt, output, pid, intent.intent, seen):
                continue  # D-042: triage ran on a stale list of open groups; ask once more
            await rt.documents_changed_locked()  # D-152: before an asker joins a group with a stale answer
            await _assign_question_locked(rt, comment_id, output, pid, basis, context_pid, source, latency_ms, scenario)
            return


class TriageQueue:
    """Adaptive micro-batch (PLANNING 5.1.2). A comment that finds a free slot is triaged alone at
    once, exactly as before. Comments that arrive while all `TRIAGE_CONCURRENCY` calls are running
    wait, and the next free slot takes up to `TRIAGE_MAX_BATCH` of them in one call. There is no
    timer: under load, the wait for a free slot is the collection window."""

    def __init__(self, rt: "SessionRuntime") -> None:
        self.rt = rt
        self.busy = 0
        self.waiting: list[tuple[TriageInput, asyncio.Future]] = []

    async def classify(self, inp: TriageInput):
        """Returns the triage result and the ids of the open groups the call saw."""
        fut = asyncio.get_running_loop().create_future()
        self.waiting.append((inp, fut))
        self._pump()
        return await fut

    def _pump(self) -> None:
        st = self.rt.settings
        while self.waiting and self.busy < st.TRIAGE_CONCURRENCY:
            batch, self.waiting = self.waiting[:st.TRIAGE_MAX_BATCH], self.waiting[st.TRIAGE_MAX_BATCH:]
            self.busy += 1
            self.rt.spawn(self._run(batch), name=f"triage:{self.rt.sid}:{len(batch)}")

    async def _run(self, batch: list[tuple[TriageInput, asyncio.Future]]) -> None:
        rt = self.rt
        try:
            open_groups = [g for g in await rt.groups() if is_open(g)]
            seen = {g.group_id for g in open_groups}
            inps = [inp for inp, _ in batch]
            for inp in inps:
                inp.open_groups = open_groups
            if len(inps) == 1:
                results = [await rt.triage.run(inps[0], deadline_ms=rt.settings.TRIAGE_TIMEOUT_MS)]
            else:
                results = await rt.triage.run_batch(inps, deadline_ms=rt.settings.TRIAGE_BATCH_TIMEOUT_MS)
            for (_, fut), res in zip(batch, results):
                if not fut.done():
                    fut.set_result((res, seen))
        except Exception as e:  # noqa: BLE001 - every waiting comment gets the error, none hangs
            for _, fut in batch:
                if not fut.done():
                    fut.set_exception(e)
        finally:
            for _, fut in batch:
                if not fut.done():
                    fut.cancel()
            self.busy -= 1
            self._pump()


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
        if output.kind == "reaction":
            note_shoutout(rt, comment, getattr(output, "shoutout", None))
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
        route, reason = ("OPERATOR", "ai_unavailable") if source == "fallback" else await _route(rt, intent, pid)
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


def _ingredients_named(rt: "SessionRuntime", product_id: str, question: str) -> list[str]:
    """D-176: the product's key ingredients (its sheet, "Name: amount") the question names, matched by the first five
    letters of each name's longest word ("hyaluronic" for "Sodium Hyaluronate")."""
    passages_of = getattr(rt.ctx.retriever, "passages_of", None)
    passages = passages_of(product_id) if callable(passages_of) else [p for p in rt.ctx.pack.passages
                                                                       if p.product_id == product_id]
    words = re.findall(r"[a-z]+", question.lower())
    out = []
    for p in passages:
        if p.section != "Key ingredients" or ":" not in p.text:
            continue
        name = re.sub(r"\(.*?\)", "", p.text.split(":", 1)[0]).strip().lower()
        stem = max(re.findall(r"[a-z]+", name), key=len, default="")[:5]
        if len(stem) == 5 and any(w.startswith(stem) for w in words):
            out.append(name)
    return sorted(set(out))


ONE_ANSWER_INTENTS = frozenset({"price", "set_price", "volume"})


async def answer_key(rt: "SessionRuntime", g: QuestionGroup) -> str:
    promo = await rt.active_price_promo()
    # D-152: a one-value intent (price, set price, volume) has one answer per product, slots and state, however the
    # question was worded, so two groups of it share one draft. D-214: only those; "shelf life once opened" and
    # "unopened shelf life" are two answers
    question = "" if g.intent in ONE_ANSWER_INTENTS else g.canonical_question
    if g.intent == "ingredient_amount" and g.product_id:
        # D-176 (comment flow CF12): "percentage of panthenol in it?" and "… in the ampoule?" drafted twice; the
        # same ingredient's amount is one answer
        named = _ingredients_named(rt, g.product_id, g.canonical_question)
        question = "ingredient:" + ",".join(named) if named else question
    state = promo_state(promo)
    if g.intent == "promo":  # D-168: an offer's answer holds while that offer runs
        state += "".join(f"+{o.promo_id}" for o in sorted(await rt.active_offers(), key=lambda o: o.promo_id))
    return answer_cache_key(g.product_id, g.intent, g.condition_slots, question, state, rt.ctx.retriever.doc_version())


async def answer_group_locked(rt: "SessionRuntime", g: QuestionGroup, new_comment_ids: list[str], scenario: str) -> None:
    """Decide what happens to the group after members joined. Never calls an LLM itself."""
    if g.status in ("closed", "rejected"):
        return
    if g.status in ("auto_answered", "answered") and g.published_message_id:
        await reply_again_locked(rt, g, new_comment_ids)
        return
    if g.answer_id is not None and g.route_reason == "no_verified_answer" and new_comment_ids:
        old = await rt.get_answer(g.answer_id)
        if old is not None and old.verify_errors and all(e in UNCHECKED for e in old.verify_errors):
            g.answer_id = None  # D-152: the draft was never judged (timeout, error): a new asker drafts again
    if g.status == "composing" or g.answer_id is not None:
        return  # members wait for the composer, the host or the operator
    intent = rt.intent(g.intent)
    if not is_composable(intent, g.product_id):
        # D-113: an unresolved product stays with the host ("Which product?"). D-178: shipping, returns,
        # payment ... keep their OPERATOR route in a solo show too (the host sees only the unanswered count)
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


async def _route(rt: "SessionRuntime", intent, product_id: str | None) -> tuple[str, str]:
    """The intent's route (§8.9.2); D-178: a host question about a product already shown and no longer on air goes
    to the operator (team) or the host's unanswered count (solo)."""
    route, reason = route_for(intent, product_id)
    if route == "HOST" and product_id is not None:
        seg = await rt.current_segment()
        aired = {x.product_id for x in await rt.segments() if x.ended_at is not None}
        if product_id in aired and (seg is None or seg.product_id != product_id):
            return "OPERATOR", "previous_product"
    return route, reason


async def no_draft_locked(rt: "SessionRuntime", g: QuestionGroup) -> None:
    """D-178 (user decision, replaces D-135's host deferral card): no verified answer, so the product info does not
    answer it. It goes to the operator (team) or only to the host's unanswered count (solo), sensitive ones too."""
    g.route, g.route_reason, g.status = "OPERATOR", "no_verified_answer", "needs_review"


async def move_previous_product_questions_locked(rt: "SessionRuntime", product_id: str) -> None:
    """D-178 (user decision): at a product switch the host's questions about the previous product go to the
    operator list (team) or the host's unanswered count (solo). Answered, AI-answered and "Which product?" groups stay."""
    for g in await rt.groups():
        if (g.product_id == product_id and g.route == "HOST" and g.status in ("new", "composing", "ready", "needs_review")
                and g.host_verbal_answer_transcript_id is None):
            g.route, g.route_reason = "OPERATOR", "previous_product"  # a ready draft stays ready for the operator
            g.version += 1
            await rt.save_group(g)
            await rt.emit("group.updated", g)


async def apply_answer_locked(rt: "SessionRuntime", g: QuestionGroup, answer: Answer, *, instant: bool) -> None:
    g.answer_id = answer.answer_id
    if answer.verified and g.route_reason in ("no_verified_answer", "needs_human"):
        # D-135: an earlier draft failed (or timed out); a verified one now takes the intent's own route
        g.route, g.route_reason = await _route(rt, rt.intent(g.intent), g.product_id)
    if not answer.verified:
        await no_draft_locked(rt, g)
        return
    if answer.needs_human and g.route == "AUTO":
        # D-135: never posted by itself; the host reads the verified draft (solo) or the operator checks it
        if (await rt.load_session()).show_mode == "solo":
            g.route, g.route_reason, g.status = "HOST", "needs_human", "ready"
        else:
            g.route, g.route_reason, g.status = "OPERATOR", "needs_human", "needs_review"
        return
    if g.route == "AUTO" and any(str(c.get("doc") or "").startswith("unreviewed-translation") for c in answer.citations):
        # D-233: an answer resting on a machine translation nobody reviewed is never posted by itself
        if (await rt.load_session()).show_mode == "solo":
            g.route, g.route_reason, g.status = "HOST", "unreviewed_translation", "ready"
        else:
            g.route, g.route_reason, g.status = "OPERATOR", "unreviewed_translation", "needs_review"
        return
    if g.route == "AUTO" and not rt.live:
        g.route, g.route_reason = "HOST", "preview"  # D-150: a preview market posts nothing by itself
    if g.route == "AUTO" and rt.settings.AUTO_ANSWER_ENABLED:
        msg = await rt.publish_message_locked(
            kind="ai_answer", text=answer.text, group=g, comment_ids=list(g.member_comment_ids),
            citations=answer.citations, idempotency_key=f"ai_answer:{g.group_id}",
        )
        g.status, g.published_message_id = "auto_answered", msg.message_id
        kind = "instant" if instant else "composed"
        rt.counters[f"{kind}_answers"] += len(g.member_comment_ids)
        await _record_reply_latency(rt, kind, g.member_comment_ids)
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
        await _record_reply_latency(rt, "instant", fresh)


async def _record_reply_latency(rt: "SessionRuntime", kind: str, comment_ids: list[str]) -> None:
    """§8.16: time from comment to reply, split into instant and composed."""
    now = rt.now()
    for cid in comment_ids:
        c = await rt.get_comment(cid)
        if c is not None:
            rt.reply_latencies[kind].append(now - c.received_at)


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
        current = await answer_key(rt, g)
        if current != key:
            # D-117 B5: product, promo or document changed while drafting: draft again for the current state
            # (unless a draft for the current state is already being written; it applies when it ends)
            if current not in rt.composing:
                g.status = "new"
                await answer_group_locked(rt, g, [], scenario)
                g.version += 1
                await rt.save_group(g)
                await rt.emit("group.updated", g)
            return
        if answer is None:
            await no_draft_locked(rt, g)
        else:
            await apply_answer_locked(rt, g, answer, instant=False)
        g.version += 1
        await rt.save_group(g)
        await rt.emit("group.updated", g)
        await rt.recompute_host_queue_locked()
        if answer is not None and answer.verified:
            # D-146: the host may already have answered it aloud while this draft was being written
            rt.spawn(rt.utterances.recheck_early(group_id), name=f"early:{group_id}")


async def _run_composer(rt: "SessionRuntime", group_id: str, key: str, scenario: str) -> Answer | None:
    g = await rt.get_group(group_id)
    if g is None:
        return None
    intent = rt.intent(g.intent)
    promo = await rt.active_price_promo()
    product_id = g.product_id if intent.product_scope == "single" else None
    rt.sync_doc_version()
    passages = await gather_passages(
        rt.ctx.retriever, rt.catalog, rt.prefetched, product_id=product_id, intent=g.intent,
        canonical_question=g.canonical_question, promo=promo, top_k=rt.settings.COMPOSER_TOP_K,
        offers=await rt.active_offers(), search=not arms.files(rt.settings.DESIGN_ARM),  # D-192: F arms do not search
    )
    decide = arms.agents_decide(rt.settings.DESIGN_ARM)
    rules = True
    if arms.tools(rt.settings.DESIGN_ARM):  # D-192 arm F1: the composer gets the sheets its tool step asked for
        got = await file_tools.fetch(rt.composer.llm, rt.catalog, product_id=product_id,
                                     question=g.canonical_question, session_id=rt.sid, scenario=scenario,
                                     deadline_ms=rt.settings.COMPOSER_TIMEOUT_MS)
        passages = [*(p for pid in got.product_ids for p in inputs.all_passages(rt.catalog, pid)), *passages]
        rules = got.rules
    elif decide:  # D-191 arms D to F2: the whole sheet of the product (of every product for multi)
        passages = list({p.passage_id: p for p in [*inputs.all_passages(rt.catalog, product_id), *passages]}.values())
    inp = ComposeInput(product_id=product_id, intent=g.intent, slots=g.condition_slots,
                       canonical_question=g.canonical_question, promo=promo, passages=passages,
                       session_id=rt.sid, scenario=scenario, sensitive=intent.sensitive, rules=rules)
    res = await rt.composer.run(inp, deadline_ms=rt.settings.COMPOSER_TIMEOUT_MS)
    if res.status != "ok" or res.output is None:
        # D-157 (comment-flow CF01): every asker had joined while the only draft timed out; draft once more
        res = await rt.composer.run(inp, deadline_ms=rt.settings.COMPOSER_TIMEOUT_MS)
    if res.status != "ok" or res.output is None:
        return None
    out = res.output
    not_approved = rt.catalog.not_approved_claims(product_id) if product_id else [
        c for p in rt.catalog.products for c in p.not_approved_claims]
    ok, errors = draft_code_gate(out, passages, product_id, arm=rt.settings.DESIGN_ARM, reflex=rt.reflex,
                                 not_approved=not_approved)
    if ok:
        asked = [c.text for cid in g.member_comment_ids[:5] if (c := await rt.get_comment(cid)) is not None]
        ok, errors = await _llm_check(rt, g.canonical_question, out, passages, product_id, promo, scenario,
                                      whole=decide, comments=asked)
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


def draft_code_gate(out, passages, product_id, *, arm: str, reflex, not_approved) -> tuple[bool, list[str]]:
    """The code layer a draft passes before the LLM draft verifier, per design arm (D-200: also what
    eval_draft_verifier scores). Arms D to F2 (D-191): none but the composer's own refusal."""
    if arms.agents_decide(arm):
        return (True, []) if out.grounded and out.answer.strip() else (False, ["not grounded"])
    return verify_answer(out, passages, product_id, multi=product_id is None, reflex=reflex,
                         not_approved_claims=not_approved, minimal=arms.meaning_to_llm(arm))  # D-187 arm B


UNCHECKED = frozenset({"draft_check_timeout", "draft_check_error", "draft_check_invalid"})


async def _llm_check(rt, question, out, passages, product_id, promo, scenario, whole=False,
                     comments=()) -> tuple[bool, list[str]]:
    """D-126: the LLM draft verifier after the code checks. A fail, a timeout or an error keeps the draft
    unverified, so it goes to the operator instead of being posted or cached."""
    inp = DraftCheckInput(product_id=product_id, question=question, answer=out.answer.strip(), promo=promo,
                          passages=passages if whole else cited_passages([c.passage_id for c in out.citations],
                                                                         passages),
                          session_id=rt.sid, scenario=scenario, comments=list(comments))
    res = await rt.draft_verifier.run(inp, deadline_ms=rt.settings.DRAFT_VERIFY_TIMEOUT_MS)
    if res.status == "timeout":  # D-152 (comment-flow CF09): a timeout is not a block; once more
        res = await rt.draft_verifier.run(inp, deadline_ms=rt.settings.DRAFT_VERIFY_TIMEOUT_MS)
    if res.status != "ok" or res.output is None:
        return False, [f"draft_check_{res.status}"]
    if res.output.verdict == "fail":
        return False, [f"draft_check: {p}" for p in res.output.problems] or [f"draft_check: {res.output.reason}"]
    return True, []


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
        g.status, g.answer_id = "new", None  # D-117 B5: a draft in progress was for the old product
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
    hit = rt.reflex.first_hit(text)
    if hit is not None and not confirm:
        rule = rt.pack.rules_by_id[hit.rule_id]
        raise ActionError(409, "restricted_phrase",
                          f"This reply contains a restricted phrase: '{hit.phrase}' ({rule.title}).")
    problems = await _check_operator_reply(rt, gid, text, origin)
    if problems and not confirm:
        raise ActionError(409, "unverified_reply", "This reply could not be verified: " + "; ".join(problems))
    async with rt.lock:
        g = await _group_or_404(rt, gid)
        if g.status in ("answered", "rejected", "closed"):
            raise ActionError(409, "invalid_state", f"group is {g.status}")
        answer = Answer(answer_id=rt.new_id("ans_"), group_id=gid, text=text, citations=[], origin=origin,
                        verified=not problems, verify_errors=problems, needs_human=False, created_at=rt.now())
        await rt.save_answer(answer)
        g.answer_id = answer.answer_id
        await _publish_answer_locked(rt, g, kind="brand_answer", text=text, citations=[], key=f"brand_answer:{gid}")
        await operator_action(rt, "answer", group_id=gid, origin=origin, confirmed_restricted=hit is not None)


async def _check_operator_reply(rt: "SessionRuntime", gid: str, text: str, origin: str) -> list[str]:
    """D-205 (full review P2): an operator's reply is checked before it is posted. Every number must be in the
    product's sheet, a running promo or the question's draft; an edited AI draft also passes the LLM draft verifier
    on the product's whole sheet. Problems need the operator's explicit confirmation ("Post anyway")."""
    g = await _group_or_404(rt, gid)
    sheet = inputs.all_passages(rt.catalog, g.product_id)
    promo = await rt.active_price_promo()
    sources = [p.text for p in sheet] + [promo_passage(o, rt.catalog).text
                                         for o in [*([promo] if promo else []), *await rt.active_offers()]]
    draft = await rt.get_answer(g.answer_id) if g.answer_id else None
    if draft is not None and draft.verified:
        sources.append(draft.text)
    allowed = set().union(*(number_set(x) for x in sources)) if sources else set()
    problems = [f"number {n} is not in the product sheet" for n in sorted(number_set(text) - allowed)]
    if origin == "operator_edit" and not problems:
        res = await rt.draft_verifier.run(DraftCheckInput(
            product_id=g.product_id, question=g.canonical_question, answer=text, promo=promo, passages=sheet,
            session_id=rt.sid, comments=[c.text for cid in g.member_comment_ids[:5]
                                         if (c := await rt.get_comment(cid)) is not None]),
            deadline_ms=rt.settings.DRAFT_VERIFY_TIMEOUT_MS)
        if res.status != "ok" or res.output is None:
            problems.append(f"draft check {res.status}")
        elif res.output.verdict == "fail":
            problems += [f"draft check: {p}" for p in res.output.problems] or [f"draft check: {res.output.reason}"]
    return problems


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
        armored = c.armor == "blocked"
        # D-125: an Armor-blocked comment comes back to chat only; it never goes to an LLM
        c.visibility, c.hide_category, c.kind = "visible", None, "reaction" if armored else "pending"
        await rt.save_comment(c)
        await rt.emit("comment.unhidden", c)
        await operator_action(rt, "unhide", comment_id=cid)
    if armored:
        return
    rt.spawn(process_comment(rt, cid, unhidden=True), name=f"unhide:{cid}")
