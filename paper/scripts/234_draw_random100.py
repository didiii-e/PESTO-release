"""Draw more random genes for the Fig. 3 panel, by the rule of the 200 already in
it (scripts/92_fig3_random50.py and 106_fig3_random50b.py): protein-coding genes
with PEPPER features, a LOEUF value and at least one GO or SynGO term, excluding
every gene of the panel given, drawn without replacement with a fixed seed.

Writes <out>/genes.tsv and pairs.tsv (the genes x the seven phenotypes of Fig. 3).

  python3 scripts/234_draw_random100.py
      100 genes, seed 20261011, excluding results/panel570/, into
      benchmark/fig3_add_random100/ (the draw of 11 October 2026)
  python3 scripts/234_draw_random100.py --n 30 --seed 20261012 --set random30_oct \\
      --panel results/panel670 --out benchmark/fig3_add_random30
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("r92", ROOT / "scripts" / "92_fig3_random50.py")
r92 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r92)

PHENOS = ["Autism Spectrum Disorder", "epilepsy", "schizophrenia", "bipolar disorder",
          "Alzheimer's disease", "congenital heart disease", "type 2 diabetes"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20261011)
    ap.add_argument("--set", default="random100_oct")
    ap.add_argument("--panel", default="results/panel570")
    ap.add_argument("--out", default="benchmark/fig3_add_random100")
    a = ap.parse_args()
    panel_file = ROOT / a.panel / "results" / "fig3_universe550_meancall_scores.tsv"
    out = ROOT / a.out
    panel = set(pd.read_csv(panel_file, sep="\t").gene.str.upper())
    pool = sorted(r92.annotated() - panel)
    pick = sorted(np.random.default_rng(a.seed).choice(pool, a.n, replace=False).tolist())
    out.mkdir(parents=True, exist_ok=True)
    with (out / "genes.tsv").open("w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["gene", "set"])
        w.writerows([g, a.set] for g in pick)
    with (out / "pairs.tsv").open("w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["gene", "phenotype", "set"])
        w.writerows([g, p, a.set] for g in pick for p in PHENOS)
    print(f"pool {len(pool)}, panel {len(panel)}, drew {len(pick)}, seed {a.seed}")
    print(" ".join(pick))


if __name__ == "__main__":
    main()
