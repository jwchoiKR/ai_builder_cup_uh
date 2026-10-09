"""Host microphone audio over WebSocket (DEV_SPEC §10.1-10.3).

Binary frames: 16 kHz mono 16-bit PCM (100 ms frames). Text frames from the server:
{"type": "status", "state": "listening" | "stopped" | "error", "message"?} and
{"type": "final", "text", "transcript_id"} for the mic indicator. One stream per session.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..pipelines.runtime import ActionError
from ..providers.stt import MAX_PHRASES, SttStatus, phrases_from_glossary

log = logging.getLogger(__name__)
router = APIRouter()

INTERIM_MIN_GAP_MS = 300
END_POLL_S = 1.0  # D-339 (review H14): how often an open mic checks that its show is still on
SHOW_ENDED = 4410  # close code: the show ended (the mic does not reconnect)
LATE_LOG_MS = 1_000  # D-339: the mic's audio this much later than its best is logged
_active: dict[str, WebSocket] = {}


def default_glossary(ctx, cat=None) -> dict:
    """§8.15 default glossary: brand, product names, ingredient names from key facts. D-230: `cat` is a session's
    own catalog (an onboarded release)."""
    from ..logic.catalog import Catalog

    cat = cat or Catalog(ctx.pack)
    if any(p.stt_terms for p in cat.products):  # a product read's STT terms already hold the brand and names
        return {"version": 0, "terms": [{"term": t, "spoken_forms": []} for p in cat.products for t in p.stt_terms]}
    terms = [{"term": cat.brand, "spoken_forms": []}]
    for p in cat.products:
        terms.append({"term": p.name, "spoken_forms": []})
        for key in p.key_facts:
            if key not in {"volume", "list_price", "live_price", "set_price", "ph", "pao_months",
                           "shelf_life_unopened_months", "made_in", "texture", "fragrance"}:
                terms.append({"term": key.replace("_", " "), "spoken_forms": []})
    return {"version": 0, "terms": terms}


def release_phrases(ctx, cat, release_id: str) -> list[str]:
    """A release's show hints the product read's STT terms (else its brand and product names)."""
    return phrases_from_glossary(default_glossary(ctx, cat))


def phrases_for_release(ctx, release_id: str, mode: str | None = None, market: str | None = None,
                        lang: str | None = None) -> list[str]:
    """D-327 eval hook: exactly the phrase hints a one-release show's speech stream sends (the mic and the test
    drive), before the language check (an "auto" stream sends none). `mode` stays for the eval's --mode base."""
    from ..logic.catalog import Catalog

    pack, _ = ctx.pack_for(market or ctx.settings.MARKET, lang or ctx.settings.BROADCAST_LANGUAGE, release_id)
    return release_phrases(ctx, Catalog(pack, release_id), release_id)[:MAX_PHRASES]


async def glossary_phrases(ctx) -> list[str]:
    return phrases_from_glossary(default_glossary(ctx))


async def _send(ws: WebSocket, payload: dict) -> None:
    try:
        await ws.send_text(json.dumps(payload))
    except Exception:  # noqa: BLE001 - the client may already be gone
        pass


# D-316: the mic's speech-recognition language (?lang=), chirp_3 codes that opened a stream in region us (10/7).
# Anything else uses the session's language. "auto" (code-switching) takes no phrase hints: it answers 404 with them.
STT_CHOICES = frozenset({"en-US", "ko-KR", "ja-JP", "cmn-Hans-CN", "cmn-Hant-TW", "id-ID", "ms-MY", "th-TH", "vi-VN",
                         "fil-PH", "auto"})


async def stream_setup(ctx, rt, asked: str = "") -> tuple[list[str], str]:
    """A speech stream's phrase hints and language code for this session (the mic, and the test drive's voice)."""
    session_id = rt.sid
    # D-230: an onboarded product's show hints its own brand and names, not the shipped products'
    s = await rt.load_session()
    if s.release_ids:  # D-279: every release's hints, the product on air first
        seg = await rt.current_segment()
        on_air = rt.pack.releases.get(seg.product_id) if seg else None
        ordered = sorted(s.release_ids, key=lambda r: r != on_air)
        glossary = list(dict.fromkeys(x for r in ordered for x in release_phrases(ctx, rt.catalog, r)))
    else:
        glossary = (release_phrases(ctx, rt.catalog, s.release_id) if s.release_id else await glossary_phrases(ctx))
    phrases = glossary[:MAX_PHRASES]  # D-186: chirp_3's cap
    # D-186: which hints this run's streams use, visible in Cloud Logging
    log.info("stt phrase hints for %s: glossary %d (hints %s)", session_id, len(phrases),
             "on" if ctx.settings.STT_PHRASE_HINTS_ENABLED else "off")
    # D-142: the session's broadcast language (STT_LANGUAGE overrides); D-316: the mic's choice first
    language = asked if asked in STT_CHOICES else (ctx.settings.STT_LANGUAGE or rt.pack.stt_language)
    if language == "auto":
        phrases = []
    log.info("stt language for %s: %s (asked %r, hints %d)", session_id, language, asked, len(phrases))
    return phrases, language


@router.websocket("/sessions/{session_id}/audio")
async def audio(ws: WebSocket, session_id: str) -> None:
    ctx = ws.app.state.ctx
    await ws.accept()
    stt = getattr(ctx, "stt", None)
    if stt is None:
        await _send(ws, {"type": "status", "state": "error", "message": "Speech-to-text is off in this environment."})  # D-337
        await ws.close(code=4400)
        return
    try:
        rt = await ctx.runtimes.get(session_id)
    except ActionError as e:
        await _send(ws, {"type": "status", "state": "error", "message": e.message})
        await ws.close(code=4404)
        return
    previous = _active.get(session_id)
    if previous is not None:  # one microphone per session: the newest wins
        await _send(previous, {"type": "status", "state": "stopped", "message": "Another microphone connected."})
        await previous.close(code=4409)
    _active[session_id] = ws

    phrases, language = await stream_setup(ctx, rt, ws.query_params.get("lang") or "")
    stream = stt.open(phrases, language)
    await _send(ws, {"type": "status", "state": "listening", "phrases": len(phrases), "lang": language})

    async def consume() -> None:
        last_interim = 0
        try:
            async for r in stream.results():
                if isinstance(r, SttStatus):  # D-339: a stall restart, and hearing again after it
                    await _send(ws, {"type": "status", "state": r.state})
                    continue
                if r.is_final:
                    try:
                        t = await rt.utterances.submit(r.text, source="mic", speech_end_at=r.speech_end_at)
                        log.info("stt final %s %s lang=%s", session_id, t.transcript_id, language)  # D-316
                        await _send(ws, {"type": "final", "text": r.text, "transcript_id": t.transcript_id})
                    except ActionError as e:  # e.g. not live yet: the line is not judged
                        await _send(ws, {"type": "final", "text": r.text, "transcript_id": None, "note": e.message})
                elif r.received_at - last_interim >= INTERIM_MIN_GAP_MS:
                    last_interim = r.received_at
                    await rt.emit("transcript.interim", {"text": r.text, "is_final": False, "source": "mic",
                                                         "received_at": r.received_at})
        except Exception as e:  # noqa: BLE001
            log.warning("speech results stopped: %s", e)
            await _send(ws, {"type": "status", "state": "error", "message": "Speech recognition stopped. Reconnecting…"})
            await ws.close(code=1011)

    async def watch_end() -> None:
        """D-339 (review H14): when the show ends, the mic's audio and its speech stream are closed."""
        while (await rt.load_session()).status != "ended":
            await asyncio.sleep(END_POLL_S)
        log.info("stt stream closed for %s: the show ended", session_id)
        await _send(ws, {"type": "status", "state": "stopped", "message": "The show ended."})
        await ws.close(code=SHOW_ENDED)

    consumer = asyncio.create_task(consume(), name=f"stt-consume:{session_id}")
    watcher = asyncio.create_task(watch_end(), name=f"stt-show-end:{session_id}")
    best: int | None = None
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes"):
                await stream.write(msg["bytes"])
            elif msg.get("text"):
                data = json.loads(msg["text"])
                if data.get("type") == "stop":
                    break
                if data.get("type") == "mark" and isinstance(data.get("t"), (int, float)):
                    # D-339: the mic's capture clock against ours; the smallest gap is the baseline, more is lateness
                    gap = ctx.clock.now_ms() - int(data["t"])
                    best = gap if best is None else min(best, gap)
                    late = gap - best
                    if (late > LATE_LOG_MS) != (getattr(stream, "client_late_ms", 0) > LATE_LOG_MS):
                        log.info("mic audio for %s %s: %d ms later than its best", session_id,
                                 "late" if late > LATE_LOG_MS else "on time again", late)
                    stream.client_late_ms = late
    except (WebSocketDisconnect, RuntimeError):  # RuntimeError: closed by watch_end while receiving
        pass
    finally:
        watcher.cancel()
        if _active.get(session_id) is ws:
            del _active[session_id]
        await stream.close()
        try:
            await asyncio.wait_for(consumer, timeout=6)
        except (TimeoutError, asyncio.CancelledError):
            consumer.cancel()
        await _send(ws, {"type": "status", "state": "stopped"})
