"""Passive recorders around the real `pesto --bench` path. Nothing here changes a
prompt, a model, a setting or any logic: it wraps calls to record them.

  * every provider call (model, prompt, answer, tokens, seconds, stop reason)
  * the router's arm and time, and the wall time of each pair
  * the full candidate pool the sieve saw, and the band of each article
  * the flow result (trace per step, counts, read set, raw answer)
  * the retry / refusal / warning lines printed during a pair
  * a spend ledger shared by every stage, with a soft stop
"""
import builtins, contextvars, gzip, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

ROOT = "/Users/dinan_elsyad/pesto_cmp"
SRC = "/Users/dinan_elsyad/Broad_projects/PESTO-release/src"
sys.path.insert(0, SRC)

from pesto import cli, config                                   # noqa: E402
from pesto.flow import run as flow_run, steps                   # noqa: E402
from pesto.services.providers import anthropic_provider as AP   # noqa: E402
from pesto.services.providers import openai_provider as OP      # noqa: E402

CTX = contextvars.ContextVar("cmp_ctx", default=None)
LOCK = threading.Lock()
LEDGER = os.path.join(ROOT, "ledger.jsonl")
SOFT_STOP = float(os.environ.get("CMP_SOFT_STOP", "34"))
HARD_STOP = 40.0
OUT = {"dir": ROOT}          # where this process writes (set per run)


class BudgetStop(RuntimeError):
    pass


def spent():
    if not os.path.exists(LEDGER):
        return 0.0
    return sum(json.loads(l)["usd"] for l in open(LEDGER))


def charge(stage, fam, usd, note=""):
    with LOCK:
        with open(LEDGER, "a") as fh:
            fh.write(json.dumps({"t": time.time(), "stage": stage, "fam": fam,
                                 "usd": round(usd, 6), "note": note}) + "\n")


def check_budget():
    s = spent()
    if s >= SOFT_STOP:
        raise BudgetStop(f"spend ${s:.2f} reached the ${SOFT_STOP:.0f} soft stop")


class Job:
    def __init__(self, fam, rep, phenotype):
        self.fam, self.rep, self.phenotype = fam, rep, phenotype
        self.gene = None
        self.t0 = time.time()
        self.calls, self.log, self.pool, self.res = [], [], None, None
        self.router_secs = self.router_arm = self.router_usage = None


# ------------------------------------------------------------------ plumbing
_orig_submit = ThreadPoolExecutor.submit


def _submit(self, fn, /, *a, **k):
    ctx = contextvars.copy_context()
    return _orig_submit(self, ctx.run, fn, *a, **k)


_orig_print = builtins.print


def _print(*a, **k):
    c = CTX.get()
    job = c.get("job") if c else None
    if job is not None and k.get("file") is None:
        job.log.append(" ".join(str(x) for x in a))
    return _orig_print(*a, **k)


def _calls_file(fam, rep):
    return os.path.join(OUT["dir"], f"calls_{rep}_{fam}.jsonl.gz")


def _write_gz(path, rec):
    with LOCK:
        with gzip.open(path, "at") as fh:
            fh.write(json.dumps(rec) + "\n")


def _wrap_provider(cls):
    orig = cls.complete

    def complete(self, *a, **k):
        model, prompt = a[0], a[1]
        c = CTX.get() or {}
        job = c.get("job")
        t = time.time()
        res = err = None
        try:
            res = orig(self, *a, **k)
            return res
        except BaseException as e:               # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:400]}"
            raise
        finally:
            rec = {"provider": self.name, "model": model,
                   "secs": round(time.time() - t, 2), "prompt_chars": len(prompt),
                   "error": err}
            if res is not None:
                rec.update(input_tokens=res.input_tokens, output_tokens=res.output_tokens,
                           reasoning_tokens=res.reasoning_tokens,
                           stop_reason=res.stop_reason,
                           usd=config.price_usd(("openai:" + model) if self.name == "openai" else model,
                                                res.input_tokens, res.output_tokens))
            if job is not None:
                job.calls.append(rec)
                full = dict(rec, fam=job.fam, rep=job.rep, gene=job.gene,
                            phenotype=job.phenotype, prompt=prompt,
                            text=(res.text if res is not None else None))
                _write_gz(_calls_file(job.fam, job.rep), full)
    cls.complete = complete


def install():
    if getattr(install, "done", False):
        return
    install.done = True
    ThreadPoolExecutor.submit = _submit
    builtins.print = _print
    AP.VERBOSE_MODE = True          # prints one line per API attempt; changes nothing else
    OP.VERBOSE_MODE = True
    _wrap_provider(AP.AnthropicProvider)
    _wrap_provider(OP.OpenAIProvider)

    # --- sieve: the pool it saw and what it said about each article
    orig_bands = steps.Bands.run

    def bands_run(self, query, corpus, terms=None):
        c = CTX.get() or {}
        job = c.get("job")
        if job is not None:
            job.pool = corpus.as_dicts()
        return orig_bands(self, query, corpus, terms)
    steps.Bands.run = bands_run

    # --- the flow result
    orig_flow = flow_run.run

    def run(arm, query, *a, **k):
        res = orig_flow(arm, query, *a, **k)
        c = CTX.get() or {}
        job = c.get("job")
        if job is not None:
            job.res = res
        return res
    flow_run.run = run

    # --- router: arm chosen, time, usage
    orig_route = cli.route

    def route(args, phenotype, reader, worker):
        base = CTX.get() or {}
        job = Job(base.get("fam"), base.get("rep"), phenotype)
        CTX.set(dict(base, job=job))
        t = time.time()
        chosen, rows = orig_route(args, phenotype, reader, worker)
        job.router_secs = round(time.time() - t, 2)
        job.router_arm = chosen.name
        job.router_usage = [dict(r) for r in rows]
        return chosen, rows
    cli.route = route

    # --- the pair: wall time, record, spend
    orig_assess = cli.assess

    def assess(arm, gene, phenotype, args, worker, flow_dir, router_rows=()):
        base = CTX.get() or {}
        job = base.get("job")
        if job is None:
            job = Job(base.get("fam"), base.get("rep"), phenotype)
            CTX.set(dict(base, job=job))
        job.gene = gene
        check_budget()
        t = time.time()
        row, err = None, None
        try:
            row = orig_assess(arm, gene, phenotype, args, worker, flow_dir, router_rows)
            return row
        except BaseException as e:               # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:400]}"
            raise
        finally:
            _finalize(job, arm, row, err, time.time() - t)
    cli.assess = assess


def _finalize(job, arm, row, err, assess_secs):
    res = job.res
    cost_rows = [dict(r) for r in ((row or {}).get("_cost") or [])]
    usd = 0.0
    for r in cost_rows:
        if r.get("step") == "total":
            continue
        try:
            usd += float(r.get("usd") or 0)
        except ValueError:
            pass
    rec = {
        "fam": job.fam, "rep": job.rep, "gene": job.gene, "phenotype": job.phenotype,
        "error": err, "arm": arm.name,
        "router_arm": job.router_arm, "router_secs": job.router_secs,
        "router_usage": job.router_usage,
        "assess_secs": round(assess_secs, 2),
        "wall_secs": round((job.router_secs or 0) + assess_secs, 2),
        "usd": round(usd, 6),
        "row": {k: v for k, v in (row or {}).items() if k != "_cost"},
        "cost_rows": cost_rows,
        "calls": job.calls, "log": job.log,
        "pool": job.pool,
        "res": None if res is None else {
            "counts": dict(res.counts), "trace": res.trace.as_list(),
            "raw": res.raw, "terms": res.terms,
            "verdict": {"call": res.verdict.call,
                        "dist": res.verdict.distribution.as_dict() if res.verdict.distribution else None,
                        "justification": res.verdict.justification,
                        "pmids": list(res.verdict.pmids or [])},
            "read": res.corpus.as_dicts() if res.corpus else [],
            "bands": {p: list(t) for p, t in (res.labels.tiers().items() if res.labels else [])},
        },
    }
    _write_gz(os.path.join(OUT["dir"], f"pairs_{job.rep}_{job.fam}.jsonl.gz"), rec)
    charge(f"e2e_{job.rep}", job.fam, usd, f"{job.gene}|{job.phenotype}")
