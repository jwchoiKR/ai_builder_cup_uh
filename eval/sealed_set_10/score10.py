"""Pool 10 (selection set) score per arm, pre-registered: pooled counts over 4 products, per product reported only.
detection = a risky line caught by an alert of its labelled kind; false alert = any alert on a safe line;
wrong red = a compliance (red) alert on a line not labelled compliance. Judge time = one call, input to output.
    python score10.py <results dir>   (files <arm>_X<n>.json, cases in onboarding10_stt/live_X<n>.jsonl)"""
import json
import sys
from pathlib import Path

S = Path(__file__).parent
R = Path(sys.argv[1])
# LABEL_CHANGES 10/14: fact values not in the prompter are out of scope (user ruling)
EXCLUDE = {"X1-31", "X4-37", "X2-31", "X2-37", "X3-23", "X3-40"}  # + rules not in the HSA PDF
cases = {}
for n in range(1, 5):
    for line in open(S / "onboarding10_stt" / f"live_X{n}.jsonl", encoding="utf-8"):
        c = json.loads(line)
        cases[c["case_id"]] = c


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


for arm in sorted({p.name.split("_")[0] for p in R.glob("*_X*.json")}):
    tot = dict(risky=0, caught=0, safe=0, false=0, wrong_red=0)
    lat = {"compliance_judge": [], "fact_checker": []}
    fails = {}
    shown = []
    per = []
    for n in range(1, 5):
        f = R / f"{arm}_X{n}.json"
        if not f.exists():
            continue
        rows = json.loads(f.read_text(encoding="utf-8"))
        p = dict(risky=0, caught=0, safe=0, false=0, wrong_red=0)
        for r in rows:
            if r["id"] in EXCLUDE:
                continue
            c = cases[r["id"]]
            e = c["expected"]
            al = r["alerts"]
            if e["risky"]:
                p["risky"] += 1
                p["caught"] += any(a["kind"] == e["kind"] for a in al)
            else:
                p["safe"] += 1
                p["false"] += bool(al)
            if e.get("kind") != "compliance":
                p["wrong_red"] += any(a["kind"] == "compliance" for a in al)
            for a in al:
                if a.get("ms_to_shown") is not None:
                    shown.append(a["ms_to_shown"])
            for call in r["calls"]:
                if call["agent"] in lat and call["status"] == "ok":
                    lat[call["agent"]].append(call["latency_ms"])
                if call.get("failure"):
                    fails[call["failure"]] = fails.get(call["failure"], 0) + 1
        per.append((n, p))
        for k in tot:
            tot[k] += p[k]
    print(f"== arm {arm}: detection {tot['caught']}/{tot['risky']}, false alerts {tot['false']}/{tot['safe']}, "
          f"wrong red {tot['wrong_red']}, failures {fails or 0}")
    for n, p in per:
        print(f"   X{n}: detection {p['caught']}/{p['risky']}, false {p['false']}/{p['safe']}, wrong red {p['wrong_red']}")
    for k, v in lat.items():
        if v:
            print(f"   {k} call ms p50/p95/max {pct(v, .5)}/{pct(v, .95)}/{max(v)}  >5s {sum(x > 5000 for x in v)}/{len(v)}")
    if shown:
        print(f"   alert shown ms p50/p95/max {pct(shown, .5)}/{pct(shown, .95)}/{max(shown)}")
