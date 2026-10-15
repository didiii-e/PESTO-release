#!/usr/bin/env python3
"""Supplementary Figure 4 (Supplementary Material Note 3): agreement between
manual curation and the Open Targets branch of PESTO on 49 gene-phenotype
pairs, before and after the curation was revised. Benchmark, curation and
figure by Dinan Elsyad (branch novel-similarity-2026, commit 39b16601); this
script is her build_analysis.py and build_grouped_bars.py with the paths made
relative, so that it runs from the repository root or from PESTO-release/paper.

Reads results/ot_manual_benchmark/plot_data.json (50 pairs: PESTO's Open
Targets verdict, initial and revised manual class; one pair has no saved
verdict) and literature_disagreement_audit.json (the literature verdicts of the
six pairs still in disagreement). Prints the numbers the note gives, writes
results/ot_manual_benchmark/metrics.json and
figures/figure_supp_ot_manual_agreement.{png,pdf}.

  python3 scripts/320_figure_supp_ot_manual.py
"""
from __future__ import annotations

import json
import os
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import spearmanr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "results", "ot_manual_benchmark")
OUT = os.path.join(ROOT, "figures", "figure_supp_ot_manual_agreement")
CODE = {"Novel": 1, "Hypothesized": 2, "Existing": 3, "Established": 4}
EXPECTED = {"initial": (39, 0.900), "revised": (43, 0.932)}


def metrics(pairs):
    out = {}
    for label, key in (("initial", "original"), ("revised", "adjusted")):
        diffs = [abs(CODE[p["pesto"]] - CODE[p[key]]) for p in pairs]
        c = Counter(diffs)
        rho = float(spearmanr([CODE[p["pesto"]] for p in pairs], [CODE[p[key]] for p in pairs]).statistic)
        n = len(pairs)
        out[label] = {"n": n, "difference_counts": {str(i): c[i] for i in range(4)},
                      "exact_count": c[0], "exact_percent": 100 * c[0] / n,
                      "within_one_count": sum(d <= 1 for d in diffs),
                      "within_one_percent": 100 * sum(d <= 1 for d in diffs) / n, "spearman_rho": rho}
        assert (c[0], round(rho, 3)) == EXPECTED[label], (label, c[0], rho)
    return out


def literature_proximity():
    audit = json.load(open(os.path.join(DATA, "literature_disagreement_audit.json")))
    tally = Counter()
    for r in audit["results"]:
        lit, man, ot = (CODE[r[k]] for k in ("literature_category", "frozen_human_category",
                                             "open_targets_category"))
        d_man, d_ot = abs(lit - man), abs(lit - ot)
        tally["closer to manual" if d_man < d_ot else "closer to Open Targets" if d_ot < d_man else "tied"] += 1
    return dict(tally)


def draw(m):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12, "pdf.fonttype": 42})
    fig, ax = plt.subplots(figsize=(7.2, 5.8))
    fig.subplots_adjust(left=.14, right=.97, top=.88, bottom=.20)
    x, w = np.array([0, 1]), .30
    for offset, key, color, label, countkey in (
            (-w / 2, "exact_percent", "#7997ad", "Exact agreement", "exact_count"),
            (w / 2, "within_one_percent", "#267e8a", "Within one class", "within_one_count")):
        vals = [m[k][key] for k in ("initial", "revised")]
        ax.bar(x + offset, vals, width=w - .025, color=color, label=label)
        for i, (val, k) in enumerate(zip(vals, ("initial", "revised"))):
            ax.text(i + offset, val + 2, f"{val:.1f}%", ha="center", va="bottom", fontsize=14, weight="bold",
                    color="#213c4d")
            ax.text(i + offset, val - 7, f"{m[k][countkey]}/{m[k]['n']}", ha="center", va="center", fontsize=10,
                    color="white")
    ax.set_ylim(0, 112)
    ax.set_xlim(-.55, 1.55)
    ax.set_yticks([0, 25, 50, 75, 100], labels=["0%", "25%", "50%", "75%", "100%"])
    ax.set_xticks(x, labels=["Initial manual curation", "Revised manual curation"])
    ax.set_ylabel("Agreement with PESTO", labelpad=10)
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    ax.spines["left"].set_color("#cbd3d9")
    ax.tick_params(axis="both", length=0, pad=9)
    ax.set_axisbelow(True)
    for y in (0, 25, 50, 75, 100):
        ax.axhline(y, color="#e9edf0", lw=.7, zorder=0)
    fig.legend(*ax.get_legend_handles_labels(), loc="upper center", bbox_to_anchor=(.55, .99), ncol=2,
               frameon=False, fontsize=11)
    for i, k in enumerate(("initial", "revised")):
        ax.text(i, -.20, f"Spearman ρ = {m[k]['spearman_rho']:.3f}", transform=ax.get_xaxis_transform(),
                ha="center", fontsize=11, color="#435c6c")
    for ext in ("png", "pdf"):
        fig.savefig(f"{OUT}.{ext}", dpi=220, facecolor="white")


def main():
    data = json.load(open(os.path.join(DATA, "plot_data.json")))
    pairs = [p for p in data if p["pesto"] in CODE]
    assert len(data) == 50 and len(pairs) == 49
    m = metrics(pairs)
    with open(os.path.join(DATA, "metrics.json"), "w") as fh:
        json.dump(m, fh, indent=2)
    for k, x in m.items():
        print(f"{k}: exact {x['exact_count']}/49 ({x['exact_percent']:.1f}%), within one class "
              f"{x['within_one_count']}/49 ({x['within_one_percent']:.1f}%), Spearman rho {x['spearman_rho']:.3f}, "
              f"differences 0/1/2/3 {'/'.join(x['difference_counts'][str(i)] .__str__() for i in range(4))}")
    print("literature on the six remaining disagreements:", literature_proximity())
    draw(m)
    print("Wrote", OUT + ".png and .pdf")


if __name__ == "__main__":
    main()
