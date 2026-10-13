"""Closed-book model asked to cite: can it back its verdict with real papers?

Same 210 dated GenCC Limited pairs as Fig. 2c,d (results/prior_year10/
sample.tsv), same model and temperature as results/prior_year10/knowledge.tsv,
same prompt with one task added: list up to five supporting publications
(PMID optional). knowledge.tsv is left untouched; verdicts here are compared
to it to see whether asking for references moves them.

Writes results/knowledge_citations/:
  runs.json     one record per pair, raw answer included
  verdicts.tsv  verdict, distribution, number of references, cost
  refs.tsv      one row per reference as the model gave it

  PESTO_PROJECT_ROOT=$PWD python3 scripts/272_knowledge_citations.py [--limit N]
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PESTO_PROJECT_ROOT", str(ROOT))

from pesto.cost import capturing
from pesto.flow.steps import Argmax
from pesto.flow.types import Query
from pesto.harness import MODELS
from pesto.services.llm_service import call_llm_with_usage
from pesto.utils.helpers import load_prompt

SAMPLE = ROOT / "results" / "prior_year10" / "sample.tsv"
KNOW = ROOT / "results" / "prior_year10" / "knowledge.tsv"
OUT = ROOT / "results" / "knowledge_citations"
RUNS = OUT / "runs.json"
VERDICTS = OUT / "verdicts.tsv"
REFS = OUT / "refs.tsv"
MODEL = "opus5"
WORKERS = 20
PROMPT = load_prompt("knowledge_citations")
LOCK = threading.Lock()
GRADES = ("Novel", "Hypothesized", "Existing", "Established")
REF_RE = re.compile(r"<ref\b(.*?)/>", re.S)
ATTR_RE = re.compile(r'(\w+)\s*=\s*"(.*?)"(?=\s+\w+\s*=|\s*$)', re.S)
REF_FIELDS = ("pmid", "first_author", "year", "journal", "title")
VERDICT_COLS = [
    "year", "gene", "phenotype", "disease_curie", "verdict", "lit_score",
    "p_established", "p_existing", "p_hypothesized", "p_novel",
    "verdict_fig2c", "lit_score_fig2c", "n_refs", "n_refs_pmid",
    "justification", "input_tokens", "output_tokens", "usd", "error",
]
REF_COLS = ["year", "gene", "phenotype", "rank", *REF_FIELDS]


def load_tsv(path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def save_tsv(path, rows, cols):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def parse_refs(text):
    block = re.search(r"<references>(.*?)</references>", text or "", re.S)
    if not block:
        return []
    refs = []
    for body in REF_RE.findall(block.group(1)):
        attrs = {k.lower(): html.unescape(v).strip()
                 for k, v in ATTR_RE.findall(body.strip())}
        ref = {f: attrs.get(f, "") for f in REF_FIELDS}
        ref["pmid"] = re.sub(r"\D", "", ref["pmid"])
        if any(ref.values()):
            refs.append(ref)
    return refs


def lit_score(dist):
    return (4 * dist.get("Established", 0) + 3 * dist.get("Existing", 0)
            + 2 * dist.get("Hypothesized", 0) + dist.get("Novel", 0)) / 100


def ask(gene, phenotype):
    text = PROMPT.format(gene_name=gene, phenotype=phenotype)
    with capturing() as cap:
        resp = call_llm_with_usage(text, MODELS[MODEL], 0.0,
                                   agent_name="knowledge_citations") or {}
    return resp.get("text", "") or "", cap.summary(MODELS[MODEL])


def work(pair, fig2c):
    out = {k: pair[k] for k in ("year", "gene", "phenotype", "disease_curie",
                                "n_pmids", "oldest_pmid")}
    old = fig2c.get((pair["gene"], pair["phenotype"]), {})
    out["verdict_fig2c"] = old.get("verdict", "")
    out["lit_score_fig2c"] = old.get("lit_score", "")
    try:
        raw, spent = ask(pair["gene"], pair["phenotype"])
        verdict = Argmax().run(Query(pair["gene"], pair["phenotype"]), raw)
        if verdict.call == "PARSE_FAIL":
            raw, spent = ask(pair["gene"], pair["phenotype"])
            verdict = Argmax().run(Query(pair["gene"], pair["phenotype"]), raw)
        refs = parse_refs(raw)
        dist = verdict.distribution.as_dict() if verdict.distribution else {}
        out.update({
            "verdict": verdict.call,
            "lit_score": lit_score(dist) if dist else "",
            "p_established": dist.get("Established", ""),
            "p_existing": dist.get("Existing", ""),
            "p_hypothesized": dist.get("Hypothesized", ""),
            "p_novel": dist.get("Novel", ""),
            "justification": verdict.justification or "",
            "refs": refs,
            "n_refs": len(refs),
            "n_refs_pmid": sum(1 for r in refs if r["pmid"]),
            "raw": raw,
            **spent,
        })
        if verdict.call not in GRADES:
            out["error"] = verdict.call
        elif "<references" not in raw:
            out["error"] = "NO_REFERENCES_BLOCK"
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def save(done):
    done = sorted(done, key=lambda r: (int(r["year"]), r["gene"], r["phenotype"]))
    RUNS.write_text(json.dumps(done, indent=1), encoding="utf-8")
    save_tsv(VERDICTS, done, VERDICT_COLS)
    save_tsv(REFS, [{**{k: r[k] for k in ("year", "gene", "phenotype")},
                     "rank": i + 1, **ref}
                    for r in done for i, ref in enumerate(r.get("refs") or [])],
             REF_COLS)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0,
                    help="run only the first N pending pairs (a pilot)")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    pairs = load_tsv(SAMPLE)
    if len(pairs) != 210:
        print(f"ERROR: expected 210 pairs, got {len(pairs)}", file=sys.stderr)
        return 1
    fig2c = {(r["gene"], r["phenotype"]): r for r in load_tsv(KNOW)}
    have = json.loads(RUNS.read_text()) if RUNS.exists() else []
    have = [r for r in have if not r.get("error")]
    done_keys = {(r["gene"], r["phenotype"]) for r in have}
    todo = [p for p in pairs if (p["gene"], p["phenotype"]) not in done_keys]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(pairs)} pairs, {len(done_keys)} done, {len(todo)} to run, "
          f"{MODELS[MODEL]}, {WORKERS} workers", flush=True)

    done = list(have)
    started = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = [pool.submit(work, p, fig2c) for p in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            with LOCK:
                done.append(rec)
                save(done)
            shown = rec.get("error") or rec.get("verdict")
            print(f"  {i:3d}/{len(todo)}  {rec['year']}  {rec['gene']:10s} "
                  f"{shown:14s} refs {rec.get('n_refs', 0)} "
                  f"(pmid {rec.get('n_refs_pmid', 0)})  "
                  f"{time.time() - started:4.0f}s", flush=True)

    ok = [r for r in done if not r.get("error")]
    same = sum(r["verdict"] == r["verdict_fig2c"] for r in ok)
    usd = sum(float(r.get("usd") or 0) for r in done)
    print(f"\n{len(ok)}/{len(done)} parsed; verdict unchanged vs Fig. 2c "
          f"{same}/{len(ok)}; total ${usd:.2f}")
    print(f"wrote {RUNS.relative_to(ROOT)}, {VERDICTS.name}, {REFS.name}")
    return 1 if len(ok) < len(done) else 0


if __name__ == "__main__":
    sys.exit(main())
