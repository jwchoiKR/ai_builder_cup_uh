"""Prompt loading and rendering (DEV_SPEC §7.1).

- system instruction = text under `## SYSTEM INSTRUCTION` up to the next `---`, followed by the
  whole `## EXAMPLES` section (few-shot);
- user template = first fenced code block under `## USER MESSAGE TEMPLATE`;
- version = `(version ...)` on the first heading;
- `judge_single` is built from `utterance_judge.md` and `fact_checker.md` as its file describes.

The loader fails fast if a required section, the version, or a placeholder builder is missing.
"""
from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROMPT_NAMES = (
    "utterance_judge", "judge_single", "compliance_judge", "context_judge", "fact_checker", "fact_relation",
    "comment_triage", "comment_triage_batch", "answer_composer", "draft_verifier", "brief_agent",
    "broadcast_summary", "verifier",
)

# Rendered as plain text; every other placeholder must contain `_json` and is rendered as JSON.
STRING_PLACEHOLDERS = frozenset({
    "utterance_text", "comment_text", "canonical_question", "product_id",
    "product_id_at_comment_time_minus_grace", "full_document_text_with_section_headings",
})

_VERSION_RX = re.compile(r"\(version ([^)]+)\)")
_PLACEHOLDER_RX = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
_DATA_CLOSE_RX = re.compile(r"</(data)", re.IGNORECASE)
_EXAMPLE_RX = re.compile(r"^Example ([A-Z])\s*$")

# judge_single: facts value added to the utterance_judge examples A-F (D-010).
SINGLE_EXAMPLE_FACTS_REASON = "Facts not shown in this example."


class PromptError(ValueError):
    pass


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    system_instruction: str
    user_template: str
    placeholders: tuple[str, ...]

    def render(self, values: Mapping[str, Any]) -> str:
        """Fill every `{{name}}` in one pass, so values are never re-expanded."""
        missing = [p for p in self.placeholders if p not in values]
        if missing:
            raise PromptError(f"{self.name}: missing values for {missing}")
        return _PLACEHOLDER_RX.sub(lambda m: render_value(m.group(1), values[m.group(1)]), self.user_template)

    def render_cached(self, values: Mapping[str, Any], static_keys: Collection[str]) -> tuple[str, str]:
        """Move complete static data blocks first; return the full prompt and its cacheable prefix.

        Partition the template before rendering, so untrusted values cannot change block boundaries.
        Instructions and mixed/dynamic lines retain their original order in the suffix.
        """
        self.render(values)  # Keep the same missing-value validation as render().
        static, dynamic = [], []
        for line in self.user_template.splitlines(keepends=True):
            keys = _PLACEHOLDER_RX.findall(line)
            destination = static if (keys and set(keys) <= set(static_keys)
                                     and re.fullmatch(r'\s*<data\b[^>]*>.*</data>\s*', line)) else dynamic
            destination.append(line)
        render = lambda text: _PLACEHOLDER_RX.sub(
            lambda m: render_value(m.group(1), values[m.group(1)]), text)
        prefix = render("".join(static))
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        return prefix + render("".join(dynamic)), prefix


def render_value(name: str, value: Any) -> str:
    if name in STRING_PLACEHOLDERS:
        text = "null" if value is None else str(value)
    else:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    # Untrusted text must not close its <data> block (§3.4). `<\/` is still valid JSON.
    return _DATA_CLOSE_RX.sub(r"<\\/\1", text)


# ---- markdown parsing --------------------------------------------------------------------------


@dataclass
class _Section:
    heading: str  # full heading line, e.g. "## EXAMPLES (few-shot, ...)"
    lines: list[str]


@dataclass
class _ParsedFile:
    name: str
    version: str
    sections: list[_Section]

    def find(self, key: str) -> _Section | None:
        for s in self.sections:
            if s.heading[3:].strip().upper().startswith(key):
                return s
        return None

    def require(self, key: str) -> _Section:
        s = self.find(key)
        if s is None:
            raise PromptError(f"{self.name}.md: missing section '## {key}'")
        return s


def _parse_file(path: Path) -> _ParsedFile:
    if not path.is_file():
        raise PromptError(f"prompt file not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    first = next((ln for ln in lines if ln.startswith("# ")), None)
    m = _VERSION_RX.search(first or "")
    if m is None:
        raise PromptError(f"{path.name}: first heading has no '(version ...)'")
    sections: list[_Section] = []
    in_fence = False
    for ln in lines:
        if ln.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and ln.startswith("## "):
            sections.append(_Section(ln.strip(), []))
        elif sections:
            sections[-1].lines.append(ln)
    return _ParsedFile(path.stem, m.group(1).strip(), sections)


def _until_rule(lines: list[str]) -> str:
    """Section text up to the first `---` line outside a code fence."""
    out, in_fence = [], False
    for ln in lines:
        if ln.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and ln.strip() == "---":
            break
        out.append(ln)
    return "\n".join(out).strip()


def _first_fence(lines: list[str], where: str) -> str:
    start = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("```")), None)
    if start is not None:
        end = next((j for j in range(start + 1, len(lines)) if lines[j].lstrip().startswith("```")), None)
        if end is not None:
            return "\n".join(lines[start + 1:end]).strip()
    raise PromptError(f"{where}: no fenced code block")


def _examples_text(pf: _ParsedFile) -> str | None:
    s = pf.find("EXAMPLES")
    if s is None:
        return None
    return _until_rule(s.lines) or None


def _with_examples(system: str, examples: str | None) -> str:
    return system if not examples else f"{system}\n\n## EXAMPLES\n\n{examples}"


# ---- judge_single --------------------------------------------------------------------------------


@dataclass
class _Example:
    label: str
    preamble: str
    output: dict
    trailer: str

    def render(self, label: str | None = None) -> str:
        parts = [f"Example {label or self.label}"]
        if self.preamble:
            parts.append(self.preamble)
        parts.append("```json\n" + json.dumps(self.output, ensure_ascii=False, separators=(",", ":")) + "\n```")
        if self.trailer:
            parts.append(self.trailer)
        return "\n".join(parts)


def _split_examples(text: str, where: str) -> list[_Example]:
    examples: list[_Example] = []
    label, chunk = None, []

    def flush() -> None:
        if label is None:
            return
        try:
            start = next(i for i, ln in enumerate(chunk) if ln.strip().startswith("```json"))
            end = next(j for j in range(start + 1, len(chunk)) if chunk[j].strip().startswith("```"))
        except StopIteration:
            raise PromptError(f"{where}: Example {label} has no ```json block") from None
        try:
            output = json.loads("\n".join(chunk[start + 1:end]))
        except json.JSONDecodeError as e:
            raise PromptError(f"{where}: Example {label} JSON is invalid: {e}") from None
        examples.append(_Example(label, "\n".join(chunk[:start]).strip(), output, "\n".join(chunk[end + 1:]).strip()))

    for ln in text.splitlines():
        m = _EXAMPLE_RX.match(ln.strip())
        if m:
            flush()
            label, chunk = m.group(1), []
        else:
            chunk.append(ln)
    flush()
    if not examples:
        raise PromptError(f"{where}: no 'Example X' entries found")
    return examples


def _empty_judge_fields(reason: str) -> dict:
    return {
        "compliance": {"violations": []},
        "correction": {"corrects_alert_ids": []},
        "answer": {"utterance_type": "product_talk", "matched_group_id": None,
                   "is_answer": False, "consistent_with_suggested": False},
        "prompter": {"covered_point_ids": [], "covered_cue_ids": [],
                     "switch": {"is_transition": False, "is_quote": False,
                                "target_product_id": None, "confidence": "low"}},
        "reason": reason,
    }


def _build_judge_single(js: _ParsedFile, uj: _ParsedFile, fc: _ParsedFile) -> PromptTemplate:
    uj_system = _until_rule(uj.require("SYSTEM INSTRUCTION").lines)
    fc_system = _until_rule(fc.require("SYSTEM INSTRUCTION").lines)
    start = fc_system.find("What to check")
    if start < 0 or "Output rules" not in fc_system[start:]:
        raise PromptError("fact_checker.md: SYSTEM INSTRUCTION lacks 'What to check' ... 'Output rules'")
    combined = _first_fence(js.require("HOW TO BUILD THIS PROMPT").lines, "judge_single.md HOW TO BUILD")
    system = f"{uj_system}\n\n### Job 5. Product facts\n{fc_system[start:].strip()}\n\n{combined}"

    # Examples generated at load time from the two source files, so they never drift.
    uj_examples = _split_examples(_examples_text(uj) or "", "utterance_judge.md EXAMPLES")
    fc_examples = _split_examples(_examples_text(fc) or "", "fact_checker.md EXAMPLES")
    rendered = []
    for ex in uj_examples:
        ex.output = {**ex.output, "facts": {"claims": [], "reason": SINGLE_EXAMPLE_FACTS_REASON}}
        rendered.append(ex.render())
    by_label = {ex.label: ex for ex in fc_examples}
    next_label = ord(uj_examples[-1].label) + 1
    for src in ("A", "B"):
        ex = by_label.get(src)
        if ex is None:
            raise PromptError(f"fact_checker.md: Example {src} missing (needed by judge_single)")
        ex.output = {**_empty_judge_fields(ex.output.get("reason", "")), "facts": ex.output}
        rendered.append(ex.render(chr(next_label)))
        next_label += 1
    return _template(js, _with_examples(system, "\n\n".join(rendered)))


# ---- loading -----------------------------------------------------------------------------------


def _template(pf: _ParsedFile, system: str) -> PromptTemplate:
    if not system.strip():
        raise PromptError(f"{pf.name}.md: empty system instruction")
    user = _first_fence(pf.require("USER MESSAGE TEMPLATE").lines, f"{pf.name}.md USER MESSAGE TEMPLATE")
    placeholders = tuple(dict.fromkeys(_PLACEHOLDER_RX.findall(user)))
    if not placeholders:
        raise PromptError(f"{pf.name}.md: user template has no placeholders")
    return PromptTemplate(pf.name, pf.version, system, user, placeholders)


def load_prompts(prompts_dir: Path, builders: Collection[str]) -> dict[str, PromptTemplate]:
    parsed = {name: _parse_file(prompts_dir / f"{name}.md") for name in PROMPT_NAMES}
    prompts: dict[str, PromptTemplate] = {}
    for name, pf in parsed.items():
        if name == "judge_single":
            prompts[name] = _build_judge_single(pf, parsed["utterance_judge"], parsed["fact_checker"])
        elif name == "comment_triage_batch":  # the single-comment rules and examples, plus the batch rules
            ct = parsed["comment_triage"]
            system = (_until_rule(ct.require("SYSTEM INSTRUCTION").lines) + "\n\n"
                      + _until_rule(pf.require("SYSTEM INSTRUCTION").lines))
            prompts[name] = _template(pf, _with_examples(system, _examples_text(ct)))
        else:
            system = _until_rule(pf.require("SYSTEM INSTRUCTION").lines)
            prompts[name] = _template(pf, _with_examples(system, _examples_text(pf)))
    errors = []
    for t in prompts.values():
        for p in t.placeholders:
            if p not in builders:
                errors.append(f"{t.name}: no builder for {{{{{p}}}}}")
            if p not in STRING_PLACEHOLDERS and "_json" not in p:
                errors.append(f"{t.name}: {{{{{p}}}}} is neither a string nor a *_json placeholder")
    if errors:
        raise PromptError("; ".join(errors))
    return prompts
