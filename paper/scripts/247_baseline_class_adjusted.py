"""Does the baseline PESTO class still predict later evidence once research attention
is accounted for? Genes PESTO calls Hypothesized have, by construction, more
literature than genes it calls Novel, and studied genes keep being studied.

For both cohorts of scripts/246_figure_baseline_class_benchmark.R (epilepsy,
2007 -> 2026, EPIGEN candidate genes; autism, 2014 -> 2026, de novo LoF genes), the
attention of a gene at the start date is the number of PubMed articles linked to it
in NCBI gene2pubmed (data/raw/gene2pubmed.gz) with a PMID at or below the last PMID
indexed on the start date (17,905,000 on 30 September 2007, between the PMIDs indexed
in the last week of September 2007 and the first week of October, read from PubMed on
14 October 2026; 25,266,000 on 30 September 2014, read on 11 October 2026). Then, among
genes Novel or Hypothesized at the start:

  logistic regression  high ~ Hypothesized + log10(1 + articles)   per cohort
                       high ~ Hypothesized + log10(1 + articles) + cohort   pooled
  Cochran-Mantel-Haenszel over tertiles of articles (within cohort)

where high is Existing or Established at the end date. P values for Hypothesized are
one-sided (Hypothesized > Novel). Also prints the ten-year horizon of the epilepsy
cohort (2007 -> 2017) with the same one-sided Fisher test. Writes
results/baseline_class_adjusted.tsv (one row per gene) and prints the models.

  python3 scripts/247_baseline_class_adjusted.py
"""
from __future__ import annotations

import gzip
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.contingency_tables import StratifiedTable

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = {"epilepsy": 17_905_000, "autism": 25_266_000}


def cohorts():
    h = pd.read_csv(ROOT / "data" / "hgnc_complete_set.txt", sep="\t", dtype=str, low_memory=False)
    epi = pd.read_csv(ROOT / "benchmark" / "epigen_extension" / "transitions.tsv", sep="\t")
    epi = epi.merge(h[["symbol", "entrez_id"]], left_on="gene", right_on="symbol", how="left")
    epi = epi.rename(columns={"c2007": "start", "c2026": "end"})[["gene", "entrez_id", "start", "end"]]
    asd = pd.read_csv(ROOT / "benchmark" / "asd_denovo2014" / "transitions.tsv", sep="\t")
    asd = asd.merge(h[["symbol", "entrez_id"]], left_on="gene", right_on="symbol", how="left")
    asd = asd.rename(columns={"c2014": "start", "c2026": "end"})[["gene", "entrez_id", "start", "end"]]
    d = pd.concat([epi.assign(cohort="epilepsy"), asd.assign(cohort="autism")], ignore_index=True)
    d = d[d["start"].isin(["Novel", "Hypothesized"])].copy()
    d["hyp"] = (d["start"] == "Hypothesized").astype(int)
    d["high"] = d["end"].isin(["Existing", "Established"]).astype(int)
    return d


def article_counts(d):
    want = set(d["entrez_id"].dropna())
    counts = {(c, e): 0 for c in CUTOFF for e in want}
    with gzip.open(ROOT / "data" / "raw" / "gene2pubmed.gz", "rt") as f:
        next(f)
        for line in f:
            tax, gene, pmid = line.rstrip("\n").split("\t")
            if tax != "9606" or gene not in want:
                continue
            for c, cut in CUTOFF.items():
                if int(pmid) <= cut:
                    counts[(c, gene)] += 1
    return [counts.get((c, e), np.nan) for c, e in zip(d["cohort"], d["entrez_id"])]


def one_sided(coef, p):
    return p / 2 if coef > 0 else 1 - p / 2


def logit(d, terms):
    X = sm.add_constant(d[terms].astype(float))
    m = sm.Logit(d["high"], X).fit(disp=False)
    b, p = m.params["hyp"], m.pvalues["hyp"]
    lo, hi = m.conf_int().loc["hyp"]
    return f"OR {np.exp(b):.2f} (95% CI {np.exp(lo):.2f}-{np.exp(hi):.2f}), one-sided P = {one_sided(b, p):.2g}"


def main():
    d = cohorts()
    d["articles"] = article_counts(d)
    missing = d["articles"].isna().sum()
    d = d.dropna(subset=["articles"])
    d["log_articles"] = np.log10(1 + d["articles"])
    d.to_csv(ROOT / "results" / "baseline_class_adjusted.tsv", sep="\t", index=False)
    if missing:
        print(f"{missing} genes without an Entrez ID dropped")

    for name, sub in [("epilepsy", d[d.cohort == "epilepsy"]), ("autism", d[d.cohort == "autism"]), ("pooled", d)]:
        print(f"\n== {name}: {len(sub)} genes, {sub.hyp.sum()} Hypothesized")
        med = sub.groupby("start")["articles"].median()
        print(f"  median articles at start: Novel {med.get('Novel', np.nan):.0f}, Hypothesized {med.get('Hypothesized', np.nan):.0f}"
              f" (Mann-Whitney P = {stats.mannwhitneyu(sub[sub.hyp == 1].articles, sub[sub.hyp == 0].articles).pvalue:.2g})")
        extra = ["cohort_autism"] if name == "pooled" else []
        sub = sub.assign(cohort_autism=(sub.cohort == "autism").astype(int))
        print("  unadjusted:              ", logit(sub, ["hyp"] + extra))
        print("  adjusted for articles:   ", logit(sub, ["hyp", "log_articles"] + extra))
        tables = []
        for _, g in sub.groupby("cohort"):
            g = g.assign(tertile=pd.qcut(g["articles"].rank(method="first"), 3, labels=False))
            for _, t in g.groupby("tertile"):
                tab = np.array([[((t.hyp == 1) & (t.high == 1)).sum(), ((t.hyp == 1) & (t.high == 0)).sum()],
                                [((t.hyp == 0) & (t.high == 1)).sum(), ((t.hyp == 0) & (t.high == 0)).sum()]])
                tables.append(tab + 0.5 * (tab == 0).any())
        st = StratifiedTable(tables)
        p = st.test_null_odds().pvalue
        print(f"  CMH over article tertiles: OR {st.oddsratio_pooled:.2f}, one-sided P = {one_sided(np.log(st.oddsratio_pooled), p):.2g}")

    t = pd.read_csv(ROOT / "benchmark" / "epigen_extension" / "transitions.tsv", sep="\t")
    t = t[t["c2007"].isin(["Novel", "Hypothesized"]) & t["c2017"].notna()]
    high = t["c2017"].isin(["Existing", "Established"])
    a, b = high[t.c2007 == "Hypothesized"].sum(), (t.c2007 == "Hypothesized").sum()
    c, n = high[t.c2007 == "Novel"].sum(), (t.c2007 == "Novel").sum()
    p = stats.fisher_exact([[a, b - a], [c, n - c]], alternative="greater")[1]
    print(f"\n== epilepsy ten-year horizon (2007 -> 2017): Hypothesized {a}/{b} vs Novel {c}/{n} "
          f"Existing or Established, OR {(a * (n - c)) / ((b - a) * c):.1f}, one-sided Fisher P = {p:.2g}")


if __name__ == "__main__":
    main()
