#!/usr/bin/env python3
"""Figure 2 on Gemini (14 October 2026): the arm that drew the Claude panels,
with every model swapped and the literature capped at the date of those runs.

The arm is `current` reading the first section of structured abstracts, which
is the fingerprint the Fig. 2a runs carry (ff136250f372, run in August 2026).
Opus 5 becomes gemini-4-argon at thinking level MEDIUM and Haiku 4.5 becomes
gemini-3.8-flash at LOW (scripts/298_gemini_pair_probe.py, which also supplies
the Gemini call the package cannot make yet). Each model expands its own
synonyms: two pipelines, each with its own search. PubMed is capped at
--max-date and the reading prompt is NOT told about the cap: no date note.

  python3 scripts/299_gemini_fig2_run.py --pilot 20 --out results/gemini_fig2/pilot
  python3 scripts/299_gemini_fig2_run.py --pairs PAIRS.tsv --out DIR --max-date 2026/08/14

--pilot N draws N/5 pairs per class (Definitive, Strong, Moderate, Limited,
Absent) from the 150 Fig. 2a pairs run on Claude in August
(benchmark/gencc_clingen_g2p/results/scored.tsv), seed 2026, and carries their
Claude verdict alongside. --pairs takes any table with gene and phenotype
columns. Writes DIR/pesto.tsv (one row per pair), DIR/summary.json and the
runs under DIR/runs; pairs already in DIR/pesto.tsv without error are skipped,
so an interrupted run resumes.
"""
from __future__ import annotations

import argparse
import collections
import csv
import importlib.util
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("PESTO_PROJECT_ROOT", ROOT)

_spec = importlib.util.spec_from_file_location("probe", os.path.join(HERE, "298_gemini_pair_probe.py"))
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

from pesto.flow import arms, run as flow_run, store  # noqa: E402
from pesto.flow.steps import FetchAbstracts  # noqa: E402
from pesto.flow.types import Query  # noqa: E402
from pesto.services import llm_service  # noqa: E402

FIG2A = os.path.join(ROOT, "benchmark", "gencc_clingen_g2p", "results", "scored.tsv")
CLASSES = ["Definitive", "Strong", "Moderate", "Limited", "Absent"]
FIG2_ARM = arms.CURRENT.but(hydrate=FetchAbstracts(sections="first"))
COLUMNS = ["gene", "phenotype", "truth", "claude_verdict", "verdict", "p_established", "p_existing",
           "p_hypothesized", "p_novel", "found", "read", "usd", "usd_2027", "seconds", "fingerprint",
           "error"]

LOCK = threading.Lock()
TOTALS = collections.defaultdict(lambda: collections.Counter())


def counted_call(prompt, model, temperature, max_retries, initial_delay):
    out = probe.call_gemini(prompt, model, temperature, max_retries, initial_delay)
    with LOCK:
        t = TOTALS[model]
        t["calls"] += 1
        t["input"] += out["input_tokens"]
        t["output"] += out["output_tokens"]
        t["thinking"] += out["thoughts"]
        t["empty"] += int(not (out.get("text") or "").strip())
    return out


def pilot_pairs(n):
    import random
    rows = list(csv.DictReader(open(FIG2A, encoding="utf-8"), delimiter="\t"))
    rng = random.Random(2026)
    out = []
    for cls in CLASSES:
        pool = sorted((r for r in rows if r["gencc_class"] == cls), key=lambda r: (r["gene"], r["phenotype"]))
        for r in rng.sample(pool, n // len(CLASSES)):
            out.append({"gene": r["gene"], "phenotype": r["phenotype"], "truth": cls,
                        "claude_verdict": r["lit_mean"]})
    return out


def table_pairs(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8"), delimiter="\t"))
    return [{"gene": r["gene"], "phenotype": r["phenotype"],
             "truth": r.get("truth") or r.get("gencc_class") or r.get("classification") or "",
             "claude_verdict": r.get("claude_verdict") or r.get("lit_mean") or ""} for r in rows]


def work(pair, arm, runs_dir):
    row = {k: "" for k in COLUMNS}
    row.update(pair)
    row["fingerprint"] = arm.fingerprint()
    started = time.time()
    try:
        res = flow_run.run(arm, Query(pair["gene"], pair["phenotype"]), runs_dir=runs_dir)
        store.save(res, runs_dir)
        v = res.verdict
        dist = v.distribution.as_dict() if v.distribution else {}
        row.update({"verdict": v.call, "found": res.counts.get("found", 0), "read": res.counts.get("read", 0),
                    "usd": probe.cost(res.trace, probe.PRICES)[1],
                    "usd_2027": probe.cost(res.trace, {**probe.PRICES, **probe.PRICES_LATER})[1],
                    **{f"p_{k.lower()}": dist.get(k, "") for k in ("Established", "Existing", "Hypothesized", "Novel")}})
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"[:300]
    row["seconds"] = round(time.time() - started, 1)
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pilot", type=int, default=0)
    ap.add_argument("--pairs", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-date", default="2026/08/14")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--arm", choices=["fig2", "prior"], default="fig2",
                    help="fig2: the literature arm of Fig. 2; prior: the model's internal knowledge, no articles")
    ap.add_argument("--panels", default="", help="keep only pairs of these panels (e.g. cd,a:Absent)")
    args = ap.parse_args()

    pairs = pilot_pairs(args.pilot) if args.pilot else table_pairs(args.pairs)
    if args.panels:
        rows = {(r["gene"], r["phenotype"]): r for r in csv.DictReader(open(args.pairs, encoding="utf-8"), delimiter="\t")}

        def wanted(p):
            r = rows[(p["gene"], p["phenotype"])]
            for spec in args.panels.split(","):
                panel, _, truth = spec.partition(":")
                if panel in r["panels"].split(",") and (not truth or r["truth"] == truth):
                    return True
            return False
        pairs = [p for p in pairs if wanted(p)]
    out = os.path.join(ROOT, args.out) if not os.path.isabs(args.out) else args.out
    runs_dir = os.path.join(out, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    table = os.path.join(out, "pesto.tsv")
    done = {}
    if os.path.exists(table):
        for r in csv.DictReader(open(table, encoding="utf-8"), delimiter="\t"):
            if not r["error"]:
                done[(r["gene"], r["phenotype"])] = r
    todo = [p for p in pairs if (p["gene"], p["phenotype"]) not in done]

    llm_service._call_gemini = counted_call
    base = FIG2_ARM if args.arm == "fig2" else arms.PRIOR
    arm = probe.on_gemini(base).using(max_date=args.max_date)
    assert not getattr(arm.read, "notes", ()), "the reading prompt must not carry a date note"
    print(f"{len(pairs)} pairs, {len(todo)} to run, arm {arm.fingerprint()}, max date {args.max_date}, "
          f"{args.workers} workers", flush=True)

    rows = list(done.values())
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(work, p, arm, runs_dir) for p in todo]
        for k, f in enumerate(as_completed(futures), 1):
            row = f.result()
            rows.append(row)
            print(f"[{k}/{len(todo)}] {row['gene']} / {row['phenotype']}: {row['verdict'] or row['error']} "
                  f"(Claude {row['claude_verdict']}, {row['truth']}) ${row['usd']} {row['seconds']}s", flush=True)
            with LOCK, open(table, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=COLUMNS, delimiter="\t", extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)

    ok = [r for r in rows if not r["error"]]
    summary = {"pairs": len(rows), "errors": len(rows) - len(ok), "max_date": args.max_date,
               "fingerprint": arm.fingerprint(), "wall_seconds": round(time.time() - started, 1),
               "usd": round(sum(float(r["usd"] or 0) for r in ok), 4),
               "usd_2027": round(sum(float(r["usd_2027"] or 0) for r in ok), 4),
               "same_verdict_as_claude": sum(r["verdict"] == r["claude_verdict"] for r in ok),
               "models": {m: dict(t) for m, t in TOTALS.items()}}
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
