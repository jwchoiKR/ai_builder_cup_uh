"""Why run P's fact checker was slow: per run, the fact calls' times next to their token counts, and the Gemini
service record for that night (gemini_monitoring_1014.json). Run: python eval/sealed_set_10/fact_latency.py"""
import json
from pathlib import Path
from statistics import median

S = Path(__file__).parent


def p95(xs):
    xs = sorted(xs)
    return xs[max(0, -(-95 * len(xs) // 100) - 1)]


print("Fact checker calls in the stored results (gemini-3.8-flash, thinking LOW)")
print(f"{'run':4} {'ok':>4} {'p50 s':>6} {'p95 s':>6} {'max s':>6} {'timeouts':>8} {'input tokens':>13} {'thinking tokens':>16}")
for run in "PBCD":
    ok, fails, inp, think = [], 0, [], 0
    for n in range(1, 5):
        for row in json.loads((S / "results/pool10" / f"{run}_X{n}.json").read_text(encoding="utf-8")):
            for c in row["calls"]:
                if c["agent"] != "fact_checker":
                    continue
                if c["status"] != "ok":
                    fails += 1
                    continue
                u = c.get("usage") or {}
                ok.append(c["latency_ms"])
                inp.append(u.get("prompt") or 0)
                think += u.get("thoughts") or 0
    print(f"{run:4} {len(ok):4} {median(ok) / 1000:6.1f} {p95(ok) / 1000:6.1f} {max(ok) / 1000:6.1f} {fails:8} "
          f"{min(inp)}-{max(inp):>6} {think:16}")

mon = json.loads((S / "gemini_monitoring_1014.json").read_text(encoding="utf-8"))
print("\nGemini service record, project of the runs, 10/14 (UTC hours; run P about 14:00-17:00)")
for model, hours in mon["models"].items():
    print(model)
    for h, v in hours.items():
        calls = v.get("calls_by_code", {})
        total = sum(calls.values())
        e504 = calls.get("504", 0)
        print(f"  {h[11:13]}:00  calls {total:5}  504 {e504:4} ({100 * e504 / total if total else 0:4.1f}%)  "
              f"server p50 {v.get('server_latency_p50_ms', 0) / 1000:7.1f} s")
