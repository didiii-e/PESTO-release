"""The 550-gene panel of Fig. 3 with what every programme analysis controls for.

Shared by the biological programme scripts (211 to 213). One row per gene and
phenotype: the PESTO mean score, whether the gene is high-evidence (score > 2.5,
as in Fig. 3), log10 PubMed records (NCBI gene2pubmed), LOEUF, and whether the
gene came from a disease list or was drawn at random. Also the two tests the
expression analyses share: Fisher's exact test and the Cochran-Mantel-Haenszel
test stratified by publication tertile and gene origin.
"""
from __future__ import annotations

import importlib.util
import json
import os

import numpy as np
import pandas as pd
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "results", "biology")
PHENOS = ["Autism Spectrum Disorder", "epilepsy", "schizophrenia", "bipolar disorder",
          "Alzheimer's disease", "congenital heart disease", "type 2 diabetes"]
SHORT = dict(zip(PHENOS, ["ASD", "EPI", "SCZ", "BD", "AD", "CHD", "T2D"]))
HIGH = 2.5

_spec = importlib.util.spec_from_file_location(
    "s202", os.path.join(ROOT, "scripts", "202_subthreshold_signal.py"))
s202 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s202)


def panel():
    scores = pd.read_csv(os.path.join(ROOT, "results", "fig3_universe550_meancall_scores.tsv"), sep="\t")
    scores = scores[scores["phenotype"].isin(PHENOS)].dropna(subset=["lit_score"]).copy()
    ref = json.load(open(os.path.join(DATA, "genelists", "reference_sets.json")))
    disease = s202.disease_list_genes(ref, scores)
    hgnc, _ = s202.hgnc_table()
    pubs = s202.pubmed_counts().set_index("entrez_id")["pubmed_records"]
    loeuf = pd.read_csv(os.path.join(DATA, "loeuf_scores.tsv"), sep="\t") \
        .drop_duplicates("gene_symbol").set_index("gene_symbol")["LOEUF"]
    d = scores[["gene", "phenotype", "lit_score"]].rename(columns={"lit_score": "score"})
    d["gene"] = d["gene"].str.upper()
    d["high"] = d["score"] > HIGH
    entrez = hgnc["entrez_id"].reindex(d["gene"]).to_numpy()
    d["log_pubs"] = np.log10(1 + pd.Series(entrez).map(pubs).fillna(0).to_numpy(float))
    d["loeuf"] = d["gene"].map(loeuf)
    d["disease_gene"] = d["gene"].isin({g.upper() for g in disease})
    d["ensembl"] = hgnc["ensembl_gene_id"].reindex(d["gene"]).to_numpy()
    d["pubs_t"] = pd.qcut(d.groupby("gene")["log_pubs"].transform("first"), 3, labels=False,
                          duplicates="drop")
    return d.reset_index(drop=True)


def fisher(inside, high):
    """OR and two-sided P of high-evidence genes among `inside` genes."""
    inside, high = np.asarray(inside, bool), np.asarray(high, bool)
    t = [[(inside & high).sum(), (inside & ~high).sum()],
         [(~inside & high).sum(), (~inside & ~high).sum()]]
    o, p = stats.fisher_exact(t)
    return o, p, int(t[0][0]), int(inside.sum())


def cmh(inside, high, strata):
    """Mantel-Haenszel OR and two-sided CMH P (continuity-corrected) over strata."""
    df = pd.DataFrame({"x": np.asarray(inside, bool), "y": np.asarray(high, bool), "s": strata})
    num = den = a_sum = e_sum = v_sum = 0.0
    for _, g in df.groupby("s"):
        n = len(g)
        if n < 2:
            continue
        a = (g.x & g.y).sum(); b = (g.x & ~g.y).sum(); c = (~g.x & g.y).sum(); dd = (~g.x & ~g.y).sum()
        num += a * dd / n; den += b * c / n
        r1, c1 = a + b, a + c
        a_sum += a; e_sum += r1 * c1 / n
        v_sum += r1 * (n - r1) * c1 * (n - c1) / (n * n * (n - 1)) if n > 1 else 0
    if v_sum == 0:
        return np.nan, np.nan
    chi = (abs(a_sum - e_sum) - 0.5) ** 2 / v_sum
    return (num / den if den else np.inf), stats.chi2.sf(chi, 1)


def top_share(values, share):
    """Genes in the top `share` of `values` (highest first), within the panel."""
    v = pd.Series(values)
    k = max(1, int(round(share * v.notna().sum())))
    return v.rank(ascending=False, method="first") <= k
