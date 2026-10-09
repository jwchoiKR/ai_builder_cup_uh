"""Record answers: a price or size question the product record settles is answered by code, with no LLM draft."""
from __future__ import annotations

import json

import pytest

from app.logic.record_answers import record_answer
from app.models.data import ProductVariant
from app.models.session import AgentCall, Answer, Message, QuestionGroup
from app.pipelines import comments as ops
from app.providers.llm import MockBackend, RawReply

from .helpers import live_runtime, make_ctx, say

CREAM = "cream_hydra_barrier"
NO_SLOTS = {"person_type": None, "life_stage": None, "condition": None, "combined_with": None, "time_of_day": None}


@pytest.fixture
async def rt(tmp_path):
    ctx = make_ctx(tmp_path, RECORD_ANSWERS=True)  # empty fixture dir: agents use their rule-based fallbacks
    runtime = await live_runtime(ctx)
    yield runtime
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()


def sheet(rt, pid=CREAM):
    return [p for p in rt.catalog.pack.passages if p.product_id == pid]


async def calls(rt, agent: str) -> list[AgentCall]:
    return [c for c in await rt.ctx.store.query(rt.path("agent_calls"), AgentCall) if c.agent == agent]


# ---- the answer itself -----------------------------------------------------------------------------


def test_price_is_the_live_price_with_the_list_price_it_is_down_from(rt):
    out, cited, value = record_answer(rt.catalog, sheet(rt), product_id=CREAM, intent="price", slots=NO_SLOTS, promo=None)
    assert out.answer == "Hydra Barrier Cream is S$36.00 during the live broadcast (list price S$48.00)."
    assert [p.passage_id for p in cited] == ["DL-CR-01#key-facts#live-broadcast-price", "DL-CR-01#key-facts#list-price"]
    assert [c.quote for c in out.citations] == [p.text for p in cited] and out.grounded and not out.needs_human


def test_price_names_a_running_offer_but_not_a_notice(rt):
    gift, notice = rt.pack.promos_by_id["promo_gift_pouch"], rt.pack.promos_by_id["promo_set_reminder"]
    out, cited, value = record_answer(rt.catalog, sheet(rt), product_id=CREAM, intent="price", slots=NO_SLOTS, promo=None,
                               offers=[notice, gift])
    assert out.answer.endswith("Also on now: Free DAON LAB travel pouch with orders over S$60.")
    assert "S$62" not in out.answer and cited[-1].passage_id == "PROMO#promo_gift_pouch"


def test_without_a_list_price_passage_the_price_stands_alone(rt):
    without = [p for p in sheet(rt) if not p.passage_id.endswith("#list-price")]
    out, cited, value = record_answer(rt.catalog, without, product_id=CREAM, intent="price", slots=NO_SLOTS, promo=None)
    assert out.answer == "Hydra Barrier Cream is S$36.00 during the live broadcast." and len(cited) == 1


def test_price_during_a_price_promo_is_the_promo_price(rt):
    promo = rt.pack.promos_by_id["promo_time_sale_10"]
    out, cited, value = record_answer(rt.catalog, sheet(rt), product_id=CREAM, intent="price", slots=NO_SLOTS, promo=promo)
    assert "S$32.40" in out.answer and "S$36.00" not in out.answer
    assert cited[0].passage_id == "PROMO#promo_time_sale_10"


def test_size_cites_the_volume_passage(rt):
    out, cited, value = record_answer(rt.catalog, sheet(rt), product_id=CREAM, intent="volume", slots=NO_SLOTS, promo=None)
    assert "50 mL" in out.answer and [p.passage_id for p in cited] == ["DL-CR-01#key-facts#volume"]


@pytest.mark.parametrize("intent", ["ingredients", "shelf_life", "set_price", "promo", "pregnancy_breastfeeding"])
def test_other_intents_are_the_composers(rt, intent):
    assert record_answer(rt.catalog, sheet(rt), product_id=CREAM, intent=intent, slots=NO_SLOTS, promo=None) is None


def test_a_condition_or_variant_is_the_composers(rt):
    for slots in (NO_SLOTS | {"person_type": "student"}, NO_SLOTS | {"variant": "100 mL"}):
        assert record_answer(rt.catalog, sheet(rt), product_id=CREAM, intent="price", slots=slots, promo=None) is None


def test_no_product_or_unknown_product(rt):
    for pid in (None, "no_such_product"):
        assert record_answer(rt.catalog, sheet(rt), product_id=pid, intent="price", slots=NO_SLOTS, promo=None) is None


def test_no_passage_for_the_value_means_no_answer(rt):
    without = [p for p in sheet(rt) if "price" not in p.passage_id]
    assert record_answer(rt.catalog, without, product_id=CREAM, intent="price", slots=NO_SLOTS, promo=None) is None
    no_volume = [p for p in sheet(rt) if not p.passage_id.endswith("#volume")]
    assert record_answer(rt.catalog, no_volume, product_id=CREAM, intent="volume", slots=NO_SLOTS, promo=None) is None


def test_two_passages_for_the_value_mean_no_answer(rt):
    live = next(p for p in sheet(rt) if p.passage_id.endswith("#live-broadcast-price"))
    twice = [*sheet(rt), live.model_copy(update={"passage_id": "DL-CR-01#key-facts#other", "text": "Member price: S$36.00"})]
    assert record_answer(rt.catalog, twice, product_id=CREAM, intent="price", slots=NO_SLOTS, promo=None) is None


def test_another_products_passages_are_never_cited(rt):
    other = [p for p in rt.catalog.pack.passages if p.product_id != CREAM]
    assert record_answer(rt.catalog, other, product_id=CREAM, intent="price", slots=NO_SLOTS, promo=None) is None


def test_variants_that_differ_are_the_composers(rt, monkeypatch):
    product = rt.catalog.get_product(CREAM)
    monkeypatch.setattr(product, "variants", [ProductVariant(label="50 mL", list_price=48, live_price=36),
                                              ProductVariant(label="100 mL", list_price=80, live_price=60)])
    assert record_answer(rt.catalog, sheet(rt), product_id=CREAM, intent="price", slots=NO_SLOTS, promo=None) is None


# ---- in the comment pipeline -------------------------------------------------------------------------


async def test_price_question_is_answered_without_composer_or_draft_check(rt):
    await say(rt, "Lee", "How much is the cream?")
    [g] = await rt.groups()
    assert (g.intent, g.route, g.status) == ("price", "AUTO", "auto_answered")
    [m] = await rt.ctx.store.query(rt.path("messages"), Message, order_by="created_at")
    assert m.kind == "ai_answer" and "S$36.00" in m.text and m.reply_to_author_names == ["Lee"]
    assert m.citations[0]["passage_id"] == "DL-CR-01#key-facts#live-broadcast-price"
    assert await calls(rt, "answer_composer") == [] and len(await calls(rt, "draft_verifier")) == 1  # the record answer is checked too
    assert rt.counters["record_answers"] == 1 and rt.counters["composed_answers"] == 0
    answer = await rt.get_answer(g.answer_id)
    assert answer.verified and answer.origin == "ai" and answer.cache_key


async def test_next_asker_gets_the_same_answer_from_the_cache(rt):
    await say(rt, "Lee", "How much is the cream?")
    await rt.ctx.scheduler.advance(60_000)  # past REPLY_COALESCE_SEC: a second reply, same text
    await say(rt, "Kumar", "How much is the cream?")
    answers = await rt.ctx.store.query(rt.path("answers"), Answer)
    assert len(answers) == 1
    first, second = await rt.ctx.store.query(rt.path("messages"), Message, order_by="created_at")
    assert first.text == second.text and second.reply_to_author_names == ["Kumar"]
    assert await calls(rt, "answer_composer") == []


async def test_other_questions_still_go_to_the_composer(rt):
    await say(rt, "Mei", "Where is the cream made?")
    assert len(await calls(rt, "answer_composer")) == 1
    assert rt.counters["record_answers"] == 0


async def test_switched_off_the_composer_drafts_the_price(tmp_path):
    ctx = make_ctx(tmp_path, RECORD_ANSWERS=False)
    rt = await live_runtime(ctx)
    try:
        await say(rt, "Lee", "How much is the cream?")
        assert len(await calls(rt, "answer_composer")) == 1 and rt.counters["composed_answers"] == 1
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


async def test_a_record_answer_that_fails_the_code_gate_is_composed_instead(rt, monkeypatch):
    real = ops.draft_code_gate
    seen = []

    def gate(out, *args, **kwargs):
        seen.append(out.reason)
        return (False, ["forced"]) if out.reason == "record answer" else real(out, *args, **kwargs)

    monkeypatch.setattr(ops, "draft_code_gate", gate)
    await say(rt, "Lee", "How much is the cream?")
    assert seen[0] == "record answer" and len(await calls(rt, "answer_composer")) == 1
    assert rt.counters["record_answers"] == 0


async def test_a_host_routed_group_gets_the_draft_but_no_post(rt):
    """The route still decides: a record answer for a group that is not AUTO is a ready draft, never a post."""
    g = QuestionGroup(group_id="g_host", product_id=CREAM, intent="volume", condition_slots=dict(NO_SLOTS),
                      canonical_question="How big is the cream?", member_comment_ids=[], unique_author_ids=[],
                      first_at=rt.now(), last_at=rt.now(), route="HOST", route_reason="intent", status="new")
    async with rt.lock:
        await rt.save_group(g)
        await ops.answer_group_locked(rt, g, [], "default")
        await rt.save_group(g)
    await rt.ctx.scheduler.idle()
    g = await rt.get_group("g_host")
    assert g.status == "ready" and g.published_message_id is None and g.answer_id is not None
    assert await rt.ctx.store.query(rt.path("messages"), Message) == []


async def test_an_offer_that_starts_changes_the_next_price_answer(rt):
    await say(rt, "Lee", "How much is the cream?")
    await rt.start_promo("promo_gift_pouch")
    await rt.ctx.scheduler.advance(60_000)
    await say(rt, "Kumar", "cream price?")
    texts = [m.text for m in await rt.ctx.store.query(rt.path("messages"), Message, order_by="created_at")
             if m.kind == "ai_answer"]
    assert "travel pouch" not in texts[0] and "travel pouch" in texts[-1]
    assert await calls(rt, "answer_composer") == []


async def test_an_offer_that_ends_is_not_named_again(rt):
    await rt.start_promo("promo_gift_pouch")
    await say(rt, "Lee", "How much is the cream?")
    await rt.stop_promo("promo_gift_pouch")
    await rt.ctx.scheduler.advance(60_000)
    await say(rt, "Kumar", "cream price?")
    texts = [m.text for m in await rt.ctx.store.query(rt.path("messages"), Message, order_by="created_at")
             if m.kind == "ai_answer"]
    assert "travel pouch" in texts[0] and "travel pouch" not in texts[-1] and len(texts) == 2


async def test_a_notice_closes_no_price_question(rt):
    await say(rt, "Lee", "How much is the cream?")
    await rt.start_promo("promo_set_reminder")
    [g] = await rt.groups()
    assert g.status == "auto_answered"


# ---- the wording (ReplyPhraser) -----------------------------------------------------------------------


class Wording(MockBackend):
    """The mock backend with a scripted ReplyPhraser reply."""

    def __init__(self, fixtures_dir, reply: str):
        super().__init__(fixtures_dir)
        self.reply, self.seen = reply, []

    async def generate(self, req, timeout_ms):
        if req.agent != "reply_phraser":
            return await super().generate(req, timeout_ms)
        self.seen.append(req.user_message)
        return RawReply(json.dumps({"reply": self.reply, "reason": "test"}), model_version="test")


async def price_reply(tmp_path, wording: str, **settings):
    backend = Wording(tmp_path, wording)
    ctx = make_ctx(backend=backend, RECORD_ANSWERS=True, **settings)
    rt = await live_runtime(ctx)
    try:
        await say(rt, "Lee", "how much ah the cream")
        [m] = await rt.ctx.store.query(rt.path("messages"), Message, order_by="created_at")
        return m.text, backend, dict(rt.counters), await calls(rt, "answer_composer")
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


PLAIN = "Hydra Barrier Cream is S$36.00 during the live broadcast (list price S$48.00)."


async def test_the_wording_is_posted_when_it_keeps_the_value(tmp_path):
    text, backend, counters, composer = await price_reply(
        tmp_path, "It's S$36.00 during the live, down from the S$48.00 list price.")
    assert text == "It's S$36.00 during the live, down from the S$48.00 list price."
    assert PLAIN in backend.seen[0] and "how much ah the cream" in backend.seen[0]  # the facts and the viewer's words
    assert counters["record_answers"] == 1 and composer == []


async def test_a_wording_may_leave_out_the_list_price_but_not_the_price(tmp_path):
    text, *_ = await price_reply(tmp_path, "It's S$36.00 during the live broadcast.")
    assert text == "It's S$36.00 during the live broadcast."
    text, _, counters, _ = await price_reply(tmp_path, "It is down from the S$48.00 list price.")
    assert text == PLAIN and counters["record_wordings_dropped"] == 1


@pytest.mark.parametrize("wording", [
    "It's S$35.00 during the live broadcast.",  # a changed value
    "It's S$36.00, and shipping is free over S$20.",  # a number the record answer does not state
    "It's S$36.00. " + "Great choice. " * 30,  # longer than a reply may be
])
async def test_a_wording_that_changes_or_adds_is_dropped_for_the_plain_sentence(tmp_path, wording):
    text, _, counters, composer = await price_reply(tmp_path, wording)
    assert text == PLAIN and counters["record_wordings_dropped"] == 1 and composer == []


async def test_without_phrasing_the_plain_sentence_is_posted_and_the_agent_is_not_called(tmp_path):
    text, backend, _, _ = await price_reply(tmp_path, "It's S$36.00.", RECORD_PHRASING=False)
    assert text == PLAIN and backend.seen == []


# ---- a rejected composer draft is written once more ---------------------------------------------------


class Drafts(MockBackend):
    """The mock backend with scripted composer drafts, in order."""

    def __init__(self, fixtures_dir, drafts: list[dict]):
        super().__init__(fixtures_dir)
        self.drafts, self.messages = list(drafts), []

    async def generate(self, req, timeout_ms):
        if req.agent != "answer_composer":
            return await super().generate(req, timeout_ms)
        self.messages.append(req.user_message)
        return RawReply(json.dumps(self.drafts.pop(0)), model_version="test")


ORIGIN = {"passage_id": "DL-CR-01#key-facts#made-in", "quote": "Made in: Republic of Korea"}
LONG = {"answer": "It is made in the Republic of Korea. " + "It is a lovely cream that many people like. " * 6,
        "citations": [ORIGIN], "grounded": True, "needs_human": False, "reason": "long"}
SHORT = {"answer": "It is made in the Republic of Korea.", "citations": [ORIGIN], "grounded": True,
         "needs_human": False, "reason": "short"}


async def origin_reply(tmp_path, drafts, **settings):
    backend = Drafts(tmp_path, drafts)
    ctx = make_ctx(backend=backend, **({"COMPOSER_REVISE": True} | settings))
    rt = await live_runtime(ctx)
    try:
        await say(rt, "Mei", "Where is the cream made?")
        [g] = await rt.groups()
        return g, backend, dict(rt.counters), await rt.ctx.store.query(rt.path("messages"), Message)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


async def test_a_too_long_draft_is_written_again_and_posted(tmp_path):
    g, backend, counters, messages = await origin_reply(tmp_path, [LONG, SHORT])
    assert g.status == "auto_answered" and [m.text for m in messages] == ["It is made in the Republic of Korea."]
    assert counters["composer_revised"] == 1 and len(backend.messages) == 2
    assert '<data name="REVISE">' in backend.messages[1] and "longer than 240 characters" in backend.messages[1]
    assert '<data name="REVISE">' not in backend.messages[0]


async def test_a_second_rejected_draft_goes_to_the_operator(tmp_path):
    g, backend, counters, messages = await origin_reply(tmp_path, [LONG, LONG])
    assert (g.route, g.route_reason, g.status) == ("OPERATOR", "no_verified_answer", "needs_review")
    assert messages == [] and counters["composer_revise_failed"] == 1 and len(backend.messages) == 2


async def test_an_ungrounded_draft_is_not_written_again(tmp_path):
    none = {"answer": "", "citations": [], "grounded": False, "needs_human": True, "reason": "no source"}
    g, backend, _, messages = await origin_reply(tmp_path, [none])
    assert g.status == "needs_review" and messages == [] and len(backend.messages) == 1


async def test_switched_off_a_rejected_draft_goes_to_the_operator_at_once(tmp_path):
    g, backend, _, messages = await origin_reply(tmp_path, [LONG], COMPOSER_REVISE=False)
    assert g.status == "needs_review" and messages == [] and len(backend.messages) == 1


# ---- the value is right, but is it what was asked? ---------------------------------------


class Verdict(MockBackend):
    """The mock backend with a scripted draft verifier verdict."""

    def __init__(self, fixtures_dir, verdict: str):
        super().__init__(fixtures_dir)
        self.verdict, self.seen = verdict, []

    async def generate(self, req, timeout_ms):
        if req.agent != "draft_verifier":
            return await super().generate(req, timeout_ms)
        self.seen.append(req.user_message)
        return RawReply(json.dumps({"verdict": self.verdict, "problems": ["rule 6: asks about one pump"] if self.verdict == "fail" else [],
                                    "reason": "test"}), model_version="test")


async def volume_reply(tmp_path, verdict: str, **settings):
    backend = Verdict(tmp_path, verdict)
    ctx = make_ctx(backend=backend, RECORD_ANSWERS=True, **settings)
    rt = await live_runtime(ctx)
    try:
        await say(rt, "Lee", "How big is the cream?")
        [g] = await rt.groups()
        return g, backend, await rt.get_answer(g.answer_id), await rt.ctx.store.query(rt.path("messages"), Message)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


async def test_a_record_answer_the_verifier_fails_is_not_posted(tmp_path):
    g, backend, answer, messages = await volume_reply(tmp_path, "fail")
    assert g.intent == "volume" and messages == [] and (g.route, g.route_reason, g.status) == ("OPERATOR", "no_verified_answer", "needs_review")
    assert answer.record and not answer.verified and answer.verify_errors == ["draft_check: rule 6: asks about one pump"]
    assert "How big is the cream?" in backend.seen[0]  # the viewer's own words are checked


async def test_a_record_answer_the_verifier_passes_is_posted(tmp_path):
    g, backend, answer, messages = await volume_reply(tmp_path, "pass")
    assert g.status == "auto_answered" and len(messages) == 1 and answer.verified and len(backend.seen) == 1
