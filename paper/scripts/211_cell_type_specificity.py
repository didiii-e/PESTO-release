"""Programme analysis 2: are PESTO high-evidence genes enriched among genes
specific to the cell types each disorder is expected to involve?

Plan fixed before the first run (10 October 2026):
- Expression: Human Protein Atlas single cell type data (rna_single_cell_type,
  nCPM per gene and cell type, all tissues), data/biology/, downloaded on 10
  October 2026 from https://www.proteinatlas.org/download/tsv/rna_single_cell_type.tsv.zip
- Specificity of a gene for cell type C, as Fig. 3b for tissues:
  log2((nCPM in C + 0.1) / (median nCPM over the other cell types + 0.1)).
- Within the 550-gene panel of Fig. 3, genes in the top 5% of that specificity
  are compared, for each phenotype, between high-evidence genes (PESTO mean
  score > 2.5) and the rest: Fisher's exact test, two-sided.
- Primary tests, one per hypothesis:
    ASD, epilepsy, schizophrenia, bipolar disorder: brain excitatory neurons,
      and brain inhibitory neurons;
    Alzheimer's disease: microglia;
    congenital heart disease: cardiomyocytes;
    type 2 diabetes: pancreatic islet cells (HPA does not separate beta cells).
- Secondary, declared now: Alzheimer's disease against oligodendrocytes,
  astrocytes and Schwann cells, which would explain why its genes are enriched in
  tibial nerve but not in brain (Extended Data Fig. 4).
- Attention control: the same contrast by the Cochran-Mantel-Haenszel test,
  stratified by tertile of PubMed records and gene origin (disease list or random).
- Sensitivity: top 10% and 20%.
- Exploratory: every phenotype against every cell type, Benjamini-Hochberg
  within phenotype.

Writes results/biology/cell_types_primary.tsv, cell_types_grid.tsv and
cell_types.log. No model call, no network.

  python3 scripts/211_cell_type_specificity.py
"""
from __future__ import annotations

import importlib.util
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

_spec = importlib.util.spec_from_file_location(
    "bp", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_biology_panel.py"))
bp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bp)

HPA = os.path.join(bp.DATA, "biology", "hpa_rna_single_cell_type.tsv.zip")
NEURONS = ["brain excitatory neurons", "brain inhibitory neurons"]
PRIMARY = {**{p: NEURONS for p in ["Autism Spectrum Disorder", "epilepsy", "schizophrenia",
                                   "bipolar disorder"]},
           "Alzheimer's disease": ["microglia"],
           "congenital heart disease": ["cardiomyocytes"],
           "type 2 diabetes": ["pancreatic islet cells"]}
SECONDARY = {"Alzheimer's disease": ["oligodendrocytes", "astrocytes", "schwann cells"]}
SHARES = [0.05, 0.10, 0.20]


def specificity(genes):
    h = pd.read_csv(HPA, sep="\t")
    m = h.pivot_table(index="Gene", columns="Cell type", values="nCPM", aggfunc="mean")
    m = m.reindex([g for g in genes if g in m.index])
    x = m.to_numpy(float)
    out = {}
    for j, c in enumerate(m.columns):
        others = np.median(np.delete(x, j, axis=1), axis=1)
        out[c] = np.log2((x[:, j] + 0.1) / (others + 0.1))
    return pd.DataFrame(out, index=m.index)


def test(d, spec, pheno, cell, share):
    g = d[d["phenotype"] == pheno].dropna(subset=["ensembl"])
    g = g[g["ensembl"].isin(spec.index)].reset_index(drop=True)
    inside = bp.top_share(spec.loc[g["ensembl"], cell].to_numpy(), share).to_numpy()
    o, p, k, n_in = bp.fisher(inside, g["high"])
    strata = g["pubs_t"].astype(str) + g["disease_gene"].astype(str)
    mh, p_mh = bp.cmh(inside, g["high"], strata)
    return {"phenotype": bp.SHORT[pheno], "cell_type": cell, "top": f"{int(share * 100)}%",
            "n_genes": len(g), "n_high": int(g["high"].sum()), "n_top": n_in, "high_in_top": k,
            "or": round(o, 2), "p": p, "or_mh": round(mh, 2), "p_mh": p_mh}


def main():
    d = bp.panel()
    spec = specificity(d["ensembl"].dropna().unique())
    rows = []
    for tier, plan in (("primary", PRIMARY), ("secondary", SECONDARY)):
        for pheno, cells in plan.items():
            for cell in cells:
                for share in SHARES:
                    rows.append({"tier": tier, **test(d, spec, pheno, cell, share)})
    prim = pd.DataFrame(rows)
    grid = []
    for pheno in bp.PHENOS:
        part = pd.DataFrame([test(d, spec, pheno, c, 0.05) for c in spec.columns])
        part["fdr"] = stats.false_discovery_control(part["p"].fillna(1))
        grid.append(part)
    grid = pd.concat(grid)
    os.makedirs(bp.OUT, exist_ok=True)
    prim.to_csv(os.path.join(bp.OUT, "cell_types_primary.tsv"), sep="\t", index=False)
    grid.to_csv(os.path.join(bp.OUT, "cell_types_grid.tsv"), sep="\t", index=False)
    with open(os.path.join(bp.OUT, "cell_types.log"), "w") as log:
        for f in (sys.stdout, log):
            print(f"{spec.shape[0]} panel genes with HPA data, {spec.shape[1]} cell types", file=f)
            print(prim.to_string(index=False), file=f)
            print("\nexploratory grid, top 5%, FDR < 0.05:", file=f)
            print(grid[grid["fdr"] < 0.05].sort_values(["phenotype", "p"]).to_string(index=False), file=f)


if __name__ == "__main__":
    main()
