"""What a pair cost, from the tokens the models actually returned.

The literature blocks already call `call_llm_with_usage`; this module is the
place those counts are kept, priced, and written out. Open Targets is outside
the arm, so its two calls are attached afterwards rather than folded into a
block fingerprint.
"""
from __future__ import annotations

import csv
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar

from .config import price_usd

_SINK = ContextVar("pesto_usage_sink", default=None)
_LOCK = threading.Lock()

COST_FIELDS = (
    "gene", "phenotype", "step", "model", "calls",
    "input_tokens", "output_tokens", "usd", "cached",
)


def record(model, input_tokens, output_tokens):
    sink = _SINK.get()
    if sink is None:
        return
    with _LOCK:
        sink.append({
            "model": model or "",
            "input_tokens": int(input_tokens or 0),
            "output_tokens": int(output_tokens or 0),
        })


def thread_pool(max_workers):
    """A pool whose workers write to the same usage sink as this thread.

    `ThreadPoolExecutor` does not copy ContextVars, so Bands (and the other
    batched Haiku passes) used to spend tokens that `capturing` never saw.
    """
    sink = _SINK.get()

    def init():
        if sink is not None:
            _SINK.set(sink)

    return ThreadPoolExecutor(max_workers=max_workers, initializer=init)


class capturing:
    """Collect every `call_llm_with_usage` on this thread (and its pool)."""

    def __enter__(self):
        self.rows = []
        self._token = _SINK.set(self.rows)
        return self

    def __exit__(self, *exc):
        _SINK.reset(self._token)

    def summary(self, declared_model=None):
        inn = sum(r["input_tokens"] for r in self.rows)
        out = sum(r["output_tokens"] for r in self.rows)
        priced = [(r, price_usd(r["model"], r["input_tokens"], r["output_tokens"]))
                  for r in self.rows]
        usd = sum(p for _, p in priced if p is not None)
        # Models with no price are named, never charged at another model's rate.
        unpriced = sorted({r["model"] or "(unnamed)" for r, p in priced if p is None})
        models = [r["model"] for r in self.rows if r["model"]]
        model = declared_model
        if not model and models:
            model = models[0] if len(set(models)) == 1 else "mixed"
        return {
            "input_tokens": inn,
            "output_tokens": out,
            "usd": round(usd, 6),          # the priced calls only; see unpriced
            "unpriced": unpriced,
            "calls": len(self.rows),
            "model": model,
        }


def row(gene, phenotype, step, model, calls, input_tokens, output_tokens,
        usd, cached):
    """One line of the cost table. `usd` of None is an unpriced call, written as
    an empty cell: a number there would be a claim about a price nobody gave."""
    return {
        "gene": gene, "phenotype": phenotype, "step": step,
        "model": model or "", "calls": int(calls or 0),
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "usd": "" if usd is None else f"{float(usd):.6f}",
        "cached": bool(cached),
    }


def from_trace(gene, phenotype, trace, cached=False):
    """One row per literature block that talked to a model."""
    rows = []
    for step in getattr(trace, "steps", ()) or ():
        inn = int(getattr(step, "input_tokens", 0) or 0)
        out = int(getattr(step, "output_tokens", 0) or 0)
        if inn == 0 and out == 0:
            continue
        unpriced = getattr(step, "unpriced", ()) or ()
        rows.append(row(
            gene, phenotype, step.block, step.model,
            getattr(step, "calls", 0) or 0, inn, out,
            None if unpriced else (getattr(step, "usd", 0) or 0), cached))
    return rows


def from_ot_tokens(gene, phenotype, tokens, cached=False):
    """The two tagged-shortlist calls, if that matcher ran."""
    if not tokens:
        return []
    from .ot_matcher import BROAD_MODEL as PUBLISHED_READER
    from .ot_matcher import GATE_MODEL as PUBLISHED_GATE
    # The models that gave the counts. Records written before the models were
    # configurable carry none, and were made by the published pair.
    GATE_MODEL = tokens.get("gate_model") or PUBLISHED_GATE
    BROAD_MODEL = tokens.get("read_model") or PUBLISHED_READER
    out = []
    gate_in, gate_out = tokens.get("gate_in") or 0, tokens.get("gate_out") or 0
    if gate_in or gate_out:
        out.append(row(gene, phenotype, "ot_gate", GATE_MODEL, 1,
                       gate_in, gate_out, price_usd(GATE_MODEL, gate_in, gate_out),
                       cached))
    read_in, read_out = tokens.get("read_in") or 0, tokens.get("read_out") or 0
    if read_in or read_out:
        out.append(row(gene, phenotype, "ot_read", BROAD_MODEL, 1,
                       read_in, read_out, price_usd(BROAD_MODEL, read_in, read_out),
                       cached))
    # broad_opus leaves a single usage blob, no gate/read split
    if not out and (tokens.get("input_tokens") or tokens.get("output_tokens")):
        inn = tokens.get("input_tokens") or 0
        tout = tokens.get("output_tokens") or 0
        out.append(row(gene, phenotype, "ot_read", BROAD_MODEL, 1,
                       inn, tout, price_usd(BROAD_MODEL, inn, tout), cached))
    return out


def from_usage(gene, phenotype, step, usage_rows, cached=False):
    """One line per model for calls captured outside a block (`capturing().rows`),
    such as the `--arm auto` router, priced like any other call."""
    by_model = {}
    for r in usage_rows or ():
        n = by_model.setdefault(r["model"], [0, 0, 0])
        n[0] += 1
        n[1] += r["input_tokens"]
        n[2] += r["output_tokens"]
    return [row(gene, phenotype, step, model, calls, inn, out,
                price_usd(model, inn, out), cached)
            for model, (calls, inn, out) in sorted(by_model.items())]


def with_total(rows, gene, phenotype, cached=False):
    if not rows:
        return [row(gene, phenotype, "total", "", 0, 0, 0, 0, cached)]
    # One unpriced line makes the total unpriced: a sum of the other lines would
    # read as the cost of the pair and be less than it.
    unpriced = any(r["usd"] in ("", None) for r in rows)
    return list(rows) + [row(
        gene, phenotype, "total", "",
        sum(int(r["calls"]) for r in rows),
        sum(int(r["input_tokens"]) for r in rows),
        sum(int(r["output_tokens"]) for r in rows),
        None if unpriced else sum(float(r["usd"]) for r in rows),
        cached)]


def path_for(pesto_out):
    """Sibling cost.tsv when the answers are pesto.tsv, else <stem>.cost.tsv."""
    pesto_out = os.path.abspath(pesto_out)
    folder, name = os.path.split(pesto_out)
    if name == "pesto.tsv":
        return os.path.join(folder, "cost.tsv")
    stem, ext = os.path.splitext(name)
    return os.path.join(folder, f"{stem}.cost{ext or '.tsv'}")


def load_table(path):
    if not path or not os.path.exists(path):
        return {}
    by = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            by.setdefault((r.get("gene", ""), r.get("phenotype", "")), []).append(r)
    return by


def write_table(path, by_pair):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    rows = []
    for key in sorted(by_pair):
        rows.extend(by_pair[key])
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COST_FIELDS, delimiter="\t",
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
