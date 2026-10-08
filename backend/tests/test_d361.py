"""D-361: fixes from the codex review of 4d4fd9f..5cfe8b2. Each test fails on the code before the fix."""
from __future__ import annotations

import asyncio
import json

import pytest

from app.models.session import Comment, Event, Session
from app.store.base import SESSIONS, sub
from app.store.firestore import FirestoreStore

from .fake_firestore import FakeFirestore


def _session(sid: str = "ses_1") -> Session:
    return Session.model_validate({"session_id": sid, "runsheet_id": "r", "title": "t", "status": "live",
                                   "created_at": 1})


async def test_d361_a_read_back_that_fails_part_way_serves_nothing_and_keeps_the_seq(monkeypatch):
    """1: the session reads but its events do not: no partial session is served (the event seq would restart and
    overwrite stored events); the call fails, and the next touch reads the whole session."""
    import app.store.firestore as fs

    from app.bus import EventBus
    from app.clock import ManualClock

    monkeypatch.setattr(fs, "READ_BACK_TRIES", 1)
    client = FakeFirestore()
    first = FirestoreStore(client=client)
    await first.put(SESSIONS, "ses_1", _session())
    for seq in (1, 2, 3):
        await first.put(sub("ses_1", "events"), f"{seq:010d}",
                        Event(seq=seq, session_id="ses_1", type="x", at=seq, payload={}))
    assert await first.flush(5)
    fresh = FirestoreStore(client=client)
    client.fail_streams[sub("ses_1", "events")] = 1
    with pytest.raises(RuntimeError, match="not serving it partially"):
        await fresh.get(SESSIONS, "ses_1", Session)
    assert fresh._data.get(SESSIONS, {}) == {}  # nothing half read
    bus = EventBus(fresh, ManualClock(0))
    assert await bus.last_seq("ses_1") == 3  # read back whole on the next touch
    assert (await bus.emit("ses_1", "y", {})).seq == 4


async def test_d361_a_flush_wakes_a_waiting_write_retry(monkeypatch):
    """2: a retry waiting on a long backoff tries again at once when the show ends or SIGTERM flushes."""
    import app.store.firestore as fs

    monkeypatch.setattr(fs, "RETRY_FIRST_SEC", 30.0)
    client = FakeFirestore()
    client.fail_next_commits = 1
    store = FirestoreStore(client=client)
    await store.put(sub("ses_1", "comments"), "cm_1", Comment(comment_id="cm_1", author_id="u", author_name="A",
                                                               text="hi", received_at=1, source="script"))
    await asyncio.sleep(0.05)  # the first commit fails; the writer now waits 30 s
    assert await store.flush(2)
    assert client.count(sub("ses_1", "comments")) == 1


def test_d361_the_quote_check_keeps_letters_of_every_script():
    """4: a Korean or Chinese quote is checked, not emptied."""
    from app.agents.originals import squash

    assert squash("질병의 치료 또는 예방을 표방하는 표현") == "질병의치료또는예방을표방하는표현"
    assert squash("不得宣称治疗疾病") == "不得宣称治疗疾病"
    assert squash("Pro ducts, 2.1!") == "products21"


def test_d361_two_packs_with_files_of_the_same_name_keep_both(tmp_path):
    """9: each pack's "regulation.pdf" is given to the judge; the later one is named with its pack."""
    from app.agents.originals import _load
    from app.onboarding.files import store

    from .helpers import text_pdf

    (tmp_path / "lawpacks").mkdir()
    for pack, job, text in (("law_sg_a_v1", "ja", "2.1 No cure claims."), ("law_sg_b_v1", "jb", "3 No safety promises.")):
        (tmp_path / "lawpacks" / f"{pack}.json").write_text(json.dumps({"pack_id": pack, "job_id": job}))
        store(tmp_path, job, "regulation.pdf", text_pdf(text))
    found, missing = _load((("law_sg_a_v1", "", None), ("law_sg_b_v1", "", None)), str(tmp_path))
    assert [d.name for d in found] == ["regulation.pdf", "law_sg_b_v1:regulation.pdf"] and missing == ()
    assert "safety" in found[1].text


async def test_d361_the_prompter_snapshot_and_blocks_hold_only_what_is_shown(catalog):
    """5: no caution behind "+N more", no test result, and no product or promo block with other facts."""
    from app.logic.prompter import prompter_passages

    from .test_d360 import _facts_alerts

    product = catalog.get_product("cream_hydra_barrier")
    texts = [p.text for p in prompter_passages(catalog, product.product_id)]
    assert not any(r.say in texts for r in product.qualified_results)
    assert sum(t in product.cautions for t in texts) == min(4, len(product.cautions))
    _, llm = await _facts_alerts("It's only thirty-two dollars today.")
    msg = llm.requests[-1].user_message
    assert '"volume"' not in msg and '"list_price"' not in msg  # the product block names the product only


async def test_d361_a_correction_the_model_lists_is_not_excluded_by_the_merge():
    """6: a correction merged with the line that raised the alert (no period, within the merge window) still counts
    when the judge lists the alert."""
    import re

    from app.providers.llm import RawReply

    from .helpers import live_runtime, make_ctx
    from .judge_fakes import ScriptedBackend, close_env, judge_output, split_part, violation

    claim, sorry = "Honestly it cures eczema", "sorry, I take that back."

    class Backend(ScriptedBackend):
        async def generate(self, req, timeout_ms):
            if req.agent == "compliance_judge" and "take that back" in req.mock_primary_text:
                block = re.search(r'<data name="ACTIVE_ALERTS">(.*?)</data>', req.user_message, re.S)
                ids = [a["alert_id"] for a in json.loads(block.group(1))] if block else []
                out = split_part("compliance_judge", judge_output(corrects=ids, utterance_type="correction"))
                return RawReply(json.dumps(out), model_version="scripted")
            return await super().generate(req, timeout_ms)

    llm = Backend()
    llm.judge(claim, violations=[violation("ASEAN-2D-DISEASE", "cures eczema")])
    rt = await live_runtime(make_ctx(backend=llm, CORRECTION_CHECK="judge"))
    try:
        await rt.inject_transcript(claim)
        await rt.ctx.scheduler.idle()
        await rt.inject_transcript(sorry)
        await rt.utterances.drain()
        await rt.ctx.scheduler.idle()
        alerts = [a for a in await rt.alerts() if a.rule_id == "ASEAN-2D-DISEASE" and a.status != "cleared"]
        assert alerts and all(a.status == "corrected" for a in alerts)
    finally:
        await close_env(rt)


async def test_d361_a_live_session_read_back_gets_its_timers_again():
    """8: a new process (a fresh runtime registry) re-arms the tick, a running promo's end and a HIGH alert's
    escalation."""
    from app.pipelines.runtime import Runtimes

    from .helpers import live_runtime, make_ctx
    from .judge_fakes import ScriptedBackend, close_env, speak, violation

    llm = ScriptedBackend()
    llm.judge("It cures eczema.", violations=[violation("ASEAN-2D-DISEASE", "cures eczema")])
    ctx = make_ctx(backend=llm, COMPLIANCE_ESCALATE_SEC=600)
    rt = await live_runtime(ctx)
    promo = rt.catalog.runsheet.promo_ids[0]
    await rt.start_promo(promo)
    await speak(rt, "It cures eczema.")
    [a] = [a for a in await rt.alerts() if a.kind == "compliance" and a.status == "active"]
    rt.shutdown()  # the old process's timers are gone
    assert not ctx.scheduler.has(rt.key(f"promo:{promo}")) and not ctx.scheduler.has(rt.key(f"escalate:{a.alert_id}"))
    fresh = await Runtimes(ctx).get(rt.sid)
    try:
        assert ctx.scheduler.has(fresh.key(f"promo:{promo}")) and ctx.scheduler.has(fresh.key("tick"))
        assert ctx.scheduler.has(fresh.key(f"escalate:{a.alert_id}"))
    finally:
        await close_env(fresh)


def test_d361_the_rule_json_judge_modes_do_not_start_in_production(monkeypatch):
    """11: JUDGE_MODE=split or single reads the rule JSON; outside the tests (and the mock provider) it refuses."""
    from .helpers import make_ctx

    monkeypatch.setattr("app.agents.split_judges.LEGACY_RULES", False)
    for mode in ("split", "single"):
        with pytest.raises(ValueError, match="production runs split3 only"):
            make_ctx(JUDGE_MODE=mode)
    make_ctx(JUDGE_MODE="split3").runtimes.shutdown()
