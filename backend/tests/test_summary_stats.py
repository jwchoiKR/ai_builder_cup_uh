"""Summary statistics on a small recorded broadcast (DEV_SPEC §8.14, §14.1)."""
from __future__ import annotations

import json

from app.logic.summary_stats import compute_summary_stats
from app.models.session import (
    AgentCall,
    Alert,
    Comment,
    CommentAnalysis,
    Event,
    Message,
    QuestionGroup,
    Segment,
    Session,
    Transcript,
)

T0 = 1_790_000_000_000
CREAM, AMPOULE = "cream_hydra_barrier", "ampoule_deep_hydration"


def comment(cid, at, kind="question", visibility="visible"):
    return Comment(comment_id=cid, author_id=f"u_{cid}", author_name=cid, text="t", received_at=at, source="script",
                   kind=kind, visibility=visibility)


def group(gid, pid, q, authors, status):
    return QuestionGroup(group_id=gid, product_id=pid, intent="price", condition_slots={}, canonical_question=q,
                         member_comment_ids=[], unique_author_ids=authors, first_at=T0, last_at=T0, route="AUTO",
                         route_reason="intent", status=status)


def message(mid, gid, kind, state="published"):
    return Message(message_id=mid, kind=kind, text="t", group_id=gid, reply_to_comment_ids=[], reply_to_author_names=[],
                   citations=[], state=state, created_at=T0, published_at=T0, idempotency_key=mid)


def ev(seq, type_, at, payload):
    return Event(seq=seq, session_id="ses_1", type=type_, at=at, payload=payload)


def recorded_broadcast():
    session = Session(session_id="ses_1", runsheet_id="daon_skincare_demo", title="DAON LAB · Skincare session",
                      status="ended", started_at=T0, ended_at=T0 + 1_200_000, settings_snapshot={"STREAM_GRACE_SEC": 2},
                      created_at=T0)
    segments = [
        Segment(segment_id="seg_1", product_id=CREAM, order=1, started_at=T0, ended_at=T0 + 840_000,
                start_reason="session_start", planned_duration_sec=900, covered_point_ids=["cr-p1", "cr-p2", "cr-p3"]),
        Segment(segment_id="seg_2", product_id=AMPOULE, order=2, started_at=T0 + 840_000, ended_at=T0 + 1_200_000,
                start_reason="auto_speech", planned_duration_sec=600, covered_point_ids=["am-p1", "am-p3", "am-p5"]),
    ]
    comments = [
        comment("c1", T0 + 10_000),
        comment("c2", T0 + 20_000, "reaction"),
        comment("c3", T0 + 30_000, "hide", "hidden"),
        comment("c4", T0 + 841_000),  # 1 s after the switch: grace window -> cream
        comment("c5", T0 + 900_000),
        comment("c6", T0 + 950_000, "reaction"),
    ]
    analyses = [CommentAnalysis(analysis_id="an_1", comment_id="c1", output={}, product_basis="context", source="llm")]
    groups = [
        group("g_price", CREAM, "How much is it?", ["u1", "u2", "u3"], "auto_answered"),
        group("g_oily", CREAM, "Is it suitable for oily skin?", ["u4", "u5"], "answered"),
        group("g_dry", CREAM, "Is it suitable for dry skin?", ["u6"], "ready"),
        group("g_amp", AMPOULE, "Does the ampoule sting?", ["u7", "u8"], "needs_review"),
        group("g_rej", AMPOULE, "spam?", ["u9"], "rejected"),
        group("g_ship", None, "Do you ship to Malaysia?", ["u10"], "needs_review"),
    ]
    messages = [
        message("m1", "g_price", "ai_answer"),
        message("m2", "g_price", "ai_answer"),  # coalescing follow-up: the group still counts once
        message("m3", "g_oily", "host_answer"),
        message("m4", "g_dry", "host_answer", state="cancelled"),
        message("m5", None, "correction_notice"),
    ]
    transcripts = [
        Transcript(transcript_id="tr_7", text="wrinkles", is_final=True, speech_end_at=T0 + 300_000,
                   received_at=T0 + 300_000, source="injected", segment_id="seg_1"),
        Transcript(transcript_id="tr_9", text="x", is_final=True, speech_end_at=T0 + 400_000,
                   received_at=T0 + 400_000, source="mic", segment_id="seg_1"),
    ]
    alerts = [
        Alert(alert_id="al_1", kind="compliance", status="corrected", transcript_id="tr_7", product_id=CREAM,
              rule_id="ASEAN-3-SKIN-AGEING", severity="HIGH", span="your wrinkles will disappear overnight",
              created_at=T0 + 300_500, shown_at=T0 + 302_300, resolved_at=T0 + 309_100,
              corrected_text="Let me correct that."),
        Alert(alert_id="al_2", kind="compliance", status="dismissed", transcript_id="tr_9", product_id=CREAM,
              rule_id="BRAND-SUPERLATIVE", severity="MEDIUM", span="the best", created_at=T0 + 400_100,
              shown_at=T0 + 401_500),
        Alert(alert_id="al_3", kind="compliance", status="cleared", transcript_id="tr_9", product_id=CREAM,
              rule_id="ASEAN-3-SKIN-ACNE", severity="HIGH", created_at=T0 + 400_000),  # never shown
        Alert(alert_id="fx_1", kind="fact", status="corrected", transcript_id="tr_9", product_id=CREAM, field="price",
              stated_value="S$32", correct_value="S$36.00", created_at=T0 + 200_000, shown_at=T0 + 201_000,
              resolved_at=T0 + 213_000),
        Alert(alert_id="fx_2", kind="fact", status="active", transcript_id="tr_9", product_id=AMPOULE,
              field="ingredient_amount", stated_value="10% niacinamide", correct_value="4% niacinamide",
              created_at=T0 + 1_000_000, shown_at=T0 + 1_000_500),
    ]
    events = [
        ev(1, "session.started", T0, {}),
        ev(40, "promo.started", T0 + 600_000, {"promo_id": "promo_time_sale_10", "started_at": T0 + 600_000,
                                               "ends_at": T0 + 1_200_000}),
        ev(41, "promo.started", T0 + 610_000, {"promo_id": "promo_gift_pouch", "started_at": T0 + 610_000}),
        ev(55, "promo.ended", T0 + 700_000, {"promo_id": "promo_time_sale_10", "ended_at": T0 + 700_000}),
    ]
    calls = [AgentCall(call_id=f"call_{i}", agent=a, model="m", prompt_version="v", started_at=T0, latency_ms=ms,
                       status=st, input_hash="h", input_preview="p")
             for i, (a, ms, st) in enumerate([("utterance_judge", 1400, "ok"), ("utterance_judge", 1700, "ok"),
                                               ("utterance_judge", 2500, "timeout"), ("answer_composer", 3200, "ok")])]
    return dict(session=session, segments=segments, comments=comments, analyses=analyses, groups=groups,
                messages=messages, alerts=alerts, transcripts=transcripts, events=events, agent_calls=calls,
                counters={"instant_answers": 9, "composed_answers": 4}, triage_hits=5, triage_misses=11,
                now=T0 + 1_300_000)


def test_summary_numbers(catalog):
    s = compute_summary_stats(catalog=catalog, **recorded_broadcast())
    assert s["title"] == "DAON LAB · Skincare session" and s["duration_sec"] == 1200

    cream, amp = s["products"]
    assert (cream["product_id"], amp["product_id"]) == (CREAM, AMPOULE)  # run-sheet order
    assert cream["duration_sec"] == 840 and cream["planned_duration_sec"] == 900
    assert (cream["required_points_covered"], cream["required_points_total"]) == (2, 3)
    assert cream["missing_points"] == [{"point_id": "cr-p4",
                                        "text": "Patch tested: 0 of 32 reported reactions (in-house test)."}]
    assert cream["comments"] == 4 and cream["questions"] == 2  # c4 counts for the cream (grace window)
    assert cream["groups"] == 3
    assert cream["answered_groups"] == {"ai_answer": 1, "host_answer": 1, "brand_answer": 0}
    assert [g["canonical_question"] for g in cream["unanswered_groups"]] == ["Is it suitable for dry skin?"]
    assert amp["duration_sec"] == 360 and (amp["required_points_covered"], amp["required_points_total"]) == (3, 3)
    assert amp["comments"] == 2 and amp["questions"] == 1 and amp["groups"] == 2
    assert [(g["canonical_question"], g["unique_askers"]) for g in amp["unanswered_groups"]] == [
        ("Does the ampoule sting?", 2)]  # the rejected group is not "unanswered"
    assert [g["canonical_question"] for g in s["general_unanswered_groups"]] == ["Do you ship to Malaysia?"]

    al1, al2 = s["compliance_alerts"]
    assert al1["rule_id"] == "ASEAN-3-SKIN-AGEING" and al1["rule_title"].startswith("Prevents, reduces")
    assert al1["speech_end_to_shown_ms"] == 2300 and al1["shown_to_corrected_ms"] == 6800
    assert al1["corrected_text"] == "Let me correct that."
    assert al2["shown_to_corrected_ms"] == "dismissed" and "unverified" not in al2  # D-435: the field is gone
    assert len(s["compliance_alerts"]) == 2  # cleared provisional alert not listed
    assert (al1["typed"], al2["typed"]) == (True, False)  # D-439: a typed line, a spoken line

    fx1, fx2 = s["fact_alerts"]
    assert (fx1["field"], fx1["stated_value"], fx1["correct_value"], fx1["corrected"], fx1["time_to_correction_ms"]) == (
        "price", "S$32", "S$36.00", True, 12000)
    assert fx2["corrected"] is False and fx2["time_to_correction_ms"] is None
    # D-096: the compliance log's columns
    assert (fx1["shown_at"], fx1["shown_to_corrected_ms"]) == (T0 + 201_000, 12000)
    assert fx2["shown_to_corrected_ms"] == "uncorrected" and fx2["speech_end_to_shown_ms"] == 600_500

    sale, gift = s["promos"]
    assert sale == {"promo_id": "promo_time_sale_10", "title": "Time sale: extra 10% off", "started_at": T0 + 600_000,
                    "ended_at": T0 + 700_000, "duration_sec": 100}
    assert gift["ended_at"] is None and gift["duration_sec"] == 590  # still running at the end of the session

    # D-202: the timeout is not in the latency, but it is in the attempts, failures and deadline attainment
    assert s["agent_latency"]["utterance_judge"] == {
        "p50_ms": 1400, "p95_ms": 1700, "calls": 2, "attempts": 3, "failures": 1, "timeouts": 1,
        "failure_rate": 0.3333, "deadline_attainment": 0.6667}
    assert s["cache"] == {"instant_answers": 9, "composed_answers": 4, "triage_hits": 5, "triage_misses": 11}
    assert s["totals"]["comments"] == 6 and s["totals"]["hidden_comments"] == 1
    assert s["totals"]["messages_by_kind"]["ai_answer"] == 2 and s["totals"]["messages_by_kind"]["correction_notice"] == 1
    json.dumps(s)  # JSON-ready


def test_summary_while_live_uses_now(catalog):
    data = recorded_broadcast()
    data["session"] = data["session"].model_copy(update={"ended_at": None, "status": "live"})
    data["segments"][1] = data["segments"][1].model_copy(update={"ended_at": None})
    s = compute_summary_stats(catalog=catalog, **data)
    assert s["duration_sec"] == 1300 and s["products"][1]["duration_sec"] == 460
