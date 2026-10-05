"""BriefAgent (DEV_SPEC §7.7): STT glossary and prompter point drafts from one product sheet.
The operator reviews and confirms the result on /setup before it is used."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..logic.reflex import Reflex
from ..models.agent_io import BriefOutput
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from . import inputs

MAX_TERMS = 40
MAX_POINTS = 6
MAX_POINT_CHARS = 90


@dataclass
class BriefInput:
    product_id: str
    document_text: str
    scenario: str = "S01"


def post_validate(out: BriefOutput, product_id: str, document_text: str, reflex: Reflex,
                  max_points: int = MAX_POINTS, max_chars: int = MAX_POINT_CHARS) -> BriefOutput:
    """Drop terms the document does not contain and drafts that are too long or carry restricted
    wording; keep at most 40 terms and 6 points."""
    o = out.model_copy(deep=True)
    o.product_id = product_id
    doc = document_text.lower()
    seen: set[str] = set()
    terms = []
    for t in o.glossary:
        key = t.term.strip().lower()
        if not key or key in seen or key not in doc:
            continue
        seen.add(key)
        t.term = t.term.strip()
        t.spoken_forms = [s.strip() for s in t.spoken_forms if s.strip()][:3]
        terms.append(t)
    o.glossary = terms[:MAX_TERMS]
    o.prompter_points = [p for p in o.prompter_points
                         if 0 < len(p.text.strip()) <= max_chars and not reflex.scan(p.text)][:max_points]
    return o


class BriefAgent:
    name = "brief_agent"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate, reflex: Reflex, *, extra: str = "",
                 max_points: int = MAX_POINTS, max_chars: int = MAX_POINT_CHARS, model: str | None = None,
                 thinking: str | None = None) -> None:
        self.llm = llm
        self.prompt = prompt
        self.prompt_version = prompt.version
        # D-265: BRIEF_MODEL / BRIEF_THINKING (an override for the eval); a release brief adds its own rules
        spec = getattr(llm, "brief", None) or llm.quality
        self.model, self.thinking = model or spec.model, thinking or spec.thinking_level
        self.system_instruction = f"{prompt.system_instruction}\n\n{extra}" if extra else prompt.system_instruction
        self.max_points, self.max_chars = max_points, max_chars
        self.reflex = reflex

    async def run(self, inp: BriefInput, *, deadline_ms: int) -> AgentResult[BriefOutput]:
        user = self.prompt.render({
            "product_id": inputs.product_id(inp.product_id),
            "full_document_text_with_section_headings": inputs.full_document_text_with_section_headings(inp.document_text),
        })
        res = await self.llm.call(LLMRequest(
            agent=self.name, model=self.model, thinking_level=self.thinking,
            prompt_version=self.prompt_version, system_instruction=self.system_instruction,
            user_message=user, output_model=BriefOutput, deadline_ms=deadline_ms, session_id=None,
            mock_primary_text=inp.product_id, mock_scenario=inp.scenario,
            mock_fallback=lambda _: rule_based_brief(inp.product_id, inp.document_text, self.reflex),
            preview=f"brief {inp.product_id}",
        ))
        if res.output is not None:
            res.output = post_validate(res.output, inp.product_id, inp.document_text, self.reflex, self.max_points,
                                       self.max_chars)
        return res


# ---- rule-based fallback for unit tests (mock provider without a fixture) ----------------------

_TABLE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")
_HEADING = re.compile(r"^#{1,3}\s+(?:\d+\.\s+)?(.+?)\s*$")


def rule_based_brief(product_id: str, document_text: str, reflex: Reflex) -> dict:
    """Brand, product name and ingredient rows as terms; approved claims as point drafts."""
    lines = document_text.splitlines()
    terms: list[dict] = []
    section = ""

    def add(term: str, kind: str, src: str) -> None:
        if term and all(t["term"].lower() != term.lower() for t in terms):
            terms.append({"term": term, "kind": kind, "spoken_forms": [term.lower()], "source_section": src})

    # D-221: no brand literal; a "Brand: X" line names the brand, the first heading names the product
    brand = next((m.group(1).strip() for ln in lines if (m := re.match(r"\W*brand\W*:\s*(.+)", ln, re.I))), "")
    if brand:
        add(brand, "brand", "Product overview")
    title = next((m.group(1) for ln in lines if (m := _HEADING.match(ln)) and ln.startswith("# ")), "")
    add(title.replace(brand, "").strip() if brand else title.strip(), "product", "Product overview")
    points: list[dict] = []
    in_claims = False
    for ln in lines:
        if m := _HEADING.match(ln):
            section = m.group(1)
            in_claims = section.lower().startswith("approved on-air claims")
            if section.lower().startswith("claims not approved"):
                in_claims = False
            continue
        if section == "Key ingredients" and (m := _TABLE_ROW.match(ln)):
            name = m.group(1)
            if not name.lower().startswith(("ingredient", "---")):
                add(re.sub(r"\s*\(.*\)$", "", name), "ingredient", "Key ingredients")
        if in_claims and ln.startswith("- "):
            text = ln[2:].strip()
            if text.endswith("*"):
                text = text[:-1].rstrip().rstrip(".") + " (in-house test)."
            if len(text) <= MAX_POINT_CHARS and not reflex.scan(text):
                points.append({"text": text, "required": False, "source_section": "Approved on-air claims"})
    return BriefOutput(product_id=product_id, glossary=terms, prompter_points=points[:MAX_POINTS],
                       reason="rule-based").model_dump()
