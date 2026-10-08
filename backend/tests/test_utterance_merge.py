"""Split sentences: a final is judged together with the previous unfinished final (D-088)."""
from __future__ import annotations

import pytest

from app.models.session import Transcript
from app.pipelines.utterances import ends_sentence

from .judge_fakes import AMPOULE, advance, close_env, events, make_env, price_contradiction, speak, violation
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
    alerts = await rt.alerts()
    assert [(a.rule_id, a.status) for a in alerts] == [("ASEAN-3-SKIN-ACNE", "cleared")]  # provisional, then cleared


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
    # D-387: the merge keeps one alert for the SAME claim (same span) of the line
    llm.judge(S07, violations=[violation("ASEAN-3-SKIN-AGEING", "your wrinkles" if fragment_flagged
                                         else "your wrinkles will disappear overnight")])
    a, b = await split(rt, S07_A, S07_B)
    [alert] = compliance(await rt.alerts())
    assert alert.status == "active" and alert.rule_id == "ASEAN-3-SKIN-AGEING"
    assert alert.transcript_id == (a if fragment_flagged else b).transcript_id
    assert len(await events(rt, "alert.created")) == 1


async def test_s12_split_counts_the_switch_cue_once(env):
    rt, llm = env
    cue = dict(transition=True, target=AMPOULE, confidence="high")
    llm.judge(S12_A, **cue)
    llm.judge(S12, **cue)
    a, b = await split(rt, S12_A, S12_B)
    sw = (await rt.load_session()).switch
    assert (sw.status, sw.cue_count, sw.cue_transcript_ids) == ("counting", 1, [b.transcript_id])
    counting = [e.payload for e in await events(rt, "segment.switch_counting")]
    assert [p["cue_count"] for p in counting] == [1, 1]
    assert counting[1]["replaces_transcript_id"] == a.transcript_id
    # the next separate utterance with ampoule information confirms (D-090)
    await advance(rt, 5000)
    info = "It's a watery gel, just two to three drops after toner."
    llm.judge(info, covered=["am-p2"])
    await speak(rt, info)
    sw = (await rt.load_session()).switch
    assert (sw.status, sw.cue_count) == ("pending", 2)


async def test_merged_judgment_withdraws_a_cue_it_does_not_repeat(env):
    rt, llm = env
    llm.judge(S12_A, transition=True, target=AMPOULE, confidence="high")
    llm.judge(S12)  # with the whole sentence: not a transition
    a, _ = await split(rt, S12_A, S12_B)
    sw = (await rt.load_session()).switch
    assert (sw.status, sw.cue_count, sw.cue_transcript_ids) == ("idle", 0, [])
    [cancel] = [e.payload for e in await events(rt, "segment.switch_cancelled")]
    assert cancel == {"reason": "merged", "withdrawn_transcript_id": a.transcript_id}


@pytest.mark.parametrize("fragment_contradicted", [True, False])
async def test_price_split_gives_one_fact_alert(env, fragment_contradicted):
    rt, llm = env
    if fragment_contradicted:
        llm.facts(PRICE_A, price_contradiction("S$32"))
    llm.facts(PRICE, price_contradiction("S$32"))
    a, b = await split(rt, PRICE_A, PRICE_B)
    [note] = [x for x in await rt.alerts() if x.kind == "fact"]
    assert note.status == "active" and note.field == "price"
    assert note.transcript_id == b.transcript_id  # D-374: a re-show carries the line that showed it last
    assert len(await events(rt, "alert.created")) == 1
    if fragment_contradicted:  # D-374: the merged verdict re-shows the same note (no merge protection), one note
        assert [e for e in await events(rt, "alert.updated") if e.payload["alert_id"] == note.alert_id]


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
