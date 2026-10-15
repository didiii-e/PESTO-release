"""Build the class-transition tables of Fig. 3b: for each gene of the two cohorts,
its PESTO literature class at the start date and on 2026/10/11.

  Epilepsy: the 200 EPIGEN genes, all scored with the same pipeline on 2007/09/30,
  the month before the EPIGEN gene list was published (benchmark/epigen_extension/
  pesto_2007.tsv), on 2017/09/30 for those Novel or Hypothesized in 2007 (pesto_2017.tsv,
  the ten-year horizon), and on 2026/10/11 (pesto_2026.tsv, and pesto_2026_dinan_ee.tsv
  for 12 of the genes Dinan screened). The earlier start class, 2010/12/31, is kept as
  c2010: Dinan's runs for her 73 genes (experiments/biological_proximity_pilot/
  replication_epigen_v2/screening_results.json) and pesto_2010.tsv for the other 127.
  Autism: the 200 genes of scripts/245_draw_asd_denovo2014.py, scored on
  2014/09/30 and 2026/10/11 (benchmark/asd_denovo2014/pesto_{2014,2026}.tsv).

Writes benchmark/epigen_extension/transitions.tsv (gene, c2007, c2010, source, c2017,
c2026) and
benchmark/asd_denovo2014/transitions.tsv (gene, c2014, c2026, asc2026).

  python3 scripts/252_build_transitions.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / "benchmark"
DINAN = ROOT / "experiments" / "biological_proximity_pilot" / "replication_epigen_v2" / "screening_results.json"


def classes(path, name):
    return pd.read_csv(path, sep="\t")[["gene", "lit_mean"]].rename(columns={"lit_mean": name})


def main():
    din = pd.DataFrame([{"gene": r["gene"], "c2010": r["verdict"]} for r in json.load(open(DINAN))
                        if r.get("verdict")])
    epi = pd.concat([din.assign(source="dinan"),
                     classes(B / "epigen_extension" / "pesto_2010.tsv", "c2010").assign(source="added")])
    end = pd.concat([classes(B / "epigen_extension" / "pesto_2026.tsv", "c2026"),
                     classes(B / "epigen_extension" / "pesto_2026_dinan_ee.tsv", "c2026")])
    epi = epi.merge(end, on="gene", how="left")
    epi = epi.merge(classes(B / "epigen_extension" / "pesto_2007.tsv", "c2007"), on="gene", how="left")
    epi = epi.merge(classes(B / "epigen_extension" / "pesto_2017.tsv", "c2017"), on="gene", how="left")
    epi = epi[["gene", "c2007", "c2010", "source", "c2017", "c2026"]]
    epi.to_csv(B / "epigen_extension" / "transitions.tsv", sep="\t", index=False)

    asd = classes(B / "asd_denovo2014" / "pesto_2014.tsv", "c2014").merge(
        classes(B / "asd_denovo2014" / "pesto_2026.tsv", "c2026"), on="gene").merge(
        pd.read_csv(B / "asd_denovo2014" / "cohort.tsv", sep="\t")[["gene", "asc2026"]], on="gene")
    asd.to_csv(B / "asd_denovo2014" / "transitions.tsv", sep="\t", index=False)
    print(f"epilepsy {len(epi)} genes, autism {len(asd)} genes")


if __name__ == "__main__":
    main()
