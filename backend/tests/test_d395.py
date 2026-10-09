"""D-395: every active compliance alert reaches the judge's ACTIVE_ALERTS (was test_d355.py; D-427: the D-355 re-say
arm and the TEST-QUALIFIER banner are gone). Made-up alerts."""
from __future__ import annotations

from app.agents.inputs import active_alerts_json
from app.models.session import Alert


def make_alert(aid: str, *, rule_id: str, created_at: int, status: str = "active") -> Alert:
    return Alert(alert_id=aid, kind="compliance", status=status, transcript_id="tr_1", product_id="p",
                 rule_id=rule_id, severity="HIGH", span="a claim", say_instead=None, created_at=created_at,
                 shown_at=created_at)


def test_d395_every_active_alert_is_sent_newest_first_with_its_product():
    """D-395 replaces D-355's 3 newest: every active or provisional compliance alert, newest first."""
    oldest = make_alert("al_q", rule_id="ASEAN-3-SKIN-AGEING", created_at=1000)
    newer = [make_alert(f"al_{i}", rule_id="ASEAN-2D-DISEASE", created_at=2000 + i) for i in range(4)]
    rows = active_alerts_json([oldest, *newer])
    assert [a["alert_id"] for a in rows] == ["al_3", "al_2", "al_1", "al_0", "al_q"]
    assert all("product_id" in a for a in rows)
    corrected = make_alert("al_q", rule_id="ASEAN-3-SKIN-AGEING", created_at=1000, status="corrected")
    assert "al_q" not in [a["alert_id"] for a in active_alerts_json([corrected, *newer])]
