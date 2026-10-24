"""Two summary figures: how much faster the optimized PESTO is, and whether its
results changed.  Reads only efficiency_figures/data/ (see prepare_data.py).

    python3 efficiency_figures/make_summary_figures.py

Naming used throughout:
  Original PESTO   the code at the start of branch efficiency/cost-and-runtime
                   (git 874eb71) with one fix so it still runs: Anthropic now
                   rejects the `temperature` parameter for Haiku 4.5.
  Optimized PESTO  the same pipeline, prompts and models after the runtime work
                   (Open Targets in parallel with the literature branch,
                   parallel synonym expansion, shared PubMed summary calls,
                   wider Haiku banding, cached disease-name embeddings,
                   pooled connections).
"""
import csv
import json
import os
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "summary")
os.makedirs(OUT, exist_ok=True)

GREY, BLUE = "#8c8c8c", "#1f77b4"
ORIG, OPT = "Original PESTO", "Optimized PESTO"
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
LEVELS = ["Novel", "Hypothesized", "Existing", "Established"]
RANK = {k: i for i, k in enumerate(LEVELS)}
numbers = []


def table(name):
    return {r["gene"] + "|" + r["phenotype"]: r
            for r in csv.DictReader(open(os.path.join(DATA, name + ".tsv")), delimiter="\t")}


def panel_letter(ax, letter, y=1.12):
    ax.text(-0.02, y, letter, transform=ax.transAxes, fontsize=15, fontweight="bold", va="bottom", ha="right")


# ============================================================ Figure 1: time
runs = [json.loads(l) for f in ("clean", "gantt") for l in open(os.path.join(DATA, f"single_pair_runs_{f}.jsonl"))]
runs = [r for r in runs if r["ok"]]
w_orig = [r["wall"] for r in runs if r["label"] == "original"]
w_opt = [r["wall"] for r in runs if r["label"] == "optimized"]
bt = {r["batch"]: r for r in csv.DictReader(open(os.path.join(DATA, "batch_runtime_and_cost.tsv")), delimiter="\t")}
b_orig, b_opt = float(bt["mixed20_original"]["wall_seconds"]), float(bt["mixed20_optimized_v2"]["wall_seconds"])
c_orig, c_opt = float(bt["mixed20_original"]["cost_usd"]), float(bt["mixed20_optimized_v2"]["cost_usd"])

fig, axes = plt.subplots(1, 3, figsize=(13, 4.8), gridspec_kw={"width_ratios": [1, 1, 1]})

ax = axes[0]
rng = np.random.default_rng(1)
for i, (vals, col, lab) in enumerate(((w_orig, GREY, ORIG), (w_opt, BLUE, OPT))):
    ax.bar(i, st.mean(vals), 0.6, color=col)
    ax.scatter(i + rng.uniform(-0.15, 0.15, len(vals)), vals, color="black", s=12, zorder=3)
    ax.text(i, max(vals) + 1.5, f"{st.mean(vals):.0f} s", ha="center", fontsize=12, fontweight="bold")
ax.set_xticks([0, 1])
ax.set_xticklabels([ORIG, OPT])
ax.set_ylim(0, 65)
ax.set_ylabel("seconds per pair, start to answer")
ax.set_title(f"One pair, nothing cached\n{st.mean(w_orig) / st.mean(w_opt):.1f}\u00d7 faster", fontsize=11)
panel_letter(ax, "A")
numbers += [("one_pair_wall_s_mean", ORIG, st.mean(w_orig)), ("one_pair_wall_s_mean", OPT, st.mean(w_opt)),
            ("one_pair_runs_per_version", "", len(w_opt))]

ax = axes[1]
for i, (v, col) in enumerate(((b_orig, GREY), (b_opt, BLUE))):
    ax.bar(i, v, 0.6, color=col)
    ax.text(i, v + 2, f"{v:.0f} s", ha="center", fontsize=12, fontweight="bold")
    ax.text(i, v / 2, f"{v / 20:.1f} s\nper pair", ha="center", color="white", fontsize=10)
ax.set_xticks([0, 1])
ax.set_xticklabels([ORIG, OPT])
ax.set_ylim(0, 140)
ax.set_ylabel("seconds for all 20 pairs")
ax.set_title(f"A group of 20 pairs (10 at a time)\n{b_orig / b_opt:.1f}\u00d7 faster", fontsize=11)
panel_letter(ax, "B")
numbers += [("group20_wall_s", ORIG, b_orig), ("group20_wall_s", OPT, b_opt)]

ax = axes[2]
for i, (v, col) in enumerate(((c_orig, GREY), (c_opt, BLUE))):
    ax.bar(i, v, 0.6, color=col)
    ax.text(i, v + 0.07, f"${v:.2f}", ha="center", fontsize=12, fontweight="bold")
ax.set_xticks([0, 1])
ax.set_xticklabels([ORIG, OPT])
ax.set_ylim(0, 4)
ax.set_ylabel("API cost for 20 pairs (US$)")
ax.set_title("Cost of the same group\nunchanged (same models and prompts)", fontsize=11)
panel_letter(ax, "C")
numbers += [("group20_cost_usd", ORIG, c_orig), ("group20_cost_usd", OPT, c_opt)]

fig.suptitle("PESTO runtime: original vs optimized", fontsize=14, fontweight="bold", y=1.0)
fig.text(0.01, 0.005,
         "A: 12 runs per version on 4 gene-phenotype pairs (DDX41, BRCA1, MEF2C, SLTM), versions interleaved, no caches (dots = single runs).   "
         "B, C: 20 gene-phenotype pairs of mixed phenotypes, 10 in parallel, same pairs for both versions.\n"
         "Original PESTO = code at git 874eb71 plus the Haiku `temperature` fix.  Optimized PESTO = branch efficiency/cost-and-runtime, "
         "expansion cache off.  Live Anthropic, PubMed (NCBI key) and Open Targets calls.", fontsize=7.5, color="#555")
fig.tight_layout(rect=(0, 0.06, 1, 0.97))
fig.savefig(os.path.join(OUT, "1_Runtime_Original_vs_Optimized_PESTO.png"), dpi=200)
plt.close(fig)

# ======================================================== Figure 2: results
orig, opt = table("mixed20_original"), table("mixed20_optimized_v2")
keys = [k for k in orig if k in opt]


def levels_diff(a, b, col, keys):
    d = [abs(RANK[a[k][col]] - RANK[b[k][col]]) for k in keys]
    return [sum(x == 0 for x in d), sum(x == 1 for x in d), sum(x >= 2 for x in d)]


off, refr, pub = table("autism20_cache_off"), table("autism20_cache_refresh"), table("autism20_published")
akeys = list(off)
rows = [
    ("Literature verdict", "Original vs Optimized\n(20 mixed pairs)", levels_diff(orig, opt, "lit_mean", keys)),
    ("Literature verdict", "Optimized run twice\n(20 autism genes)", levels_diff(off, refr, "lit_mean", akeys)),
    ("Literature verdict", "Published results vs Optimized\n(20 autism genes)", levels_diff(pub, off, "lit_mean", akeys)),
    ("Open Targets verdict", "Original vs Optimized\n(20 mixed pairs)", levels_diff(orig, opt, "open_targets_verdict", keys)),
    ("Open Targets verdict", "Published results vs Optimized\n(20 autism genes)", levels_diff(pub, off, "open_targets_verdict", akeys)),
]
for g, lab, v in rows:
    numbers.append(("verdict_agreement[identical,1_level,2+_levels]", f"{g}: {lab.replace(chr(10), ' ')}", v))

fig = plt.figure(figsize=(15, 6.4))
gs = fig.add_gridspec(1, 3, width_ratios=[1, 1.5, 1], wspace=0.75, left=0.07, right=0.97, top=0.80, bottom=0.27)

# A. confusion matrix
ax = fig.add_subplot(gs[0])
M = np.zeros((4, 4), int)
for k in keys:
    M[RANK[orig[k]["lit_mean"]], RANK[opt[k]["lit_mean"]]] += 1
ax.imshow(M, cmap="Blues", vmin=0, vmax=8)
for i in range(4):
    for j in range(4):
        if M[i, j]:
            ax.text(j, i, M[i, j], ha="center", va="center", fontsize=13,
                    color="white" if M[i, j] > 4 else "black", fontweight="bold")
ax.set_xticks(range(4))
ax.set_yticks(range(4))
ax.set_xticklabels([l.replace("Hypothesized", "Hypoth-\nesized") for l in LEVELS], fontsize=8.5)
ax.set_yticklabels(LEVELS, fontsize=9)
ax.set_xlabel(f"{OPT}: literature verdict")
ax.set_ylabel(f"{ORIG}: literature verdict")
ax.xaxis.tick_top()
ax.xaxis.set_label_position("top")
ax.set_title("Literature verdict, pair by pair", fontsize=11, pad=62)
ax.text(0.5, -0.1, f"{M.trace()} of {len(keys)} pairs get the same verdict;\nthe other {len(keys) - M.trace()} differ by one level",
        transform=ax.transAxes, ha="center", va="top", fontsize=9.5)
panel_letter(ax, "A", 1.3)

# B. agreement bars
ax = fig.add_subplot(gs[1])
cols = ["#2b6cb0", "#9ecae1", "#d6604d"]
labs = ["identical", "one level apart", "two or more levels apart"]
ypos = [0, 1, 2, 3.6, 4.6]
for y, (g, lab, v) in zip(ypos, rows):
    left = 0
    for n, c in zip(v, cols):
        if n:
            ax.barh(y, n, left=left, color=c, height=0.7)
            ax.text(left + n / 2, y, str(n), ha="center", va="center", color="white" if c == cols[0] else "black", fontsize=11)
        left += n
ax.set_yticks(ypos)
ax.set_yticklabels([r[1] for r in rows], fontsize=8.5)
ax.invert_yaxis()
ax.set_xlim(0, 20)
ax.set_xticks([0, 5, 10, 15, 20])
ax.set_xlabel("number of pairs (of 20)")
ax.text(20.3, 1, "Literature\nverdict", fontsize=8.5, color="#333", va="center")
ax.text(20.3, 4.1, "Open Targets\nverdict", fontsize=8.5, color="#333", va="center")
ax.set_title("Is the difference larger than normal run-to-run variation?", fontsize=11, pad=12)
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in cols]
ax.legend(handles, labs, frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.4, -0.16), ncol=3)
panel_letter(ax, "B")

# C. probability scatter
ax = fig.add_subplot(gs[2])
x = np.array([float(orig[k]["p_established"]) for k in keys])
y = np.array([float(opt[k]["p_established"]) for k in keys])
ax.plot([0, 100], [0, 100], color="#bbb", lw=1, zorder=0)
ax.scatter(x, y, color=BLUE, s=36, alpha=0.8, zorder=3)
r = np.corrcoef(x, y)[0, 1]
ax.set_xlim(-3, 103)
ax.set_ylim(-3, 103)
ax.set_aspect("equal")
ax.set_xlabel(f"{ORIG}: P(Established), %")
ax.set_ylabel(f"{OPT}: P(Established), %")
ax.set_title(f"P(Established), pair by pair\nr = {r:.3f}, mean difference {np.abs(x - y).mean():.1f} points", fontsize=11, pad=12)
panel_letter(ax, "C")
numbers += [("p_established_pearson_r_original_vs_optimized", "20 mixed pairs", r),
            ("p_established_mean_abs_diff_points", "20 mixed pairs", float(np.abs(x - y).mean()))]

fig.suptitle("PESTO results: does optimizing change the answers?", fontsize=14, fontweight="bold", y=0.97)
changed = [(k.split("|")[0], orig[k]["lit_mean"], opt[k]["lit_mean"]) for k in keys if orig[k]["lit_mean"] != opt[k]["lit_mean"]]
fig.text(0.01, 0.005,
         "Verdict levels: Novel < Hypothesized < Existing < Established.  Literature verdicts that changed: "
         + "; ".join(f"{g} {a} \u2192 {b}" for g, a, b in changed)
         + ".  \"Optimized run twice\" = the same code run on the same pairs a second time (re-asking the synonym expansion):\n"
         "its disagreement with itself is the size of normal sampling variation, since Opus no longer accepts a fixed temperature.  "
         "\"Published results\" = the pesto.tsv rows released with the paper.",
         fontsize=7.5, color="#555", wrap=True)
fig.savefig(os.path.join(OUT, "2_Results_Original_vs_Optimized_PESTO.png"), dpi=200, bbox_inches="tight")
plt.close(fig)

with open(os.path.join(OUT, "summary_numbers.tsv"), "w") as fh:
    fh.write("measure\tseries_or_comparison\tvalue\n")
    for m, s, v in numbers:
        fh.write(f"{m}\t{s}\t{[round(i, 3) for i in v] if isinstance(v, list) else round(v, 3)}\n")
print("wrote", sorted(os.listdir(OUT)))
