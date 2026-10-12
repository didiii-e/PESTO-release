"""Draw the autism genes of the baseline-class benchmark: does a gene PESTO calls
Hypothesized for autism before its de novo loss-of-function report reach Existing
or Established later more often than one it calls Novel? The test of Dinan's
EPIGEN epilepsy benchmark (experiments/biological_proximity_pilot/
replication_epigen_v2/endpoint2020/pesto_class_benchmark/), on a cohort fixed in 2014.

The cohort is every gene with a de novo loss-of-function variant (stop-gained,
frameshift, splice donor or acceptor, start or stop lost) in an autistic proband
of the two exome studies published in October 2014, Iossifov et al. (Nature 515,
216; PMID 25363768) and De Rubeis et al. (Nature 515, 209; PMID 25363760), as
recorded in denovo-db 1.6.1 (data/raw/denovo_db/). Symbols are brought to the
current HGNC approved symbol through previous and alias symbols. 200 genes are
drawn without replacement with a fixed seed; the rest are kept for later.

Writes <out>/cohort.tsv (all genes, with whether they are drawn and whether they
are in the ASC 2026 list) and <out>/pairs.tsv (the drawn genes x autism).

  python3 scripts/245_draw_asd_denovo2014.py
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DDB = ROOT / "data" / "raw" / "denovo_db"
STUDIES = ["Iossifov", "DeRubeis2014"]
LOF = {"stop-gained", "frameshift", "splice-donor", "splice-acceptor", "stop-gained-near-splice",
       "frameshift-near-splice", "start-lost", "stop-lost"}
PHENOTYPE = "Autism Spectrum Disorder"


def hgnc_map():
    h = pd.read_csv(ROOT / "data" / "hgnc_complete_set.txt", sep="\t", dtype=str, low_memory=False)
    h = h[h["status"] == "Approved"]
    approved = set(h["symbol"])
    other = {}
    for col in ("prev_symbol", "alias_symbol"):
        for sym, names in zip(h["symbol"], h[col].fillna("")):
            for n in names.split("|"):
                if n and n not in approved:
                    other.setdefault(n, set()).add(sym)
    return approved, {k: next(iter(v)) for k, v in other.items() if len(v) == 1}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20261011)
    ap.add_argument("--out", default="benchmark/asd_denovo2014")
    a = ap.parse_args()

    d = pd.concat([pd.read_csv(DDB / f, sep="\t", skiprows=1, low_memory=False)
                   for f in ("denovo-db.ssc-samples.variants.tsv.gz",
                             "denovo-db.non-ssc-samples.variants.tsv.gz")])
    d = d[d["StudyName"].isin(STUDIES) & (d["PrimaryPhenotype"] == "autism")]
    d = d[d["FunctionClass"].map(lambda fc: any(c in LOF for c in str(fc).split(",")))]
    carriers = d.dropna(subset=["Gene"]).groupby("Gene")["#SampleID"].nunique()

    approved, other = hgnc_map()
    rows = []
    for sym, n in carriers.items():
        cur = sym if sym in approved else other.get(sym)
        if cur:
            rows.append({"gene": cur, "denovo_db_symbol": sym, "lof_probands": n})
    c = pd.DataFrame(rows).groupby("gene", as_index=False).agg(
        denovo_db_symbol=("denovo_db_symbol", "|".join), lof_probands=("lof_probands", "sum"))
    asc = set(pd.read_csv(ROOT / "data" / "raw" / "ASC_GeneList_12082026.txt")["Gene"].str.strip())
    c["asc2026"] = c["gene"].isin(asc)
    c = c.sort_values("gene").reset_index(drop=True)
    pick = np.random.default_rng(a.seed).choice(len(c), size=a.n, replace=False)
    c["drawn"] = False
    c.loc[pick, "drawn"] = True

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    c.to_csv(out / "cohort.tsv", sep="\t", index=False)
    drawn = c[c["drawn"]]
    pd.DataFrame({"gene": drawn["gene"], "phenotype": PHENOTYPE}).to_csv(out / "pairs.tsv", sep="\t", index=False)
    print(f"{len(carriers)} denovo-db symbols, {len(c)} HGNC genes ({len(carriers) - len(rows)} unmapped); "
          f"{c['asc2026'].sum()} in ASC 2026. Drawn {len(drawn)}, {drawn['asc2026'].sum()} in ASC 2026.")


if __name__ == "__main__":
    main()
