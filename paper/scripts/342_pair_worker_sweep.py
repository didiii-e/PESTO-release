#!/usr/bin/env python3
"""How many pairs should a batch run at once?  A sweep of `--workers`.

Within a pair, the literature branch and Open Targets already run side by side.
This measures the other axis, pairs at the same time, on one fixed batch, and
changes nothing else: same pipeline, prompts, models and retrieval. The pesto
CLI runs unmodified; this script only watches it from outside by wrapping
(never altering) the calls that reach the network:

  Anthropic   every `messages.create` (in flight, latency, status) and every
              `_call_anthropic` (what the pipeline sees), plus the SDK's own
              retry log lines, which are otherwise silent: the SDK retries 429
              and overloads twice before pesto's own retry loop hears of it
  NCBI        every request (in flight, latency, status) and the time spent
              waiting at the process-wide rate gate (9/s with a key)
  Open Targets and other hosts   the same, per host
  Per pair    wall time, the literature branch's time, Open Targets' time
  Machine     process and system CPU, resident memory, free memory, threads,
              sampled four times a second

Usage (from the repository root, with the API keys in the environment or .env):

  python3 paper/scripts/342_pair_worker_sweep.py run --workers 2 4 6 8 10 20 \\
      --tag A                       # ascending, one run per worker count
  python3 paper/scripts/342_pair_worker_sweep.py run --workers 20 10 8 6 4 2 \\
      --tag B                       # reverse order, so drift cancels
  python3 paper/scripts/342_pair_worker_sweep.py report

Each `run` costs about $3 per worker count (20 pairs). Raw runs go to
/tmp/pair_sweep/raw (they hold model-written text); `report` writes the trimmed
tables and figures to efficiency_figures/pair_concurrency/.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
RAW = os.environ.get("PAIR_SWEEP_RAW", "/tmp/pair_sweep/raw")
BATCH = os.path.join(REPO, "efficiency_figures", "data", "mixed20_original.tsv")
BATCH_INPUT = os.environ.get("PAIR_SWEEP_BATCH", "/tmp/san/base/input.tsv")
OUT = os.path.join(REPO, "efficiency_figures", "pair_concurrency")


# =============================================================== the watcher
def child(argv):
    """Run `pesto --bench ...` in this process, recording what it does."""
    import logging
    import psutil
    import requests

    sys.path.insert(0, os.path.join(REPO, "src"))
    import anthropic
    import pesto.cli as C
    import pesto.flow.run as FR
    from pesto.services import llm_service as L
    from pesto.services import pubmed_service as P

    lock = threading.Lock()
    live, peak = {}, {}
    REQ, LLM, LOGICAL, GATE, PAIRS, LOGS, SAMPLES = [], [], [], [], [], [], []

    def up(name):
        with lock:
            live[name] = live.get(name, 0) + 1
            peak[name] = max(peak.get(name, 0), live[name])

    def down(name):
        with lock:
            live[name] -= 1

    def host_key(url):
        host = urlparse(str(url)).netloc
        if "ncbi" in host:
            return "ncbi"
        if "opentargets" in host:
            return "opentargets"
        return host or "other"

    # ---- every requests call (NCBI, Open Targets, full text)
    orig_request = requests.Session.request

    def request(self, method, url, *a, **k):
        key = host_key(url)
        up("http:" + key)
        t0, status = time.time(), None
        try:
            r = orig_request(self, method, url, *a, **k)
            status = r.status_code
            return r
        except BaseException as exc:
            status = type(exc).__name__
            raise
        finally:
            down("http:" + key)
            REQ.append((t0, time.time(), key, status))

    requests.Session.request = request

    # ---- the NCBI gate: how long a request waits for its slot
    orig_wait = P._wait_for_slot

    def wait_for_slot():
        up("ncbi_waiting")
        t0 = time.time()
        try:
            return orig_wait()
        finally:
            down("ncbi_waiting")
            GATE.append((t0, time.time()))

    P._wait_for_slot = wait_for_slot

    # ---- Anthropic, at the SDK (includes its silent retries) ...
    Messages = anthropic.resources.messages.Messages
    orig_create = Messages.create

    def create(self, *a, **k):
        up("anthropic_sdk")
        t0, status = time.time(), 200
        try:
            return orig_create(self, *a, **k)
        except anthropic.APIStatusError as exc:
            status = exc.status_code
            raise
        except BaseException as exc:
            status = type(exc).__name__
            raise
        finally:
            down("anthropic_sdk")
            LLM.append((t0, time.time(), str(k.get("model")), status))

    Messages.create = create

    # ... and where the pipeline sees it
    orig_call = L._call_anthropic

    def call(prompt, model, *a, **k):
        up("anthropic_calls")
        t0, status = time.time(), "ok"
        try:
            return orig_call(prompt, model, *a, **k)
        except BaseException as exc:
            status = type(exc).__name__
            raise
        finally:
            down("anthropic_calls")
            LOGICAL.append((t0, time.time(), str(model), status))

    L._call_anthropic = call

    # ---- the SDK's own retry log lines (messages only, never the prompts)
    keep = ("Retrying", "Encountered", "Not retrying", "Re-raising", "retry left")

    class Tap(logging.Handler):
        def emit(self, record):
            first = str(record.msg)
            if record.name.startswith("httpx"):
                text = record.getMessage()
                if "anthropic" in text:
                    LOGS.append((time.time(), "http", text.rsplit('"', 2)[-2][:40]))
            elif first.startswith(keep):
                LOGS.append((time.time(), "sdk", first % record.args if record.args else first))

    tap = Tap(level=logging.DEBUG)
    for name, level in (("anthropic", logging.DEBUG), ("httpx", logging.INFO)):
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.addHandler(tap)

    # ---- per pair: wall, literature seconds, Open Targets seconds
    tl = threading.local()
    orig_assess, orig_run = C.assess, FR.run

    def run(*a, **k):
        t0 = time.time()
        try:
            return orig_run(*a, **k)
        finally:
            tl.lit = time.time() - t0

    FR.run = run

    def assess(arm, gene, phenotype, args, worker, flow_dir):
        up("pairs_active")
        tl.lit = None
        t0, row, err = time.time(), None, None
        try:
            row = orig_assess(arm, gene, phenotype, args, worker, flow_dir)
            return row
        except BaseException as exc:
            err = f"{type(exc).__name__}: {exc}"[:200]
            raise
        finally:
            down("pairs_active")
            t1 = time.time()
            timing = (row or {}).get("_timing") or {}
            PAIRS.append({"gene": gene, "phenotype": phenotype, "start": t0, "end": t1,
                          "wall": t1 - t0, "lit_seconds": tl.lit,
                          "ot_seconds": timing.get("open_targets"), "error": err})

    C.assess = assess

    # ---- the machine, four times a second
    stop = threading.Event()
    proc = psutil.Process()

    def sampler():
        proc.cpu_percent(None)
        psutil.cpu_percent(None)
        while not stop.wait(0.25):
            with lock:
                snap = dict(live)
            vm = psutil.virtual_memory()
            SAMPLES.append({"t": time.time(), "live": snap,
                            "cpu_proc": proc.cpu_percent(None), "cpu_sys": psutil.cpu_percent(None),
                            "rss_mb": proc.memory_info().rss / 2**20,
                            "avail_mb": vm.available / 2**20, "threads": proc.num_threads()})

    thread = threading.Thread(target=sampler, daemon=True)
    thread.start()
    t_main0 = time.time()
    rc = 1
    try:
        rc = C.main(argv)
    finally:
        t_main1 = time.time()
        stop.set()
        thread.join(timeout=2)
        record = {"argv": argv, "rc": rc, "t_main0": t_main0, "t_main1": t_main1,
                  "cpu_count": os.cpu_count(), "ncbi_key": bool(P.NCBI_API_KEY),
                  "ncbi_per_second": P.pubmed_rate(), "peak": peak,
                  "pairs": PAIRS, "requests": REQ, "anthropic_sdk": LLM, "anthropic_calls": LOGICAL,
                  "ncbi_gate": GATE, "log": LOGS, "samples": SAMPLES}
        with open(os.environ["SWEEP_RUN_JSON"], "w") as fh:
            json.dump(record, fh)
    return rc


# ============================================================ the orchestrator
def run_sweep(args):
    os.makedirs(RAW, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=os.path.join(REPO, "src"))
    for i, w in enumerate(args.workers):
        d = os.path.join(RAW, f"{args.tag}_w{w:02d}")
        os.makedirs(d, exist_ok=True)
        inp = os.path.join(d, "input.tsv")
        with open(BATCH_INPUT) as src, open(inp, "w") as dst:
            dst.write(src.read())
        data_dir = tempfile.mkdtemp(prefix="pair_sweep_")
        env["SWEEP_RUN_JSON"] = os.path.join(d, "run.json")
        cmd = [sys.executable, os.path.abspath(__file__), "child", "--bench", inp, "--workers", str(w),
               "--no-cache", "--data-dir", data_dir, "--out", os.path.join(d, "pesto.tsv")]
        t0 = time.time()
        with open(os.path.join(d, "log.txt"), "w") as log:
            rc = subprocess.run(cmd, env=env, cwd=REPO, stdout=log, stderr=subprocess.STDOUT).returncode
        print(f"{args.tag} workers={w:2d} exit={rc} {time.time() - t0:5.0f}s", flush=True)
        if i < len(args.workers) - 1 and args.cooldown:
            time.sleep(args.cooldown)   # let the API's per-minute budgets refill


# ================================================================== the report
def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))] if v else float("nan")


def one_run(path):
    r = json.load(open(path))
    pairs = [p for p in r["pairs"] if not p["error"]]
    t_first = min(p["start"] for p in r["pairs"])
    t_last = max(p["end"] for p in r["pairs"])
    batch = t_last - t_first
    walls = [p["wall"] for p in pairs]
    lit = [p["lit_seconds"] for p in pairs if p["lit_seconds"] is not None]
    ot = [p["ot_seconds"] for p in pairs if p["ot_seconds"]]
    samples = [s for s in r["samples"] if t_first <= s["t"] <= t_last]

    def mean_live(name):
        return st.mean(s["live"].get(name, 0) for s in samples) if samples else float("nan")

    def peak_live(name):
        return max((s["live"].get(name, 0) for s in samples), default=0)

    ncbi = [q for q in r["requests"] if q[2] == "ncbi"]
    ot_req = [q for q in r["requests"] if q[2] == "opentargets"]
    gate = [b - a for a, b in r["ncbi_gate"]]
    sdk = r["anthropic_sdk"]
    # busiest second of NCBI traffic, by request start
    starts = sorted(q[0] for q in ncbi)
    busiest = max((sum(1 for s in starts if t <= s < t + 1) for t in starts), default=0)
    sdk_retry = [m for _, kind, m in r["log"] if kind == "sdk" and m.startswith("Retrying request")]
    sdk_status = {}
    for _, kind, m in r["log"]:
        if kind == "sdk" and m.startswith("Retrying due to status code"):
            code = m.rsplit(" ", 1)[-1]
            sdk_status[code] = sdk_status.get(code, 0) + 1
    timeouts = sum(1 for _, kind, m in r["log"] if kind == "sdk" and "TimeoutException" in m)
    # A 400 is pesto's own probe: a model that refuses `temperature` is
    # remembered and called without it. Counted apart from real failures.
    bad_sdk, temperature_probes = {}, 0
    for *_, status in sdk:
        if status == 400:
            temperature_probes += 1
        elif status != 200:
            bad_sdk[str(status)] = bad_sdk.get(str(status), 0) + 1
    bad_ncbi, bad_ot = {}, {}
    for bad, group in ((bad_ncbi, ncbi), (bad_ot, ot_req)):
        for *_, status in group:
            if status != 200:
                bad[str(status)] = bad.get(str(status), 0) + 1
    models = {}
    for t0, t1, model, _ in sdk:
        models.setdefault("opus" if "opus" in model else "haiku" if "haiku" in model else model, []).append(t1 - t0)
    cpu_n = r["cpu_count"]
    return {
        "workers": int(r["argv"][r["argv"].index("--workers") + 1]),
        "batch_seconds": batch, "startup_seconds": t_first - r["t_main0"],
        "pairs_ok": len(pairs), "pairs_failed": len(r["pairs"]) - len(pairs),
        "pairs_per_minute": 60 * len(pairs) / batch,
        "pair_median": st.median(walls), "pair_mean": st.mean(walls), "pair_p90": pct(walls, 90), "pair_max": max(walls),
        "lit_median": st.median(lit), "ot_median": st.median(ot),
        "lit_p90": pct(lit, 90), "ot_p90": pct(ot, 90),
        "pairs_active_mean": mean_live("pairs_active"),
        "anthropic_calls": len(r["anthropic_calls"]), "anthropic_sdk_requests": len(sdk),
        "anthropic_inflight_peak": peak_live("anthropic_sdk"), "anthropic_inflight_mean": mean_live("anthropic_sdk"),
        "haiku_latency_median": st.median(models.get("haiku", [float("nan")])),
        "haiku_latency_p90": pct(models.get("haiku", []), 90),
        "opus_latency_median": st.median(models.get("opus", [float("nan")])),
        "opus_latency_p90": pct(models.get("opus", []), 90),
        "ncbi_requests": len(ncbi), "ncbi_inflight_peak": peak_live("http:ncbi"),
        "ncbi_inflight_mean": mean_live("http:ncbi"), "ncbi_waiting_peak": peak_live("ncbi_waiting"),
        "ncbi_waiting_mean": mean_live("ncbi_waiting"),
        "ncbi_rate_mean": len(ncbi) / batch, "ncbi_rate_busiest_second": busiest, "ncbi_cap": r["ncbi_per_second"],
        "ncbi_latency_median": st.median([q[1] - q[0] for q in ncbi]) if ncbi else float("nan"),
        "gate_wait_median": st.median(gate) if gate else 0, "gate_wait_p95": pct(gate, 95), "gate_wait_max": max(gate, default=0),
        "gate_wait_total": sum(gate),
        "opentargets_requests": len(ot_req), "opentargets_inflight_peak": peak_live("http:opentargets"),
        "sdk_retries": len(sdk_retry), "sdk_retry_status": sdk_status, "sdk_timeouts": timeouts,
        "anthropic_errors_after_retries": bad_sdk, "anthropic_temperature_400_probes": temperature_probes,
        "ncbi_non200": bad_ncbi, "opentargets_non200": bad_ot,
        "cpu_proc_mean_pct_of_machine": st.mean(s["cpu_proc"] for s in samples) / cpu_n if samples else float("nan"),
        "cpu_proc_peak_pct_of_machine": max((s["cpu_proc"] for s in samples), default=0) / cpu_n,
        "cpu_sys_mean_pct": st.mean(s["cpu_sys"] for s in samples) if samples else float("nan"),
        "cpu_sys_peak_pct": max((s["cpu_sys"] for s in samples), default=0),
        "rss_peak_mb": max((s["rss_mb"] for s in samples), default=0),
        "avail_mb_min": min((s["avail_mb"] for s in samples), default=0),
        "threads_peak": max((s["threads"] for s in samples), default=0),
    }


def report(args):
    import csv
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for d in sorted(os.listdir(RAW)):
        p = os.path.join(RAW, d, "run.json")
        if os.path.exists(p):
            row = one_run(p)
            row["run"] = d
            row["tag"] = d.split("_w")[0]
            # sanity: did the answers come out the same as the reference run of these pairs?
            ref = {(r["gene"], r["phenotype"]): r for r in csv.DictReader(open(BATCH), delimiter="\t")}
            got = {(r["gene"], r["phenotype"]): r for r in csv.DictReader(open(os.path.join(RAW, d, "pesto.tsv")), delimiter="\t")}
            both = [k for k in ref if k in got and got[k]["lit_mean"]]
            row["lit_verdict_same_as_reference"] = sum(ref[k]["lit_mean"] == got[k]["lit_mean"] for k in both)
            row["ot_verdict_same_as_reference"] = sum(ref[k]["open_targets_verdict"] == got[k]["open_targets_verdict"] for k in both)
            rows.append(row)
    rows.sort(key=lambda r: (r["workers"], r["tag"]))
    keys = list(rows[0])
    with open(os.path.join(OUT, "worker_sweep_runs.tsv"), "w") as fh:
        fh.write("\t".join(keys) + "\n")
        for r in rows:
            fh.write("\t".join(json.dumps(r[k]) if isinstance(r[k], dict) else
                               (f"{r[k]:.3f}" if isinstance(r[k], float) else str(r[k])) for k in keys) + "\n")
    print(f"wrote {len(rows)} runs to {OUT}/worker_sweep_runs.tsv")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "child":
        sys.exit(child(sys.argv[2:]))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--workers", type=int, nargs="+", required=True)
    r.add_argument("--tag", required=True)
    r.add_argument("--cooldown", type=int, default=60, help="seconds between runs")
    sub.add_parser("report")
    args = ap.parse_args()
    run_sweep(args) if args.cmd == "run" else report(args)


if __name__ == "__main__":
    main()
