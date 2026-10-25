"""Frozen-input comparisons, built on the pools and packets the Claude r1 run recorded.

  sieve   Luna bands the identical candidate pool (same synonyms, same batches, same prompt)
          that Haiku banded in the live run; selects what each sieve would hand the reader
  readers Sol on the Haiku-selected packet; Opus and Sol on the Luna-selected packet when it differs
          (Opus on the Haiku packet IS the live Claude read: same prompt, asserted byte-identical)
  stab_sieve  Haiku and Luna, two more draws each, on the same pools of the 12 stability pairs

Everything goes through production code: harness.band, harness.select_bands, arm.read.run
(including its garbled-answer retry) and arm.judge.run. Resumable JSONL.
"""
import argparse, csv, gzip, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/Users/dinan_elsyad/pesto_cmp")
import instr                                                      # noqa: E402
from pesto import cli, config, cost, harness                      # noqa: E402
from pesto.flow import arms, run as flow_run, steps               # noqa: E402
from pesto.flow.render import render                              # noqa: E402
from pesto.flow.types import Corpus, FIELDS, Query                # noqa: E402

ROOT = instr.ROOT
LUNA, SOL, OPUS, HAIKU = "openai:gpt-6-luna", "openai:gpt-6.1-sol", "opus5", "haiku"
LOCK = threading.Lock()


def load_claude(rep="r1"):
    path = f"{ROOT}/runs/{rep}/pairs_{rep}_claude.jsonl.gz"
    out = {}
    for l in gzip.open(path, "rt"):
        r = json.loads(l)
        if r["error"] is None and r["res"] and r["pool"]:
            out[(r["gene"], r["phenotype"])] = r
    return out


def bands_block(arm):
    return next(b for b in arm.annotate if isinstance(b, steps.Bands))


def selection(arm, pool, bands):
    sel = arm.select
    chosen = harness.select_bands(pool, bands, sel.budget, sel.cap4)
    keep = {a["pmid"] for a in chosen}
    return [a["pmid"] for a in pool if a["pmid"] in keep]       # corpus order, as ByStrength.run


def key(*a):
    return "|".join(str(x) for x in a)


def done(path):
    s = set()
    if os.path.exists(path):
        for l in open(path):
            s.add(json.loads(l)["key"])
    return s


def emit(path, rec):
    with LOCK:
        with open(path, "a") as fh:
            fh.write(json.dumps(rec) + "\n")


def run_band(rec, model, rep, out, stage):
    g, p = rec["gene"], rec["phenotype"]
    arm = arms.get(rec["router_arm"])
    blk = bands_block(arm)
    pool = rec["pool"]
    k = key(stage, g, p, model, rep)
    instr.check_budget()
    t = time.time()
    try:
        with cost.capturing() as spent:
            b = harness.band(g, p, pool, model, blk.batch,
                             synonyms=rec["res"]["terms"].get("synonyms"), prompt=blk.uses[0])
        rows, err = spent.rows, None
    except Exception as e:                                       # noqa: BLE001
        b, rows, err = {}, [], f"{type(e).__name__}: {str(e)[:300]}"
    spec = harness.MODELS.get(model, model)
    inp = sum(r["input_tokens"] for r in rows)
    outp = sum(r["output_tokens"] for r in rows)
    usd = config.price_usd(spec, inp, outp) or 0.0
    instr.charge(stage, model, usd, k)
    row = {"key": k, "stage": stage, "gene": g, "phenotype": p, "model": model, "rep": rep,
           "arm": rec["router_arm"], "bands": b, "selected": selection(arm, pool, b) if b else None,
           "n": len(pool), "calls": len(rows), "seconds": round(time.time() - t, 1),
           "input_tokens": inp, "output_tokens": outp, "usd": usd, "error": err}
    emit(out, row)
    return row


def run_reader(rec, packet, tag, model, rep, out, stage):
    g, p = rec["gene"], rec["phenotype"]
    k = key(stage, g, p, tag, model, rep)
    instr.check_budget()
    arm = arms.get(rec["router_arm"]).using(reader=model, worker=None, max_date=None, notes=())
    pool_corpus = Corpus.of(rec["pool"], FIELDS)
    corpus = pool_corpus.keep(packet)
    t = time.time()
    err, text, resp, tries = None, "", {}, 0
    try:
        for attempt in range(1, flow_run.READ_TRIES + 1):
            tries = attempt
            text, resp = arm.read.run(Query(g, p), corpus)
            if not arm.judge.garbled(text):
                break
        verdict = arm.judge.run(Query(g, p), text, corpus)
        dist = verdict.distribution.as_dict() if verdict.distribution else None
        call, just, pmids = verdict.call, verdict.justification, list(verdict.pmids or [])
    except Exception as e:                                       # noqa: BLE001
        err = f"{type(e).__name__}: {str(e)[:300]}"
        dist = call = just = None
        pmids = []
    spec = harness.MODELS.get(model, model)
    inp, outp = resp.get("input_tokens", 0), resp.get("output_tokens", 0)
    usd = (config.price_usd(spec, inp, outp) or 0.0) * tries     # every try is paid for
    instr.charge(stage, model, usd, k)
    row = {"key": k, "stage": stage, "gene": g, "phenotype": p, "packet": tag, "model": model,
           "rep": rep, "arm": rec["router_arm"], "n_packet": len(packet), "tries": tries,
           "dist": dist, "argmax": call, "mean": cli.mean_call(dist or {}), "justification": just,
           "pmids": pmids, "raw": text, "input_tokens": inp, "output_tokens": outp,
           "stop_reason": resp.get("stop_reason"), "seconds": round(time.time() - t, 1),
           "usd": usd, "error": err}
    emit(out, row)
    return row


def stab_keys():
    return {(r["gene"], r["phenotype"]) for r in csv.DictReader(open(f"{ROOT}/stab_pairs.tsv"), delimiter="\t")}


def fidelity(recs):
    """The frozen Haiku selection is what the live run read, and the frozen reader prompt is
    the prompt the live Opus call was sent, byte for byte."""
    ok_sel = ok_prompt = n = 0
    bad = []
    import gzip as gz
    live = {}
    for l in gz.open(f"{ROOT}/runs/r1/calls_r1_claude.jsonl.gz", "rt"):
        c = json.loads(l)
        if c["model"] == "claude-opus-5" and "<probabilities>" in c["prompt"]:
            live[(c["gene"], c["phenotype"])] = c["prompt"]
    for (g, p), r in recs.items():
        n += 1
        arm = arms.get(r["router_arm"])
        hb = {pm: v[0] for pm, v in r["res"]["bands"].items()}
        sel = selection(arm, r["pool"], hb)
        read = [a["pmid"] for a in r["res"]["read"]]
        ok_sel += (sel == read)
        reader = arm.using(reader=OPUS, worker=None, max_date=None, notes=()).read
        corpus = Corpus.of(r["pool"], FIELDS).keep(sel)
        prompt = reader.template().format(
            gene_name=g, phenotype=p, articles_list=render(corpus, reader.needs, block=reader.kind),
            alias_note="", dismiss_note=harness.DISMISS)
        same = live.get((g, p)) == prompt
        ok_prompt += same
        if sel != read or not same:
            bad.append((g, p, sel == read, same))
    return {"pairs": n, "selection_matches_live_read": ok_sel, "prompt_byte_identical": ok_prompt, "bad": bad[:10]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("fidelity", "sieve", "readers", "stab_sieve", "stab_readers"))
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    instr.OUT["dir"] = ROOT
    recs = load_claude()
    print(len(recs), "Claude r1 pairs with pool+bands", file=sys.stderr)
    if a.stage == "fidelity":
        r = fidelity(recs)
        json.dump(r, open(f"{ROOT}/frozen_fidelity.json", "w"), indent=1)
        print(json.dumps(r, indent=1))
        return
    sieve_path = f"{ROOT}/frozen_sieve.jsonl"
    read_path = f"{ROOT}/frozen_readers.jsonl"
    stab = stab_keys()
    jobs = []
    if a.stage == "sieve":
        have = done(sieve_path)
        jobs = [(run_band, (r, LUNA, 1, sieve_path, "sieve")) for r in recs.values()
                if key("sieve", r["gene"], r["phenotype"], LUNA, 1) not in have]
    elif a.stage == "stab_sieve":
        have = done(sieve_path)
        for r in recs.values():
            if (r["gene"], r["phenotype"]) not in stab:
                continue
            for model in (LUNA, HAIKU):
                for rep in (2, 3):
                    if key("stab_sieve", r["gene"], r["phenotype"], model, rep) not in have:
                        jobs.append((run_band, (r, model, rep, sieve_path, "stab_sieve")))
    elif a.stage == "readers":
        sv = {}
        for l in open(sieve_path):
            d = json.loads(l)
            if d["stage"] == "sieve" and d["error"] is None:
                sv[(d["gene"], d["phenotype"])] = d
        have = done(read_path)
        for (g, p), r in recs.items():
            arm = arms.get(r["router_arm"])
            hsel = selection(arm, r["pool"], {pm: v[0] for pm, v in r["res"]["bands"].items()})
            lsel = sv[(g, p)]["selected"] if (g, p) in sv else None
            work = [("H", hsel, SOL)]
            if lsel is not None and set(lsel) != set(hsel):
                work += [("L", lsel, OPUS), ("L", lsel, SOL)]
            for tag, packet, model in work:
                if key("readers", g, p, tag, model, 1) not in have:
                    jobs.append((run_reader, (r, packet, tag, model, 1, read_path, "readers")))
    elif a.stage == "stab_readers":
        have = done(read_path)
        for (g, p), r in recs.items():
            if (g, p) not in stab:
                continue
            arm = arms.get(r["router_arm"])
            hsel = selection(arm, r["pool"], {pm: v[0] for pm, v in r["res"]["bands"].items()})
            for model in (OPUS, SOL):
                for rep in (2, 3):
                    if key("stab_readers", g, p, "H", model, rep) not in have:
                        jobs.append((run_reader, (r, hsel, "H", model, rep, read_path, "stab_readers")))
    print(len(jobs), "jobs; spend so far $%.2f" % instr.spent(), file=sys.stderr, flush=True)

    def go(j):
        fn, args = j
        row = fn(*args)
        print(f"  {row['stage']:12s} {row['gene']:8s} {row['phenotype'][:26]:26s} {row['model'][:20]:20s} "
              f"{row.get('error') or ''} ${row['usd']:.3f}", file=sys.stderr, flush=True)
        return row

    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        list(pool.map(go, jobs))
    print("done; spend so far $%.2f" % instr.spent(), file=sys.stderr)


if __name__ == "__main__":
    main()
