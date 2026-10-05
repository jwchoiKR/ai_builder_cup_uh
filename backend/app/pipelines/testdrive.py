"""Judge test drive (D-238): a bundled fictional sample product is onboarded, approved with one click, and a short
scene plays on its show: a risky line and its spoken correction, a comment burst answered by AI with a citation, a
sensitive question the host answers aloud, a viewer's purchase for the AI PD. Built from the session's own catalog,
so nothing in it names a shipped product. Guarded by a rate cap.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)

SAMPLE_DIR = "onboarding_dev/p1_lumen_serum"  # fictional brand, every format incl. a label photo (D-216)
MAX_PER_HOUR = 6
_starts: list[float] = []
_running: set[str] = set()


class TestDriveBusy(Exception):
    pass


def allow_start(now: float | None = None) -> None:
    """At most MAX_PER_HOUR test drives per hour and one at a time per process (spend cap)."""
    now = now or time.time()
    _starts[:] = [t for t in _starts if now - t < 3600]
    if _running or len(_starts) >= MAX_PER_HOUR:
        raise TestDriveBusy("the test drive is busy; try again in a few minutes")
    _starts.append(now)


def sample_files(data_path: Path) -> list[tuple[str, bytes]]:
    folder = data_path / SAMPLE_DIR
    return [(p.name, p.read_bytes()) for p in sorted(folder.iterdir()) if p.is_file()]


def cache_key(files: list[tuple[str, bytes]]) -> str:
    return hashlib.sha256(b"".join(hashlib.sha256(b).digest() for _, b in files)).hexdigest()[:16]


def load_cached(root: Path, key: str) -> dict | None:
    path = root / "testdrive_cache" / f"{key}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def save_cached(root: Path, key: str, result: dict) -> None:
    folder = root / "testdrive_cache"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{key}.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    from ..onboarding.storage import persisted

    persisted(folder / f"{key}.json")  # D-263


def scene(rt) -> list[tuple[float, str, str, str]]:
    """(seconds from start, kind, author, text) for this session's product. Kinds: host, comment."""
    cat = rt.catalog
    p = cat.get_product(cat.order[0])
    word = p.name.split()[-1].lower() if p.name else "product"
    claim = (p.approved_claims[0] if p.approved_claims else "it feels light on the skin").rstrip(".*†")
    return [
        (0.0, "host", "Host", f"Hi everyone, welcome! Today we are looking at the {p.name}."),
        (5.0, "host", "Host", f"Honestly, this {word} erases wrinkles completely, guaranteed for everyone."),
        (12.0, "host", "Host", f"Sorry, let me correct that. {claim}."),
        (17.0, "comment", "Mei", "how much is it?"),
        (17.8, "comment", "Raj", "price pls"),
        (18.6, "comment", "Ana", "how much is this one?"),
        (21.0, "comment", "Siti", "can I use it while pregnant?"),
        (38.0, "host_answer", "Host", "Siti asked about pregnancy."),  # then the verified draft, read aloud
        (46.0, "comment", "Tom", "Just bought two, so excited!!"),
        (75.0, "end", "", ""),
    ]


async def play(rt) -> None:
    """Runs the scene on the live session in real time, then ends it (the reset)."""
    from .comments import submit_comment

    _running.add(rt.sid)
    t0 = time.monotonic()
    try:
        for at, kind, author, text in scene(rt):
            wait = at - (time.monotonic() - t0)
            if wait > 0:
                await asyncio.sleep(wait)
            if kind == "host":
                await rt.inject_transcript(text, scenario="testdrive")
            elif kind == "host_answer":
                # the host answers the waiting question aloud with its verified draft, so the answer is posted
                draft = None
                for g in await rt.groups():
                    if g.route == "HOST" and g.answer_id and g.published_message_id is None:
                        a = await rt.get_answer(g.answer_id)
                        if a is not None and a.verified:
                            draft = a.text
                            break
                await rt.inject_transcript(f"{text} {draft}" if draft else text, scenario="testdrive")
            elif kind == "comment":
                await submit_comment(rt, author_id=f"td_{author.lower()}", author_name=author, text=text,
                                     source="script", scenario="testdrive")
            else:
                await rt.end()
    except Exception:  # noqa: BLE001 - a test drive never takes the service down
        log.exception("test drive %s stopped", rt.sid)
    finally:
        _running.discard(rt.sid)
