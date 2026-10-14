"""Score the four modes run by scripts/166_modes_benchmark_140.py on the 140 pairs.

Same score, average precision, bootstrap interval (2000 draws) and one-sided
paired permutation (20000 swaps) as Fig. 2d and Extended Data Fig. 2a, from
PESTO-release/paper/scripts/141_score_fig2d_last_bar.py. The published scores
of the same 140 pairs (model knowledge, PESTO-titles, PESTO) are scored beside
the new runs as a check of how far a rerun moves them. No model call.

Writes results/modes_benchmark_140/ap.tsv (AP and 95% CI per mode, new and
published), tests.tsv (paired permutation P per comparison, each direction
and two-sided), cost_time.tsv (per mode) and arms.tsv (which arm each pair
went to).

  python3 scripts/167_modes_benchmark_scores.py
"""
import json
import os
import sys
from importlib import import_module

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
bench = import_module("166_modes_benchmark_140")

BASE = bench.BASE
MODES = ["knowledge", "titles", "abstracts", "fulltext"]
NAMES = {"knowledge": "Model knowledge", "titles": "PESTO-titles", "abstracts": "PESTO",
         "fulltext": "PESTO full text"}


def main():
    fig2d = bench.fig2d_module()
    ed2 = import_module_from(os.path.join(bench.RELEASE_PAPER, "scripts", "143_ed2_titles_data.py"))
    pairs = pd.read_csv(os.path.join(BASE, "pairs.tsv"), sep="\t")
    keys = [fig2d.key(g, p) for g, p in zip(pairs["gene"], pairs["phenotype"])]
    y = (pairs["label"] != "Absent").astype(int).to_numpy()

    vec, timing = {}, {}
    for m in MODES:
        t = pd.read_csv(os.path.join(BASE, m, "timing.tsv"), sep="\t")
        s = {fig2d.key(g, p): fig2d.score(e, x, h, n) for g, p, e, x, h, n in zip(
            t["gene"], t["phenotype"], t["p_established"], t["p_existing"],
            t["p_hypothesized"], t["p_novel"])}
        vec[NAMES[m]] = np.array([s[k] for k in keys])
        timing[m] = t

    lim_p, lim_k = fig2d.limited()
    abs_p, abs_k = fig2d.absent()
    lim_t, abs_t = ed2.titles_scores()
    published = {"Model knowledge": {**lim_k, **abs_k}, "PESTO-titles": {**lim_t, **abs_t},
                 "PESTO": {**lim_p, **abs_p}}
    for m, s in published.items():
        vec[f"{m} (published)"] = np.array([s[k] for k in keys])

    ap_rows = []
    for m, v in vec.items():
        lo, hi = fig2d.boot_ci(v, y, np.random.default_rng(1))
        ap_rows.append({"method": m, "run": "published" if "published" in m else "rerun",
                        "ap": round(fig2d.ap(v, y), 4), "lo": round(float(lo), 4),
                        "hi": round(float(hi), 4)})
        print(f"{m:32s} AP {ap_rows[-1]['ap']:.3f} ({lo:.3f}-{hi:.3f})")
    pd.DataFrame(ap_rows).to_csv(os.path.join(BASE, "ap.tsv"), sep="\t", index=False)

    # Each pair is tested in both directions; the two-sided P is twice the
    # smaller one-sided P, the form used for a claim of no difference.
    comparisons = [("PESTO", "PESTO-titles"), ("PESTO-titles", "Model knowledge"),
                   ("PESTO", "Model knowledge"), ("PESTO full text", "PESTO"),
                   ("PESTO full text", "Model knowledge"), ("PESTO", "PESTO (published)"),
                   ("PESTO-titles", "PESTO-titles (published)")]
    tests = []
    for a, b in comparisons:
        p_ab = fig2d.paired_perm(vec[a], vec[b], y, np.random.default_rng(7))
        p_ba = fig2d.paired_perm(vec[b], vec[a], y, np.random.default_rng(7))
        tests.append({"a": a, "b": b,
                      "ap_difference": round(fig2d.ap(vec[a], y) - fig2d.ap(vec[b], y), 4),
                      "p_a_better": round(p_ab, 5), "p_b_better": round(p_ba, 5),
                      "p_two_sided": round(min(1.0, 2 * min(p_ab, p_ba)), 5)})
        print(f"{a} vs {b}: dAP {tests[-1]['ap_difference']:+.3f}, "
              f"P(a>b) = {p_ab:.4f}, two-sided P = {tests[-1]['p_two_sided']:.4f}")
    pd.DataFrame(tests).to_csv(os.path.join(BASE, "tests.tsv"), sep="\t", index=False)

    rows = []
    for m in MODES:
        s = json.load(open(os.path.join(BASE, m, "summary.json")))
        t = timing[m]
        rows.append({"mode": m, "method": NAMES[m], "pairs": s["pairs"],
                     "usd_mean": t["usd"].mean(), "usd_sd": t["usd"].std(),
                     "seconds_median": t["seconds"].median(),
                     "batch_wall_min": s["batch_wall_s"] / 60,
                     "sequential_min": s["per_pair_sum_s"] / 60, "speedup": s["speedup"],
                     "read_mean": pd.to_numeric(t["read"], errors="coerce").mean()})
    ct = pd.DataFrame(rows)
    ct.to_csv(os.path.join(BASE, "cost_time.tsv"), sep="\t", index=False)
    print(ct.round(3).to_string(index=False))

    arms = pd.concat([timing[m][["mode", "gene", "phenotype", "arm"]] for m in MODES])
    arms.to_csv(os.path.join(BASE, "arms.tsv"), sep="\t", index=False)
    print(arms.groupby(["mode", "arm"]).size().to_string())
    return 0


def import_module_from(path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    sys.exit(main())
