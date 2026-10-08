"""D-347 probe (real model, costs ~14 Flash-Lite calls): the fact checker (Flash-Lite, LOW, seed 7) on a made-up release whose brochure holds
lists, v5 vs v8. One call per case and prompt. Output: per case, the claims (relation, cited sentence) and whether a
fact alert would show (a contradicted claim after code's provenance checks)."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
from app.agents.fact_checker import DROPS, FactChecker, FactInput, sentence_index  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.context import build_context  # noqa: E402
from app.logic.catalog import Catalog  # noqa: E402
from app.models.session import SwitchState  # noqa: E402
from app.onboarding.files import store  # noqa: E402
from app.onboarding.read import normalise  # noqa: E402
from app.onboarding.record import ProductRecord  # noqa: E402
from app.onboarding.release import save_release  # noqa: E402
from tests.test_onboarding import _record  # noqa: E402

BROCHURE = """Velmora Night Balm
Net volume: 50 mL, S$36.00
Apply a thin layer at night.
Not approved for children under 3 years.
NOT APPROVED: Cures eczema.
Do not say: heals scars in three days.
| Claim | Status |
| Removes wrinkles for good | NOT APPROVED |
TIDAK DILULUSKAN: Menghilangkan jerawat dalam sehari.
"""
CASES = [  # (case, host line as said live, must alert)
    ("record+file list: cures eczema", "This balm clears up eczema overnight, guys.", False),
    ("table row: removes wrinkles", "Honestly, it gets rid of your wrinkles for good, you'll see.", False),
    ("other language: clears acne in a day", "Your pimples will be gone in just one day, trust me.", False),
    ("Do not say: heals scars", "Scars heal in three days with this, seriously.", False),
    ("true fact, list present", "You get a nice big 50 ml jar.", False),
    ("wrong fact next to the list", "And you get a 30 ml jar, so it lasts a while.", True),
    ("real caution reversed", "Even your two-year-old can use it, no problem at all.", True),
]
BANNED = ("NOT APPROVED", "Do not say", "TIDAK DILULUSKAN", "Claims not approved")


async def main():
    root = Path(tempfile.mkdtemp())
    ev = [{"file": "brochure.txt", "locator": "line 5", "quote": "NOT APPROVED: Cures eczema."}]
    pev = [{"file": "brochure.txt", "locator": "line 2", "quote": "Net volume: 50 mL, S$36.00"}]
    rec, _ = normalise(ProductRecord.model_validate(_record(
        brand="Velmora", product_name="Night Balm", category="Cosmetic",
        not_approved_claims=[{"text": "Cures eczema.", "evidence": ev}],
        variants=[{"variant_id": "A", "name": "Night Balm 50 ml", "size_value": "50", "size_unit": "mL", "market": "sg",
                   "prices": [{"currency": "S$", "minor": 3600, "kind": "live", "market": "sg", "evidence": pev}],
                   "evidence": pev}],
        cautions=[{"text": "Not approved for children under 3 years.", "evidence": ev}])))
    store(root, "job1", "brochure.txt", BROCHURE.encode())
    rid = save_release(root, rec, "job1")
    out = {}
    for v in ("v5", "v8"):
        s = get_settings().model_copy(update={
            "ONBOARDING_DIR": str(root), "FACT_MODE": "docs", "FACT_RELATION": True, "FACT_PROMPT": v,
            "JUDGE_ARM": "single", "SINGLE_MODEL": "gemini-3.5-flash-lite", "SINGLE_THINKING": "MEDIUM",
            "SINGLE_FACTS_THINKING": "LOW", "JUDGE_SEED": "7", "STORE": "memory", "HEDGED_AGENTS": ""})
        ctx = build_context(s)
        pack, _ = ctx.pack_for(ctx.pack.market.market, ctx.pack.lang, rid)
        cat = Catalog(pack, rid)
        pid = cat.order[0]
        fc = FactChecker(ctx.llm, ctx.prompts[f"fact_relation_{v}"], cat)
        passages = [p for p in pack.passages if p.product_id == pid]
        for name, line, must in CASES:
            sink = []
            tok = DROPS.set(sink)
            try:
                res = await fc.run(FactInput(utterance=line, on_air=pid, switch=SwitchState(), promo=None,
                                             passages=passages, session_id="probe"), deadline_ms=30_000)
            finally:
                DROPS.reset(tok)
            raw = res.meta.get("raw") if res.meta else None
            claims = res.output.claims if res.output else []
            _, index = sentence_index(fc._source(FactInput(utterance=line, on_air=pid, switch=SwitchState(),
                                                           promo=None, passages=passages)))
            rows = [(c.verdict, c.quote) for c in claims]
            alert = any(c.verdict == "contradicted" for c in claims)
            banned_cite = any(c.verdict == "contradicted" and any(b in (c.quote or "") for b in BANNED) for c in claims)
            out.setdefault(name, {})[v] = {"status": res.status, "alert": alert, "banned_cite": banned_cite,
                                           "claims": rows, "dropped": [d["reason"] for d in sink], "must": must}
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
    print(json.dumps(out, ensure_ascii=False, indent=1))


asyncio.run(main())
