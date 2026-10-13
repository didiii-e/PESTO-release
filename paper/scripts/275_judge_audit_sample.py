"""Draw the Haiku citation judgments a person reads to check the judge.

Forty judgments from results/knowledge_citations/ref_checks.tsv, stratified by
arm and label (about seven A, seven B and six C per arm), seeded. The arm is
written in its own column at the end so the reader can hide it. Fill
`human_label` with A, B or C, then rerun with --score to get the agreement.

  python3 scripts/275_judge_audit_sample.py           # writes the sample
  python3 scripts/275_judge_audit_sample.py --score   # agreement once filled
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "results" / "knowledge_citations"
OUT = IN / "judge_audit_sample.tsv"
SEED = 2026
PER_ARM = {"A": 7, "B": 7, "C": 6}
COLS = ["item", "gene", "phenotype", "pmid", "title", "abstract",
        "judge_label", "judge_reason", "human_label", "arm"]


def load_tsv(path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def draw():
    rows = load_tsv(IN / "ref_checks.tsv")
    records = json.loads((IN / "pubmed_records.json").read_text())
    rng = random.Random(SEED)
    seen, sample = set(), []
    for arm in ("pesto", "knowledge"):
        for label, n in PER_ARM.items():
            pool = [r for r in rows if r["arm"] == arm and r["label"] == label
                    and (r["resolved_pmid"], r["gene"], r["phenotype"]) not in seen]
            rng.shuffle(pool)
            for r in pool[:n]:
                seen.add((r["resolved_pmid"], r["gene"], r["phenotype"]))
                rec = records.get(r["resolved_pmid"]) or {}
                sample.append({
                    "gene": r["gene"], "phenotype": r["phenotype"],
                    "pmid": r["resolved_pmid"], "title": rec.get("title", ""),
                    "abstract": (rec.get("abstract") or "").replace("\t", " "),
                    "judge_label": r["label"], "judge_reason": r["reason"],
                    "human_label": "", "arm": arm,
                })
    rng.shuffle(sample)
    for i, s in enumerate(sample, 1):
        s["item"] = i
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, COLS, delimiter="\t")
        w.writeheader()
        w.writerows(sample)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(sample)} judgments "
          f"{dict(Counter((s['arm'], s['judge_label']) for s in sample))}")


def score():
    rows = [r for r in load_tsv(OUT) if r["human_label"].strip()]
    if not rows:
        print("no human_label filled yet", file=sys.stderr)
        return 1
    agree = sum(r["human_label"].strip().upper() == r["judge_label"] for r in rows)
    print(f"agreement {agree}/{len(rows)}")
    pairs = Counter((r["judge_label"], r["human_label"].strip().upper()) for r in rows)
    for (j, h), n in sorted(pairs.items()):
        print(f"  judge {j}  human {h}  {n}")
    a_agree = [r for r in rows if r["judge_label"] == "A"]
    if a_agree:
        ok = sum(r["human_label"].strip().upper() == "A" for r in a_agree)
        print(f"A confirmed by the reader: {ok}/{len(a_agree)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--score", action="store_true")
    sys.exit(score() if ap.parse_args().score else draw())
