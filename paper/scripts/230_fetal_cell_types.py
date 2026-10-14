"""Programme analysis 2, fetal: are PESTO high-evidence genes enriched among genes
specific to fetal cell types, where the adult atlas (scripts/211) left congenital
heart disease and the developmental side of autism and epilepsy untested?

Plan fixed before the first run (11 October 2026):
- Expression: the human fetal atlas of Cao et al. (Science 2020; Descartes), 77
  cell types pooled over 15 organs, mean UMI per cell for each gene, as served by
  the UCSC Genome Browser (track fetalGeneAtlasCellType). Files in data/biology/,
  downloaded on 11 October 2026: cell_type.bb and cell_type.stats from
  https://hgdownload.soe.ucsc.edu/gbdb/hg38/bbi/fetalGeneAtlas/, and the order of
  the 77 values (barChartBars of the track in
  kent/src/hg/makeDb/trackDb/human/hg38/fetalGeneAtlas.ra).
- Expression is scaled to UMI per 10,000 per cell type (by its mean total UMI per
  cell), then, as for adult cell types and tissues: specificity =
  log2((expression in C + 0.1) / (median over the other cell types + 0.1)); top
  5% within the 550-gene panel; Fisher's exact test of high-evidence genes (PESTO
  mean score > 2.5) against the rest, two-sided.
- Primary tests:
    autism, epilepsy, schizophrenia, bipolar disorder: excitatory neurons and
      inhibitory neurons;
    Alzheimer's disease: microglia;
    congenital heart disease: cardiomyocytes and endocardial cells;
    type 2 diabetes: islet endocrine cells.
- Secondary, declared now: Alzheimer's disease against astrocytes,
  oligodendrocytes and Schwann cells; congenital heart disease against vascular
  endothelial cells, epicardial adipose cells, smooth muscle cells and stromal
  cells; autism and epilepsy against inhibitory interneurons and limbic system
  neurons.
- Attention control: Cochran-Mantel-Haenszel test stratified by tertile of PubMed
  records and gene origin. Sensitivity: top 10% and 20%. Exploratory: every
  phenotype against every cell type, Benjamini-Hochberg within phenotype.

Writes results/biology/fetal_cell_types_primary.tsv, fetal_cell_types_grid.tsv
and fetal_cell_types.log. No model call, no network.

  python3 scripts/230_fetal_cell_types.py
"""
from __future__ import annotations

import importlib.util
import os
import sys

import numpy as np
import pandas as pd
import pyBigWig
from scipy import stats

_spec = importlib.util.spec_from_file_location(
    "bp", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_biology_panel.py"))
bp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bp)

DIR = os.path.join(bp.DATA, "biology")
BB = os.path.join(DIR, "descartes_fetal_cell_type.bb")
STATS = os.path.join(DIR, "descartes_fetal_cell_type.stats")
BARS = os.path.join(DIR, "descartes_fetal_cell_type_bars.txt")
NEURONS = ["excitatory_neuron", "inhibitory_neuron"]
PRIMARY = {**{p: NEURONS for p in ["Autism Spectrum Disorder", "epilepsy", "schizophrenia",
                                   "bipolar disorder"]},
           "Alzheimer's disease": ["microglial_cell"],
           "congenital heart disease": ["cardiomyocyte", "endocardial_cell"],
           "type 2 diabetes": ["islet_endocrine_cell"]}
SECONDARY = {"Alzheimer's disease": ["astrocyte", "oligodendrocyte", "Schwann_cell"],
             "congenital heart disease": ["vascular_endothelial_cell", "epicardial_adipose_cell",
                                          "smooth_muscle_cell", "stromal_cell"],
             "Autism Spectrum Disorder": ["inhibitory_interneuron", "limbic_system_neuron"],
             "epilepsy": ["inhibitory_interneuron", "limbic_system_neuron"]}
SHARES = [0.05, 0.10, 0.20]


def cell_types():
    """Bar name -> (cell class, mean total UMI per cell)."""
    bars = [l.strip() for l in open(BARS) if l.strip()]
    s = pd.read_csv(STATS, sep="\t")
    s.columns = [c.lstrip("#") for c in s.columns]
    by = {}
    for _, r in s.iterrows():
        for k in (r["cell_type"].replace(" ", "_"), r["organ and cell type"].replace(" ", "_")):
            by.setdefault(k, (r["cell_class"], float(r["mean_total"])))
    return bars, {b: by[b] for b in bars}


def specificity(ensembl):
    bars, meta = cell_types()
    want = {e: None for e in ensembl}
    b = pyBigWig.open(BB)
    rows = {}
    for chrom in b.chroms():
        for _, _, rest in b.entries(chrom, 0, b.chroms()[chrom]) or []:
            f = rest.split("\t")
            eid = f[0].split(".")[0]
            if eid in want and eid not in rows:
                rows[eid] = np.array(f[5].split(","), float)
    x = pd.DataFrame(rows, index=bars).T
    x = x / np.array([meta[c][1] for c in bars]) * 1e4
    v = x.to_numpy(float)
    out = {c: np.log2((v[:, j] + 0.1) / (np.median(np.delete(v, j, axis=1), axis=1) + 0.1))
           for j, c in enumerate(bars)}
    return pd.DataFrame(out, index=x.index), meta


def test(d, spec, pheno, cell, share):
    g = d[(d["phenotype"] == pheno) & d["ensembl"].isin(spec.index)].reset_index(drop=True)
    inside = bp.top_share(spec.loc[g["ensembl"], cell].to_numpy(), share).to_numpy()
    o, p, k, n_in = bp.fisher(inside, g["high"])
    strata = g["pubs_t"].astype(str) + g["disease_gene"].astype(str)
    mh, p_mh = bp.cmh(inside, g["high"], strata)
    return {"phenotype": bp.SHORT[pheno], "cell_type": cell, "top": f"{int(share * 100)}%",
            "n_genes": len(g), "n_high": int(g["high"].sum()), "n_top": n_in, "high_in_top": k,
            "or": round(o, 2), "p": p, "or_mh": round(mh, 2), "p_mh": p_mh}


def main():
    d = bp.panel()
    spec, meta = specificity(d["ensembl"].dropna().unique())
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
        part["cell_class"] = part["cell_type"].map(lambda c: meta[c][0])
        grid.append(part)
    grid = pd.concat(grid)
    prim.to_csv(os.path.join(bp.OUT, "fetal_cell_types_primary.tsv"), sep="\t", index=False)
    grid.to_csv(os.path.join(bp.OUT, "fetal_cell_types_grid.tsv"), sep="\t", index=False)
    with open(os.path.join(bp.OUT, "fetal_cell_types.log"), "w") as log:
        for f in (sys.stdout, log):
            print(f"{spec.shape[0]} panel genes in the fetal atlas, {spec.shape[1]} cell types", file=f)
            print(prim.to_string(index=False), file=f)
            print("\nexploratory grid, top 5%, FDR < 0.05:", file=f)
            print(grid[grid["fdr"] < 0.05].sort_values(["phenotype", "p"]).to_string(index=False), file=f)


if __name__ == "__main__":
    main()
