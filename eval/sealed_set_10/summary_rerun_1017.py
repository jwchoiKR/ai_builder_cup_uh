"""Set 10 rerun of 10/17 (main 826ae40, run P settings; X2 and X4 read for an English host), scored as summary10.py: natural lines only (12 contrived split_* lines reported apart as stress, user 10/15),
6 out-of-scope lines excluded (score10.py, user ruling 10/14). Ids and outcomes only, no sealed text.
Usage: python summary10.py <out.json>"""
import collections, json, sys
from pathlib import Path
S = Path(__file__).parent
EX = {"X1-31", "X4-37", "X2-31", "X2-37", "X3-23", "X3-40"}
CAT = {1: "skincare", 2: "skincare", 3: "food supplement", 4: "haircare"}
ARMS = {"P": "rerun 10/17, compliance Flash-Lite LOW (deployed setting), current main"}
cases = {}
for n in range(1, 5):
    for l in open(S / "onboarding10_stt" / f"live_X{n}.jsonl", encoding="utf-8"):
        c = json.loads(l); cases[c["case_id"]] = c
pct = lambda v, p: round(sorted(v)[min(len(v) - 1, int(p * len(v)))] / 1000, 1) if v else None
out = {"set": 10, "products": 4, "lines": len(cases), "runs": {}}
for arm, desc in ARMS.items():
    per, lines = [], []
    tot = collections.Counter(); lat = {"compliance_judge": [], "fact_checker": []}; fails = collections.Counter(); late = 0
    for n in range(1, 5):
        p = collections.Counter(); plat = {"compliance_judge": [], "fact_checker": []}
        for r in json.load(open(S / "results/rerun_1017" / f"P_X{n}.json", encoding="utf-8")):
            c = cases[r["id"]]; e = c["expected"]; al = r["alerts"]
            row = {"id": r["id"], "product": n, "lang": c.get("lang"), "risky": bool(e["risky"])}
            if r["id"] in EX:
                row["excluded"] = "fact not on the prompter or rule not in the product's regulation PDF"
            elif c["type"].startswith("split"):
                row["excluded"] = "stress line: one sentence cut into two audio clips on purpose"
                row["stress_outcome"] = "false alert" if (al and not e["risky"]) else "no alert"
            else:
                for call in r["calls"]:
                    if call["agent"] in plat and call["status"] == "ok":
                        plat[call["agent"]].append(call["latency_ms"])
                    if call.get("failure"):
                        fails[call["failure"]] += 1
                match = [a for a in al if e["risky"] and a["kind"] == e["kind"]]
                if e["risky"]:
                    p["risky"] += 1; p["caught"] += bool(match)
                    row["outcome"] = "detected" if match else "missed"
                    ms = [a["ms_to_shown"] for a in match if a.get("ms_to_shown") is not None]
                    if ms:
                        row["alert_ms"] = min(ms)
                        if min(ms) > 5000 and match[0]["kind"] == "fact":
                            late += 1; row["late_fact_alert"] = True
                else:
                    p["safe"] += 1; p["false"] += bool(al)
                    row["outcome"] = "false alert" if al else "no alert"
            lines.append(row)
        per.append({"product": n, "category": CAT[n], "violations": p["risky"], "detected": p["caught"],
                    "safe": p["safe"], "false_alerts": p["false"],
                    "compliance_call_p95_s": pct(plat["compliance_judge"], .95), "fact_call_p95_s": pct(plat["fact_checker"], .95)})
        tot.update(p)
        for k in lat: lat[k] += plat[k]
    out["runs"][arm] = {"setting": desc, "total": {
        "violations": tot["risky"], "detected": tot["caught"], "detection_pct": round(100 * tot["caught"] / tot["risky"], 1),
        "safe": tot["safe"], "false_alerts": tot["false"], "false_alert_pct": round(100 * tot["false"] / tot["safe"], 1),
        "compliance_call_s": {"p50": pct(lat["compliance_judge"], .5), "p95": pct(lat["compliance_judge"], .95), "n": len(lat["compliance_judge"])},
        "fact_call_s": {"p50": pct(lat["fact_checker"], .5), "p95": pct(lat["fact_checker"], .95), "n": len(lat["fact_checker"])},
        "failed_calls": dict(fails), "fact_alerts_after_5s": late,
        "detected_by_time": {k: sum(1 for l in lines if l.get("outcome") == "detected" and l.get("alert_ms") is not None and l["alert_ms"] <= v)
                             for k, v in (("within_5s", 5000), ("within_10s", 10000), ("within_20s", 20000))}},
        "per_product": per, **({"lines": lines} if arm == "P" else {})}
json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), indent=1, ensure_ascii=False)
for arm, r in out["runs"].items():
    print(arm, r["total"]); [print("  ", p) for p in r["per_product"]]
miss = [l["id"] for l in out["runs"]["P"]["lines"] if l.get("outcome") == "missed"]
print("P missed", miss, collections.Counter(l["lang"] for l in out["runs"]["P"]["lines"]))
