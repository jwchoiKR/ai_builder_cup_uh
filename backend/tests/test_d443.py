"""D-443: the backend checks of D-433, D-436 and D-439 on the rebuilt onboarding's show (a product and its uploaded
regulation PDF, no demo pack): the red alert's cited title, the retraction phrase in the snapshot and the correction
cue, the summary's typed flag and the transcripts the snapshot carries. A made-up supplement and regulation; the
compliance judge's answers are scripted."""
from __future__ import annotations

from app.models.session import Alert
from app.pipelines import utterances as utt
from app.pipelines.summary import compute_stats

from .judge_fakes import close_env, speak
from .test_d358 import CLAIM, CODE, _Backend, _verdict


async def _show(llm):
    from app.pipelines.runtime import create_session

    from .helpers import make_ctx, product_show

    ctx = make_ctx(backend=llm)
    key = product_show(ctx, {"brand": "Kelmar", "product_name": "Joint Ease", "currency": "SGD", "variants": [{"label": "", "list_price": "30.00", "live_price": "25.00"}],
                             "points": [{"text": "Supports normal joint comfort.", "required": True}]},
                       [("kelmar_code.pdf", CODE)])
    s = await create_session(ctx, "", release_id=key)
    rt = await ctx.runtimes.get(s.session_id)
    await rt.start()
    await ctx.scheduler.advance(5000)
    return rt


async def _red(rt, llm) -> Alert:
    llm.outputs[("compliance_judge", CLAIM)] = _verdict(
        "kelmar_code.pdf#2.1", "must not be presented as treating, curing or preventing disease")
    await speak(rt, CLAIM)
    [a] = [a for a in await rt.alerts() if a.kind == "compliance"]
    return a


async def test_d433_a_cited_red_alert_carries_the_documents_readable_title():
    llm = _Backend()
    rt = await _show(llm)
    try:
        a = await _red(rt, llm)
        # an uploaded PDF has no separate title: its file name without the extension, then the section as cited
        assert (a.rule_id, a.cited_title) == ("kelmar-code#2-1", "kelmar_code 2.1")
    finally:
        await close_env(rt)


async def test_d436_the_cue_and_the_snapshot_take_the_claim_back_first():
    llm = _Backend()
    rt = await _show(llm)
    try:
        assert rt.pack.lang_pack.retraction_phrase == "Sorry, I take that back."
        a = await _red(rt, llm)
        cue = await utt.correction_cue(rt, a.alert_id)
        assert cue.text == "Take it back, then say: 'Sorry, I take that back. It supports normal joint comfort.'"
        bare = a.model_copy(update={"alert_id": "al_bare", "say_instead": None})
        await rt.save_alert(bare)
        assert (await utt.correction_cue(rt, "al_bare")).text == "Take it back, then say: 'Sorry, I take that back.'"
        assert (await rt.snapshot("host"))["market"]["retraction_phrase"] == "Sorry, I take that back."
    finally:
        await close_env(rt)


async def test_d439_the_snapshot_carries_the_alerts_lines_and_the_summary_marks_typed_lines():
    llm = _Backend()
    rt = await _show(llm)
    try:
        await speak(rt, "This tub has sixty capsules.")  # no alert: its line is not carried to the host
        a = await _red(rt, llm)
        host, op = await rt.snapshot("host"), await rt.snapshot("operator")
        assert [t["transcript_id"] for t in host["transcripts"]] == [a.transcript_id]
        assert a.transcript_id in {t["transcript_id"] for t in op["transcripts"]} and len(op["transcripts"]) == 2
        [row] = (await compute_stats(rt))["compliance_alerts"]
        assert row["typed"] is True and row["speech_end_to_shown_ms"] is not None  # an injected line has no speech end
        from app.models.session import Transcript

        [t] = [x for x in await rt.ctx.store.query(rt.path("transcripts"), Transcript) if x.transcript_id == a.transcript_id]
        await rt.ctx.store.put(rt.path("transcripts"), t.transcript_id, t.model_copy(update={"source": "mic"}))
        assert (await compute_stats(rt))["compliance_alerts"][0]["typed"] is False  # a spoken line
    finally:
        await close_env(rt)
