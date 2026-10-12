"""Extend Dinan's EPIGEN epilepsy cohort of the baseline-class benchmark to 200
screened genes, as many as the autism cohort (scripts/245_draw_asd_denovo2014.py).

Dinan screened the first 73 genes of her frozen random order (SHA-256 of the
Ensembl ID, column screening_rank of experiments/biological_proximity_pilot/
replication_epigen_v2/audit/eligible_universe.tsv, 271 genes) and kept the 61
Novel or Hypothesized ones. This takes ranks 74 to 200 of that same order, so the
200 genes are the ones she would have screened by going on; hers are not rerun.

Writes <out>/cohort.tsv and <out>/pairs.tsv (the 127 genes x epilepsy), to be run
at --max-date 2010/12/31 and 2020/12/31 like hers.

  python3 scripts/248_draw_epigen_extension.py
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = ROOT / "experiments" / "biological_proximity_pilot" / "replication_epigen_v2" / "audit" / "eligible_universe.tsv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", type=int, default=74)
    ap.add_argument("--last", type=int, default=200)
    ap.add_argument("--out", default="benchmark/epigen_extension")
    a = ap.parse_args()
    u = pd.read_csv(UNIVERSE, sep="\t")
    c = u[u["screening_rank"].between(a.first, a.last)][["gene", "canonical_identifier", "hgnc_id", "screening_rank"]]
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    c.to_csv(out / "cohort.tsv", sep="\t", index=False)
    pd.DataFrame({"gene": c["gene"], "phenotype": "epilepsy"}).to_csv(out / "pairs.tsv", sep="\t", index=False)
    print(f"{len(u)} eligible genes; ranks {a.first}-{a.last}: {len(c)} genes written to {out}")


if __name__ == "__main__":
    main()
