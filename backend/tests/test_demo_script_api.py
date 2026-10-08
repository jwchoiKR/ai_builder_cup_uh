"""The whole demo script (data/demo/host_script.md) through the REST API on recorded fixtures:
the backend half of the end-to-end check (DEV_SPEC §14.4). Each scene's 'Expected' state is asserted."""
from __future__ import annotations

import httpx
import pytest

from app.clock import ManualClock
from app.main import create_app
from app.pipelines.demo_script import load_host_script
from app.scheduler import ManualScheduler

from .conftest import make_settings

CREAM, AMPOULE = "cream_hydra_barrier", "ampoule_deep_hydration"
LINE_GAP_MS = 8000  # judge, fact check, 2 s publish window, 5 s escalation


class Demo:
    def __init__(self, client: httpx.AsyncClient, scheduler: ManualScheduler) -> None:
        self.c, self.sched, self.sid = client, scheduler, ""
        self.state: dict = {}
        self.viewer: dict = {}

    async def refresh(self) -> dict:
        self.state = (await self.c.get(f"/sessions/{self.sid}/state", params={"role": "operator"})).json()
        self.viewer = (await self.c.get(f"/sessions/{self.sid}/state", params={"role": "viewer"})).json()
        return self.state

    async def ok(self, method: str, path: str, **kw) -> dict:
        r = await self.c.request(method, f"/sessions/{self.sid}{path}", **kw)
        assert r.status_code in (200, 201), r.text
        return r.json()

    async def line(self, text: str, scene: str, wait_ms: int = LINE_GAP_MS) -> dict:
        t = await self.ok("POST", "/transcripts", json={"text": text, "scene": scene})
        await self.sched.advance(wait_ms)
        await self.refresh()
        return t

    # ---- selectors ---------------------------------------------------------------------------------

    def segment(self) -> dict:
        return next(s for s in self.state["segments"] if s["ended_at"] is None)

    def groups(self, intent: str, product: str | None = "any") -> list[dict]:
        return [g for g in self.state["groups"] if g["intent"] == intent and (product == "any" or g["product_id"] == product)]

    def alerts(self, transcript_id: str) -> list[dict]:
        return [a for a in self.state["alerts"] if a["transcript_id"] == transcript_id]

    def messages(self, group: dict) -> list[dict]:
        return [m for m in self.state["messages"] if m["group_id"] == group["group_id"]]


@pytest.fixture
async def demo():
    clock = ManualClock()
    scheduler = ManualScheduler(clock)
    app = create_app(make_settings(), clock=clock, scheduler=scheduler)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api") as client:
        d = Demo(client, scheduler)
        d.sid = (await client.post("/sessions")).json()["session_id"]
        yield d
    app.state.ctx.runtimes.shutdown()
    scheduler.shutdown()


async def test_demo_script_end_to_end(demo: Demo):
    steps = load_host_script(str(make_settings().data_path))
    lines = {s.text: s for s in steps if s.action == "host_line"}
    L = [s.text for s in steps if s.action == "host_line"]

    # ---- S02 Start ---------------------------------------------------------------------------------
    await demo.ok("POST", "/start")
    await demo.sched.advance(3000)
    st = await demo.refresh()
    assert st["session"]["status"] == "live" and demo.segment()["product_id"] == CREAM
    assert st["prompter"]["next_product_id"] == AMPOULE
    t = await demo.line(L[0], "S02")
    assert not [a for a in demo.alerts(t["transcript_id"]) if a["status"] == "active"]
    await demo.line(L[1], "S02")
    assert "cr-p1" in demo.segment()["covered_point_ids"]
    await demo.line(L[2], "S02")
    assert "cr-p2" in demo.segment()["covered_point_ids"]
    assert demo.state["prompter"]["required_covered"] == 1 and demo.state["prompter"]["required_total"] == 3

    # ---- S03, S04 bursts ---------------------------------------------------------------------------
    for burst in ("B1", "B2"):
        await demo.ok("POST", f"/feed/burst/{burst}")
        await demo.sched.advance(15_000)
    await demo.refresh()
    [price] = demo.groups("price")
    assert price["status"] == "auto_answered" and len(price["unique_author_ids"]) == 4
    oily = next(g for g in demo.groups("suitability") if g["condition_slots"]["person_type"] == "oily")
    [makeup] = demo.groups("compatibility")
    assert len(oily["unique_author_ids"]) == 7 and len(makeup["unique_author_ids"]) == 4
    assert {s["group_id"] for s in demo.state["host_slots"]} >= {oily["group_id"], makeup["group_id"]}

    # ---- S05 host answers: pending 2 s, then posted as Host answer; the card leaves --------------
    await demo.ok("POST", "/transcripts", json={"text": L[3], "scene": "S05"})
    await demo.sched.advance(1000)
    await demo.refresh()
    pending = [m for m in demo.state["messages"] if m["kind"] == "host_answer"]
    assert pending and pending[0]["state"] == "pending" and pending[0]["group_id"] == oily["group_id"]
    await demo.sched.advance(LINE_GAP_MS)
    await demo.refresh()
    [host_answer] = [m for m in demo.state["messages"] if m["kind"] == "host_answer"]
    assert host_answer["state"] == "published" and "Raj" in host_answer["reply_to_author_names"]
    assert oily["group_id"] not in {s["group_id"] for s in demo.state["host_slots"]}
    assert any(m["kind"] == "host_answer" for m in demo.viewer["messages"])

    # ---- S06 fact error and correction ---------------------------------------------------------
    t = await demo.line(L[4], "S06")
    [fx] = [a for a in demo.alerts(t["transcript_id"]) if a["kind"] == "fact"]
    assert fx["status"] == "active" and fx["field"] == "price" and fx["correct_value"] == "S$36.00"
    assert fx["stated_value"].replace(".00", "") == "S$32"
    await demo.line(L[5], "S06")
    fx = next(a for a in demo.state["alerts"] if a["alert_id"] == fx["alert_id"])
    assert fx["status"] == "corrected"

    # ---- S07 compliance: full screen HIGH, escalation, correction ----------------------------------
    t = await demo.line(L[6], "S07")
    [al] = [a for a in demo.alerts(t["transcript_id"]) if a["kind"] == "compliance" and a["status"] == "active"]
    assert al["rule_id"] == "ASEAN-3-SKIN-AGEING" and al["severity"] == "HIGH" and al["say_instead"]
    assert al["shown_at"] - t["speech_end_at"] <= 5000
    assert al["escalated_at"] is not None  # not corrected within 5 s
    await demo.line(L[7], "S07")
    al = next(a for a in demo.state["alerts"] if a["alert_id"] == al["alert_id"])
    assert al["status"] == "corrected" and al["corrected_text"] == L[7]
    assert "cr-p3" in demo.segment()["covered_point_ids"]

    # ---- S08 negation: no full-screen alert --------------------------------------------------------
    t = await demo.line(L[8], "S08")
    assert not [a for a in demo.alerts(t["transcript_id"]) if a["status"] == "active"]

    # ---- S09 sensitive burst and operator edit ----------------------------------------------------
    await demo.ok("POST", "/feed/burst/B3")
    await demo.sched.advance(12_000)
    await demo.refresh()
    [preg] = demo.groups("pregnancy_breastfeeding")
    assert preg["status"] == "ready" and demo.state["answers"][preg["answer_id"]]["verified"]  # D-113: to the host
    hidden = {c["author_id"] for c in demo.state["comments"] if c["visibility"] == "hidden"}
    assert {"u_spam1", "u_rude", "u_spam2"} <= hidden
    draft = demo.state["answers"][preg["answer_id"]]["text"]
    await demo.ok("POST", f"/groups/{preg['group_id']}/answer",
                  json={"text": draft.replace("Please", "Please do"), "origin": "operator_edit"})
    await demo.refresh()
    [brand] = [m for m in demo.messages(preg) if m["kind"] == "brand_answer"]
    assert brand["state"] == "published"
    assert next(g for g in demo.state["groups"] if g["group_id"] == preg["group_id"])["status"] == "answered"

    # ---- S10 points 3/3 ----------------------------------------------------------------------------
    await demo.line(L[9], "S10")
    assert "cr-p4" in demo.segment()["covered_point_ids"]
    assert demo.state["prompter"]["required_covered"] == 3

    # ---- S11 time sale ----------------------------------------------------------------------------
    await demo.ok("POST", "/promos/promo_time_sale_10/start")
    await demo.ok("POST", "/feed/burst/B4")
    await demo.sched.advance(10_000)
    await demo.refresh()
    sale = [m for m in demo.state["messages"] if m["kind"] == "ai_answer"
            and m["created_at"] >= demo.state["session"]["promo_started_at"]]
    assert any("S$32.40" in m["text"] for m in sale) and any("S$55.80" in m["text"] for m in sale)
    assert not any("S$36.00" in m["text"] for m in sale)

    # ---- S12 switch -------------------------------------------------------------------------------
    await demo.line(L[10], "S12")
    assert demo.segment()["product_id"] == CREAM
    r = await demo.ok("POST", "/feed/burst/B5")
    assert r["status"] == "armed"
    await demo.line(L[11], "S12")  # D-415: the transition that names the next product switches at once
    seg = demo.segment()
    assert seg["product_id"] == AMPOULE and seg["start_reason"] == "auto_speech"
    t = await demo.ok("POST", "/transcripts", json={"text": L[12], "scene": "S12"})
    await demo.sched.advance(6000)
    await demo.refresh()
    seg = demo.segment()
    assert {"am-p1", "am-p2"} <= set(seg["covered_point_ids"])
    assert not [a for a in demo.alerts(t["transcript_id"]) if a["kind"] == "fact"]
    assert all(g["product_id"] != CREAM for g in demo.state["groups"]
               if g["group_id"] in {s["group_id"] for s in demo.state["host_slots"]})
    await demo.sched.advance(17_000)  # B5 at the ampoule segment start
    await demo.refresh()
    comments = {c["text"]: c for c in demo.state["comments"]}
    analyses = demo.state["analyses"]
    how_much = analyses[comments["how much?"]["comment_id"]]
    assert how_much["product_id"] == CREAM and how_much["product_basis"] == "context"
    assert analyses[comments["is the cream fragrance free?"]["comment_id"]]["product_id"] == CREAM
    sting = next(g for g in demo.state["groups"] if comments["Does the ampoule sting?"]["comment_id"] in g["member_comment_ids"])
    assert sting["product_id"] == AMPOULE and (sting["route"], sting["status"]) == ("HOST", "ready")  # D-113

    # ---- S13 fact error on the ampoule -------------------------------------------------------------
    t = await demo.line(L[13], "S13")
    [fx] = [a for a in demo.alerts(t["transcript_id"]) if a["kind"] == "fact"]
    assert fx["field"] == "ingredient_amount" and fx["correct_value"] == "4% niacinamide"
    await demo.line(L[14], "S13")
    assert next(a for a in demo.state["alerts"] if a["alert_id"] == fx["alert_id"])["status"] == "corrected"

    # ---- S14 end ----------------------------------------------------------------------------------
    await demo.ok("POST", "/end")
    await demo.refresh()
    assert demo.state["session"]["status"] == "ended"
    assert len(lines) == 15
