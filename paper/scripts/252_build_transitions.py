"""Build the class-transition tables of Fig. 3b: for each gene of the two cohorts,
its PESTO literature class at the start date and on 2026/10/11.

  Epilepsy: Dinan's 61 Novel or Hypothesized genes (start class from her 2010 runs,
  experiments/biological_proximity_pilot/replication_epigen_v2/final_cohort.tsv)
  and the 127 genes of scripts/248_draw_epigen_extension.py (benchmark/
  epigen_extension/pesto_2010.tsv), all scored on 2026/10/11 (pesto_2026.tsv).
  Autism: the 200 genes of scripts/245_draw_asd_denovo2014.py, scored on
  2014/09/30 and 2026/10/11 (benchmark/asd_denovo2014/pesto_{2014,2026}.tsv).

Writes benchmark/epigen_extension/transitions.tsv (gene, c2010, source, c2026) and
benchmark/asd_denovo2014/transitions.tsv (gene, c2014, c2026, asc2026).

  python3 scripts/252_build_transitions.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / "benchmark"
DINAN = ROOT / "experiments" / "biological_proximity_pilot" / "replication_epigen_v2" / "final_cohort.tsv"


def classes(path, name):
    return pd.read_csv(path, sep="\t")[["gene", "lit_mean"]].rename(columns={"lit_mean": name})


def main():
    din = pd.read_csv(DINAN, sep="\t")[["gene", "verdict_2010"]].rename(columns={"verdict_2010": "c2010"})
    epi = pd.concat([din.assign(source="dinan"),
                     classes(B / "epigen_extension" / "pesto_2010.tsv", "c2010").assign(source="added")])
    epi = epi.merge(classes(B / "epigen_extension" / "pesto_2026.tsv", "c2026"), on="gene", how="left")
    epi.to_csv(B / "epigen_extension" / "transitions.tsv", sep="\t", index=False)

    asd = classes(B / "asd_denovo2014" / "pesto_2014.tsv", "c2014").merge(
        classes(B / "asd_denovo2014" / "pesto_2026.tsv", "c2026"), on="gene").merge(
        pd.read_csv(B / "asd_denovo2014" / "cohort.tsv", sep="\t")[["gene", "asc2026"]], on="gene")
    asd.to_csv(B / "asd_denovo2014" / "transitions.tsv", sep="\t", index=False)
    print(f"epilepsy {len(epi)} genes, autism {len(asd)} genes")


if __name__ == "__main__":
    main()
