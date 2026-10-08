"""D-358: the regulation ORIGINALS the live compliance judge reads, as they are (no rule JSON).

For the show's products, the sources of their rules point at the original documents: a market source's local file
(SG cosmetics: the ASEAN Appendix III PDF), or a law or brand pack's own uploaded files (the pack's onboarding job's
files.json). The model gets the files as parts of its cached prefix; code keeps each file's text only to check that a
cited quote is really in that original (provenance). The rule pack is read only to find which documents apply."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from ..config import REPO_DIR
from ..logic import qualifier

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Original:
    name: str  # the document name the model cites ("asean_cosmetic_claims_guideline_appendix_iii_2007.pdf")
    title: str
    source_id: str
    data: bytes
    mime: str
    text: str  # what code can read of it, for the quote check


def squash(text: str) -> str:
    """Letters and digits only, lower case: PDF text extraction splits and joins words ("pro ducts")."""
    return re.sub(r"[^0-9a-z]", "", text.casefold())


def _slug(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "-", text.casefold()).strip("-")


def citation_rule_id(doc: str, section: str) -> str:
    """The alert's rule id for a citation: the document's stem and the section, normalised ("asean-...-2007#3-b")."""
    return f"{_slug(Path(doc).stem)}#{_slug(section)}"


def _text(name: str, data: bytes) -> str:
    from ..onboarding.files import model_part
    from ..onboarding.sources import _code_text

    return _code_text(model_part(name, data))


def _local(source_id: str, title: str, file: str | None) -> list[Original]:
    path = REPO_DIR / file if file else None
    if path is None or not path.is_file():
        return []
    data = path.read_bytes()
    from ..onboarding.files import model_part

    part = model_part(path.name, data)
    return [Original(path.name, title, source_id, part.data, part.mime, _text(path.name, data))]


def _pack_files(source_id: str, root: Path) -> list[Original]:
    """A law or brand pack's originals: the files of the onboarding job that made it (`<root>/<job_id>/files.json`,
    read back from the bucket when needed). D-360: each way the lookup fails is logged with the path it tried."""
    from ..onboarding.files import model_part
    from ..onboarding.storage import ensure

    for folder in ("lawpacks", "brandpacks"):
        pack = root / folder / f"{source_id}.json"
        if not ensure(pack):
            continue
        job = json.loads(pack.read_text(encoding="utf-8")).get("job_id")
        if not job:
            log.warning("compliance originals: pack %s names no job_id (%s)", source_id, pack)
            return []
        index = root / job / "files.json"
        if not ensure(index):
            log.warning("compliance originals: pack %s: no %s (local or in the bucket)", source_id, index)
            return []
        out = []
        for e in json.loads(index.read_text(encoding="utf-8")):
            path = root / job / e["file"]
            if not ensure(path):
                log.warning("compliance originals: pack %s: file %s (%s) is missing", source_id, e["name"], path)
                continue
            data = path.read_bytes()
            part = model_part(e["name"], data)
            out.append(Original(e["name"], e["name"], source_id, part.data, part.mime, _text(e["name"], data)))
        return out
    log.warning("compliance originals: no law or brand pack %s under %s", source_id, root)
    return []


_LOADED: dict[tuple, tuple] = {}


def _load(sources: tuple, root: str) -> tuple[tuple[Original, ...], tuple[str, ...]]:
    """D-360: a complete result is kept; one with a source missing is looked up again next time (a file read back from
    the bucket later, or a pack approved after the first show), never cached as missing."""
    if (sources, root) in _LOADED:
        return _LOADED[(sources, root)]
    found, missing = [], []
    for sid, title, file in sources:
        docs = _local(sid, title, file) or _pack_files(sid, Path(root))
        if docs:
            found.extend(d for d in docs if d.name not in {x.name for x in found})
        else:
            missing.append(sid)
    out = (tuple(found), tuple(missing))
    if not missing:
        _LOADED[(sources, root)] = out
    return out


def originals_of_rules(rules, sources, onboarding_root: Path) -> tuple[tuple[Original, ...], tuple[str, ...]]:
    """The originals behind these rules (by their source ids), and the source ids that have no original."""
    wanted = {r.source_id for r in rules} - {qualifier.SOURCE_ID}
    by_id = {s.source_id: (s.source_id, s.title, s.file) for s in sources}
    return _load(tuple(sorted(by_id.get(sid, (sid, "", None)) for sid in wanted)), str(onboarding_root))


def originals_for(catalog, onboarding_root: Path, product_ids) -> tuple[tuple[Original, ...], tuple[str, ...]]:
    """The originals behind the rules of these products, and the source ids that have no original (logged)."""
    rules = catalog.rules_for(set(product_ids)) if catalog.pack.rule_products is not None else catalog.pack.rules.rules
    found, missing = originals_of_rules(rules, catalog.pack.rules.sources, onboarding_root)
    if missing:
        log.warning("compliance originals missing for sources %s: those rules' documents are not given to the judge",
                    list(missing))
    return found, missing
