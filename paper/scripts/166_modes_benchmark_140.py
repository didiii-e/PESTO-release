"""Performance, cost and time of the literature modes on the 140 pairs of Fig. 2d.

The pairs are those of the 2023-2025 bar of Fig. 2d and of Extended Data
Fig. 2a: the 40 GenCC Limited pairs first reported in 2023-2025 against the
100 Absent pairs of Fig. 2a, loaded with the functions of
PESTO-release/paper/scripts/141_score_fig2d_last_bar.py. Each mode is run
through `pesto --bench` of the released package on all 140 pairs, the same
day, with 10 workers and no cache:

  knowledge   --arm knowledge   (the model's own knowledge, no literature)
  titles      --arm titles      (PESTO-titles)
  abstracts   the default       (PESTO in the main text)
  fulltext    --fulltext        (adds Europe PMC full texts)

The benchmark scores the literature branch only, so the Open Targets branch is
replaced inside this process by a function that returns no answer, and the
embedding model is not loaded (--ot-encoder none). The package is not
modified. Each pair is timed by wrapping the function the batch runner calls
per pair, so the batch wall time is that of the literature branch alone.

The number of PubMed records linked to each gene in NCBI Gene is counted as in
scripts/162_select_cost_time_pairs.py, sharing its cache of counts.

Run each mode in its own process with the release's interpreter:

  for m in knowledge titles abstracts fulltext; do
    ../PESTO-release/.venv/bin/python scripts/166_modes_benchmark_140.py $m
  done

Writes results/modes_benchmark_140/pairs.tsv and, per mode, <mode>/ with
input.tsv, pesto.tsv, cost.tsv, timing.tsv and summary.json. About $50 for the
four modes.
"""
import time

T0 = time.perf_counter()

import argparse  # noqa: E402
import csv  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import statistics  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
from importlib import import_module  # noqa: E402
from importlib.metadata import version  # noqa: E402

import pandas as pd  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE_PAPER = os.path.join(os.path.dirname(ROOT), "PESTO-release", "paper")
BASE = os.path.join(ROOT, "results", "modes_benchmark_140")
MODES = {"knowledge": ["--arm", "knowledge"], "titles": ["--arm", "titles"],
         "abstracts": [], "fulltext": ["--fulltext"],
         "abstracts-fast": ["--fast"]}
WORKERS = 10


def fig2d_module():
    spec = importlib.util.spec_from_file_location(
        "fig2d", os.path.join(RELEASE_PAPER, "scripts", "141_score_fig2d_last_bar.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def original_names(fig2d):
    """The gene symbols as written in the source tables; the loaders upper-case them."""
    names = {}
    sources = [os.path.join(RELEASE_PAPER, "results", "prior_year10", "knowledge.tsv"),
               os.path.join(RELEASE_PAPER, "benchmark", "gencc_clingen_g2p", "pesto.tsv")]
    sources += [os.path.join(RELEASE_PAPER, "results", d, "pesto.tsv")
                for d in ("fig2a_absent_extra20", "fig2a_absent_extra20b", "fig2a_absent_extra30")]
    for path in sources:
        for r in fig2d.read_tsv(path):
            names.setdefault(fig2d.key(r["gene"], r["phenotype"]), r["gene"])
    return names


def build_pairs():
    path = os.path.join(BASE, "pairs.tsv")
    if os.path.exists(path):
        return pd.read_csv(path, sep="\t")
    fig2d = fig2d_module()
    lim, _ = fig2d.limited()
    absent, _ = fig2d.absent()
    names = original_names(fig2d)
    rows = ([{"gene": names[k], "phenotype": k[1], "label": "Limited 2023-2025"}
             for k in sorted(lim)]
            + [{"gene": names[k], "phenotype": k[1], "label": "Absent"} for k in sorted(absent)])
    pairs = pd.DataFrame(rows)
    assert len(pairs) == 140 and pairs[["gene", "phenotype"]].drop_duplicates().shape[0] == 140
    sel = import_module("162_select_cost_time_pairs")
    sel.COUNTS = os.path.join(ROOT, "results", "cost_time_3modes", "gene_pubmed_counts.tsv")
    counts = sel.gene_counts(sorted(pairs["gene"].unique()))
    pairs["pubmed_records"] = pairs["gene"].map(counts)
    os.makedirs(BASE, exist_ok=True)
    pairs.to_csv(path, sep="\t", index=False)
    return pairs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", choices=MODES)
    ap.add_argument("--pairs-only", action="store_true",
                    help="build pairs.tsv and the gene counts, run nothing")
    args = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    pairs = build_pairs()
    if args.pairs_only:
        print(pairs.groupby("label")["pubmed_records"].describe().round(0).to_string())
        return 0
    if not args.mode:
        ap.error("give a mode, or --pairs-only")

    out_dir = os.path.join(BASE, args.mode)
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    bench = os.path.join(out_dir, "input.tsv")
    pairs[["gene", "phenotype"]].to_csv(bench, sep="\t", index=False)

    from pesto import cli

    lock, spans = threading.Lock(), {}
    assess = cli.assess

    def timed_assess(arm, gene, phenotype, *a, **k):
        start = time.perf_counter()
        try:
            return assess(arm, gene, phenotype, *a, **k)
        finally:
            with lock:
                spans[(gene, phenotype)] = (start - T0, time.perf_counter() - T0)

    cli.assess = timed_assess
    cli.open_targets = lambda *a, **k: ("", None, {}, {})
    out = os.path.join(out_dir, "pesto.tsv")
    code = cli.main(["--bench", bench, "--workers", str(WORKERS), "--no-cache",
                     "--ot-encoder", "none", "--data-dir", os.path.join(out_dir, "runs"),
                     "--out", out, "--quiet"] + MODES[args.mode])
    t_end = time.perf_counter() - T0

    answers = pd.read_csv(out, sep="\t", keep_default_na=False).set_index(["gene", "phenotype"])
    cost = pd.read_csv(os.path.join(out_dir, "cost.tsv"), sep="\t")
    usd = cost[cost["step"] == "total"].set_index(["gene", "phenotype"])["usd"]
    rows = []
    for key, (a, b) in sorted(spans.items(), key=lambda kv: kv[1][0]):
        r = answers.loc[key] if key in answers.index else {}
        rows.append({"mode": args.mode, "gene": key[0], "phenotype": key[1],
                     "start_s": round(a, 2), "end_s": round(b, 2), "seconds": round(b - a, 2),
                     "usd": round(float(usd.get(key, 0)), 5),
                     "p_established": r.get("p_established", ""),
                     "p_existing": r.get("p_existing", ""),
                     "p_hypothesized": r.get("p_hypothesized", ""),
                     "p_novel": r.get("p_novel", ""), "lit_mean": r.get("lit_mean", ""),
                     "found": r.get("found", ""), "read": r.get("read", ""),
                     "arm": r.get("arm", ""), "fingerprint": r.get("fingerprint", ""),
                     "cached": r.get("cached", ""), "error": r.get("error", "")})
    t = pd.DataFrame(rows).merge(pairs, on=["gene", "phenotype"])
    t.to_csv(os.path.join(out_dir, "timing.tsv"), sep="\t", index=False)

    first, last = t["start_s"].min(), t["end_s"].max()
    summary = {
        "mode": args.mode, "pesto_version": version("pesto-genetics"),
        "pairs": len(t), "workers": WORKERS, "cpus": os.cpu_count(),
        "errors": int((t["error"].astype(str).str.len() > 0).sum()),
        "missing_distribution": int((t["p_novel"].astype(str) == "").sum()),
        "cached": int((t["cached"].astype(str) == "True").sum()),
        "arms": sorted(t["arm"].astype(str).unique().tolist()),
        "startup_s": round(first, 1), "batch_wall_s": round(last - first, 1),
        "process_wall_s": round(t_end, 1), "per_pair_sum_s": round(t["seconds"].sum(), 1),
        "speedup": round(t["seconds"].sum() / (last - first), 2),
        "per_pair_median_s": round(statistics.median(t["seconds"]), 1),
        "usd_mean": round(t["usd"].mean(), 4), "usd_sd": round(t["usd"].std(), 4),
        "usd_total": round(t["usd"].sum(), 3), "exit_code": code,
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=1)
    sys.__stdout__.write(json.dumps(summary, indent=1) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
