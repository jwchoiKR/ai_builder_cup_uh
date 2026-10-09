"""Split sentences: a final is judged together with the previous unfinished final (D-088)."""
from __future__ import annotations

import pytest

from app.models.session import Transcript
from app.pipelines.utterances import ends_sentence

from .judge_fakes import rid, advance, claim, close_env, events, make_env, price_contradiction, speak, violation
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


# ---- rule 5: the four required cases -------------------------------------------------------------


# ---- rule 4: a merged judgment never clears its fragment's alert ------------------------------------


# ---- rule 3: host-answer linking, never publish twice --------------------------------------------


ANSWER_A = ANSWER.removesuffix(", so just use a smaller amount on oily areas.")
ANSWER_B = "so just use a smaller amount on oily areas."


# ---- D-397: a merged line's verdict replaces its chain's alerts --------------------------------------


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


# ---- D-403: the model says which listed note a claim repeats (same_as) -----------------------------------------
