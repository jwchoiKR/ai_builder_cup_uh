"""Reply translation: a posted reply shown also in the language of the viewers who asked in another language.

Runs after the reply is posted, so it never delays it. Each language is translated once per message; the result is
kept only when it states exactly the reply's numbers (`faithful_numbers`)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..agents.reply_translator import TranslateInput, faithful_numbers

if TYPE_CHECKING:
    from .runtime import SessionRuntime

log = logging.getLogger(__name__)
REPLY_KINDS = frozenset({"ai_answer", "host_answer", "brand_answer"})
MAX_LANGUAGES = 4  # per message


def _same_language(a: str, b: str) -> bool:
    return a.split("-")[0].lower() == b.split("-")[0].lower() and ("hant" in a.lower()) == ("hant" in b.lower())


async def translate_reply(rt: "SessionRuntime", message_id: str) -> None:
    msg = await rt.get_message(message_id)
    if msg is None or msg.kind not in REPLY_KINDS or msg.state == "cancelled":
        return
    show_language = (await rt.load_session()).lang
    asked: dict[str, list[str]] = {}  # language -> the askers' comments in it
    for cid in msg.reply_to_comment_ids:
        c = await rt.get_comment(cid)
        if c is None or not c.language or _same_language(c.language, show_language):
            continue
        asked.setdefault(c.language, []).append(c.text)
    for language, comments in list(asked.items())[:MAX_LANGUAGES]:
        if language in msg.translations or (message_id, language) in rt.translating:
            continue
        rt.translating.add((message_id, language))
        try:
            res = await rt.reply_translator.run(
                TranslateInput(text=msg.text, language=language, comments=comments, session_id=rt.sid),
                deadline_ms=rt.settings.REPLY_TRANSLATION_TIMEOUT_MS)
            if res.status != "ok" or res.output is None:
                continue
            text = res.output.translation.strip()
            if not faithful_numbers(msg.text, text):
                log.info("translation of %s to %s dropped: empty or its numbers differ from the reply's", message_id, language)
                rt.counters["translations_dropped"] += 1
                continue
            async with rt.lock:
                current = await rt.get_message(message_id)
                if current is None or current.state == "cancelled" or current.text != msg.text:
                    continue
                current.translations[language] = text
                await rt.save_message(current)
                rt.counters["translations"] += 1
                await rt.emit("message.updated", current)
        finally:
            rt.translating.discard((message_id, language))
