#!/usr/bin/env python3
"""Summary table and figure for the pair-worker sweep (342_pair_worker_sweep.py).

Reads the raw runs the sweep left in /tmp/pair_sweep/raw, averages the passes
at each worker count, and writes to efficiency_figures/pair_concurrency/:
  worker_sweep_runs.tsv      one row per run
  worker_sweep_summary.tsv   mean over the passes at each worker count
  pair_workers_sweep.png     the figure
"""
import importlib.util
import json
import os
import statistics as st
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sweep", os.path.join(HERE, "342_pair_worker_sweep.py"))
sweep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sweep)

RAW, OUT = sweep.RAW, sweep.OUT
os.makedirs(OUT, exist_ok=True)

rows = []
for d in sorted(os.listdir(RAW)):
    path = os.path.join(RAW, d, "run.json")
    if os.path.exists(path):
        row = sweep.one_run(path)
        row["tag"] = d.split("_w")[0]
        rows.append(row)
rows.sort(key=lambda r: (r["workers"], r["tag"]))

workers = sorted({r["workers"] for r in rows})
numeric = [k for k, v in rows[0].items() if isinstance(v, (int, float)) and k != "workers"]
mean = {w: {k: st.mean(r[k] for r in rows if r["workers"] == w) for k in numeric} for w in workers}
for w in workers:
    m = mean[w]
    # Little's law: at steady state, throughput = pairs in flight / time per pair.
    # A 20-pair batch ramps up and drains, which flatters a few workers and
    # hides the ceiling of many; this is what a long batch would settle to.
    m["steady_pairs_per_minute"] = 60 * w / m["pair_mean"]
    m["n_runs"] = sum(1 for r in rows if r["workers"] == w)

cols = ["n_runs", "batch_seconds", "pairs_per_minute", "steady_pairs_per_minute", "pair_median", "pair_p90",
        "lit_median", "ot_median", "haiku_latency_median", "haiku_latency_p90", "opus_latency_median",
        "opus_latency_p90", "anthropic_inflight_peak", "ncbi_waiting_peak", "ncbi_rate_mean",
        "gate_wait_median", "gate_wait_p95", "sdk_retries", "sdk_timeouts", "pairs_failed",
        "cpu_sys_mean_pct", "rss_peak_mb", "threads_peak"]
with open(os.path.join(OUT, "worker_sweep_summary.tsv"), "w") as fh:
    fh.write("workers\t" + "\t".join(cols) + "\n")
    for w in workers:
        fh.write(f"{w}\t" + "\t".join(f"{mean[w][c]:.2f}" for c in cols) + "\n")

keys = list(rows[0])
with open(os.path.join(OUT, "worker_sweep_runs.tsv"), "w") as fh:
    fh.write("\t".join(keys) + "\n")
    for r in rows:
        fh.write("\t".join(json.dumps(r[k]) if isinstance(r[k], dict) else
                           (f"{r[k]:.3f}" if isinstance(r[k], float) else str(r[k])) for k in keys) + "\n")

grey, blue, orange, red = "#888888", "#2b6cb0", "#dd6b20", "#c53030"
fig, ax = plt.subplots(2, 2, figsize=(11, 8))


def dots(a, key, color, label=None):
    for tag, marker in (("A", "o"), ("B", "s")):
        pts = [(r["workers"], r[key]) for r in rows if r["tag"] == tag]
        a.scatter(*zip(*pts), color=color, marker=marker, s=24, alpha=.5, zorder=3)
    a.plot(workers, [mean[w][key] for w in workers], color=color, lw=2, label=label, zorder=2)


a = ax[0, 0]
dots(a, "batch_seconds", blue)
a.set(title="Whole 20-pair batch", ylabel="seconds (lower is better)")
a = ax[0, 1]
dots(a, "pair_median", blue, "one pair, total")
dots(a, "lit_median", orange, "literature branch")
dots(a, "ot_median", grey, "Open Targets branch")
a.legend(frameon=False)
a.set(title="Time for one pair (median)", ylabel="seconds (lower is better)")
a = ax[1, 0]
a.plot(workers, [mean[w]["pairs_per_minute"] for w in workers], color=blue, lw=2, marker="o",
       label="this 20-pair batch")
a.plot(workers, [mean[w]["steady_pairs_per_minute"] for w in workers], color=orange, lw=2, marker="o",
       label="steady state (workers / time per pair)")
a.legend(frameon=False)
a.set(title="Throughput", ylabel="pairs per minute (higher is better)")
a = ax[1, 1]
dots(a, "gate_wait_p95", red, "NCBI rate-gate wait, 95th percentile")
dots(a, "opus_latency_median", orange, "Opus call, median")
dots(a, "haiku_latency_p90", grey, "Haiku call, 90th percentile")
a.legend(frameon=False)
a.set(title="Where contention shows up", ylabel="seconds")
for a in ax.flat:
    a.set_xticks(workers)
    a.set_xlabel("pairs run at once")
    a.set_ylim(bottom=0)
    a.spines[["top", "right"]].set_visible(False)
fig.suptitle("PESTO: pairs run at once vs speed (same 20 pairs; circles forward pass, squares reverse pass)")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "pair_workers_sweep.png"), dpi=150)

print(f"wrote {OUT}")
print("workers  batch_s  pair_med_s  pair_p90_s  steady/min  gate_p95_s  opus_med_s")
for w in workers:
    m = mean[w]
    print(f"{w:7d} {m['batch_seconds']:8.0f} {m['pair_median']:11.1f} {m['pair_p90']:11.1f} "
          f"{m['steady_pairs_per_minute']:11.1f} {m['gate_wait_p95']:11.1f} {m['opus_latency_median']:11.1f}")
