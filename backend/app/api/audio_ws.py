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
from ..providers.stt import phrases_from_glossary, risk_phrases, with_risk_phrases

log = logging.getLogger(__name__)
router = APIRouter()

INTERIM_MIN_GAP_MS = 300
_active: dict[str, WebSocket] = {}


def default_glossary(ctx, cat=None) -> dict:
    """§8.15 default glossary: brand, product names, ingredient names from key facts. D-230: `cat` is a session's
    own catalog (an onboarded release)."""
    from ..logic.catalog import Catalog

    cat = cat or Catalog(ctx.pack)
    terms = [{"term": cat.brand, "spoken_forms": []}]
    for p in cat.products:
        terms.append({"term": p.name, "spoken_forms": []})
        for key in p.key_facts:
            if key not in {"volume", "list_price", "live_price", "set_price", "ph", "pao_months",
                           "shelf_life_unopened_months", "made_in", "texture", "fragrance"}:
                terms.append({"term": key.replace("_", " "), "spoken_forms": []})
    return {"version": 0, "terms": terms}


async def glossary_phrases(ctx) -> list[str]:
    try:
        from ..pipelines.setup import current_glossary

        glossary = await current_glossary(ctx)
    except (ImportError, AttributeError):
        glossary = default_glossary(ctx)
    return phrases_from_glossary(glossary)


async def _send(ws: WebSocket, payload: dict) -> None:
    try:
        await ws.send_text(json.dumps(payload))
    except Exception:  # noqa: BLE001 - the client may already be gone
        pass


@router.websocket("/sessions/{session_id}/audio")
async def audio(ws: WebSocket, session_id: str) -> None:
    ctx = ws.app.state.ctx
    await ws.accept()
    stt = getattr(ctx, "stt", None)
    if stt is None:
        await _send(ws, {"type": "status", "state": "error", "message": "Speech-to-text is off (STT_PROVIDER=mock)."})
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

    # D-230: an onboarded product's show hints its own brand and names, not the shipped products'
    glossary = (phrases_from_glossary(default_glossary(ctx, rt.catalog)) if (await rt.load_session()).release_id
                else await glossary_phrases(ctx))
    risk = risk_phrases(rt.pack.rules.rules) if ctx.settings.STT_RISK_HINTS else []
    phrases = with_risk_phrases(glossary, risk)
    # D-186: which hints this run's streams use, visible in Cloud Logging
    log.info("stt phrase hints for %s: glossary %d, risk %d (STT_RISK_HINTS=%s, hints %s)", session_id, len(glossary),
             len(phrases) - len(glossary), ctx.settings.STT_RISK_HINTS,
             "on" if ctx.settings.STT_PHRASE_HINTS_ENABLED else "off")
    stream = stt.open(phrases, rt.pack.stt_language)  # D-142: the session's broadcast language
    await _send(ws, {"type": "status", "state": "listening", "phrases": len(phrases)})

    async def consume() -> None:
        last_interim = 0
        try:
            async for r in stream.results():
                if r.is_final:
                    try:
                        t = await rt.utterances.submit(r.text, source="mic", speech_end_at=r.speech_end_at)
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

    consumer = asyncio.create_task(consume(), name=f"stt-consume:{session_id}")
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes"):
                await stream.write(msg["bytes"])
            elif msg.get("text") and json.loads(msg["text"]).get("type") == "stop":
                break
    except WebSocketDisconnect:
        pass
    finally:
        if _active.get(session_id) is ws:
            del _active[session_id]
        await stream.close()
        try:
            await asyncio.wait_for(consumer, timeout=6)
        except (TimeoutError, asyncio.CancelledError):
            consumer.cancel()
        await _send(ws, {"type": "status", "state": "stopped"})
