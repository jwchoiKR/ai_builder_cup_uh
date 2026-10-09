"""Split sentences: a final is judged together with the previous unfinished final (D-088)."""
from __future__ import annotations

import pytest

from app.models.session import Transcript
from app.pipelines.utterances import ends_sentence

from .judge_fakes import advance, claim, close_env, events, make_env, price_contradiction, speak, violation
from .test_publish import ANSWER, messages, oily_on_host

S08_A, S08_B = "Just to be clear, it does not", "treat acne. It's a moisturiser."
S08 = f"{S08_A} {S08_B}"
S07_A, S07_B = "Use it every night and your wrinkles", "will disappear overnight."
S07 = f"{S07_A} {S07_B}"
S12_A, S12_B = "Now let me show you our ampoule,", "the Deep Hydration Ampoule."
S12 = f"{S12_A} {S12_B}"
PRICE_A, PRICE_B = "And today the live price is only thirty-two", "dollars."
PRICE = f"{PRICE_A} {PRICE_B}"


@pytest.fixture
async def env():
    rt, llm = await make_env()
    yield rt, llm
    await close_env(rt)


async def stored(rt, t: Transcript) -> Transcript:
    return await rt.ctx.store.get(rt.path("transcripts"), t.transcript_id, Transcript)


async def split(rt, first: str, second: str, gap_ms: int = 1200) -> tuple[Transcript, Transcript]:
    a = await speak(rt, first)
    await advance(rt, gap_ms)
    b = await speak(rt, second)
    return a, b


def compliance(alerts):
    return [a for a in alerts if a.kind == "compliance"]


# ---- rule 1: when finals are merged ---------------------------------------------------------------


def test_ends_sentence():
    assert ends_sentence("It does not treat acne.") and ends_sentence("Really?") and ends_sentence("Wow!  ")
    assert ends_sentence('He said "it works."') and ends_sentence("(in our in-house test.)")
    assert not ends_sentence(S08_A) and not ends_sentence("thirty-two,") and not ends_sentence("so")


async def test_unfinished_previous_within_window_is_merged(env):
    rt, llm = env
    a, b = await split(rt, S08_A, S08_B, gap_ms=3500)
    b = await stored(rt, b)
    assert b.merged_from_transcript_id == a.transcript_id and b.judged_text == S08 and b.text == S08_B
    for agent in ("compliance_judge", "context_judge", "fact_checker"):
        assert (agent, S08) in llm.calls and (agent, S08_B) not in llm.calls
    [ev] = [e for e in await events(rt, "transcript.final") if e.payload["transcript_id"] == b.transcript_id]
    assert ev.payload["judged_text"] == S08


@pytest.mark.parametrize("first, gap_ms", [
    (S08_A, 3501),                      # previous final too old
    ("Just to be clear.", 500),         # previous final ended the sentence
    ("Is it clear?", 500),
    ("It is clear!", 500),
])
async def test_not_merged(env, first, gap_ms):
    rt, llm = env
    _, b = await split(rt, first, S08_B, gap_ms=gap_ms)
    b = await stored(rt, b)
    assert b.merged_from_transcript_id is None and b.judged_text is None
    assert ("compliance_judge", S08_B) in llm.calls and ("context_judge", S08_B) in llm.calls


async def test_merge_off_and_chain_limit():
    rt, llm = await make_env(UTTERANCE_MERGE_WINDOW_MS=0)
    try:
        _, b = await split(rt, S08_A, S08_B)
        assert (await stored(rt, b)).merged_from_transcript_id is None
    finally:
        await close_env(rt)
    rt, llm = await make_env()
    try:
        ts = [await speak(rt, w) for w in ("one", "two", "three", "four")]
        got = [(await stored(rt, t)).judged_text for t in ts]
        assert got == [None, "one two", "one two three", None]  # at most 3 finals per judgment
    finally:
        await close_env(rt)


async def test_recent_transcript_excludes_the_merged_fragment(env):
    from .test_utterance_pipeline import RecordingScripted, data_block
    from .helpers import live_runtime, make_ctx

    llm = RecordingScripted()
    rt = await live_runtime(make_ctx(backend=llm))
    try:
        await speak(rt, "Hi everyone.")
        await advance(rt, 5000)
        await split(rt, S08_A, S08_B)
        for agent in ("compliance_judge", "context_judge"):
            assert data_block(llm.messages[(agent, S08)], "RECENT_TRANSCRIPT") == '["Hi everyone."]'
    finally:
        await close_env(rt)


# ---- rule 5: the four required cases -------------------------------------------------------------


async def test_s08_split_after_does_not_gives_no_active_alert(env):
    rt, llm = env
    llm.judge(S08_B, violations=[violation("ASEAN-3-SKIN-ACNE", "treat acne")])  # the fragment on its own
    llm.judge(S08, violations=[violation("ASEAN-3-SKIN-ACNE", "treat acne", negated=True)])
    await split(rt, S08_A, S08_B)
    assert await rt.alerts() == []  # D-410: no provisional alert; the merged verdict is negated


async def test_s08_split_with_judge_failure_falls_back_on_the_negated_reflex(env):
    rt, llm = env
    llm.fail("utterance_judge", S08)
    await split(rt, S08_A, S08_B)
    assert not [a for a in await rt.alerts() if a.status == "active"]  # §8.4.3: negated nearby -> cleared


@pytest.mark.parametrize("fragment_flagged", [True, False])
async def test_s07_split_mid_claim_gives_exactly_one_alert(env, fragment_flagged):
    rt, llm = env
    if fragment_flagged:
        llm.judge(S07_A, violations=[violation("ASEAN-3-SKIN-AGEING", "your wrinkles")])
    # D-397/D-401: the merged line's verdict replaces the fragment's alert (a new alert; the old one is cleared)
    llm.judge(S07, violations=[violation("ASEAN-3-SKIN-AGEING", "your wrinkles will disappear overnight")])
    a, b = await split(rt, S07_A, S07_B)
    [alert] = [x for x in compliance(await rt.alerts()) if x.status == "active"]
    assert alert.rule_id == "ASEAN-3-SKIN-AGEING"
    assert alert.transcript_id == b.transcript_id and alert.span == "your wrinkles will disappear overnight"
    assert len(await events(rt, "alert.created")) == (2 if fragment_flagged else 1)


@pytest.mark.parametrize("fragment_contradicted", [True, False])
async def test_price_split_gives_one_fact_alert(env, fragment_contradicted):
    rt, llm = env
    if fragment_contradicted:
        llm.facts(PRICE_A, price_contradiction("S$32"))
    llm.facts(PRICE, price_contradiction("S$32"))
    a, b = await split(rt, PRICE_A, PRICE_B)
    # D-401: the merged verdict's note is new; the fragment's is cleared (no id reuse, a short flicker)
    [note] = [x for x in await rt.alerts() if x.kind == "fact" and x.status == "active"]
    assert note.field == "price" and note.transcript_id == b.transcript_id
    assert len(await events(rt, "alert.created")) == (2 if fragment_contradicted else 1)
    if fragment_contradicted:
        [old] = [x for x in await rt.alerts() if x.kind == "fact" and x.transcript_id == a.transcript_id]
        assert old.status == "cleared"


# ---- rule 4: a merged judgment never clears its fragment's alert ------------------------------------


# ---- rule 3: host-answer linking, never publish twice --------------------------------------------


ANSWER_A = ANSWER.removesuffix(", so just use a smaller amount on oily areas.")
ANSWER_B = "so just use a smaller amount on oily areas."


async def test_split_host_answer_is_posted_once(env):
    rt, llm = env
    g = await oily_on_host(rt)
    for text in (ANSWER_A, f"{ANSWER_A} {ANSWER_B}"):
        llm.judge(text, utterance_type="answer", matched=g.group_id, is_answer=True, consistent=True)
    await split(rt, ANSWER_A, ANSWER_B, gap_ms=1000)
    [m] = await messages(rt, "host_answer")
    assert m.state == "pending"
    await advance(rt, 2000)
    [m] = await messages(rt, "host_answer")
    assert m.state == "published" and (await rt.get_group(g.group_id)).status == "answered"


async def test_merged_judgment_replaces_the_fragment_answer_link(env):
    rt, llm = env
    g = await oily_on_host(rt)
    llm.judge(ANSWER_A, utterance_type="answer", matched=g.group_id, is_answer=True, consistent=True)
    llm.judge(f"{ANSWER_A} {ANSWER_B}", utterance_type="answer", matched=g.group_id, is_answer=True, consistent=False)
    _, b = await split(rt, ANSWER_A, ANSWER_B, gap_ms=1000)
    [m] = await messages(rt, "host_answer")
    assert m.state == "cancelled"  # the fragment's post was still in its cancel window
    g = await rt.get_group(g.group_id)
    assert g.host_verbal_answer_transcript_id == b.transcript_id and g.published_message_id is None
    await advance(rt, 3000)
    assert not await events(rt, "message.published")


async def test_a_long_new_sentence_is_still_judged_alone(env):
    rt, _ = env
    t1, t2 = await split(rt, "It absorbs really fast.", "And now let me show you the texture on my hand.")
    assert (await stored(rt, t2)).merged_from_transcript_id is None


async def test_the_fact_checker_sees_where_a_merged_utterance_was_split(env):
    """D-167 (local SEED1 replay): "about 50% no plain water" + "Niacinamide" was read as "50% Niacinamide"; the
    fact checker now gets the parts with " / " and a rule not to pair a number with the next sentence's subject."""
    rt, llm = env
    seen: list[str] = []
    generate = llm.generate

    async def record(req, timeout_ms):
        if req.agent == "fact_checker":
            seen.append(req.user_message)
        return await generate(req, timeout_ms)
    llm.generate = record
    await speak(rt, "The base is aloe water, about half, no plain water")
    await speak(rt, "Ceramides")
    assert '>The base is aloe water, about half, no plain water / Ceramides</data>' in seen[-1]
    assert "The base is aloe water, about half, no plain water" in seen[0] and " / " not in seen[0]


async def test_a_bare_continuation_can_be_checked_against_the_product_just_named(env):
    """D-172 (local SEED3 replay): "list price 42" after the ampoule's price, with the cream on air, was checked
    against the cream: the ampoule's sheet was not even among the fact passages."""
    rt, llm = env
    seen: list[str] = []
    generate = llm.generate

    async def record(req, timeout_ms):
        if req.agent == "fact_checker":
            seen.append(req.user_message)
        return await generate(req, timeout_ms)
    llm.generate = record
    await speak(rt, "If you want the ampoule on its own, it is 32 dollars.")
    await rt.ctx.scheduler.advance(5000)  # past the merge window: judged alone
    await speak(rt, "regular price 42")
    assert "DL-AM-01" in seen[-1] and "DL-CR-01" in seen[-1]  # the ampoule just named, and the cream on air


# ---- D-397: a merged line's verdict replaces its chain's alerts --------------------------------------


async def test_d397_a_fragment_claim_the_merged_sentence_negates_is_cleared(env):
    rt, llm = env
    llm.judge(S08_A, violations=[violation("ASEAN-3-SKIN-ACNE", "treat acne")])  # the fragment alone reads as a claim
    llm.judge(S08, violations=[violation("ASEAN-3-SKIN-ACNE", "treat acne", negated=True)])
    await split(rt, S08_A, S08_B)
    assert [a.status for a in compliance(await rt.alerts())] == ["cleared"]


async def test_d397_two_claims_of_one_rule_5_s_apart_are_two_alerts(env):
    rt, llm = env
    first, second = "It treats acne overnight.", "And honestly it treats acne for good."
    llm.judge(first, violations=[violation("ASEAN-3-SKIN-ACNE", "treats acne overnight")])
    llm.judge(second, violations=[violation("ASEAN-3-SKIN-ACNE", "treats acne for good")])
    await speak(rt, first)
    await advance(rt, 5000)
    await speak(rt, second)
    assert sorted(a.span for a in compliance(await rt.alerts()) if a.status == "active") == [
        "treats acne for good", "treats acne overnight"]


async def test_d397_a_fragment_verdict_that_lands_after_the_merged_one_is_not_applied(env):
    import asyncio

    rt, llm = env
    llm.judge(S07_A, violations=[violation("ASEAN-3-SKIN-AGEING", "your wrinkles")])
    llm.judge(S07, violations=[violation("ASEAN-3-SKIN-AGEING", "your wrinkles will disappear overnight")])
    llm.delays[("compliance_judge", S07_A)] = 0.4  # the fragment's verdict arrives last
    await rt.inject_transcript(S07_A)
    await advance(rt, 1200)
    await rt.inject_transcript(S07_B)
    await rt.utterances.drain()
    await asyncio.sleep(0.5)
    await rt.ctx.scheduler.idle()
    assert [a.span for a in compliance(await rt.alerts()) if a.status == "active"] == [
        "your wrinkles will disappear overnight"]


# ---- D-401: codex review of the merge supersede -----------------------------------------------------


async def _late(rt, first: str, second: str) -> None:
    """The fragment's checks are slow; the merged line is checked first."""
    import asyncio

    await rt.inject_transcript(first)
    await advance(rt, 1200)
    await rt.inject_transcript(second)
    await rt.utterances.drain()
    await asyncio.sleep(0.5)
    await rt.ctx.scheduler.idle()


async def test_d401_a_failed_merged_verdict_does_not_block_the_fragment_s(env):
    rt, llm = env
    llm.judge(S07_A, violations=[violation("ASEAN-3-SKIN-AGEING", "your wrinkles")])
    llm.delays[("compliance_judge", S07_A)] = 0.4
    llm.fail("compliance_judge", S07)
    await _late(rt, S07_A, S07_B)
    assert [a.span for a in compliance(await rt.alerts()) if a.status == "active"] == ["your wrinkles"]


async def test_d401_two_claims_of_one_rule_from_a_merge_are_corrected_one_at_a_time(env):
    rt, llm = env
    llm.judge(S07_A, violations=[violation("ASEAN-3-SKIN-AGEING", "your wrinkles")])
    llm.judge(S07, violations=[violation("ASEAN-3-SKIN-AGEING", "your wrinkles"),
                               violation("ASEAN-3-SKIN-AGEING", "disappear overnight")])
    a, b = await split(rt, S07_A, S07_B)
    active = [x for x in compliance(await rt.alerts()) if x.status == "active"]
    assert sorted(x.span for x in active) == ["disappear overnight", "your wrinkles"]
    assert all(x.transcript_id == b.transcript_id for x in active)  # the merged line's own alerts, none reused
    first = next(x for x in active if x.span == "your wrinkles")
    await advance(rt, 5000)
    fix = "Sorry, I take back the wrinkles part."
    llm.judge(fix, corrects=[first.alert_id], utterance_type="correction")
    await speak(rt, fix)
    status = {x.alert_id: x.status for x in compliance(await rt.alerts())}
    assert [status[x.alert_id] for x in active if x is not first] == ["active"] and status[first.alert_id] == "corrected"


async def test_d401_a_merged_fix_only_verdict_leaves_the_fragment_s_note_corrected(env):
    rt, llm = env
    llm.facts(PRICE_A, price_contradiction("S$32"))
    llm.facts(PRICE, fixed=["F1"])  # the whole sentence: no contradiction, and it fixes the fragment's note
    a, b = await split(rt, PRICE_A, PRICE_B)
    [note] = [x for x in await rt.alerts() if x.kind == "fact"]
    assert note.status == "corrected"


# ---- D-403: the model says which listed note a claim repeats (same_as) -----------------------------------------


async def test_d403_a_merged_line_repeating_f1_keeps_the_note_s_id(env):
    rt, llm = env
    llm.facts(PRICE_A, price_contradiction("S$32"))
    llm.facts(PRICE, {**price_contradiction("S$32"), "span": "only thirty-two dollars", "same_as": "F1"})
    a, b = await split(rt, PRICE_A, PRICE_B)
    [note] = [x for x in await rt.alerts() if x.kind == "fact"]
    assert note.status == "active" and note.transcript_id == a.transcript_id and note.span == "only thirty-two dollars"
    assert len(await events(rt, "alert.created")) == 1  # no new note, no flicker


async def test_d403_a_note_dismissed_during_the_merge_stays_closed_and_a_new_claim_shows(env):
    import asyncio

    from app.pipelines.utterances import dismiss_alert

    rt, llm = env
    llm.facts(PRICE_A, price_contradiction("S$32"))
    vol = claim("volume", "contradicted", stated="30 mL", correct="50 mL", span="a thirty mL tube")
    llm.facts(PRICE, {**price_contradiction("S$32"), "same_as": "F1"}, vol, delay=0.4)
    await speak(rt, PRICE_A)
    [frag] = [x for x in await rt.alerts() if x.kind == "fact"]
    await advance(rt, 1200)
    await rt.inject_transcript(PRICE_B)
    await asyncio.sleep(0.1)
    await dismiss_alert(rt, frag.alert_id)  # the operator dismisses it while the merged check runs
    await rt.utterances.drain()
    await asyncio.sleep(0.5)
    await rt.ctx.scheduler.idle()
    status = {x.field: x.status for x in await rt.alerts() if x.kind == "fact"}
    assert status == {"price": "dismissed", "volume": "active"}


async def test_d403_the_summary_leaves_out_a_superseded_note(env):
    """A fragment's note replaced by the merged line's note, then corrected: one note in the summary, corrected."""
    from app.pipelines.summary import compute_stats

    rt, llm = env
    llm.facts(PRICE_A, price_contradiction("S$32"))
    llm.facts(PRICE, price_contradiction("S$32"))
    fix = "Sorry, it's thirty-six dollars."
    llm.facts(fix, fixed=["F1"])
    await split(rt, PRICE_A, PRICE_B)
    await advance(rt, 3000)
    await speak(rt, fix)
    assert sorted(x.status for x in await rt.alerts() if x.kind == "fact") == ["cleared", "corrected"]
    facts = (await compute_stats(rt))["fact_alerts"]
    assert [(f["corrected"], f["shown_to_corrected_ms"] != "uncorrected") for f in facts] == [(True, True)]


pytestmark = pytest.mark.legacy_live  # D-434: not migrated yet (removed in its batch)
