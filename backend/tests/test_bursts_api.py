"""P1 done-when: bursts B1-B4 produce the expected /state snapshots (DEV_SPEC §15, host_script S03,
S04, S09, S11). Uses the recorded fixtures in tests/fixtures/llm (scenario = scene id)."""
from __future__ import annotations

import httpx
import pytest

from app.clock import ManualClock
from app.main import create_app
from app.scheduler import ManualScheduler

from .conftest import make_settings

CREAM = "cream_hydra_barrier"


@pytest.fixture
async def api():
    clock = ManualClock()
    scheduler = ManualScheduler(clock)
    app = create_app(make_settings(), clock=clock, scheduler=scheduler)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api") as client:
        yield client, scheduler
    app.state.ctx.runtimes.shutdown()
    scheduler.shutdown()


async def burst(client, scheduler, sid, burst_id, seconds=15):
    r = await client.post(f"/sessions/{sid}/feed/burst/{burst_id}")
    assert r.status_code == 200, r.text
    await scheduler.advance(seconds * 1000)
    state = (await client.get(f"/sessions/{sid}/state", params={"role": "operator"})).json()
    viewer = (await client.get(f"/sessions/{sid}/state", params={"role": "viewer"})).json()
    return state, viewer


def by_question(state, intent, *, status=None):
    return [g for g in state["groups"] if g["intent"] == intent and (status is None or g["status"] == status)]


def replies_to(state, group):
    return [m for m in state["messages"] if m["group_id"] == group["group_id"] and m["state"] == "published"]


async def test_bursts_b1_to_b4(api):
    client, scheduler = api
    sid = (await client.post("/sessions")).json()["session_id"]
    assert (await client.post(f"/sessions/{sid}/start")).status_code == 200
    await scheduler.advance(5000)

    # ---- S03 / B1: reactions ignored, one price group answered once, set price separate -------
    state, viewer = await burst(client, scheduler, sid, "B1")
    texts = {c["comment_id"]: c for c in state["comments"]}
    reactions = [c for c in texts.values() if c["kind"] == "reaction"]
    assert {c["text"] for c in reactions} == {"So pretty! 💜", "love the packaging", "😍😍😍"}
    [price] = by_question(state, "price")
    assert price["product_id"] == CREAM and price["status"] == "auto_answered"
    assert sorted(price["unique_author_ids"]) == ["u_daniel", "u_kumar", "u_lee", "u_nur"]  # Lee repeats: still 4
    assert len(price["member_comment_ids"]) == 5
    price_replies = replies_to(state, price)
    assert price_replies and all("S$36.00" in m["text"] for m in price_replies)
    answered = {cid for m in price_replies for cid in m["reply_to_comment_ids"]}
    assert answered == set(price["member_comment_ids"])  # every asker so far got the reply
    assert all(m["kind"] == "ai_answer" for m in price_replies)
    [set_group] = by_question(state, "set_price")
    [set_reply] = replies_to(state, set_group)
    assert "S$62.00" in set_reply["text"]
    assert not any(m["reply_to_comment_ids"] and texts[m["reply_to_comment_ids"][0]]["kind"] == "reaction"
                   for m in state["messages"])
    assert state["metrics"]["instant_answers"] >= 1  # later askers answered without a new LLM call

    # ---- S04 / B2: grouping and host top 3 -----------------------------------------------------------
    state, viewer = await burst(client, scheduler, sid, "B2")
    suit = by_question(state, "suitability")
    oily = next(g for g in suit if g["condition_slots"].get("person_type") == "oily")
    dry = next(g for g in suit if g["condition_slots"].get("person_type") == "dry")
    assert len(oily["unique_author_ids"]) == 7 and oily["status"] == "ready" and oily["route"] == "HOST"
    assert dry["group_id"] != oily["group_id"]
    [makeup] = by_question(state, "compatibility")
    assert len(makeup["unique_author_ids"]) == 4 and makeup["status"] == "ready"
    on_host = [s["group_id"] for s in state["host_slots"]]
    # D-113: an AI-answered question with 3+ askers also waits there, to be read out on air
    assert [g for g in on_host if g in (oily["group_id"], makeup["group_id"])] == [oily["group_id"], makeup["group_id"]]
    for g in (oily, makeup):
        assert state["answers"][g["answer_id"]]["verified"]
    [fragrance] = by_question(state, "fragrance")
    assert fragrance["status"] == "auto_answered" and replies_to(state, fragrance)

    # ---- S09 / B3: sensitive questions go to the host (D-113); abuse hidden ----------------------
    state, viewer = await burst(client, scheduler, sid, "B3")
    [preg] = by_question(state, "pregnancy_breastfeeding")
    assert preg["status"] == "ready" and preg["route"] == "HOST" and len(preg["unique_author_ids"]) == 3  # D-113
    draft = state["answers"][preg["answer_id"]]
    assert draft["verified"] and {c["section"] for c in draft["citations"]} <= {"Cautions", "Frequently asked questions"}
    assert preg["group_id"] in [s["group_id"] for s in state["host_slots"]] and not replies_to(state, preg)
    [eczema] = by_question(state, "medical_condition")
    assert eczema["status"] == "needs_review"
    assert eczema["answer_id"] is None or not state["answers"][eczema["answer_id"]]["verified"]
    [ship] = by_question(state, "shipping")
    assert ship["status"] == "needs_review" and ship["answer_id"] is None
    hidden = {c["author_id"]: c for c in state["comments"] if c["visibility"] == "hidden"}
    assert set(hidden) >= {"u_spam1", "u_rude", "u_spam2"}
    assert hidden["u_spam1"]["hide_category"] == "link" and hidden["u_spam2"]["hide_category"] == "personal_info"
    assert not any(c["author_id"] in ("u_spam1", "u_rude", "u_spam2") for c in viewer["comments"])

    # ---- S11 / B4: time sale; price answers regenerated with promo prices ------------------------
    assert (await client.post(f"/sessions/{sid}/promos/promo_time_sale_10/start")).status_code == 200
    state, viewer = await burst(client, scheduler, sid, "B4")
    assert state["session"]["active_promo_id"] == "promo_time_sale_10"
    old = [g for g in state["groups"] if g["intent"] in ("price", "set_price", "promo") and g["closed_reason"] == "promo_changed"]
    assert {g["group_id"] for g in old} == {price["group_id"], set_group["group_id"]}
    new_price = [g for g in state["groups"] if g["intent"] in ("price", "promo") and g["status"] == "auto_answered"]
    new_set = [g for g in by_question(state, "set_price") if g["status"] == "auto_answered"]
    assert new_price and new_set
    assert all("S$32.40" in m["text"] for g in new_price for m in replies_to(state, g))
    assert all("S$55.80" in m["text"] for g in new_set for m in replies_to(state, g))
    stale = [m for m in state["messages"] if "S$36.00" in m["text"] and m["created_at"] > state["session"]["promo_started_at"]]
    assert stale == []
