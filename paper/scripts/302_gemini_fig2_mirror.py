#!/usr/bin/env python3
"""Lay the Gemini results of Figure 2 out as scripts/21_figure2.R reads the
Claude ones, so that the same script draws the Gemini figure (14 October 2026).

Reads results/gemini_fig2/:
  full/pesto.tsv              the literature arm on the 1,043 pairs of Fig. 2
  extra2010/pesto.tsv         the 10 dated pairs of 2010 (citations only)
  knowledge/pesto.tsv         the model's internal knowledge, panels c and d
  knowledge_citations/        panels e and f (scripts/301_gemini_citations.py)
and the Claude tables only for what is not a result: which pairs, their GenCC
class or ASC group, the year of first report, and how each panel's source file
splits its rows. Scores are the confidence-weighted mean on the 1-4 scale; the
verdict of panels a and b is that mean rounded, as in the Claude figure.

Writes the tree results/gemini_fig2/fig2_root/ (with a link to scripts/), then:

  PESTO_FIG2_ROOT=results/gemini_fig2/fig2_root PESTO_FIG2_STEM=figure2_gemini \\
      Rscript scripts/21_figure2.R

  python3 scripts/302_gemini_fig2_mirror.py [--draw]
--draw also runs the R script and copies the figure to figures/figure2_gemini.*.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(ROOT, "results")
G = os.path.join(R, "gemini_fig2")
MIRROR = os.path.join(G, "fig2_root")
VERDICTS = ["Novel", "Hypothesized", "Existing", "Established"]
WEIGHTS = {"p_novel": 1, "p_hypothesized": 2, "p_existing": 3, "p_established": 4}


def tsv(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write(rel, rows, cols):
    path = os.path.join(MIRROR, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def score(r):
    if not r or r.get("error") or not r.get("p_novel"):
        return None
    return sum(float(r[k]) * w for k, w in WEIGHTS.items()) / 100


def call(s):
    return VERDICTS[max(0, min(3, int(s + 0.5) - 1))] if s is not None else ""


def results(*paths):
    out = {}
    for p in paths:
        if os.path.exists(p):
            for r in tsv(p):
                out[(r["gene"], r["phenotype"])] = r
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--draw", action="store_true")
    args = ap.parse_args()

    lit = results(os.path.join(G, "full", "pesto.tsv"), os.path.join(G, "extra2010", "pesto.tsv"))
    know = results(os.path.join(G, "knowledge", "pesto.tsv"))
    missing = []

    def lit_of(gene, phenotype):
        s = score(lit.get((gene, phenotype)))
        if s is None:
            missing.append(("literature", gene, phenotype))
        return s

    def know_of(gene, phenotype):
        s = score(know.get((gene, phenotype)))
        if s is None:
            missing.append(("knowledge", gene, phenotype))
        return s

    if os.path.isdir(MIRROR):
        shutil.rmtree(MIRROR)
    os.makedirs(MIRROR)
    os.symlink(os.path.join(ROOT, "scripts"), os.path.join(MIRROR, "scripts"))

    # Panel a: the original 150, their 30 Absent with knowledge (panels c, d).
    scored = tsv(os.path.join(ROOT, "benchmark", "gencc_clingen_g2p", "results", "scored.tsv"))
    rows, absent30 = [], []
    for r in scored:
        s = lit_of(r["gene"], r["phenotype"])
        rows.append({**r, "lit_mean": call(s)})
        if r["gencc_class"] == "Absent":
            dist = lit.get((r["gene"], r["phenotype"]), {})
            absent30.append({"gene": r["gene"], "phenotype": r["phenotype"], "gencc_class": "Absent",
                             **{k: dist.get(k, "") for k in WEIGHTS}})
    write("benchmark/gencc_clingen_g2p/results/scored.tsv", rows, ["gene", "phenotype", "gencc_class", "lit_mean"])
    write("benchmark/gencc_clingen_g2p/pesto.tsv", absent30, ["gene", "phenotype", "gencc_class", *WEIGHTS])
    write("results/ablation_fig2/knowledge.tsv",
          [{"draw": 1, "gene": r["gene"], "phenotype": r["phenotype"],
            "lit_score": know_of(r["gene"], r["phenotype"])} for r in absent30],
          ["draw", "gene", "phenotype", "lit_score"])

    extra40 = [{**r, "current": lit_of(r["gene"], r["phenotype"])}
               for r in tsv(os.path.join(R, "fig2a_extra40", "combined_n100.tsv")) if r["source"] != "original"]
    write("results/fig2a_extra40/combined_n100.tsv", extra40, ["gene", "phenotype", "gencc_class", "source", "current"])
    for d in ("fig2a_absent_extra20", "fig2a_absent_extra20b", "fig2a_absent_extra30"):
        src = [r for r in tsv(os.path.join(R, d, "pesto.tsv")) if not r["error"]]
        write(f"results/{d}/pesto.tsv",
              [{"gene": r["gene"], "phenotype": r["phenotype"], "lit_score": lit_of(r["gene"], r["phenotype"]),
                "error": ""} for r in src], ["gene", "phenotype", "lit_score", "error"])
        write(f"results/{d}/knowledge.tsv",
              [{"gene": r["gene"], "phenotype": r["phenotype"], "lit_score": know_of(r["gene"], r["phenotype"])}
               for r in src], ["gene", "phenotype", "lit_score"])

    # Panel b, with each of the two random draws in its own file as the R script splits them.
    asd = [r for r in tsv(os.path.join(R, "bench_asd_current.tsv"))
           if r["classification"] in ("autism known", "ID known", "autism candidate", "novel candidate")
           and r["lit_mean"] in VERDICTS]
    write("results/bench_asd_current.tsv",
          [{**r, "lit_mean": call(lit_of(r["gene"].upper(), r["phenotype"]))} for r in asd],
          ["gene", "phenotype", "classification", "lit_mean"])
    random101 = sorted((r for r in tsv(os.path.join(ROOT, "benchmark", "asd_extra101", "pesto.tsv"))
                        if r["set"] == "random" and r["lit_mean"] in VERDICTS), key=lambda r: r["gene"])[:50]
    extra50 = [r for r in tsv(os.path.join(ROOT, "benchmark", "extra50_random", "pesto.tsv"))
               if r["phenotype"] == "Autism Spectrum Disorder" and r["lit_mean"] in VERDICTS]
    curated = {r["gene"].upper() for r in asd}
    for rel, src in (("benchmark/asd_extra101/pesto.tsv", random101), ("benchmark/extra50_random/pesto.tsv", extra50)):
        out = []
        for r in src:
            gene = r["gene"].upper()
            if gene in curated:
                continue
            dist = lit.get((gene, r["phenotype"]), {})
            out.append({"gene": gene, "phenotype": r["phenotype"], "set": "random",
                        "lit_mean": call(lit_of(gene, r["phenotype"])), **{k: dist.get(k, "") for k in WEIGHTS}})
        write(rel, out, ["gene", "phenotype", "set", "lit_mean", *WEIGHTS])

    # Panels c and d: the dated Limited pairs, both methods.
    dated = [r for r in tsv(os.path.join(R, "prior_year10", "knowledge.tsv")) if r["year"]]
    write("results/prior_year10/knowledge.tsv",
          [{"year": r["year"], "gene": r["gene"], "phenotype": r["phenotype"],
            "lit_score": know_of(r["gene"], r["phenotype"]) if int(r["year"]) >= 2011 else
            score(know.get((r["gene"], r["phenotype"]))) or ""} for r in dated],
          ["year", "gene", "phenotype", "lit_score"])
    runs = []
    for r in dated:
        row = lit.get((r["gene"], r["phenotype"]))
        if score(row) is None:
            missing.append(("literature", r["gene"], r["phenotype"]))
            continue
        runs.append({"gene": r["gene"], "phenotype": r["phenotype"], "verdict": row["verdict"],
                     "distribution": {k[2:].capitalize(): float(row[k]) for k in WEIGHTS}})
    path = os.path.join(MIRROR, "results", "prior_year10", "pesto.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(runs, fh, indent=1)

    # Panels e and f.
    cit = os.path.join(G, "knowledge_citations")
    for name in ("pair_summary.tsv", "ref_checks.tsv"):
        src = os.path.join(cit, name)
        if os.path.exists(src):
            os.makedirs(os.path.join(MIRROR, "results", "knowledge_citations"), exist_ok=True)
            shutil.copy(src, os.path.join(MIRROR, "results", "knowledge_citations", name))
        else:
            missing.append(("citations", name, ""))

    missing = sorted(set(missing))
    print(f"mirror written to {os.path.relpath(MIRROR, ROOT)}; {len(missing)} missing results")
    for m in missing[:20]:
        print("  missing", *m)
    if missing:
        return 1
    if args.draw:
        env = {**os.environ, "PESTO_FIG2_ROOT": MIRROR, "PESTO_FIG2_STEM": "figure2_gemini"}
        # The script ends on a side plot of literature against Max verdicts, which
        # needs the Open Targets branch the Gemini run does not have; it fails
        # after Figure 2 is written, so success is the figure, not the exit code.
        subprocess.run(["Rscript", os.path.join(ROOT, "scripts", "21_figure2.R")], env=env, cwd=ROOT)
        if not os.path.exists(os.path.join(MIRROR, "figures", "figure2_gemini.png")):
            return 1
        for ext in ("png", "pdf"):
            shutil.copy(os.path.join(MIRROR, "figures", f"figure2_gemini.{ext}"),
                        os.path.join(ROOT, "figures", f"figure2_gemini.{ext}"))
        print("figures/figure2_gemini.png and .pdf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
