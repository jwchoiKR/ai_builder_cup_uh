"""Draft-verifier gate (proof-plan item 3): which seeded bad drafts pass the deterministic
`verify_answer`? If some do, an LLM draft verifier is worth building; this script measures the layers.

    uv run python scripts/eval_draft_verifier.py --cases draft_verifier_cases.jsonl --out ../docs/eval/draft-verifier.md

Pass lines for the full pipeline (later): bad drafts passing every layer 0, good drafts blocked <= 3%.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import REPO_DIR, get_settings  # noqa: E402
from app.logic.catalog import Catalog, DataPack  # noqa: E402
from app.logic.reflex import Reflex  # noqa: E402
from app.logic.verify import verify_answer  # noqa: E402
from app.models.agent_io import ComposerOutput  # noqa: E402


def load_cases(name: str) -> list[dict]:
    path = get_settings().data_path / "eval" / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_all(cases: list[dict]) -> list[dict]:
    pack = DataPack.load(get_settings().data_path)
    catalog, reflex = Catalog(pack), Reflex(pack.rules)
    rows = []
    for c in cases:
        out = ComposerOutput.model_validate(c["composer_output"])
        pid = c.get("product_id")
        multi = pid is None
        ok, errors = verify_answer(out, pack.passages, pid, multi=multi, reflex=reflex,
                                   not_approved_claims=catalog.not_approved_claims(pid) if pid else [])
        rows.append({"draft_id": c["draft_id"], "label": c["label"], "flaw": c.get("flaw"), "passed": ok,
                     "errors": errors, "answer": out.answer})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="draft_verifier_cases.jsonl")
    ap.add_argument("--out", type=Path, default=REPO_DIR / "docs/eval/draft-verifier.md")
    args = ap.parse_args()
    rows = check_all(load_cases(args.cases))
    bad = [r for r in rows if r["label"] == "bad"]
    good = [r for r in rows if r["label"] == "good"]
    bad_pass = [r for r in bad if r["passed"]]
    good_block = [r for r in good if not r["passed"]]
    lines = [
        "# Draft verifier gate: verify_answer alone", "",
        f"{dt.date.today().isoformat()} · `{args.cases}` · {len(bad)} bad and {len(good)} good drafts.", "",
        f"- Bad drafts that pass verify_answer: **{len(bad_pass)} / {len(bad)}**",
        f"- Good drafts that verify_answer blocks: **{len(good_block)} / {len(good)}**", "",
        "## Bad drafts that pass", "",
        *[f"- {r['draft_id']}: {r['flaw']} — \"{r['answer']}\"" for r in bad_pass], "",
        "## Good drafts that are blocked", "",
        *([f"- {r['draft_id']}: {'; '.join(r['errors'])} — \"{r['answer']}\"" for r in good_block] or ["- none"]),
    ]
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"bad passing verify_answer {len(bad_pass)}/{len(bad)}; good blocked {len(good_block)}/{len(good)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
