"""D-355: a qualified re-say of the same test result may clear its TEST-QUALIFIER banner. The prompt addendum is an
arm (COMPLIANCE_RESAY, off until measured); the banner stays in ACTIVE_ALERTS while it is active, beyond the 3 newest
alerts. Made-up alerts."""
from __future__ import annotations

from app.agents.inputs import active_alerts_json
from app.logic.qualifier import RULE_ID as QUALIFIER
from app.models.session import Alert


def make_alert(aid: str, *, rule_id: str, created_at: int, status: str = "active") -> Alert:
    return Alert(alert_id=aid, kind="compliance", status=status, transcript_id="tr_1", product_id="p",
                 rule_id=rule_id, severity="MEDIUM", span="a claim", say_instead=None, created_at=created_at,
                 shown_at=created_at)


def test_d395_every_active_alert_is_sent_newest_first_with_its_product():
    """D-395 replaces D-355's 3 newest: every active or provisional compliance alert, newest first."""
    banner = make_alert("al_q", rule_id=QUALIFIER, created_at=1000)
    newer = [make_alert(f"al_{i}", rule_id="ASEAN-2D-DISEASE", created_at=2000 + i) for i in range(4)]
    rows = active_alerts_json([banner, *newer])
    assert [a["alert_id"] for a in rows] == ["al_3", "al_2", "al_1", "al_0", "al_q"]
    assert all("product_id" in a for a in rows)
    corrected = make_alert("al_q", rule_id=QUALIFIER, created_at=1000, status="corrected")
    assert "al_q" not in [a["alert_id"] for a in active_alerts_json([corrected, *newer])]


async def test_d355_the_resay_addendum_is_an_arm():
    from app.agents.split_judges import ComplianceJudge

    from .helpers import live_runtime, make_ctx
    from .judge_fakes import ScriptedBackend, close_env

    for on in (False, True):
        rt = await live_runtime(make_ctx(backend=ScriptedBackend(), COMPLIANCE_RESAY=on))
        try:
            judge = ComplianceJudge(rt.ctx.llm, rt.ctx.prompts, rt.catalog, rt.reflex)
            assert ("D-355 (Job 2, correction)" in judge.system_instruction) is on
            assert ("8 of 10 people" in judge.system_instruction) is on
        finally:
            await close_env(rt)
