"""Run-to-run reproducibility of PESTO on 50 All of Us–GeneBass associations.

Draws 50 of the 248 All of Us–GeneBass associations of Fig. 1 (study
'All of Us-GeneBass' or 'Both' in Supplementary Table 1) with a fixed seed, and
runs the released package on them three times, from scratch each time: the
literature branch with --no-cache (term expansion, searches, banding and
reading are all redone) and the Open Targets branch, which has no cache. The
arm is `auto`, as in Fig. 1, so the disease-or-trait call is redone too. No
earlier run is reused.

Writes results/reproducibility_aou50/input.tsv and run1/, run2/, run3/, each
with pesto.tsv and the evidence of every pair. About $20 for the three runs.

  python3 scripts/181_reproducibility_aou50.py            # draw and run all three
  python3 scripts/181_reproducibility_aou50.py --runs 2   # only run2
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results", "reproducibility_aou50")
TABLE = os.path.join(ROOT, "results", "supplementary_table1.tsv")
PESTO = os.path.join(os.path.dirname(ROOT), "PESTO-release", ".venv", "bin", "pesto")
SEED = 20261009
N = 50


def draw():
    rows = list(csv.DictReader(open(TABLE), delimiter="\t"))
    pool = [r for r in rows if r["study"] in ("All of Us-GeneBass", "Both")]
    picked = random.Random(SEED).sample(pool, N)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "input.tsv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["gene", "phenotype"])
        for r in picked:
            w.writerow([r["gene"], r["phenotype"]])
    print(f"{len(pool)} All of Us–GeneBass associations, {N} drawn -> {path}")
    return path


def run(i, inp, workers):
    d = os.path.join(OUT, f"run{i}")
    os.makedirs(d, exist_ok=True)
    cmd = [PESTO, "--bench", inp, "--no-cache", "--workers", str(workers),
           "--out", os.path.join(d, "pesto.tsv"), "--data-dir", d, "--quiet"]
    t0 = time.time()
    with open(os.path.join(d, "run.log"), "w") as log:
        code = subprocess.call(cmd, stdout=log, stderr=subprocess.STDOUT)
    print(f"run{i}: exit {code}, {time.time() - t0:.0f} s")
    return code


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, nargs="*", default=[1, 2, 3])
    ap.add_argument("--workers", type=int, default=30)
    args = ap.parse_args()
    inp = os.path.join(OUT, "input.tsv")
    if not os.path.exists(inp):
        inp = draw()
    for i in args.runs:
        if run(i, inp, args.workers):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
