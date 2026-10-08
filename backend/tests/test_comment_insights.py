"""What viewers asked (summary page): topics from the agent, every number counted by code from the stored comments."""
from __future__ import annotations

import json

from app.models.agent_io import CommentInsightsOutput, InsightTopic
from app.models.session import Comment, Message, QuestionGroup
from app.pipelines.comment_insights import accept, build_insights, run_comment_insights, timeline
from app.pipelines.summary import get_summary, run_summary
from app.providers.llm import LLMTimeout, MockBackend, RawReply

from .firestore_fake import FakeFirestore
from .helpers import live_runtime, make_ctx, say

T0 = 1_790_000_000_000


def comment(cid, author, text, at=0, **kw):
    return Comment(comment_id=cid, author_id=author, author_name=author, text=text, received_at=T0 + at, source="viewer",
                   **({"kind": "question"} | kw))


def group(gid, intent, members, authors, at=0, **kw):
    return QuestionGroup(group_id=gid, product_id=None, intent=intent, condition_slots={}, canonical_question=f"Q {gid}",
                         member_comment_ids=members, unique_author_ids=authors, first_at=T0 + at, last_at=T0 + at,
                         **({"route": "AUTO", "route_reason": "auto", "status": "ready"} | kw))


def message(mid, gid, kind, replies, at, state="published"):
    return Message(message_id=mid, kind=kind, text="t", group_id=gid, reply_to_comment_ids=replies,
                   reply_to_author_names=[], citations=[], state=state, created_at=T0 + at, published_at=T0 + at,
                   idempotency_key=mid)


def sample():
    comments = [comment("c1", "u1", "how much?"), comment("c2", "u2", "price pls", 1000),
                comment("c3", "u3", "ok while pregnant?", 2000), comment("c4", "u4", "ship to msia?", 3000),
                comment("c5", "u5", "my number is 9123 4567, ship?", 4000, visibility="hidden"),
                comment("c6", "u1", "so pretty", 5000, kind="reaction"),
                comment("c7", "u6", "no sound", 6000, kind="reaction", signal="stream_issue")]
    groups = [group("g1", "price", ["c1", "c2"], ["u1", "u2"]),
              group("g2", "pregnancy_breastfeeding", ["c3"], ["u3"], 2000, needs_approval=True, approval_reason="health",
                    route="HOST", route_reason="approval"),
              group("g3", "shipping", ["c4", "c5"], ["u4", "u5"], 3000, needs_approval=True, approval_reason="outside",
                    route="OPERATOR", route_reason="no_verified_answer")]
    messages = [message("m1", "g1", "ai_answer", ["c1", "c2"], 5000),
                message("m2", "g2", "host_answer", ["c3"], 32000),
                message("m3", "g3", "brand_answer", ["c4"], 9000, state="pending")]  # not posted: still unanswered
    return comments, groups, messages


def test_counts_come_from_the_stored_records():
    comments, groups, messages = sample()
    out = build_insights(comments, groups, messages, {"g1": "Price and offers", "g2": "Use in pregnancy",
                                                      "g3": "Shipping"}, ["A note."], source="firestore",
                         buying_labels={"Price and offers", "Shipping"})
    assert (out["comments"], out["questions"], out["reactions"], out["hidden"], out["stream_reports"]) == (7, 5, 2, 1, 1)
    assert (out["viewers"], out["askers"]) == (6, 5)
    assert out["outcomes"] == {"auto_answered": 2, "answered_by_person": 1, "unanswered": 2}
    assert [(t["label"], t["questions"], t["askers"], t["buying"]) for t in out["topics"]] == [
        ("Price and offers", 2, 2, True), ("Shipping", 2, 2, True), ("Use in pregnancy", 1, 1, False)]
    assert out["topics"][1]["examples"] == ["ship to msia?"]  # the hidden comment is never quoted
    assert out["reply_time_sec"] == {"auto": {"n": 2, "p50": 4.0, "p95": 5.0}, "person": {"n": 1, "p50": 30.0, "p95": 30.0}}
    assert out["buying"] == {"questions": 4, "topics": ["Price and offers", "Shipping"], "unanswered": 2}
    assert out["not_in_product_information"] == {"questions": 2, "examples": ["Q g3"]}
    assert out["waited_for_a_person_by_reason"] == {"outside": 2, "health": 1}
    assert out["notes"] == ["A note."] and out["source"] == "firestore"
    json.dumps(out)


def test_timeline_counts_per_minute_and_names_the_busiest_slice():
    comments, _, _ = sample()
    late = [comment("c8", "u7", "price?", 125_000), comment("c9", "u8", "size?", 130_000), comment("c10", "u9", "lol", 131_000, kind="reaction")]
    out = timeline(comments + late, T0, T0 + 170_000, on_air=lambda at: "Cream" if at < T0 + 120_000 else "Ampoule")
    assert out["bin_sec"] == 60
    assert [(b["start_sec"], b["comments"], b["questions"], b["product"]) for b in out["bins"]] == [
        (0, 7, 5, "Cream"), (60, 0, 0, "Cream"), (120, 3, 2, "Ampoule")]
    assert out["peak"]["start_sec"] == 0
    long = timeline([comment("a", "u", "q", 0), comment("b", "u", "q", 50 * 60_000)], T0, None)
    assert long["bin_sec"] == 300 and len(long["bins"]) == 11 and long["bins"][10]["questions"] == 1
    assert timeline([], T0, None) is None


def test_without_topics_the_stored_labels_are_used():
    comments, groups, messages = sample()
    out = build_insights(comments, groups, messages, None, [], source="store")
    assert [(t["label"], t["buying"]) for t in out["topics"]] == [
        ("Price", True), ("Shipping", True), ("Pregnancy breastfeeding", False)]


def test_the_agents_topics_are_checked():
    offered = {"q1": "g1", "q2": "g2", "q3": "g3"}
    out = CommentInsightsOutput(
        topics=[InsightTopic(label="Price and offers", buying=True, keys=["q1", "q9"]),  # q9 was never offered
                InsightTopic(label="Top 3 worries", keys=["q2"]),  # a number in a label
                InsightTopic(label="Shipping", buying=True, keys=["q1", "q3"])],  # q1 again: the first topic keeps it
        notes=["Viewers asked about pregnancy.", "90% asked the price.", " ", "a", "b", "c"])
    by_group, notes, buying = accept(out, offered)
    assert by_group == {"g1": "Price and offers", "g2": "Other", "g3": "Shipping"}
    assert notes == ["Viewers asked about pregnancy.", "a", "b"] and buying == {"Price and offers", "Shipping"}


class Sorter(MockBackend):
    """The mock backend with a scripted comment_insights reply (a dict), or a timeout (None)."""

    def __init__(self, fixtures_dir, reply):
        super().__init__(fixtures_dir)
        self.reply, self.asked = reply, []

    async def generate(self, req, timeout_ms):
        if req.agent != "comment_insights":
            return await super().generate(req, timeout_ms)
        self.asked.append(req.user_message)
        if self.reply is None:
            raise LLMTimeout("deadline")
        return RawReply(json.dumps(self.reply), model_version="test")


async def ended_show(tmp_path, reply, **settings):
    backend = Sorter(tmp_path, reply)
    ctx = make_ctx(backend=backend, RECORD_ANSWERS=True, **settings)
    rt = await live_runtime(ctx)
    await say(rt, "Lee", "How much is the cream?")
    await say(rt, "Mei", "cream price?")
    await say(rt, "Hana", "So pretty! 💜")
    return ctx, rt, backend


async def test_the_summary_carries_the_analysis(tmp_path):
    reply = {"topics": [{"label": "Price and offers", "buying": True, "keys": ["q1", "q2"]}], "notes": []}
    ctx, rt, backend = await ended_show(tmp_path, reply)
    try:
        await run_summary(rt)
        got = (await get_summary(rt))["comment_insights"]
        assert got["topic_source"] == "analysis" and got["source"] == "store"
        assert [(t["label"], t["questions"], t["auto_answered"]) for t in got["topics"]] == [("Price and offers", 2, 2)]
        assert got["buying"]["questions"] == 2 and got["reactions"] == 1
        assert sum(b["comments"] for b in got["timeline"]["bins"]) == 3 and got["timeline"]["peak"]["product"]
        assert len(backend.asked) == 1 and "cream price?" in backend.asked[0] and "So pretty" not in backend.asked[0]
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


async def test_a_failed_analysis_falls_back_to_the_stored_labels(tmp_path):
    ctx, rt, _ = await ended_show(tmp_path, None)
    try:
        got = await run_comment_insights(rt)
        assert got["topic_source"] == "labels" and [t["label"] for t in got["topics"]] == ["Price"]
        assert got["outcomes"]["auto_answered"] == 2 and got["notes"] == []
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


async def test_with_the_comment_mirror_the_documents_are_read_from_firestore(tmp_path):
    fake = FakeFirestore()
    reply = {"topics": [{"label": "Price and offers", "buying": True, "keys": ["q1", "q2"]}], "notes": []}
    ctx, rt, _ = await ended_show(tmp_path, reply, SESSIONS_FIRESTORE=True, GCP_PROJECT="p", firestore_client=fake)
    try:
        got = await run_comment_insights(rt)
        assert got["source"] == "firestore" and got["questions"] == 2 and got["comments"] == 3
        assert any(p.endswith("/comments") for p in fake.reads)  # read back from the stored documents
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
        await ctx.store.aclose()
