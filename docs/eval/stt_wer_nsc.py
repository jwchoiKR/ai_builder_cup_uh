"""chirp_3 word error rate on Singapore-accented read speech (IMDA NSC Part 1 sample), per language code.

    python stt_wer.py <audio_dir> <n> <code> [<code> ...]
Batch Recognize (region us), same model as production (chirp_3). Prints WER per code and saves raw results.
"""
import base64, concurrent.futures as cf, glob, json, os, re, subprocess, sys, time, urllib.request

DIR, N, CODES = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
TOKEN = subprocess.run("gcloud auth print-access-token", shell=True, capture_output=True, text=True).stdout.strip()
URL = "https://us-speech.googleapis.com/v2/projects/separk-cloocus/locations/us/recognizers/_:recognize"
NUM = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine"}


def norm(t):
    t = t.lower().replace("%", " percent")
    t = re.sub(r"\d", lambda m: " " + NUM[m.group(0)] + " ", t)
    t = re.sub(r"[^a-z' ]+", " ", t)
    return t.split()


def wer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)], len(r)


def recognize(path, code):
    body = {"config": {"autoDecodingConfig": {}, "languageCodes": [code], "model": "chirp_3",
                       "features": {"enableAutomaticPunctuation": True}},
            "content": base64.b64encode(open(path, "rb").read()).decode()}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.load(r).get("results", [])
                return " ".join(x["alternatives"][0].get("transcript", "") for x in res if x.get("alternatives"))
        except Exception as e:
            err = str(e); time.sleep(2)
    return f"<ERROR {err}>"


pairs = []
for j in sorted(glob.glob(os.path.join(DIR, "*.json"))):
    flac = j[:-5] + ".flac"
    if os.path.exists(flac):
        meta = json.load(open(j, encoding="utf-8"))
        pairs.append((flac, meta.get("read_text") or meta.get("original_text"), meta.get("SpeakerID")))
pairs = pairs[:N]
out = {}
for code in CODES:
    with cf.ThreadPoolExecutor(8) as ex:
        hyps = list(ex.map(lambda p: recognize(p[0], code), pairs))
    errs = toks = fails = 0
    rows = []
    for (flac, ref, spk), hyp in zip(pairs, hyps):
        if hyp.startswith("<ERROR"):
            fails += 1; rows.append({"file": os.path.basename(flac), "ref": ref, "hyp": hyp}); continue
        e, n = wer(ref, hyp); errs += e; toks += n
        rows.append({"file": os.path.basename(flac), "spk": spk, "ref": ref, "hyp": hyp, "errors": e, "words": n})
    out[code] = {"wer": round(errs / max(toks, 1), 4), "words": toks, "utterances": len(pairs) - fails, "errors": fails, "rows": rows}
    print(f"{code:12s} WER {out[code]['wer']*100:5.2f}%  utt {len(pairs)-fails}  failed {fails}", flush=True)
json.dump(out, open(os.path.join(DIR, "..", f"stt_wer_{os.path.basename(DIR.rstrip('/'))}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
