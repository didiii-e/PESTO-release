#!/usr/bin/env python3
"""Do the constraint and tissue enrichments of Fig. 4 survive adjustment for how
much each gene has been studied?

Question (Dinan's tracker, "rather than research attention alone"): high-evidence
genes might be enriched among constrained or tissue-specific genes only because
they are well-studied genes. For each phenotype, the Fig. 4 test is repeated with
publication counts (NCBI gene2pubmed, log10(1 + records)) taken into account in
two ways:

- logistic regression, high-evidence ~ in top set + log10 publications;
- Cochran-Mantel-Haenszel test stratified by publication tertile and gene origin
  (disease list or random draw), as for the cell-type analyses (211, 230).

Sets, as in Fig. 4 and Extended Data Fig. 4a: the 66 most constrained of the 660
panel genes with a LOEUF value (lowest decile within the panel), and the top 5%
of panel genes by GTEx specificity, log2((median TPM in the tissue + 0.1) /
(median TPM in the other samples + 0.1)), for brain, heart, liver and pancreas.

Run from results/panel670 (the root is the parent of scripts/):
  cp scripts/269_publication_adjusted_enrichment.py results/panel670/scripts/
  cd results/panel670 && python3 scripts/269_publication_adjusted_enrichment.py
Writes results/biology/publication_adjusted_enrichment.tsv.
"""
from __future__ import annotations

import gzip
import importlib.util
import os

import numpy as np
import pandas as pd
import statsmodels.api as sm

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("bp", os.path.join(HERE, "_biology_panel.py"))
bp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bp)

TISSUES = ["Brain", "Heart", "Liver", "Pancreas"]
OUT = os.path.join(bp.OUT, "publication_adjusted_enrichment.tsv")


def ntile_top(values, n, lowest=False):
    """dplyr::ntile(values, n) == n (or == 1 with lowest=True), ties by order."""
    v = pd.Series(values)
    r = (v if not lowest else -v).rank(method="first").to_numpy() - 1
    tile = np.floor(r * n / len(v)).astype(int) + 1
    return tile == n


def gtex_specificity(genes):
    with gzip.open(os.path.join(bp.DATA, "gtex_median_tpm.gct.gz"), "rt") as f:
        g = pd.read_csv(f, sep="\t", skiprows=2)
    cols = [c for c in g.columns if c not in ("Name", "Description")]
    g["gene"] = g["Description"].str.upper()
    g["mx"] = g[cols].max(axis=1)
    g = g[g["gene"].isin(genes)].sort_values("mx", ascending=False).drop_duplicates("gene")
    m = g.set_index("gene")[cols]
    grp = pd.Series([c.split(" - ")[0] for c in cols], index=cols)
    out = {}
    for t in TISSUES:
        inn = grp.index[grp == t]
        oth = grp.index[grp != t]
        out[t] = np.log2((m[inn].median(axis=1) + 0.1) / (m[oth].median(axis=1) + 0.1))
    return pd.DataFrame(out)


def tests(d, inside, label):
    rows = []
    for ph in bp.PHENOS:
        s = d[d["phenotype"] == ph].copy()
        s["inside"] = s["gene"].map(inside)
        s = s.dropna(subset=["inside"])
        s["inside"] = s["inside"].astype(bool)
        o, p, k, n_in = bp.fisher(s["inside"], s["high"])
        x = sm.add_constant(s[["inside", "log_pubs"]].astype(float))
        fit = sm.Logit(s["high"].astype(float), x).fit(disp=0)
        lo, hi = np.exp(fit.conf_int().loc["inside"])
        strata = s["pubs_t"].astype(str) + s["disease_gene"].astype(str)
        mh, p_mh = bp.cmh(s["inside"], s["high"], strata)
        rows.append({"set": label, "phenotype": bp.SHORT[ph], "n_genes": len(s), "n_in_set": n_in,
                     "high_in_set": k, "or": o, "p": p,
                     "or_adj_pubs": float(np.exp(fit.params["inside"])), "lo_adj": lo, "hi_adj": hi,
                     "p_adj_pubs": float(fit.pvalues["inside"]), "or_mh": mh, "p_mh": p_mh})
    return rows


def main():
    d = bp.panel()
    genes = d["gene"].unique()
    lt = pd.read_csv(os.path.join(bp.DATA, "loeuf_scores.tsv"), sep="\t")
    lt = lt.assign(gene=lt["gene_symbol"].str.upper()).dropna(subset=["LOEUF"]).drop_duplicates("gene")
    lo = lt[lt["gene"].isin(genes)].set_index("gene")["LOEUF"]
    rows = tests(d, pd.Series(ntile_top(lo.to_numpy(), 10, lowest=True), index=lo.index),
                 "top 10% constrained")
    spec = gtex_specificity(set(genes))
    for t in TISSUES:
        rows += tests(d, pd.Series(ntile_top(spec[t].to_numpy(), 20), index=spec.index), f"top 5% {t}")
    res = pd.DataFrame(rows)
    res.to_csv(OUT, sep="\t", index=False)
    show = res[(res["set"].isin(["top 10% constrained", "top 5% Brain"])) |
               ((res["set"] == "top 5% Heart") & (res["phenotype"] == "CHD")) |
               ((res["set"].isin(["top 5% Liver", "top 5% Pancreas"])) & (res["phenotype"] == "T2D"))]
    with pd.option_context("display.width", 200, "display.float_format", "{:.3g}".format):
        print(show[["set", "phenotype", "n_in_set", "high_in_set", "or", "p", "or_adj_pubs", "lo_adj",
                    "hi_adj", "p_adj_pubs", "or_mh", "p_mh"]].to_string(index=False))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
