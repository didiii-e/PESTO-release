"""Agreement between the three fresh runs of scripts/181_reproducibility_aou50.py.

For the literature verdict (rounded confidence-weighted mean, as in the paper),
the Open Targets verdict and the Max verdict, over the 50 pairs answered in all
three runs:
  - pairs with the same verdict in all three runs;
  - pairs whose three verdicts lie within one level of each other;
  - mean pairwise agreement (the three pairs of runs);
  - Fleiss' kappa over the four levels.
For the literature evidence score (1–4): the intraclass correlation ICC(2,1)
(two-way random effects, absolute agreement), the mean pairwise Spearman
correlation, and the median per-pair standard deviation across runs. Also how
often the disease-or-trait call that picks the prompt family agreed.

Writes results/reproducibility_aou50/summary.tsv and per_pair.tsv. No model call.

  python3 scripts/183_reproducibility_stats.py
"""
from __future__ import annotations

import csv
import itertools
import os
import sys

import numpy as np
from scipy.stats import spearmanr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "results", "reproducibility_aou50")
RUNS = ["run1", "run2", "run3"]
LEVEL = {"Novel": 1, "Hypothesized": 2, "Existing": 3, "Established": 4}


def load(run):
    rows = list(csv.DictReader(open(os.path.join(BASE, run, "pesto.tsv")), delimiter="\t"))
    out = {}
    for r in rows:
        if r["error"] or r["lit_mean"] not in LEVEL or r["open_targets_verdict"] not in LEVEL:
            continue
        w = [float(r[k] or 0) for k in ("p_novel", "p_hypothesized", "p_existing", "p_established")]
        lit, ot = LEVEL[r["lit_mean"]], LEVEL[r["open_targets_verdict"]]
        out[(r["gene"], r["phenotype"])] = {
            "lit": lit, "ot": ot, "max": max(lit, ot), "arm": r["arm"],
            "score": sum((i + 1) * x for i, x in enumerate(w)) / sum(w)}
    return out


def fleiss(m, k=4):
    """m: pairs x raters matrix of levels 1..k."""
    n, r = m.shape
    counts = np.stack([(m == j).sum(1) for j in range(1, k + 1)], 1)
    p_j = counts.sum(0) / (n * r)
    p_i = ((counts ** 2).sum(1) - r) / (r * (r - 1))
    pe = (p_j ** 2).sum()
    return (p_i.mean() - pe) / (1 - pe)


def icc21(y):
    n, k = y.shape
    gm = y.mean()
    msr = k * ((y.mean(1) - gm) ** 2).sum() / (n - 1)
    msc = n * ((y.mean(0) - gm) ** 2).sum() / (k - 1)
    sse = ((y - y.mean(1, keepdims=True) - y.mean(0, keepdims=True) + gm) ** 2).sum()
    mse = sse / ((n - 1) * (k - 1))
    return (msr - mse) / (msr + (k - 1) * mse + k * (msc - mse) / n)


def main():
    runs = [load(r) for r in RUNS]
    keys = sorted(set.intersection(*(set(r) for r in runs)))
    n = len(keys)
    rows = []
    for b, name in (("lit", "Literature"), ("ot", "Open Targets"), ("max", "Max")):
        m = np.array([[run[k][b] for run in runs] for k in keys])
        same = int((m.min(1) == m.max(1)).sum())
        within = int((m.max(1) - m.min(1) <= 1).sum())
        pair = np.mean([(m[:, a] == m[:, c]).mean() for a, c in itertools.combinations(range(3), 2)])
        rows.append({"branch": name, "n": n, "identical_all_three": same,
                     "within_one_level": within, "mean_pairwise_agreement": round(pair, 3),
                     "fleiss_kappa": round(fleiss(m), 3)})
    s = np.array([[run[k]["score"] for run in runs] for k in keys])
    rho = np.mean([spearmanr(s[:, a], s[:, c])[0] for a, c in itertools.combinations(range(3), 2)])
    arms = sum(len({run[k]["arm"] for run in runs}) == 1 for k in keys)
    score = {"icc21": round(icc21(s), 3), "mean_pairwise_spearman": round(rho, 3),
             "median_sd": round(float(np.median(s.std(1, ddof=1))), 3),
             "max_sd": round(float(s.std(1, ddof=1).max()), 3),
             "same_prompt_family": arms}
    with open(os.path.join(BASE, "summary.tsv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t")
        w.writeheader()
        w.writerows(rows)
        f.write("\n" + "\n".join(f"{k}\t{v}" for k, v in score.items()) + "\n")
    with open(os.path.join(BASE, "per_pair.tsv"), "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["gene", "phenotype"] + [f"{b}_{r}" for b in ("lit", "ot", "max", "score")
                                            for r in RUNS])
        for k in keys:
            w.writerow(list(k) + [runs[i][k][b] if b != "score" else round(runs[i][k][b], 3)
                                  for b in ("lit", "ot", "max", "score") for i in range(3)])
    missing = 50 - n
    print(f"{n} pairs answered in all three runs ({missing} missing)")
    for r in rows:
        print(r)
    print(score)
    return 0


if __name__ == "__main__":
    sys.exit(main())
