"""D-351 SWITCH_MODE=immediate, the user's switch rule: the host says they move on AND names the next product (its
name, short name or type word). The context judge decides (`moving_to_next_named`); code only checks that the line is
not a quote and that the target is the next product in the fixed run sheet. Made-up shows; the judge's verdicts are
scripted, so these tests check the wiring the model's verdict goes through."""
from __future__ import annotations

import asyncio

import pytest

from app.onboarding.read import normalise
from app.onboarding.record import ProductRecord
from app.onboarding.release import product_key, save_release
from app.pipelines.runtime import create_session

from .helpers import make_ctx
from .judge_fakes import ScriptedBackend, close_env, events, speak
from .test_clean_base import clean_data
from .test_multi_release import cream


def _skincare(name: str, short: str, word: str) -> ProductRecord:
    rec = cream().model_dump() | {"product_name": f"Lumen {name}", "short_names": [short], "generic_word": word}
    return normalise(ProductRecord.model_validate(rec))[0]


NIGHT_CREAM = _skincare("Night Cream", "the night cream", "cream")
GLOW_SERUM = _skincare("Glow Serum", "the glow serum", "serum")
CALM_TONER = _skincare("Calm Toner", "the calm toner", "toner")
DEW_SERUM = _skincare("Dew Serum", "the dew serum", "serum")
CREAM, SERUM, TONER, SERUM2 = (product_key(r) for r in (NIGHT_CREAM, GLOW_SERUM, CALM_TONER, DEW_SERUM))


class _Backend(ScriptedBackend):
    def __init__(self) -> None:
        super().__init__()
        self.requests = []
        self.fail_once: set[str] = set()

    async def generate(self, req, timeout_ms):
        self.requests.append(req)
        if req.agent == "context_judge" and req.mock_primary_text in self.fail_once:
            self.fail_once.discard(req.mock_primary_text)
            from app.providers.llm import LLMError

            raise LLMError("scripted failure")
        return await super().generate(req, timeout_ms)


async def _show(tmp_path, records=(NIGHT_CREAM, GLOW_SERUM, CALM_TONER)):
    onb = tmp_path / "onb"
    ids = [save_release(onb, r, f"job_{i}") for i, r in enumerate(records)]
    llm = _Backend()
    ctx = make_ctx(backend=llm, DATA_DIR=str(clean_data(tmp_path)), ONBOARDING_DIR=str(onb))
    s = await create_session(ctx, "", release_ids=ids)
    rt = await ctx.runtimes.get(s.session_id)
    await rt.start()
    await ctx.scheduler.advance(5000)
    return rt, llm


@pytest.fixture
async def show(tmp_path):
    rt, llm = await _show(tmp_path)
    yield rt, llm
    await close_env(rt)


async def _on_air(rt) -> str:
    return (await rt.current_segment()).product_id


def _move(llm, line: str, target: str | None, *, named: bool = True, transition: bool = True, quote: bool = False,
          utterance_type: str = "transition"):
    llm.judge(line, utterance_type=utterance_type, transition=transition, quote=quote, target=target,
              confidence="low", named=named)  # confidence decides nothing


async def test_d351_the_context_judge_gets_the_run_sheet_with_short_names_and_type_words(show):
    rt, llm = show
    await speak(rt, "This cream is so rich.")
    req = [r for r in llm.requests if r.agent == "context_judge"][-1]
    for word in ('"short_name":"the glow serum"', '"type":"serum"', '"type":"toner"', '"status":"next"'):
        assert word in req.user_message
    assert "moving_to_next_named" in req.output_model.model_json_schema()["$defs"]["SwitchCueN"]["properties"]


@pytest.mark.parametrize("line, kw", [
    ("Okay, moving on, let me show you the Lumen Glow Serum.", {}),  # the name
    ("Alright, next up, the serum.", {}),  # the type word only, no brand
    ("Yes Mei, it ships today. Okay, now the serum!", {"utterance_type": "answer"}),  # an answer, then the move
])
async def test_d351_moving_on_and_naming_the_next_product_switches(show, line, kw):
    rt, llm = show
    _move(llm, line, SERUM, **kw)
    await speak(rt, line)
    assert await _on_air(rt) == SERUM


@pytest.mark.parametrize("line, kw", [
    ("The serum is coming later, so stay with me.", {"transition": False, "named": False}),  # a plan
    ("This feels lighter than the serum, honestly.", {"transition": False, "named": False}),  # a comparison
    ("Okay, next one!", {"named": False}),  # moving on, nothing named
    ("Now let me show you the toner.", {"named": False}),  # the product after next
    ("Now let me show you the toner.", {}),  # ... even when a verdict says named: the target is not the next one
    ("Someone asked about the serum, we'll get there.", {"quote": True}),
])
async def test_d351_no_switch_without_moving_on_to_the_named_next_product(show, line, kw):
    rt, llm = show
    _move(llm, line, TONER if "toner" in line else SERUM, **kw)
    await speak(rt, line)
    assert await _on_air(rt) == CREAM
    assert all(not d.payload["switch"] for d in await events(rt, "segment.switch_decided"))


async def test_d351_a_move_split_over_two_finals_switches_on_the_second(show):
    rt, llm = show
    _move(llm, "Okay, next up.", None, named=False)
    _move(llm, "The glow serum.", SERUM)
    await speak(rt, "Okay, next up.")
    assert await _on_air(rt) == CREAM
    second = await speak(rt, "The glow serum.")
    assert await _on_air(rt) == SERUM
    [d] = [d for d in await events(rt, "segment.switch_decided") if d.payload["switch"]]
    assert d.payload["transcript_id"] == second.transcript_id


async def test_d351_two_products_of_one_type_switch_only_to_the_next_one(tmp_path):
    rt, llm = await _show(tmp_path, (NIGHT_CREAM, GLOW_SERUM, DEW_SERUM))
    try:
        _move(llm, "Next up, the serum.", SERUM2)  # the later serum
        await speak(rt, "Next up, the serum.")
        assert await _on_air(rt) == CREAM
        _move(llm, "Okay, now the serum.", SERUM)  # the next one
        await speak(rt, "Okay, now the serum.")
        assert await _on_air(rt) == SERUM
    finally:
        await close_env(rt)


async def test_d351_a_late_verdict_after_an_undo_is_never_applied(show):
    from app.pipelines.utterances import undo_switch

    rt, llm = show
    _move(llm, "Moving on to the glow serum.", SERUM)
    await speak(rt, "Moving on to the glow serum.")
    late = "And now, the calm toner!"
    _move(llm, late, TONER)  # the next product once the serum is on air
    llm.delays[("utterance_judge", late)] = 0.2
    await speak(rt, late, wait=False)
    await asyncio.sleep(0.05)
    await undo_switch(rt)  # the operator takes the serum back before the toner verdict arrives
    await rt.utterances.drain()
    assert await _on_air(rt) == CREAM
    started = [e.payload["product_id"] for e in await events(rt, "segment.started")]
    assert started.count(SERUM) == 1 and TONER not in started


async def test_d351_a_failed_context_call_is_made_once_more_without_the_429_wait(show):
    rt, llm = show
    line = "Moving on to the glow serum now."
    _move(llm, line, SERUM)
    llm.fail_once.add(line)
    await speak(rt, line)
    assert await _on_air(rt) == SERUM
    calls = [r for r in llm.requests if r.agent == "context_judge" and r.mock_primary_text == line]
    assert len(calls) == 2 and all(r.retry_429 is False for r in calls)
    assert all(r.deadline_ms <= rt.settings.JUDGE_TIMEOUT_MS for r in calls)
