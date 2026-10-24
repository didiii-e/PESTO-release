"""Detail figures: per-pair runtimes, a timeline of one pair, the 20-pair batches
and the synonym-expansion cache.  Reads efficiency_figures/data/ (prepare_data.py).
Original PESTO = git 874eb71 plus the Haiku `temperature` fix; Optimized PESTO =
branch efficiency/cost-and-runtime.  The two summary figures are made by
make_summary_figures.py.

    PYTHONPATH=src python3 efficiency_figures/make_figures.py
"""
import csv
import json
import os
import statistics as st
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DET = os.path.join(HERE, "details")
os.makedirs(DET, exist_ok=True)
DISPLAY = {"original": "Original PESTO", "optimized": "Optimized PESTO"}
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
from pesto.flow.timing import STAGES  # noqa: E402

GREY, BLUE = "#9a9a9a", "#1f77b4"
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})

rows = [json.loads(l) for f in ("clean", "gantt") for l in open(os.path.join(DATA, f"single_pair_runs_{f}.jsonl"))]
rows = [r for r in rows if r["ok"]]
pairs = list(dict.fromkeys((r["gene"], r["phenotype"]) for r in rows))


def walls(label, pair):
    return [r["wall"] for r in rows if r["label"] == label and (r["gene"], r["phenotype"]) == pair]


pairs = [p for p in pairs if walls("original", p) and walls("optimized", p)]
numbers = []

# --- Figure 1: one pair, wall time -----------------------------------------
fig, ax = plt.subplots(figsize=(6.5, 4))
w = 0.38
for i, p in enumerate(pairs):
    for off, label, col in ((-w / 2, "original", GREY), (w / 2, "optimized", BLUE)):
        v = walls(label, p)
        ax.bar(i + off, st.mean(v), w, color=col, label=DISPLAY[label] if i == 0 else None)
        ax.scatter([i + off] * len(v), v, color="black", s=10, zorder=3)
        ax.text(i + off, max(v) + 1.2, f"{st.mean(v):.0f}", ha="center", fontsize=9)
        numbers.append(("single_pair_wall_s_mean", f"{p[0]}/{p[1]}", label, st.mean(v)))
allo = [x for p in pairs for x in walls("original", p)]
alln = [x for p in pairs for x in walls("optimized", p)]
mo, mn = st.mean(allo), st.mean(alln)
ax.set_xticks(range(len(pairs)))
ax.set_xticklabels([p[0] for p in pairs])
ax.set_ylabel("seconds for one pair (start to answer)")
ax.set_title(f"One pair, nothing cached: {mo:.0f} s \u2192 {mn:.0f} s ({mo / mn:.1f}\u00d7)")
ax.set_ylim(0, 66)
ax.legend(frameon=False, loc="upper center", ncol=2)
fig.text(0.01, 0.005, f"bars = mean, dots = individual runs ({len(allo)//len(pairs)} per version per pair), "
         "versions interleaved, --no-cache", fontsize=7.5, color="#555")
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig(os.path.join(DET, "1_Runtime_per_pair_by_gene_Original_vs_Optimized_PESTO.png"), dpi=200)
plt.close(fig)

# --- Figure 2: timeline of one pair, original vs optimized -----------------
GANTT_PAIR = "DDX41"
LANES = [("start-up", None), ("Open Targets", ["open_targets"]), ("expand", ["expand"]),
         ("PubMed search", ["pubmed"]), ("sieve + fetch", ["fetch", "sieve"]),
         ("band (Haiku)", ["bands"]), ("select + read (Opus)", ["select", "read", "judge"])]
LANE_COLOR = ["#cccccc", "#e4a11b", "#6fa8d6", "#2c7fb8", "#7fbf7b", "#9b59b6", "#d6604d"]
block_stage = {b: name for name, blocks in STAGES for b in blocks}
block_stage["OpenTargets"] = "open_targets"
g = {r["label"]: r for r in (json.loads(l) for l in open(os.path.join(DATA, "single_pair_runs_gantt.jsonl")))
     if r["ok"] and r["gene"] == GANTT_PAIR}
fig, axes = plt.subplots(2, 1, figsize=(8.5, 5), sharex=True)
xmax = max(r["wall"] for r in g.values()) + 2
for ax, label in zip(axes, ("original", "optimized")):
    r = g[label]
    t0 = r["start"]
    for lane, (name, parts) in enumerate(LANES):
        if parts is None:
            segs = [(0, r["main_start"] - t0)]
        else:
            segs = [(b["t0"] - t0, b["t1"] - b["t0"]) for b in r["blocks"] if block_stage.get(b["block"]) in parts]
            segs = [(a, d) for a, d in segs]
        ax.broken_barh([(a, d) for a, d in segs], (lane - 0.38, 0.76), color=LANE_COLOR[lane], edgecolor="white", linewidth=0.3)
    ax.set_yticks(range(len(LANES)))
    ax.set_yticklabels([n for n, _ in LANES], fontsize=9)
    ax.invert_yaxis()
    ax.axvline(r["wall"], color="black", lw=1, ls="--")
    ax.text(r["wall"] + 0.3, 0.2, f"{r['wall']:.0f} s", fontsize=10, va="top")
    ax.set_title(DISPLAY[label], loc="left", fontsize=11, fontweight="bold")
    numbers.append(("timeline_wall_s", GANTT_PAIR, label, r["wall"]))
    ot = [b for b in r["blocks"] if b["block"] == "OpenTargets"]
    if ot:
        numbers.append(("timeline_open_targets_s", GANTT_PAIR, label, ot[0]["t1"] - ot[0]["t0"]))
axes[1].set_xlim(0, xmax)
axes[1].set_xlabel("seconds since the command started")
fig.suptitle(f"One pair ({GANTT_PAIR}, nothing cached): what runs when", y=0.995)
fig.tight_layout()
fig.savefig(os.path.join(DET, "2_Timeline_of_one_pair_Original_vs_Optimized_PESTO.png"), dpi=200)
plt.close(fig)

# --- Figure 3: batches of 20 -------------------------------------------------
fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 4), gridspec_kw={"width_ratios": [3, 2]})
labels, vals, cols = ["Original\nPESTO", "Optimized\n(first version)", "Optimized\n(current)"], [117, 86, 80], [GREY, "#6fa8d6", BLUE]
a1.bar(labels, vals, color=cols)
for i, v in enumerate(vals):
    a1.text(i, v + 1.5, f"{v} s", ha="center")
    numbers.append(("batch20_diverse_wall_s", "20 mixed pairs", labels[i].replace("\n", " "), v))
a1.set_ylabel("seconds for all 20 pairs (10 at a time)")
a1.set_title("20 mixed pairs (different phenotypes)")
bt = {r["batch"]: float(r["wall_seconds"]) for r in csv.DictReader(open(os.path.join(DATA, "batch_runtime_and_cost.tsv")), delimiter="\t")}
prog = {"off": int(bt["autism20_cache_off"]), "on": int(bt["autism20_cache_on"])}
a2.bar(["expansion cache\noff", "expansion cache\non"], [prog["off"], prog["on"]], color=[GREY, BLUE])
for i, k in enumerate(("off", "on")):
    a2.text(i, prog[k] + 1.5, f"{prog[k]} s", ha="center")
    numbers.append(("batch20_asd_wall_s", "20 autism genes", f"expansion cache {k}", prog[k]))
a2.set_ylim(0, 125)
a2.set_title("20 autism genes, Optimized PESTO")
fig.suptitle("Wall time for a group of 20 pairs, 10 run at once", y=0.99)
fig.tight_layout()
fig.savefig(os.path.join(DET, "3_Runtime_of_20_pair_batches_Original_vs_Optimized_PESTO.png"), dpi=200)
plt.close(fig)

# --- Figure 4: the expansion stage, per pair, cache off vs on ---------------


def expand_seconds(run):
    rows_ = csv.DictReader(open(os.path.join(DATA, "autism20_expand_stage_seconds.tsv")), delimiter="\t")
    return sorted(float(r["expand_seconds"]) for r in rows_ if r["cache"] == run)


eo, en = expand_seconds("off"), expand_seconds("on")
fig, ax = plt.subplots(figsize=(6, 4))
for i, (vals, col) in enumerate(((eo, GREY), (en, BLUE))):
    ax.scatter([i + (j - len(vals) / 2) * 0.012 for j in range(len(vals))], vals, color=col, s=28, alpha=0.85)
    ax.hlines(st.mean(vals), i - 0.25, i + 0.25, color="black")
    ax.text(i + 0.28, st.mean(vals), f"mean {st.mean(vals):.1f} s", va="center", fontsize=9)
    for v in vals:
        pass
numbers.append(("expand_stage_mean_s", "20 autism genes", "cache off", st.mean(eo)))
numbers.append(("expand_stage_mean_s", "20 autism genes", "cache on", st.mean(en)))
ax.set_xticks([0, 1])
ax.set_xticklabels(["cache off\n(each pair asks)", "cache on\n(asked once)"])
ax.set_xlim(-0.5, 1.8)
ax.set_ylim(0, max(eo + en) + 1.5)
ax.set_ylabel("seconds spent expanding synonyms, per pair")
ax.set_title("Synonym expansion, 20 genes on one phenotype")
fig.text(0.01, 0.005, "10 pairs run at once: with the cache the first 10 share one call (about 7-8 s);\nthe other 10 start after it and find it saved (about 0 s).", fontsize=7.5, color="#555")
fig.tight_layout(rect=(0, 0.06, 1, 1))
fig.savefig(os.path.join(DET, "4_Synonym_expansion_cache_per_pair_time_Optimized_PESTO.png"), dpi=200)
plt.close(fig)

with open(os.path.join(DET, "detail_figure_numbers.tsv"), "w") as fh:
    fh.write("measure\tsubject\tseries\tvalue\n")
    for m, s, k, v in numbers:
        fh.write(f"{m}\t{s}\t{k}\t{round(v, 2)}\n")
print("wrote 4 figures and figure_data.tsv; pairs used:", pairs)
