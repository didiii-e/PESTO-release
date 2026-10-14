#!/usr/bin/env python3
"""Every pair of Figure 2, with the panel it belongs to, for the Gemini rerun
(scripts/299_gemini_fig2_run.py). The selections are those of
scripts/21_figure2.R, rule for rule, so that the Gemini figure is drawn on the
same pairs as the Claude one; every source was run with the same arm
(ff136250f372).

  a   GenCC: the 150 pairs of benchmark/gencc_clingen_g2p/results/scored.tsv
      (120 curated, 30 Absent), the 280 later curated draws of
      results/fig2a_extra40/combined_n100.tsv (source != original) and the 70
      Absent of fig2a_absent_extra20, 20b and 30. 100 per class.
  b   ASC: the 253 curated genes of results/bench_asd_current.tsv, and 100 genes
      not in the list: the first 50 random genes of benchmark/asd_extra101 in
      gene order, then extra50_random on autism, minus curated genes.
  cd  The 200 GenCC Limited pairs dated 2011 to 2025 of results/prior_year10
      (40 per window); their negatives are the 100 Absent of a.

A pair in several panels is listed once, with all its panels.

  python3 scripts/300_gemini_fig2_pairs.py
Writes results/gemini_fig2/pairs.tsv.
"""
from __future__ import annotations

import csv
import json
import os
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(ROOT, "results")
VERDICTS = {"Novel", "Hypothesized", "Existing", "Established"}
CURATED = ["Definitive", "Strong", "Moderate", "Limited"]
OUT = os.path.join(R, "gemini_fig2", "pairs.tsv")


def tsv(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def main():
    pairs = OrderedDict()

    def add(gene, phenotype, panel, truth):
        key = (gene, phenotype)
        if key not in pairs:
            pairs[key] = {"gene": gene, "phenotype": phenotype, "panels": [], "truth": truth}
        if panel not in pairs[key]["panels"]:
            pairs[key]["panels"].append(panel)

    scored = tsv(os.path.join(ROOT, "benchmark", "gencc_clingen_g2p", "results", "scored.tsv"))
    for r in scored:
        if r["lit_mean"] in VERDICTS and r["gencc_class"] in CURATED + ["Absent"]:
            add(r["gene"], r["phenotype"], "a", r["gencc_class"])
    for r in tsv(os.path.join(R, "fig2a_extra40", "combined_n100.tsv")):
        if r["source"] != "original" and r["gencc_class"] in CURATED + ["Absent"]:
            add(r["gene"], r["phenotype"], "a", r["gencc_class"])
    for d in ("fig2a_absent_extra20", "fig2a_absent_extra20b", "fig2a_absent_extra30"):
        for r in tsv(os.path.join(R, d, "pesto.tsv")):
            if not r["error"]:
                add(r["gene"], r["phenotype"], "a", "Absent")

    groups = {"autism known": "ASD known", "ID known": "ASD candidate",
              "autism candidate": "ASD candidate", "novel candidate": "Novel candidate"}
    curated = [r for r in tsv(os.path.join(R, "bench_asd_current.tsv"))
               if r["classification"] in groups and r["lit_mean"] in VERDICTS]
    for r in curated:
        add(r["gene"].upper(), r["phenotype"], "b", groups[r["classification"]])
    seen = {r["gene"].upper() for r in curated}
    random101 = sorted((r for r in tsv(os.path.join(ROOT, "benchmark", "asd_extra101", "pesto.tsv"))
                        if r["set"] == "random" and r["lit_mean"] in VERDICTS), key=lambda r: r["gene"])[:50]
    extra50 = [r for r in tsv(os.path.join(ROOT, "benchmark", "extra50_random", "pesto.tsv"))
               if r["phenotype"] == "Autism Spectrum Disorder" and r["lit_mean"] in VERDICTS]
    for r in random101 + extra50:
        gene = r["gene"].upper()
        if gene not in seen:
            seen.add(gene)
            add(gene, r["phenotype"], "b", "Not in ASD list")

    years = {(r["gene"], r["phenotype"]): int(r["year"]) for r in tsv(os.path.join(R, "prior_year10", "knowledge.tsv"))
             if r["year"] and r["lit_score"]}
    with open(os.path.join(R, "prior_year10", "pesto.json"), encoding="utf-8") as fh:
        for r in json.load(fh):
            year = years.get((r["gene"], r["phenotype"]))
            if year and year >= 2011:
                add(r["gene"], r["phenotype"], "cd", f"Limited {year}")

    counts = {}
    for p in pairs.values():
        for panel in p["panels"]:
            counts.setdefault(panel, {}).setdefault(p["truth"] if panel != "cd" else "Limited", 0)
            counts[panel][p["truth"] if panel != "cd" else "Limited"] += 1
    print(len(pairs), "pairs;", json.dumps(counts))
    assert all(counts["a"][c] == 100 for c in CURATED + ["Absent"]), counts["a"]
    assert sum(counts["b"].values()) == 353 and counts["b"]["Not in ASD list"] == 100, counts["b"]
    assert counts["cd"]["Limited"] == 200, counts["cd"]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["gene", "phenotype", "panels", "truth"])
        for p in pairs.values():
            w.writerow([p["gene"], p["phenotype"], ",".join(p["panels"]), p["truth"]])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
