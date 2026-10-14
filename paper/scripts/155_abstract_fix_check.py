"""Does reading whole structured abstracts change the paper's verdicts?

Until 26 September 2026 fetch_abstracts kept only the first section of a
structured abstract; every run behind Figures 1-3 was made that way. This takes
20 of those runs, spread over the paper (Figure 1 cohorts and negative
controls, the GenCC classes of Figure 2a, the ASC groups of Figure 2b, the
year windows of Figure 2c,d and four phenotypes of Figure 3), and replays them
on the same corpus with whole abstracts.

Only the abstract text changes. The corpus is the run's own (the PMIDs it
banded, in that order), the expansion terms are the run's own, and the bands,
the selection, the reading and the judge are the arm's blocks with the same
models on Vertex. Titles and whole abstracts are fetched again from PubMed.
The banding order within a batch of ten is not recorded, so the corpus order
is the order of the saved labels.

Compared: the 1-4 mean of the distribution (paired Wilcoxon signed-rank test)
and the rounded verdict (agreement, and a sign test on the direction of the
changes).

  PESTO_PROJECT_ROOT=$PWD python3 scripts/155_abstract_fix_check.py
"""
from __future__ import annotations

import csv
import glob
import json
import os
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PESTO_PROJECT_ROOT", str(ROOT))

from pesto import harness  # noqa: E402
from pesto.flow import arms  # noqa: E402
from pesto.flow.store import slug  # noqa: E402
from pesto.flow.types import FIELDS, Corpus, Query  # noqa: E402

OLD_FPS = {"ff136250f372", "20ff05471c58"}
OUT_DIR = ROOT / "results" / "abstract_fix_check"
OUT = ROOT / "results" / "abstract_fix_check.tsv"
SEED = 155
W = {"Novel": 1, "Hypothesized": 2, "Existing": 3, "Established": 4}
ORDER = ("Novel", "Hypothesized", "Existing", "Established")


def tsv(path):
    with open(ROOT / path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def run_index():
    idx = {}
    for p in glob.glob(str(ROOT / "**" / "*.json"), recursive=True):
        m = re.search(r"/([^/]+)__([0-9a-f]{12})\.json$", p)
        if m and m.group(2) in OLD_FPS and "/attic/" not in p:
            idx.setdefault(m.group(1), p)
    return idx


def pick(rows, n, rng, used):
    rows = [r for r in rows if (r["gene"], r["phenotype"]) not in used]
    return rng.sample(rows, min(n, len(rows)))


def strata(idx):
    """(stratum, gene, phenotype) for the 20 pairs."""
    rng = random.Random(SEED)
    used, out = set(), []

    def add(name, rows, n=1):
        rows = [r for r in rows if slug(Query(r["gene"], r["phenotype"])) in idx]
        for r in pick(rows, n, rng, used):
            used.add((r["gene"], r["phenotype"]))
            out.append((name, r["gene"], r["phenotype"]))

    cohort = [r for r in tsv("results/all_runs_auto_v7.tsv")
              if r["source"] in ("AoU", "BRAVA")]
    for v in ORDER:
        add(f"Fig 1 cohort, {v}", [r for r in cohort if r["lit_mean"] == v])
    add("Fig 1 negative control", tsv("results/bench_fig1c_absent50_hgnc_pesto_v7.tsv"))
    gencc = tsv("benchmark/gencc_clingen_g2p/pesto.tsv")
    for c in ("Definitive", "Strong", "Moderate", "Limited", "Absent"):
        add(f"Fig 2a GenCC {c}", [r for r in gencc if r["gencc_class"] == c])
    asd = tsv("results/bench_asd_current.tsv")
    for c in ("autism known", "autism candidate", "novel candidate"):
        add(f"Fig 2b ASC {c}", [r for r in asd if r["classification"] == c])
    add("Fig 2b not in ASC", [r for r in tsv("benchmark/asd_extra101/pesto.tsv")
                              if r.get("set") == "random"])
    year = {(r["gene"], r["phenotype"]): int(r["year"])
            for r in tsv("results/prior_year10/sample.tsv")}
    limited = [r for r in tsv("results/prior_year10/pesto.tsv")
               if (r["gene"], r["phenotype"]) in year]
    add("Fig 2c,d Limited 2011-2013",
        [r for r in limited if 2011 <= year[(r["gene"], r["phenotype"])] <= 2013])
    add("Fig 2c,d Limited 2023-2025",
        [r for r in limited if 2023 <= year[(r["gene"], r["phenotype"])] <= 2025])
    fig3 = tsv("results/fig3_universe550_meancall_scores.tsv")
    for ph in ("epilepsy", "schizophrenia", "congenital heart disease",
               "type 2 diabetes"):
        add(f"Fig 3 {ph}", [r for r in fig3 if r["phenotype"] == ph])
    return out


def mean(dist):
    total = sum(dist.get(k, 0) for k in W) or 1
    return sum(W[k] * dist.get(k, 0) for k in W) / total


def call(m):
    return ORDER[max(1, min(4, round(m))) - 1]


def articles(pmids):
    out = []
    for i in range(0, len(pmids), 100):
        out += harness.articles_from_pmids(pmids[i:i + 100])
    return out


def replay(item, idx):
    stratum, gene, pheno = item
    query = Query(gene, pheno)
    old = json.load(open(idx[slug(query)], encoding="utf-8"))
    arm = arms.get(old["arm"])
    bands, select, read, judge = arm.annotate[0], arm.select, arm.read, arm.judge
    pmids = list(old["labels"].keys())
    corpus = Corpus.of(articles(pmids), FIELDS)
    labels = bands.run(query, corpus, old["terms"])
    chosen = select.run(corpus, labels)
    text, _ = read.run(query, chosen)
    verdict = judge.run(query, text, chosen)
    new_dist = verdict.distribution.as_dict() if verdict.distribution else {}
    old_dist = old["verdict"]["distribution"] or {}
    old_read = {a["pmid"] for a in old["articles"]}
    new_read = set(chosen.pmids)
    longer = sum(1 for a in chosen if a.pmid in old_read and len(a.abstract) >
                 len(next(o for o in old["articles"] if o["pmid"] == a.pmid)
                     .get("abstract") or "") + 20)
    row = {"stratum": stratum, "gene": gene, "phenotype": pheno,
           "arm": old["arm"], "old_fingerprint": old["fingerprint"],
           "corpus": len(corpus), "old_mean": round(mean(old_dist), 3),
           "new_mean": round(mean(new_dist), 3) if new_dist else "",
           "old_call": call(mean(old_dist)),
           "new_call": call(mean(new_dist)) if new_dist else "PARSE_FAIL",
           "read_overlap": len(old_read & new_read),
           "read_longer_abstract": longer}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / f"{slug(query)}.json", "w", encoding="utf-8") as fh:
        json.dump({**row, "old_distribution": old_dist, "new_distribution": new_dist,
                   "new_raw": text, "new_read": sorted(new_read)}, fh, indent=1)
    print(f"  {stratum:32s} {gene:9s} {row['old_call']:13s} -> {row['new_call']:13s}"
          f" {row['old_mean']} -> {row['new_mean']}", flush=True)
    return row


def main():
    idx = run_index()
    items = strata(idx)
    print(f"{len(items)} pairs", flush=True)
    with ThreadPoolExecutor(10) as ex:
        rows = list(ex.map(lambda it: replay(it, idx), items))
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]), delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    ok = [r for r in rows if r["new_mean"] != ""]
    old = [r["old_mean"] for r in ok]
    new = [r["new_mean"] for r in ok]
    same = sum(r["old_call"] == r["new_call"] for r in ok)
    up = sum(W[r["new_call"]] > W[r["old_call"]] for r in ok)
    down = sum(W[r["new_call"]] < W[r["old_call"]] for r in ok)
    diffs = [n - o for o, n in zip(old, new)]
    wil = stats.wilcoxon(new, old) if any(diffs) else None
    sign = stats.binomtest(up, up + down) if up + down else None
    rho = stats.spearmanr(old, new)
    print(f"\n{len(ok)} pairs compared")
    print(f"verdict unchanged {same}/{len(ok)}; up {up}, down {down}"
          + (f"; sign test P = {sign.pvalue:.3g}" if sign else ""))
    print(f"mean change {sum(diffs) / len(diffs):+.3f} (median "
          f"{sorted(diffs)[len(diffs) // 2]:+.3f}); Wilcoxon P = "
          + (f"{wil.pvalue:.3g}" if wil else "n/a (no change)"))
    print(f"Spearman rho old vs new {rho.statistic:.3f}")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
