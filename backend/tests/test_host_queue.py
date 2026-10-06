from __future__ import annotations

import pytest

from app.logic.host_queue import HostQueueFull, QueueParams, compute_slots, push_slot
from app.logic.ranking import score
from app.models.session import HostSlot, QuestionGroup

CREAM, AMPOULE = "cream_hydra_barrier", "ampoule_deep_hydration"
P = QueueParams(top_n=3, min_dwell_ms=20_000, repeat_threshold=5)


def g(gid, *, askers=1, status="ready", route="HOST", pid=CREAM, intent="suitability", first_at=0, **kw):
    return QuestionGroup(group_id=gid, product_id=pid, intent=intent, condition_slots={}, canonical_question=gid,
                         member_comment_ids=[f"c{i}" for i in range(askers)],
                         unique_author_ids=[f"u{i}" for i in range(askers)], first_at=first_at, last_at=first_at,
                         route=route, route_reason="intent", status=status, **kw)


def run(slots, groups, now, on_air=CREAM, seg_start=0, scores=None):
    by_id = {x.group_id: x for x in groups}
    scores = scores or {x.group_id: float(len(x.unique_author_ids)) for x in groups}
    return compute_slots(slots, by_id, scores, on_air=on_air, segment_started_at=seg_start, now=now, params=P,
                         scope_of=lambda i: "multi" if i == "product_comparison" else "single")


def ids(slots):
    return [s.group_id for s in slots]


def test_score_formula(pack):
    w = pack.intents.ranking_weights
    intent = pack.intents_by_name["suitability"]  # purchase_impact 2
    grp = g("a", askers=7, first_at=0)
    assert score(grp, intent, w, CREAM, now=3 * 60_000) == 2.0 * 7 + 1.5 * 2 + 3.0 + 0.1 * 3
    assert score(grp, intent, w, AMPOULE, now=60 * 60_000) == 2.0 * 7 + 1.5 * 2 + 0.1 * 5  # wait capped at 5 min


def test_fills_by_score_and_keeps_places():
    groups = [g("a", askers=2), g("b", askers=5), g("c", askers=1), g("d", askers=3)]
    slots = run([], groups, now=0)
    assert ids(slots) == ["b", "d", "a"]
    # within dwell nothing moves even if a better candidate appears
    groups.append(g("e", askers=9))
    assert ids(run(slots, groups, now=10_000)) == ["b", "d", "a"]
    # after dwell the lowest item is replaced in place by the better outside candidate
    assert ids(run(slots, groups, now=25_000)) == ["b", "d", "e"]


def test_candidates_only():
    groups = [g("needs", status="needs_review", route="OPERATOR"), g("comp", status="composing"),
              g("ai_few", status="auto_answered", route="AUTO", askers=4),
              g("ai_many", status="auto_answered", route="AUTO", askers=5),
              g("ai_conf", status="auto_answered", route="AUTO", askers=6, host_confirmed=True),
              g("other_product", pid=AMPOULE), g("cmp", pid=None, intent="product_comparison"),
              g("verbal", host_verbal_answer_transcript_id="tr_1"), g("recalled", recalled_at=50_000)]
    # recalled 10 s ago is blocked; a drafting question waits in the host's list too (D-113)
    assert set(ids(run([], groups, now=60_000))) == {"ai_many", "cmp", "comp"}
    assert "recalled" in ids(run([], [x for x in groups if x.group_id != "comp"], now=110_001))


def test_answered_and_switch_remove_immediately():
    groups = [g("a", askers=3), g("b", askers=2)]
    slots = run([], groups, now=0)
    groups[0].status = "answered"
    assert ids(run(slots, groups, now=1000)) == ["b"]
    # product switch: cream items leave at once, even within dwell
    assert ids(run(slots, groups, now=2000, on_air=AMPOULE, seg_start=1500)) == []


def test_pinned_priority_and_switch():
    groups = [g("a", askers=9), g("b", askers=8), g("p", askers=1, pid=AMPOULE, pinned_by_operator_at=100)]
    scores = {"a": 9.0, "b": 8.0, "p": 1.0}
    slots = push_slot([], "p", scores, now=100, top_n=3)
    out = run(slots, groups, now=200, scores=scores)
    assert ids(out) == ["p", "a", "b"] and out[0].pinned  # pinned first, may be another product
    # pinned before the switch to a third product -> removed; pinned after -> kept
    assert "p" not in ids(run(out, groups, now=300, on_air="x", seg_start=250, scores=scores))
    assert "p" in ids(run(out, groups, now=300, on_air="x", seg_start=50, scores=scores))


def test_push_replaces_lowest_auto_and_rejects_when_all_pinned():
    slots = [HostSlot(group_id="a", on_host_since=0), HostSlot(group_id="b", on_host_since=0),
             HostSlot(group_id="c", on_host_since=0)]
    scores = {"a": 5.0, "b": 1.0, "c": 3.0}
    pushed = push_slot(slots, "x", scores, now=10, top_n=3)
    assert ids(pushed) == ["x", "a", "c"] and pushed[0].pinned
    all_pinned = [HostSlot(group_id=k, pinned=True, on_host_since=0) for k in "abc"]
    with pytest.raises(HostQueueFull, match="Recall a question first"):
        push_slot(all_pinned, "x", scores, now=10, top_n=3)
    # pushing a group already on host just pins it
    assert [(s.group_id, s.pinned) for s in push_slot(slots, "b", scores, now=10, top_n=3)] == [
        ("b", True), ("a", False), ("c", False)]


def test_repeat_threshold():
    groups = [g("ai", status="auto_answered", route="AUTO", askers=5)]
    assert ids(run([], groups, now=0)) == ["ai"]
    groups[0].unique_author_ids.pop()
    assert ids(run([], groups, now=0)) == []


async def test_queue_refresh_skips_history_and_saves_only_changes():
    """Review B9 (D-117): answered/closed groups are neither rescored nor saved on every refresh."""
    from app.models.session import QuestionGroup

    from .helpers import live_runtime, make_ctx

    ctx = make_ctx()
    rt = await live_runtime(ctx)
    try:
        for i in range(30):
            await rt.save_group(QuestionGroup(
                group_id=f"grp_old{i}", product_id=CREAM, intent="price", condition_slots={},
                canonical_question=f"Old {i}?", member_comment_ids=[], unique_author_ids=[], first_at=0, last_at=0,
                route="AUTO", route_reason="intent", status="answered" if i % 2 else "closed"))
        saved = []
        real = rt.save_group

        async def counting(g):
            saved.append(g.group_id)
            await real(g)

        rt.save_group = counting
        async with rt.lock:
            await rt.recompute_host_queue_locked()
        assert not [gid for gid in saved if gid.startswith("grp_old")]
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
