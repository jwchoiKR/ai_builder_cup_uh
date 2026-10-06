"""The BriefAgent on an approved release (D-265): an STT glossary and prompter points for an onboarded product.

Before this, a release's show had the approved claims as prompter points (the first one required) and a glossary of
only its brand, product and four ingredient names, so new names had few phrase hints for speech-to-text. At approval
the BriefAgent now reads the release's record and its source files' readable text (any language) and writes
briefs/<release_id>.json, write-once like the release. A session from the release uses its glossary as phrase hints
and its points on the prompter; without a brief (a failure, or a release made before) nothing changes.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from ..agents.brief import BriefAgent, BriefInput
from ..models.agent_io import BriefOutput
from .record import ProductRecord, money_value
from .release import record_facts
from .storage import persisted

log = logging.getLogger(__name__)

MAX_POINTS = 10
MAX_POINT_CHARS = 140

ADDENDUM = """This is an onboarded product. DOCUMENT holds its approved record and the readable text of its source files,
in any language. The show's language is {lang}. These rules replace the counts and lengths above.
A. Glossary: every brand, product and short name, ingredient and key technical term as the files write it (original
spelling, any script), with `spoken_forms`: how a host says it in {lang}, and sound-alikes a speech recogniser may hear
instead. Up to 40 terms.
B. Prompter points, written in {lang}: the must-say items: the key approved claims with their qualifiers and test
conditions, the cautions the host must say, and the offers with their conditions. `required=true` for the cautions
and the qualified claims that must be said. At most {max_points} points, each at most {max_chars} characters. Never a
claim the record lists as not approved, and never a value the DOCUMENT does not state."""
# D-269 arm "terms" (blind brief grading: 0 of 17 offer points kept all their conditions)
OFFER_POINT_CHARS = 240
OFFER_POINTS = 3  # per offer, on top of MAX_POINTS
# D-269 patch (blind grading of "terms": one point said "combines with other offers" for "only with the spend gift";
# 4 points of 34-41 words were too dense to read aloud)
OFFER_RULE = """
D. Offers: for each line under "Offers", 2 or 3 points in this order, each with `source_section` "Offer <id>" (the id
in brackets on that line) and `required=true`: (1) what the viewer gets: the amount or price and any code; (2) when
and where: dates or duration, store or market, who qualifies; (3) the limits and what it does or does not combine
with. Leave out a point with nothing to say. Each point is one full spoken sentence of about 25 words or fewer. Write
dates, sizes and counts the way a host reads them aloud ("from 1 to 14 November", "two 30 ml tubes"), with no
slashes, abbreviations or symbols. Every term on the line appears in one of its points. Say what it combines with
exactly as the terms as written say; never widen it ("only with the spend gift" never becomes "with other offers").
Offer points do not count toward the {max_points} points above."""


def offer_misses(record: ProductRecord, points, lang: str, lexicon=None) -> list[str]:
    """D-269: each offer condition its points do not carry (its numbers, and half its words by their first five
    letters). Only when the record and the show share a language; the misses are logged, nothing is dropped.
    Numbers count in digits or, with `lexicon`, in words ("thirty"); a lone "1" is not checked, as "one" alone is not
    read as a number. ponytail: word stems, not meaning; a paraphrase can be reported as a miss."""
    if record.language.split("-")[0].lower() != lang.split("-")[0].lower():
        return []
    misses = []
    for o in record.offers:
        said = " ".join(p.text for p in points if p.source_section == f"Offer {o.offer_id}").lower()
        stems = {w[:5] for w in re.findall(r"[a-z]{4,}", said)}
        nums = set(re.findall(r"\d+", said)) | (lexicon.spoken_numbers(said) if lexicon is not None else set())
        for c in o.conditions:
            words = re.findall(r"[a-z]{4,}", c.lower())
            if (not set(re.findall(r"\d+", c)) - {"1"} <= nums
                    or sum(w[:5] in stems for w in words) < len(words) / 2):
                misses.append(f"{o.offer_id}: {c}")
    return misses


def release_document(record: ProductRecord, file_texts: list[tuple[str, str]] = (), offers: str = "sheet") -> str:
    """The record as a sheet with section headings, then each source file's readable text. D-269 `offers="terms"`:
    each offer line carries every term the fact checker gets (percent, dates, combinability, conditions, the terms as
    written) and its id."""
    lines = [f"# {record.product_name}", f"Brand: {record.brand}"]
    if record.short_names:
        lines.append("Also called: " + ", ".join(record.short_names))
    lines.append(f"Category: {record.category}")
    if record.ingredients:
        lines += ["", "## Key ingredients", "| Ingredient | Amount |", "|---|---|"]
        lines += [f"| {i.name} | {(i.amount_value or '') + ' ' + (i.amount_unit or '')} |".replace("  ", " ")
                  for i in record.ingredients]
    sections = (("Approved on-air claims", [c.text for c in record.approved_claims]),
                ("Test results", [f"{q.statement}{', ' + q.conditions if q.conditions else ''} ({q.qualifier})"
                                  for q in record.qualified_results]),
                ("Cautions", [c.text for c in record.cautions]),
                ("Offers", [f"[{k.removeprefix('offer-')}] {x.removeprefix('Offer: ')}" for k, x in record_facts(
                    record, lambda m: f"{money_value(m.currency, m.minor)} {m.currency}") if k.startswith("offer-")]
                 if offers == "terms" else
                 [o.title + "".join(f"; {c}" for c in o.conditions)
                  + (f"; {money_value(o.amount.currency, o.amount.minor)} {o.amount.currency}" if o.amount
                     else "") for o in record.offers]),
                ("How to use", [h.text for h in record.how_to_use]),
                ("Key facts", [k.text for k in record.key_facts]),
                ("Claims not approved", [c.text for c in record.not_approved_claims]))
    for title, items in sections:
        if items:
            lines += ["", f"## {title}", *(f"- {x}" for x in items)]
    for name, text in file_texts:
        if text.strip():
            lines += ["", f"## Source file {name}", text.strip()]
    return "\n".join(lines)


async def brief_release(llm, prompt, reflex, root: Path, release_id: str, record: ProductRecord, lang: str, *,
                        model: str | None = None, thinking: str | None = None, deadline_ms: int = 60_000,
                        offers: str = "sheet"):
    """(AgentResult, seconds) of the BriefAgent on a release. `model`/`thinking` override BRIEF_MODEL/BRIEF_THINKING
    (scripts/eval_brief.py); `offers` is BRIEF_OFFERS (D-269)."""
    from .sources import release_sources

    texts = [(p.doc, p.text) for p in release_sources(str(root), release_id)[1]]
    extra = ADDENDUM.format(lang=lang, max_points=MAX_POINTS, max_chars=MAX_POINT_CHARS)
    terms = offers == "terms"
    if terms:
        extra += OFFER_RULE.format(max_points=MAX_POINTS)
    agent = BriefAgent(llm, prompt, reflex, extra=extra,
                       max_points=MAX_POINTS + (OFFER_POINTS * len(record.offers) if terms else 0),
                       max_chars=MAX_POINT_CHARS, model=model, thinking=thinking,
                       offer_chars=OFFER_POINT_CHARS if terms else 0)
    t0 = time.perf_counter()
    res = await agent.run(BriefInput(product_id=release_id, document_text=release_document(record, texts, offers)),
                          deadline_ms=deadline_ms)
    if terms and res.output is not None:
        for miss in offer_misses(record, res.output.prompter_points, lang, reflex.lexicon):
            log.info("brief offer condition not in its points: %s | release=%s", miss, release_id)
    return res, round(time.perf_counter() - t0, 1)


def save_brief(root: Path, release_id: str, out: BriefOutput, models: str) -> Path:
    folder = root / "briefs"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{release_id}.json"
    path.write_text(json.dumps({"release_id": release_id, "model": models, "at": int(time.time() * 1000),
                                "brief": out.model_dump(mode="json")}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    persisted(path, create_only=True)  # D-263: write-once, like the release
    return path


def load_brief(root: Path, release_id: str) -> BriefOutput | None:
    path = root / "briefs" / f"{release_id}.json"
    if not path.is_file():
        return None
    return BriefOutput.model_validate(json.loads(path.read_text(encoding="utf-8"))["brief"])
