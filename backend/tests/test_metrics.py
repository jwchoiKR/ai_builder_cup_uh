from __future__ import annotations

from app.logic.metrics import compute_metrics, percentile
from app.models.session import AgentCall, Alert, Comment, Message, Transcript

T0 = 1_790_000_000_000


def tr(tid, end, source="injected", received=None):
    return Transcript(transcript_id=tid, text="x", is_final=True, speech_end_at=end,
                      received_at=received if received is not None else end, source=source, segment_id="seg_1")


def alert(aid, tid, shown, *, kind="compliance", status="active", rendered=None, resolved=None):
    return Alert(alert_id=aid, kind=kind, status=status, transcript_id=tid, product_id="cream_hydra_barrier",
                 rule_id="ASEAN-3-SKIN-AGEING", severity="HIGH", created_at=shown or T0, shown_at=shown,
                 host_rendered_at=rendered, resolved_at=resolved)


def call(agent, ms, status="ok"):
    return AgentCall(call_id=f"call_{agent}_{ms}_{status}", agent=agent, model="m", prompt_version="v",
                     started_at=T0, latency_ms=ms, status=status, input_hash="h", input_preview="p")


def msg(kind, state="published"):
    return Message(message_id=f"msg_{kind}_{state}", kind=kind, text="t", reply_to_comment_ids=[],
                   reply_to_author_names=[], citations=[], state=state, created_at=T0, idempotency_key=f"{kind}{state}")


def test_percentile_nearest_rank():
    assert percentile([], 0.5) is None
    assert percentile([5], 0.95) == 5
    assert percentile([1, 2, 3, 4], 0.5) == 2
    assert percentile(list(range(1, 21)), 0.95) == 19
    assert percentile([10, 1, 7], 0.95) == 10


def test_compute_metrics_full_shape():
    transcripts = [tr("tr_1", T0), tr("tr_2", T0 + 60_000), tr("tr_3", T0 + 90_000, "mic", T0 + 91_200)]
    alerts = [
        alert("al_1", "tr_1", T0 + 2_400, rendered=T0 + 2_480, status="corrected", resolved=T0 + 9_400),
        alert("al_2", "tr_2", T0 + 61_800, rendered=None),
        alert("al_3", "tr_1", None, status="cleared"),  # provisional only: not counted
        alert("fx_1", "tr_2", T0 + 61_000, kind="fact"),
    ]
    calls = [call("utterance_judge", 1400), call("utterance_judge", 1600), call("utterance_judge", 2500, "timeout"),
             call("comment_triage", 1200), call("comment_triage", 900, "invalid")]
    messages = [msg("ai_answer"), msg("ai_answer", "cancelled"), msg("host_answer"), msg("host_answer", "pending")]
    comments = [Comment(comment_id="cm_1", author_id="u", author_name="U", text="hi", received_at=T0, source="script")]
    m = compute_metrics(alerts=alerts, transcripts=transcripts, agent_calls=calls, messages=messages, comments=comments,
                        counters={"instant_answers": 12, "composed_answers": 3},
                        reply_latencies={"instant": [300, 500, 900], "composed": [8000]}, triage_hits=4, triage_misses=9)

    assert m["alert"] == {"last_server_ms": 1800, "last_render_ms": None, "server_p50_ms": 1800, "server_p95_ms": 2400,
                          "render_p50_ms": 2480, "render_p95_ms": 2480, "count": 2}
    assert m["correction"] == {"p50_ms": 7000, "p95_ms": 7000, "count": 1}
    assert m["agents"]["utterance_judge"] == {"p50_ms": 1400, "p95_ms": 1600, "max_ms": 1600,
                                              "ok": 2, "timeout": 1, "error": 0, "invalid": 0}
    assert m["agents"]["comment_triage"]["invalid"] == 1 and m["agents"]["comment_triage"]["p50_ms"] == 1200
    assert m["answers"] == {"instant": 12, "composed": 3, "median_reply_ms": {"instant": 500, "composed": 8000}}
    assert m["triage_cache"] == {"hits": 4, "misses": 9}
    assert m["messages_by_kind"] == {"ai_answer": 1, "host_answer": 1}
    assert m["stt_final_latency_ms"] == {"p50_ms": 1200, "p95_ms": 1200, "count": 1}
    # last alert has no render ack -> header falls back to its server latency
    assert m["header"] == {"alert_in_s": 1.8, "judge_p50_s": 1.4, "instant_answers": 12, "answers_total": 15}
    assert (m["instant_answers"], m["composed_answers"], m["triage_cache_hits"], m["triage_cache_misses"]) == (12, 3, 4, 9)


def test_header_prefers_render_latency_and_single_judge():
    transcripts = [tr("tr_1", T0)]
    alerts = [alert("al_1", "tr_1", T0 + 2_000, rendered=T0 + 2_150)]
    m = compute_metrics(alerts=alerts, transcripts=transcripts, agent_calls=[call("judge_single", 2100)], messages=[],
                        comments=[], counters={}, reply_latencies={}, triage_hits=0, triage_misses=0)
    assert m["header"]["alert_in_s"] == 2.1  # 2150 ms rounded to one decimal
    assert m["header"]["judge_p50_s"] == 2.1
    assert m["answers"]["median_reply_ms"] == {"instant": None, "composed": None}


def test_empty_metrics():
    m = compute_metrics(alerts=[], transcripts=[], agent_calls=[], messages=[], comments=[], counters={},
                        reply_latencies={}, triage_hits=0, triage_misses=0)
    assert m["alert"]["count"] == 0 and m["alert"]["last_server_ms"] is None
    assert m["header"] == {"alert_in_s": None, "judge_p50_s": None, "instant_answers": 0, "answers_total": 0}
    assert m["agents"] == {} and m["stt_final_latency_ms"]["count"] == 0
