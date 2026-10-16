"""D-491 (user: "지금 Summary에서 이상 있는 부분은 실제 코드랑 매핑해서 나올 수 있도록 다 수정해야 함"): every Summary number
maps to what the code did. One made-up show whose numbers are counted by hand; the agent-name drift guard; the recap
prompt's v2 rules."""
from __future__ import annotations

import re
from pathlib import Path

from app.logic.summary_stats import compute_summary_stats
from app.models.session import AgentCall, Alert, Comment, Message, QuestionGroup, Segment, Session, Transcript
from app.providers.llm import DEADLINE_AGENTS, NO_DEADLINE_AGENTS

from .judge_fakes import close_env
from .test_d450 import _Backend, _show

APP = Path(__file__).resolve().parents[1] / "app"


def _stats(catalog):
    item = sorted(catalog.runsheet.items, key=lambda i: i.order)[0]
    pid, required = item.product_id, list(item.required_point_ids)
    session = Session.model_construct(session_id="ses_1", runsheet_id="rs", title="T", status="ended", started_at=0,
                                      ended_at=600_000, settings_snapshot={"STREAM_GRACE_SEC": 2})
    seg = Segment.model_construct(segment_id="seg_1", product_id=pid, order=1, started_at=0, ended_at=600_000,
                                  start_reason="session_start", planned_duration_sec=600,
                                  covered_point_ids=required[:1])
    comments = [
        Comment.model_construct(comment_id="c1", author_id="u1", author_name="A", text="q1", received_at=10_000,
                                source="viewer", visibility="visible", kind="question"),
        Comment.model_construct(comment_id="c2", author_id="u2", author_name="B", text="q2", received_at=20_000,
                                source="viewer", visibility="visible", kind="question"),
        Comment.model_construct(comment_id="c3", author_id="u3", author_name="C", text="spam", received_at=30_000,
                                source="viewer", visibility="hidden", kind="hide"),
    ]

    def group(gid, product, status):
        return QuestionGroup.model_construct(group_id=gid, product_id=product, status=status, canonical_question=gid,
                                             unique_author_ids=["u1"], intent="other")
    groups = [group("g_both", pid, "answered"), group("g_open", pid, "ready"), group("g_closed", pid, "closed"),
              group("g_gen_open", None, "new"), group("g_gen_closed", None, "closed")]
    messages = [Message.model_construct(message_id="m1", kind="ai_answer", group_id="g_both", state="published"),
                Message.model_construct(message_id="m2", kind="host_answer", group_id="g_both", state="published")]
    transcripts = [
        Transcript.model_construct(transcript_id="t_mic1", speech_end_at=100_000, source="mic"),
        Transcript.model_construct(transcript_id="t_typed", speech_end_at=150_000, source="injected"),
        Transcript.model_construct(transcript_id="t_mic2", speech_end_at=200_000, source="mic"),
    ]

    def alert(aid, kind, tid, shown):
        return Alert.model_construct(alert_id=aid, kind=kind, status="active", transcript_id=tid, product_id=pid,
                                     created_at=shown, shown_at=shown, resolved_at=None, rule_id=None, severity="HIGH",
                                     span="x", corrected_text=None, field="price", stated_value="1",
                                     correct_value="2")
    alerts = [alert("a1", "compliance", "t_mic1", 104_000),  # 4.0 s
              alert("a2", "compliance", "t_typed", 151_000),  # typed: not counted
              alert("a3", "fact", "t_mic2", 206_000)]  # 6.0 s

    def call(agent, status, ms):
        return AgentCall.model_construct(agent=agent, status=status, latency_ms=ms)
    calls = [call("prompter_judge", "ok", 1900), call("prompter_judge", "ok", 19_700),
             call("prompter_judge", "error", 300), call("compliance_judge", "ok", 1200),
             call("compliance_judge", "timeout", 60_000)]
    out = compute_summary_stats(session=session, segments=[seg], catalog=catalog, comments=comments, analyses=[],
                                groups=groups, messages=messages, alerts=alerts, transcripts=transcripts, events=[],
                                agent_calls=calls, counters={}, triage_hits=0, triage_misses=0, now=600_000)
    return out, pid, required


async def test_every_summary_number_equals_the_hand_count():
    rt = await _show(_Backend())  # a made-up two-product show, built as onboarding builds one
    try:
        s, pid, required = _stats(rt.catalog)
    finally:
        await close_env(rt)
    assert required  # the first product has a required point
    p = next(x for x in s["products"] if x["product_id"] == pid)
    assert (p["comments"], p["questions"], p["groups"]) == (3, 2, 3)  # received, hidden included
    assert p["answered_groups"] == {"ai_answer": 1, "host_answer": 1, "brand_answer": 0}
    assert p["answered_any"] == 1  # one group with an AI and a host answer counts once
    assert [g["group_id"] for g in p["unanswered_groups"]] == ["g_open"]
    assert [g["group_id"] for g in p["closed_groups"]] == ["g_closed"]
    assert (p["required_points_covered"], p["required_points_total"]) == (min(1, len(required)), len(required))
    assert [g["group_id"] for g in s["general_unanswered_groups"]] == ["g_gen_open"]
    assert [g["group_id"] for g in s["general_closed_groups"]] == ["g_gen_closed"]
    assert s["alerts_within_5s"] == {"mic_alerts": 2, "within_5s": 1, "share": 0.5}
    pj, cj = s["agent_latency"]["prompter_judge"], s["agent_latency"]["compliance_judge"]
    assert (pj["ok_calls"], pj["attempts"], pj["failures"]) == (2, 3, 1)
    assert pj["deadline_attainment"] is None and pj["deadline_ms"] is None  # no deadline, nothing waits on it
    assert pj["within_5s"] == round(1 / 3, 4)
    assert (cj["ok_calls"], cj["attempts"], cj["timeouts"], cj["deadline_attainment"], cj["within_5s"]) == (
        1, 2, 1, 0.5, 0.5)
    assert "deadline_ms" not in cj and "calls" not in cj
    assert s["agent_totals"] == {"ok_calls": 3, "attempts": 5, "failures": 2}


def test_every_agent_in_the_code_has_a_known_deadline_kind():
    names = set()
    for f in APP.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        names |= set(re.findall(r'agent="([a-z_]+)"', text))
        if f.parent.name == "agents":
            names |= set(re.findall(r'^\s+name = "([a-z_]+)"', text, re.M))
    names |= {"judge_single"}  # utterance_judge.py: agent="judge_single" if self.single else self.name
    assert names, "no agent names found"
    assert not DEADLINE_AGENTS & NO_DEADLINE_AGENTS
    assert names <= DEADLINE_AGENTS | NO_DEADLINE_AGENTS, names - DEADLINE_AGENTS - NO_DEADLINE_AGENTS


def test_the_recap_prompt_is_v2_with_the_reading_rules(prompts):
    p = prompts["broadcast_summary"]
    assert p.version == "broadcast_summary_v2"
    assert "Use agent_totals for the whole show." in p.system_instruction
    assert "deadline_attainment null means the agent has no deadline" in p.system_instruction
    assert "not detected as said" in p.system_instruction
