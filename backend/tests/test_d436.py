"""D-436: a red claim is taken back first. The language pack's retraction phrase comes before say_instead on the
correction cue, and the host screen gets the phrase with the market. Made-up lines only."""
from __future__ import annotations

from app.models.session import Alert
from app.pipelines import utterances as utt

from .judge_fakes import CREAM, close_env, make_env


async def _red(rt, say: str | None) -> Alert:
    a = Alert(alert_id=f"al_{len(say or '')}", kind="compliance", status="active", transcript_id="t_1",
              product_id=CREAM, severity="HIGH", span="it treats eczema", say_instead=say, created_at=rt.now(),
              shown_at=rt.now())
    await rt.save_alert(a)
    return a


async def test_d436_the_cue_takes_the_claim_back_before_say_instead():
    rt, _ = await make_env()
    try:
        assert rt.pack.lang_pack.retraction_phrase == "Sorry, I take that back."
        a = await _red(rt, "Helps relieve the feeling of dryness.")
        cue = await utt.correction_cue(rt, a.alert_id)
        assert cue.text == "Take it back, then say: 'Sorry, I take that back. Helps relieve the feeling of dryness.'"
        b = await _red(rt, None)  # no say_instead: the phrase alone
        assert (await utt.correction_cue(rt, b.alert_id)).text == "Take it back, then say: 'Sorry, I take that back.'"
    finally:
        await close_env(rt)


async def test_d436_the_host_snapshot_carries_the_phrase():
    rt, _ = await make_env()
    try:
        snap = await rt.snapshot("host")
        assert snap["market"]["retraction_phrase"] == "Sorry, I take that back."
    finally:
        await close_env(rt)
