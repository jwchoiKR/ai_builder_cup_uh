# Comment-flow eval

2026-10-05 · `comment_flow_cases.jsonl` · 12 scenarios × 2 runs · real runtime per scenario, events replayed on the wall clock.

**FAIL** · kind 100.0% (100%; short or odd 100.0%) · must_not_merge 0 (0) · route 100.0% (100%) · stale or wrong posts 0 (0) · host answers before confirm 0 (0) · cache reuse 96.2% (100%)

Clustering (mean per scenario): pairwise precision 97.5%, recall 97.9%.

Parallelism: first comment to verified draft p50 4.5s, p95 5.9s; triage alone p50 1.3s, p95 1.6s.

| scenario | run | kind | route | pairs P/R | must_not_merge | stale/wrong | host early | cache |
|---|---|---|---|---|---|---|---|---|
| CF01 | 0 | 13/13 | 7/7 | 100%/100% | 0 | 0 | 0 | 2/2 |
| CF02 | 0 | 13/13 | 13/13 | 100%/100% | 0 | 0 | 0 | 3/3 |
| CF03 | 0 | 13/13 | 12/12 | 100%/100% | 0 | 0 | 0 | 2/2 |
| CF04 | 0 | 13/13 | 12/12 | 100%/100% | 0 | 0 | 0 | 3/3 |
| CF05 | 0 | 13/13 | 12/12 | 100%/100% | 0 | 0 | 0 | 1/1 |
| CF06 | 0 | 13/13 | 12/12 | 100%/100% | 0 | 0 | 0 | 1/1 |
| CF07 | 0 | 12/12 | 12/12 | 100%/100% | 0 | 0 | 0 | 0/0 |
| CF08 | 0 | 12/12 | 12/12 | 100%/100% | 0 | 0 | 0 | 0/0 |
| CF09 | 0 | 12/12 | 12/12 | 100%/100% | 0 | 0 | 0 | 4/4 |
| CF10 | 0 | 12/12 | 12/12 | 100%/83% | 0 | 0 | 0 | 3/4 |
| CF12 | 0 | 12/12 | 12/12 | 100%/100% | 0 | 0 | 0 | 4/4 |
| CF11 | 0 | 12/12 | 12/12 | 70%/100% | 0 | 0 | 0 | 2/2 |
| CF01 | 1 | 13/13 | 7/7 | 100%/100% | 0 | 0 | 0 | 2/2 |
| CF02 | 1 | 13/13 | 13/13 | 100%/100% | 0 | 0 | 0 | 3/3 |
| CF03 | 1 | 13/13 | 12/12 | 100%/100% | 0 | 0 | 0 | 2/2 |
| CF04 | 1 | 13/13 | 12/12 | 100%/83% | 0 | 0 | 0 | 3/3 |
| CF05 | 1 | 13/13 | 12/12 | 100%/100% | 0 | 0 | 0 | 1/1 |
| CF06 | 1 | 13/13 | 12/12 | 100%/100% | 0 | 0 | 0 | 1/1 |
| CF07 | 1 | 12/12 | 12/12 | 100%/100% | 0 | 0 | 0 | 0/0 |
| CF08 | 1 | 12/12 | 12/12 | 100%/100% | 0 | 0 | 0 | 0/0 |
| CF09 | 1 | 12/12 | 12/12 | 100%/100% | 0 | 0 | 0 | 4/4 |
| CF10 | 1 | 12/12 | 12/12 | 100%/83% | 0 | 0 | 0 | 3/4 |
| CF12 | 1 | 12/12 | 12/12 | 100%/100% | 0 | 0 | 0 | 4/4 |
| CF11 | 1 | 12/12 | 12/12 | 70%/100% | 0 | 0 | 0 | 2/2 |

## Problems

- CF10 run 0: c_set_sale: 2 drafts for one question (cache not reused)
- CF10 run 1: c_set_sale: 2 drafts for one question (cache not reused)
