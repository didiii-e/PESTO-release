#!/usr/bin/env python3
"""Ask whether a gene and a phenotype are already linked in the literature.

    pesto --gene DDX41 --phenotype "myelodysplastic syndrome"
    pesto --bench pairs.tsv
    pesto browser

Two answers come back, from two sources that are kept apart on purpose. The
literature verdict is read off the abstracts the pipeline retrieves and weighs.
The Open Targets verdict is read off that database's own evidence for the gene.
They disagree often, and the disagreement is informative, so neither is folded
into the other. A table of pairs is the same two answers, in parallel, one
process, so the embedding model is loaded once.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import logging
import os
import sys
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import config

CREDENTIALS_SOURCE = ("https://github.com/jeremyguez/PESTO-release/blob/main/"
                      "src/pesto/credentials.py")

KEY_HELP = """\
No {label} API key found, and this run calls {used}.
{why}Get a key from {key_url}:

  export {key_env}={key_example}
"""

KEY_FOOTER = """\
or the same line, without `export`, in a .env file you create here:
  {env_path}

A key stays on this machine. PESTO never writes it to disk, never prints it
and never stores it in a saved run; each is handed only to its vendor's
official client, which sends it to that vendor ({hosts}) and nowhere else.
The code that reads them is short:
  {source}
"""

# Why the run calls a model, in the words a person would use for it.
ROUTER_WHY = ("`--arm auto` asks {model} whether the phenotype is a disease or "
              "a trait. Name another model with --router-model, or pass "
              "`--arm abstracts` or `--arm abstracts-trait`, which ask none.\n")


def pick_models(reader, worker):
    """What to read with, where None means: whatever the arm already says.

    An arm names the models its published numbers were produced by. Passing
    --model or --model-fast swaps them, and the fingerprint records that it did.
    A bare name is an Anthropic model; `openai:NAME[@effort]` is an OpenAI one.
    A spec that cannot run is refused here, before anything is fetched or paid for.
    """
    from .services import providers
    for flag, spec in (("--model", reader), ("--model-fast", worker)):
        if spec:
            try:
                providers.validate(spec)
            except ValueError as exc:
                raise SystemExit(f"pesto: {flag}: {exc}")
    return reader or None, worker or None


def needed_models(args, arm, fitted):
    """Every model this command would call, with why: {spec: [reasons]}.

    `arm` is None for `--arm auto`, in which case both arms of the family are
    candidates and the router is called. The keys asked for are the keys of
    these models and no others: a run on OpenAI models needs no Anthropic key
    unless one of the calls above is Anthropic's.
    """
    from .flow import arms
    needed = {}

    def need(spec, why):
        needed.setdefault(spec, []).append(why)

    if arm is None:
        need(router_model_of(args), "the `--arm auto` router")
        for name in arms.FAMILIES[family_of(args)]:
            for spec in fitted(name).models():
                need(spec, "the literature arm")
    else:
        for spec in arm.models():
            need(spec, "the literature arm")
    if not getattr(args, "max_date", None):
        gate_model, reader_model = ot_models_of(args)
        need(reader_model, "the Open Targets reader")
        if not getattr(args, "no_ot_gate", False) and config.OT_GATE:
            need(gate_model, "the Open Targets gate")
    return needed


def ot_models_of(args):
    """The Open Targets gate and reader this command asks for, as canonical
    specs, or a refusal naming the flag whose value cannot run."""
    from .services import providers
    gate = getattr(args, "ot_gate_model", None)
    reader = getattr(args, "ot_reader_model", None)
    for flag, spec in (("--ot-gate-model", gate), ("--ot-reader-model", reader)):
        if spec:
            try:
                providers.validate(spec)
            except ValueError as exc:
                raise SystemExit(f"pesto: {flag}: {exc}")
    return config.ot_models(gate, reader)


def providers_canonical(spec):
    from .services import providers
    return providers.canonical(spec)


def router_model_of(args):
    """The model that tells a disease from a trait under `--arm auto`: the one
    the paper used unless --router-model names another. A refusal names the
    flag if its value cannot run."""
    from .flow import arms
    from .services import providers
    spec = getattr(args, "router_model", None)
    if not spec:
        return arms.ROUTER_MODEL
    try:
        providers.validate(spec)
    except ValueError as exc:
        raise SystemExit(f"pesto: --router-model: {exc}")
    return spec


def route(args, phenotype, reader, worker):
    """The arm `--arm auto` picks for this phenotype, and what the router spent.

    Returns (arm, usage_rows). The router is not part of any arm, so it is not
    in an arm's fingerprint and not in the cache key of a run: a stored run is
    valid whichever router sent the pair to its arm. Its model is recorded with
    the result instead (`router_model` in --json, a `router` line in the cost
    table).
    """
    from .cost import capturing
    from .flow import arms
    with capturing() as spent:
        chosen = arms.resolve(arms.AUTO, phenotype, model=router_model_of(args),
                              family=family_of(args))
    return fit(chosen, args, reader, worker), spent.rows


def router_cost_rows(args, gene, phenotype, usage_rows):
    """The router's cost lines, when a router was asked for by name.

    With the default router they are left out, as they always have been, so
    that the cost of a default run is the figure it has always been. Naming a
    router is a choice about cost, and the cost is then shown."""
    from .cost import from_usage
    if not getattr(args, "router_model", None):
        return []
    return from_usage(gene, phenotype, "router", usage_rows)


def require_keys(needed):
    """Stop, before anything is fetched or paid for, if a model this run calls
    belongs to a provider whose key is missing. Says which, and why."""
    from .services import providers
    missing = providers.missing_keys(needed)
    if not missing:
        return
    blocks = []
    for provider in missing:
        specs = sorted(s for s in needed if providers.resolve(s).provider is provider)
        why = "".join(ROUTER_WHY.format(model=s)
                      for s in specs if "the `--arm auto` router" in needed[s])
        blocks.append(KEY_HELP.format(
            label=provider.label, used=", ".join(specs), why=why,
            key_url=provider.key_url, key_env=provider.key_env,
            key_example=provider.key_example))
    raise SystemExit("\n".join(blocks) + "\n" + KEY_FOOTER.format(
        env_path=os.path.join(config.PROJECT_ROOT, ".env"),
        hosts=", ".join(sorted({p.host for p in missing})),
        source=CREDENTIALS_SOURCE))


# What the Open Targets columns say when --max-date kept that branch from running.
OT_SKIPPED = "not run: --max-date"

MAX_DATE_WARNING = """\
pesto: --max-date {date}: PubMed and Europe PMC are searched for articles
published up to that date only. Open Targets is not run: the API serves only
its current release, whose scores cannot be dated. {reader}"""
DATE_NOTE_ON = """The model that reads the
abstracts is told to judge from them alone (--no-date-note: not told), but it
may still know of work published later."""
DATE_NOTE_OFF = """The model that reads the
abstracts may still know of work published later."""


def reader_notes(args, arm):
    """What the reading prompt is told before the articles: the instruction
    --max-date adds unless --no-date-note, then every --note in order."""
    notes = [n.strip() for n in (getattr(args, "note", None) or ()) if n.strip()]
    if (getattr(args, "max_date", None) and not getattr(args, "no_date_note", False)
            and arm.read.takes("notes")):
        from .utils.helpers import load_prompt
        notes.insert(0, load_prompt("max_date_note").strip().format(
            date=args.max_date))
    return tuple(notes)


def fit(arm, args, reader, worker):
    """The arm as this command line asks for it: models, date and notes."""
    try:
        return arm.using(reader=reader, worker=worker,
                         max_date=getattr(args, "max_date", None),
                         notes=reader_notes(args, arm))
    except ValueError as exc:
        raise SystemExit(f"pesto: {exc}")


def open_targets(gene, phenotype, synonyms, model, runs_dir, args=None):
    """That database's own answer, kept apart from the literature's.

    It is a lookup and a match, not a reading, so it does not belong in the arm.
    Where the two disagree is informative, which is the reason neither is folded
    into the other.
    """
    if getattr(args, "max_date", None):
        return "", None, {}, {"channel": OT_SKIPPED}
    from .open_targets import fetch_and_save_open_targets_traits
    from .scoring import open_targets_verdict
    traits = fetch_and_save_open_targets_traits(
        gene, runs_dir, phenotype, list(synonyms or ()), model=model,
        matcher=getattr(args, "ot_matcher", None),
        encoder=getattr(args, "ot_encoder", None),
        top_k=getattr(args, "ot_top", None),
        gate_model=getattr(args, "ot_gate_model", None),
        reader_model=getattr(args, "ot_reader_model", None),
        # The flags read the other way round from the parameters, so that both
        # read naturally where they are written: `--no-ot-gate` on the command
        # line, `gate=False` in the call.
        gate=False if getattr(args, "no_ot_gate", False) else None,
        reasons=True if getattr(args, "ot_reasons", False) else None)
    match = (traits or {}).get("match") or {}
    ot_tokens = match.get("tokens") or match.get("usage") or {}
    return open_targets_verdict(traits) + (ot_tokens, match)


def render(result, ot_verdict, arm, show_reasoning):
    """The two verdicts, and what they were read from."""
    q = result.query
    out = [f"{q.gene}  /  {q.phenotype}", ""]
    out.append(f"  literature      {result.verdict.call}")
    out.append(f"  open targets    "
               f"{ot_verdict or (OT_SKIPPED if result.max_date else 'unknown')}")
    if result.max_date:
        out.append(f"  articles published up to {result.max_date}")
    out.append("")

    read = result.counts.get("read", 0)
    found = result.counts.get("found", 0)
    source = ("reused an identical earlier run" if result.cached else
              f"{found} articles found, {read} read")
    out.append(f"  {source}, pipeline {arm.name} [{result.fingerprint}]")

    if show_reasoning and result.verdict.justification:
        out.append("")
        out.extend("  " + line for line in
                   textwrap.wrap(result.verdict.justification, width=76))
    if show_reasoning and result.verdict.pmids:
        out.append("")
        out.append("  rests on  " + ", ".join(result.verdict.pmids))
    return "\n".join(out)


WEIGHT = {"Established": 4, "Existing": 3, "Hypothesized": 2, "Novel": 1}
ORDER = ("Novel", "Hypothesized", "Existing", "Established")


def mean_call(dist):
    """The category the hundred points average to, as figure 2a already plots."""
    if not dist:
        return ""
    total = sum(dist.get(k, 0) for k in WEIGHT) or 1
    rank = sum(WEIGHT[k] * dist.get(k, 0) for k in WEIGHT) / total
    return ORDER[max(1, min(4, round(rank))) - 1]


def read_bench(path):
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    if not rows:
        raise SystemExit(f"pesto: {path} is empty")
    if "gene" not in rows[0] or "phenotype" not in rows[0]:
        raise SystemExit(f"pesto: {path} needs gene and phenotype columns")
    return rows


def assess(arm, gene, phenotype, args, worker, flow_dir, router_rows=()):
    """One pair: literature, then Open Targets. Same path as a single call."""
    from .flow import run as flow_run
    from .flow.types import Query
    query = Query(gene, phenotype)
    chatter = io.StringIO()
    with contextlib.redirect_stdout(chatter):
        result = flow_run.run(arm, query, cache=not args.no_cache,
                              runs_dir=flow_dir)
        ot_verdict, ot_score, ot_tokens, ot_match = open_targets(
            gene, phenotype, result.terms.get("synonyms"),
            worker or config.DEFAULT_MODEL, args.data_dir, args)
    dist = (result.verdict.distribution.as_dict()
            if result.verdict.distribution else None)
    from .cost import from_ot_tokens, from_trace, with_total
    return {
        "gene": gene, "phenotype": phenotype,
        "arm": arm.name, "fingerprint": result.fingerprint,
        "max_date": arm.max_date,
        "notes": " | ".join(getattr(arm.read, "notes", ())).replace("\t", " "),
        "lit_argmax": result.verdict.call,
        "lit_mean": mean_call(dist or {}),
        "p_established": (dist or {}).get("Established", ""),
        "p_existing": (dist or {}).get("Existing", ""),
        "p_hypothesized": (dist or {}).get("Hypothesized", ""),
        "p_novel": (dist or {}).get("Novel", ""),
        "open_targets_verdict": ot_verdict,
        "open_targets_max_score": "" if ot_score is None else ot_score,
        "ot_channel": ot_match.get("channel") or "",
        "ot_tag": ot_match.get("deciding_tag") or "",
        "ot_trait": ot_match.get("basis") or "",
        "ot_cap": ot_match.get("cap") or "",
        "found": result.counts.get("found", 0),
        "read": result.counts.get("read", 0),
        "cached": result.cached,
        "justification": (result.verdict.justification or "").replace("\t", " "),
        "error": "",
        "_cost": with_total(
            list(router_rows)
            + from_trace(gene, phenotype, result.trace, result.cached)
            + from_ot_tokens(gene, phenotype, ot_tokens,
                             cached=bool(ot_match.get("cached"))),
            gene, phenotype, result.cached),
    }


def resumable(out, fingerprints, fields):
    """Pairs an earlier attempt already answered, keyed like the work queue.

    The criterion is the arm's fingerprint, exactly as in the flow cache: a row
    answers this question only if this pipeline produced it. Two rows are
    refused on top of that. One carrying an error is not an answer, and one
    without a literature verdict came from a run that stopped in the middle --
    which is precisely what an interrupted batch leaves behind.

    An empty Open Targets verdict is *not* refused: a gene that branch cannot
    resolve legitimately has none, and asking again would never fill it.

    Unlike the flow cache this reuses the summary row rather than reopening the
    stored run, so it also skips the Open Targets call, which has no cache of
    its own and is otherwise repaid on every attempt.
    """
    if not os.path.exists(out):
        return {}
    keep = {}
    if hasattr(fingerprints, "fingerprint"):
        allowed = {fingerprints.fingerprint()}
    else:
        allowed = set(fingerprints)
    with open(out, encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if row.get("fingerprint") not in allowed:
                continue
            if (row.get("error") or "").strip():
                continue
            if not (row.get("lit_mean") or "").strip():
                continue
            keep[(row["gene"], row["phenotype"])] = {k: row.get(k, "")
                                                     for k in fields}
    return keep


def write_table(out, fields, rows):
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t",
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# The columns a table of answers carries after the input's own.
ANSWER_FIELDS = ["lit_mean", "lit_argmax", "p_established", "p_existing",
                 "p_hypothesized", "p_novel", "open_targets_verdict",
                 "open_targets_max_score", "ot_channel", "ot_tag",
                 "ot_trait", "ot_cap", "found", "read", "cached",
                 "arm", "fingerprint", "max_date", "notes", "justification",
                 "error"]


def run_bench(args, arm, worker, reader=None):
    """Every row of a TSV, in parallel, one process."""
    from .flow import arms
    from .ot_shortlist import encoder, resolve_encoder
    rows = read_bench(args.bench)
    # Traits live under --data-dir; literature runs sit beside them so a
    # benchmark folder holds both and does not mix with data/runs/.
    flow_dir = os.path.join(args.data_dir, "flow")
    os.makedirs(args.data_dir, exist_ok=True)
    os.makedirs(flow_dir, exist_ok=True)
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.bench)),
                                   "pesto.tsv")
    from .cost import load_table as load_cost, path_for as cost_path, write_table as write_cost
    costs_out = cost_path(out)
    extra = [k for k in rows[0] if k not in ("gene", "phenotype")]
    fields = ["gene", "phenotype"] + extra + ANSWER_FIELDS

    max_date = getattr(args, "max_date", None)

    def fitted(name):
        return fit(arms.get(name), args, reader, worker)

    family = family_of(args)
    if arm is None:
        allowed = {fitted(n).fingerprint() for n in arms.FAMILIES[family]}
        label = "auto: " + " or ".join(arms.FAMILIES[family])
    else:
        allowed = {arm.fingerprint()}
        label = f"{arm.name} [{arm.fingerprint()}]"

    done, lock = {}, threading.Lock()
    costs = load_cost(costs_out) if getattr(args, "resume", False) else {}
    if getattr(args, "resume", False):
        done.update(resumable(out, allowed, fields))
        rows = [r for r in rows if (r["gene"], r["phenotype"]) not in done]
        print(f"resumed {len(done)} rows from {out}", file=sys.stderr)
        if not rows:
            write_table(out, fields, done.values())
            write_cost(costs_out, costs)
            print(f"nothing left to do; wrote {out}", file=sys.stderr)
            return 0
    resumed = len(done)

    # One load, on this thread, before anyone asks for a ranking. After the
    # resume check, so a batch with nothing left to do does not pay for it.
    if not max_date and resolve_encoder(args.ot_encoder) != "none":
        encoder(args.ot_encoder)

    started = time.time()
    print(f"{len(rows)} pairs, {args.workers} workers, {label}", file=sys.stderr)

    def work(r):
        gene, pheno = r["gene"], r["phenotype"]
        chosen = arm
        if chosen is None:
            with contextlib.redirect_stdout(io.StringIO()):
                chosen, routed = route(args, pheno, reader, worker)
        try:
            row = assess(chosen, gene, pheno, args, worker, flow_dir,
                         router_rows=router_cost_rows(args, gene, pheno, routed))
        except Exception as exc:
            row = {k: "" for k in fields}
            row.update({"gene": gene, "phenotype": pheno,
                        "error": f"{type(exc).__name__}: {exc}"})
        for k in extra:
            row[k] = r.get(k, "")
        with lock:
            done[(gene, pheno)] = row
            if row.get("_cost"):
                costs[(gene, pheno)] = row["_cost"]
            write_table(out, fields, done.values())
            write_cost(costs_out, costs)
            n = len(done) - resumed
            left = (len(rows) - n) * (time.time() - started) / max(n, 1)
            print(f"  {n:3d}/{len(rows)}  {gene:10s} "
                  f"{row.get('lit_mean') or row.get('error', '')[:20]:14s} "
                  f"{row.get('open_targets_verdict') or '':13s} "
                  f"~{left / 60:.0f} min left", file=sys.stderr, flush=True)
        return row

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, rows))
    print(f"wrote {out}", file=sys.stderr)
    print(f"wrote {costs_out}", file=sys.stderr)
    return 0


def family_of(args):
    """Which family `auto` picks a disease or trait arm from."""
    return "fulltext" if getattr(args, "fulltext", False) else "abstracts"


def download_models():
    """Fetch the embedding models now, and report which were already here."""
    from .ot_shortlist import download
    try:
        got = download()
    except Exception as exc:
        print(f"pesto: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    for key, repo, had in got:
        print(f"  {key:<9} {repo:<48} "
              f"{'already cached' if had else 'downloaded'}")
    print("\nWeights live in ~/.cache/huggingface and are shared between "
          "installs.\nSet HF_HUB_OFFLINE=1 to forbid any further download.")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="pesto",
        description="Is this gene-phenotype association already known?",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Verdicts, weakest to strongest:
              Novel          nothing in the literature links the two
              Hypothesized   suggested, or shown for a closely related phenotype
              Existing       reported, in one study or in a form that falls short
              Established    reported repeatedly, in humans, with genetic evidence

            `pesto browser` opens the same pipeline in a web page.
            """))
    p.add_argument("--gene", metavar="SYMBOL",
                   help="HGNC gene symbol, e.g. DDX41")
    p.add_argument("--phenotype", metavar="NAME",
                   help="disease or trait, spelled as you would search for it")
    p.add_argument("--bench", metavar="TSV",
                   help="table of pairs (columns gene, phenotype). Runs them "
                        "in parallel instead of --gene / --phenotype")
    p.add_argument("--workers", type=int, default=config.DEFAULT_WORKERS,
                   metavar="N",
                   help="parallel pairs when --bench is set "
                        "(default: %(default)s)")
    p.add_argument("--out", metavar="TSV",
                   help="where the table of answers is written (--bench only; "
                        "default: pesto.tsv beside the input)")
    # Not a `choices` list: that would need the arms imported before --help can
    # be printed, and the declaration is the only place their names should live.
    # An unknown name is caught below, by the module that knows them.
    p.add_argument("--arm", default="auto", metavar="NAME",
                   help="which pipeline reads the literature. `auto` asks Opus "
                        "whether the name is a disease and then runs "
                        "`abstracts` or `abstracts-trait` (PESTO as in the "
                        "paper: twenty abstracts weighed in one call). "
                        "`fulltext` and `fulltext-trait` add a Europe PMC "
                        "search of article bodies; `titles`, `knowledge`, "
                        "`abstracts-bare`, `abstracts-open` and "
                        "`abstracts-score` are the paper's comparisons "
                        "(default: %(default)s)")
    p.add_argument("--router-model", metavar="MODEL",
                   help="with --arm auto, the model that tells a disease from "
                        "a trait (default: claude-opus-5). Same spelling as "
                        "--model, e.g. openai:gpt-6.1-sol@medium. Not part of "
                        "any arm's fingerprint: it only chooses the arm. Its "
                        "cost is shown as a `router` line in the cost table "
                        "when it is set")
    p.add_argument("--fulltext", action="store_true",
                   help="with --arm auto, choose between `fulltext` and "
                        "`fulltext-trait` instead")
    p.add_argument("--model", metavar="MODEL",
                   help="model that reads the corpus (default: the arm's own, "
                        "claude-opus-5). A bare name is an Anthropic model; "
                        "`openai:NAME[@EFFORT]` is an OpenAI one, e.g. "
                        "openai:gpt-6.1-sol@medium. Needs that provider's "
                        "API key. Does not change the Open Targets models")
    p.add_argument("--model-fast", metavar="MODEL",
                   help="model for the cheap steps: expanding the "
                        "phenotype, sieving and banding (default: the arm's "
                        "own, claude-haiku-4-5 and claude-opus-5 for synonyms). "
                        "Same spelling as --model, e.g. openai:gpt-6-luna")
    p.add_argument("--max-date", metavar="DATE",
                   help="search only articles published up to this date: "
                        "YYYY, YYYY/MM or YYYY/MM/DD (2019 means 2019/12/31), "
                        "to see what was known then. Open Targets is not run, "
                        "since it cannot be dated. The date is part of the "
                        "pipeline's fingerprint, so a cached run is reused "
                        "only for the same date. The reading model is told to "
                        "judge from the articles alone, unless --no-date-note")
    p.add_argument("--no-date-note", action="store_true",
                   help="with --max-date, send the standard reading prompt, "
                        "without the instruction to judge from the articles "
                        "alone")
    p.add_argument("--note", action="append", metavar="TEXT",
                   help="a sentence added to the reading prompt, before the "
                        "articles. Repeat for several. Part of the "
                        "fingerprint, so a cached run is reused only for the "
                        "same notes")
    p.add_argument("--no-cache", action="store_true",
                   help="read the literature again even if the same pipeline "
                        "has already answered this pair")
    p.add_argument("--resume", action="store_true",
                   help="keep the rows an earlier attempt already answered "
                        "(--bench only) and ask only for the rest. Matches on "
                        "the arm's fingerprint, so it never hands back an "
                        "answer from a different pipeline. Unlike the run "
                        "cache this also skips the Open Targets call, which "
                        "has no cache and is otherwise repaid every time")
    # The Open Targets side. Its default reads the twenty traits nearest the
    # question, sieved by a cheap model and graded one by one by an expensive
    # one, which is about half the price of reading the whole answer and grades
    # the tie rather than only finding it.
    p.add_argument("--ot-encoder", metavar="NAME",
                   help="which model ranks the answer for closeness: `biolord` "
                        "finds ties that run through a disease rather than "
                        "through a word, `sapbert` is a little faster, `none` "
                        "reads the whole answer (default: %s; `none` when "
                        "PyTorch is not installed)" % config.OT_ENCODER)
    p.add_argument("--ot-top", type=int, metavar="N",
                   help="how many of the nearest traits are read; 0 reads them "
                        "all (default: %d)" % config.OT_TOP_K)
    p.add_argument("--no-ot-gate", action="store_true",
                   help="grade every shortlisted trait, without first letting "
                        "a cheap model remove the plainly unrelated ones")
    p.add_argument("--ot-gate-model", metavar="MODEL",
                   help="model that sieves the shortlist (default: %s). Same "
                        "spelling as --model. A different model is a "
                        "different Open Targets cache entry"
                        % config.OT_PUBLISHED_GATE_MODEL)
    p.add_argument("--ot-reader-model", metavar="MODEL",
                   help="model that grades each shortlisted trait (default: "
                        "%s). Same spelling as --model" % config.OT_PUBLISHED_READER_MODEL)
    p.add_argument("--ot-reasons", action="store_true",
                   help="make the grader state why each trait got its tag. "
                        "Costs more and holds the grading up, so it is worth "
                        "it when the grades are being read and not just the "
                        "verdict")
    p.add_argument("--show-pipeline", action="store_true",
                   help="print the arm's blocks and their fingerprints, then stop")
    p.add_argument("--download-models", action="store_true",
                   help="fetch the two embedding models, 439 MB each, and stop. "
                        "Optional: the first assessment that needs one fetches "
                        "it anyway. This only moves that wait somewhere you "
                        "chose, and prepares a machine that will later run "
                        "without a network")
    p.add_argument("--data-dir", metavar="DIR", default=config.NOVEL_RUNS_DIR,
                   help="where a run writes its evidence. A single pair "
                        "defaults to data/runs/novel; --bench defaults to "
                        "runs/ beside the table, so a benchmark does not mix "
                        "with earlier answers")
    p.add_argument("--json", action="store_true",
                   help="print the whole result as JSON instead")
    p.add_argument("--quiet", action="store_true",
                   help="print the two verdicts and nothing else")
    p.add_argument("--verbose", action="store_true",
                   help="report each step on stderr while it runs")
    return p


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    # Read before parsing, because fetching weights is the one thing here that
    # is not about a pair.
    if "--download-models" in argv:
        return download_models()
    if argv[:1] == ["browser"]:
        from .browser.server import main as browser_main
        return browser_main(argv[1:])

    args = build_parser().parse_args(argv)
    if args.max_date:
        from .services.pubmed_service import normalize_max_date
        try:
            args.max_date = normalize_max_date(args.max_date)
        except ValueError as exc:
            raise SystemExit(f"pesto: --max-date: {exc}")
        print(MAX_DATE_WARNING.format(
            date=args.max_date,
            reader=DATE_NOTE_OFF if args.no_date_note else DATE_NOTE_ON),
            file=sys.stderr)
    elif args.no_date_note:
        raise SystemExit("pesto: --no-date-note only applies with --max-date")
    if args.router_model and args.arm != "auto":
        raise SystemExit("pesto: --router-model only applies with --arm auto "
                         f"(this run uses --arm {args.arm}, which asks no router)")
    if (not config.TORCH_INSTALLED and not args.ot_encoder and not args.max_date
            and not os.environ.get("OT_ENCODER") and not args.show_pipeline):
        print("pesto: PyTorch is not installed, so the Open Targets branch grades "
              "every trait associated with the gene instead of the 20 nearest, "
              "which costs up to about $0.50 a pair for well-studied genes. See "
              "'Without PyTorch' in the README.", file=sys.stderr)
    # Describing a pipeline calls nothing, so it needs no key.
    reader, worker = pick_models(args.model, args.model_fast or args.model)

    logging.basicConfig(
        stream=sys.stderr, format="%(message)s",
        level=logging.INFO if args.verbose else logging.WARNING)

    from .flow import arms, run as flow_run
    from .flow.types import Query

    def fitted(name):
        try:
            return fit(arms.get(name), args, reader, worker)
        except KeyError as exc:
            raise SystemExit(str(exc).strip('"'))

    auto = args.arm == arms.AUTO
    arm = None if auto else fitted(args.arm)
    if args.show_pipeline:
        if auto:
            disease, trait = arms.FAMILIES[family_of(args)]
            print(fitted(disease).describe())
            print()
            print(fitted(trait).describe())
        else:
            print(arm.describe())
        return 0
    # Now that the arm is known: a key for each provider it will call, and
    # none for one it will not.
    require_keys(needed_models(args, arm, fitted))

    if args.bench:
        if args.gene or args.phenotype:
            raise SystemExit("pesto: --bench cannot be combined with "
                             "--gene / --phenotype")
        # A table of pairs writes its own tree, so it does not mix with
        # whatever a single-pair run left under data/runs/novel.
        if args.data_dir == config.NOVEL_RUNS_DIR:
            args.data_dir = os.path.join(
                os.path.dirname(os.path.abspath(args.bench)), "runs")
        return run_bench(args, arm, worker, reader)

    if not args.gene or not args.phenotype:
        raise SystemExit("pesto: --gene and --phenotype are required, "
                         "or pass --bench")

    query = Query(args.gene, args.phenotype)
    # The services report progress and failures on standard output. That is the
    # channel the answer goes out on, and --json makes it a parsed one, so it is
    # held aside and released to stderr where it belongs.
    chatter = io.StringIO()
    try:
        with contextlib.redirect_stdout(chatter):
            routed = []
            if auto:
                arm, routed = route(args, args.phenotype, reader, worker)
            result = flow_run.run(arm, query, cache=not args.no_cache)
            ot_verdict, ot_score, ot_tokens, ot_match = open_targets(
                args.gene, args.phenotype, result.terms.get("synonyms"),
                worker or config.DEFAULT_MODEL, args.data_dir, args)
    except Exception as exc:
        sys.stderr.write(chatter.getvalue())
        from .services import providers
        refused = providers.auth_failure(exc)
        if refused:
            print(f"pesto: the {refused.label} API refused the key in "
                  f"{refused.key_env} (401). Check it at {refused.key_url}.",
                  file=sys.stderr)
        else:
            print(f"pesto: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if args.verbose:
        sys.stderr.write(chatter.getvalue())

    from .cost import from_ot_tokens, from_trace, with_total
    cost_rows = with_total(
        router_cost_rows(args, args.gene, args.phenotype, routed)
        + from_trace(args.gene, args.phenotype, result.trace, result.cached)
        + from_ot_tokens(args.gene, args.phenotype, ot_tokens,
                         cached=bool(ot_match.get("cached"))),
        args.gene, args.phenotype, result.cached)
    total = next((r for r in cost_rows if r["step"] == "total"), None)

    if args.json:
        print(json.dumps({
            "gene": args.gene, "phenotype": args.phenotype,
            "arm": arm.name, "fingerprint": result.fingerprint,
            "router_model": (providers_canonical(router_model_of(args))
                             if auto else None),
            "max_date": arm.max_date or None,
            "notes": list(getattr(arm.read, "notes", ())),
            "verdict": result.verdict.call,
            "distribution": (result.verdict.distribution.as_dict()
                             if result.verdict.distribution else None),
            "justification": result.verdict.justification,
            "supporting_pmids": list(result.verdict.pmids),
            "open_targets_verdict": ot_verdict,
            "open_targets_max_score": ot_score,
            "counts": result.counts, "cached": result.cached,
            "detail": result.verdict.detail,
            "cost": cost_rows,
        }, indent=2, default=str))
    elif args.quiet:
        print(f"{result.verdict.call}\t{ot_verdict}")
    else:
        print(render(result, ot_verdict, arm, show_reasoning=True))
        if total:
            # An empty usd is a model with no price, not a free run.
            spent = (f"${float(total['usd']):.4f}" if total["usd"] not in ("", None)
                     else "unpriced (a model used has no price in config.MODEL_PRICES)")
            print(f"\n  cost  {spent}  "
                  f"({total['input_tokens']} in / {total['output_tokens']} out)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
