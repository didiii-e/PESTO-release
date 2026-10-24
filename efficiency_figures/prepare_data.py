"""Copies the measurements behind the efficiency figures out of /tmp into
efficiency_figures/data/ (trimmed: no justification text), so the figures can be
rebuilt later.  Run once, right after the benchmark runs:

    python3 efficiency_figures/prepare_data.py

Sources (all produced on branch efficiency/cost-and-runtime):
  /tmp/expcmp/clean.jsonl, gantt.jsonl   original vs optimized, one pair at a time
  /tmp/san/{base,new,new2}               20 mixed pairs: original, optimized v1, optimized v2
  /tmp/expcmp/final/{off,on,refresh}     20 autism genes with the expansion cache off/on/refresh
  /tmp/expcmp/final/reference.tsv        the published pesto.tsv rows for those 20 genes
"""
import csv
import glob
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data")
os.makedirs(OUT, exist_ok=True)

KEEP = ["gene", "phenotype", "lit_mean", "lit_argmax", "p_established", "p_existing",
        "p_hypothesized", "p_novel", "open_targets_verdict", "found", "read", "error"]


def trim(src, dst):
    rows = list(csv.DictReader(open(src), delimiter="\t"))
    with open(os.path.join(OUT, dst), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=KEEP, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def cost(path):
    rows = csv.DictReader(open(path), delimiter="\t")
    return round(sum(float(r["usd"]) for r in rows if r["step"] == "total"), 3)


for src, dst in [("/tmp/san/base", "mixed20_original"), ("/tmp/san/new", "mixed20_optimized_v1"),
                 ("/tmp/san/new2", "mixed20_optimized_v2"), ("/tmp/expcmp/final/off", "autism20_cache_off"),
                 ("/tmp/expcmp/final/on", "autism20_cache_on"),
                 ("/tmp/expcmp/final/refresh", "autism20_cache_refresh")]:
    trim(src + "/pesto.tsv", dst + ".tsv")
trim("/tmp/expcmp/final/reference.tsv", "autism20_published.tsv")

# Wall-clock seconds of each 20-pair batch (10 pairs at a time). The mixed-set times
# were read from the run logs during the session; the autism times are in progress.txt.
walls = {"mixed20_original": 117, "mixed20_optimized_v1": 86, "mixed20_optimized_v2": 80}
for line in open("/tmp/expcmp/final/progress.txt"):
    if "exit=" in line:
        walls["autism20_cache_" + line.split()[0]] = int(line.split(" in ")[1].rstrip("s\n"))
costs = {"mixed20_original": cost("/tmp/san/base/cost.tsv"), "mixed20_optimized_v1": cost("/tmp/san/new/cost.tsv"),
         "mixed20_optimized_v2": cost("/tmp/san/new2/cost.tsv"),
         **{f"autism20_cache_{n}": cost(f"/tmp/expcmp/final/{n}/cost.tsv") for n in ("off", "on", "refresh")}}
with open(os.path.join(OUT, "batch_runtime_and_cost.tsv"), "w") as fh:
    fh.write("batch\twall_seconds\tcost_usd\n")
    for k in walls:
        fh.write(f"{k}\t{walls[k]}\t{costs[k]}\n")

for f in ("clean", "gantt"):
    shutil.copy(f"/tmp/expcmp/{f}.jsonl", os.path.join(OUT, f"single_pair_runs_{f}.jsonl"))

with open(os.path.join(OUT, "autism20_expand_stage_seconds.tsv"), "w") as fh:
    fh.write("cache\tpair_file\texpand_seconds\n")
    for run in ("off", "on"):
        for p in sorted(glob.glob(f"/tmp/expcmp/final/{run}/runs/flow/*.json")):
            tr = json.load(open(p))["trace"]
            sec = next(s["seconds"] for s in tr if s["block"] == "Expand")
            fh.write(f"{run}\t{os.path.basename(p).split('__')[0]}\t{sec}\n")
print("wrote", sorted(os.listdir(OUT)))
