"""Checks that do not call a model: the fast arms exist, timing folds, NCBI pace."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("PESTO_PROJECT_ROOT", os.path.join(HERE, "fixtures"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from pesto.flow import arms  # noqa: E402
from pesto.flow.timing import format_stages, stage_times  # noqa: E402
from pesto.flow.types import Step, Trace  # noqa: E402
from pesto.services import pubmed_service  # noqa: E402


def main():
    failed = 0
    for name in ("abstracts-fast", "abstracts-fast-trait"):
        arm = arms.get(name)
        kinds = [b.kind for b in arm.blocks()]
        if "TitleKick" not in kinds:
            print(f"FAIL  {name} has no TitleKick: {kinds}")
            failed += 1
        if arm.hydrate_at != 1:
            print(f"FAIL  {name} hydrate_at={arm.hydrate_at}, want 1")
            failed += 1
        bands = next(b for b in arm.blocks() if b.kind.startswith("Bands"))
        if bands.batch != 20:
            print(f"FAIL  {name} band batch={bands.batch}, want 20")
            failed += 1
        print(f"ok    {name} [{arm.fingerprint()}]")

    paper = arms.get("abstracts")
    if paper.hydrate_at != 0:
        print(f"FAIL  abstracts hydrate_at moved to {paper.hydrate_at}")
        failed += 1
    else:
        print(f"ok    abstracts still hydrates first [{paper.fingerprint()}]")

    trace = Trace((
        Step("Synonyms", "", seconds=2.0),
        Step("Broadened", "", seconds=1.0),
        Step("NameSearch", "", seconds=5.0),
        Step("ESummary", "", seconds=1.2),
        Step("Bands", "", seconds=8.0),
        Step("ProbabilityRead", "", seconds=6.0),
    ))
    timing = stage_times(trace, ot_seconds=9.0, wall=12.0)
    if timing["expand"] != 3.0 or timing["pubmed"] != 6.2 or timing["bands"] != 8.0:
        print(f"FAIL  stage fold {timing}")
        failed += 1
    else:
        print("ok    stage_times")
    line = format_stages(timing)
    if "wall 12s" not in line or "open_targets 9" not in line:
        print(f"FAIL  format {line!r}")
        failed += 1
    else:
        print("ok    format_stages")

    # Overlapping expanders: the elapsed `Expand` step is the stage, and the
    # per-block rows are not added to it.
    overlapped = Trace().then(Step("GeneNames", "", seconds=0.9)).then(
        Step("Synonyms", "", seconds=4.5)).then(
        Step("Broadened", "", seconds=1.3)).then(
        Step("Expand", "", seconds=4.6))
    got = stage_times(overlapped)["expand"]
    if got != 4.6:
        print(f"FAIL  expand stage {got}, want the elapsed 4.6")
        failed += 1
    else:
        print("ok    expand uses elapsed time")

    # Which model-written expanders may start before the local ones finish.
    # Anchors read the gene names, so they must not.
    from pesto.flow import steps  # noqa: E402
    early = {b.kind: not getattr(b, "reads_local_terms", True)
             for b in arms.get("fulltext").expand
             if getattr(b, "model", None)}
    want_early = {"Synonyms": True, "Broadened": True, "Anchors": False}
    if early and early != {k: v for k, v in want_early.items() if k in early}:
        print(f"FAIL  early-start flags {early}")
        failed += 1
    elif getattr(steps.Anchors, "reads_local_terms", True) is not True:
        print("FAIL  Anchors must wait for the local terms")
        failed += 1
    else:
        print(f"ok    early-start flags {early or 'n/a'}")

    pace = pubmed_service.pubmed_rate()
    want = 9.0 if pubmed_service.NCBI_API_KEY else 2.5
    if pace != want:
        print(f"FAIL  pubmed_rate {pace} want {want}")
        failed += 1
    else:
        print(f"ok    pubmed_rate {pace}/s key={bool(pubmed_service.NCBI_API_KEY)}")

    failed += expansion_cache_checks()

    print("failed" if failed else "ok", failed)
    return 1 if failed else 0


def expansion_cache_checks():
    """The phenotype expansion cache, with fake model calls."""
    import tempfile
    import threading
    import time

    from pesto import expansion_cache as ec

    failed = 0

    def check(ok, label):
        nonlocal failed
        print(("ok    " if ok else "FAIL  ") + label)
        failed += 0 if ok else 1

    def parse(text):
        return [t for t in text.split(",") if t]

    class Asker:
        def __init__(self, reply="a,b,c", delay=0.0, boom=False):
            self.calls, self.reply, self.delay, self.boom = 0, reply, delay, boom
            self.lock = threading.Lock()

        def __call__(self):
            with self.lock:
                self.calls += 1
            time.sleep(self.delay)
            if self.boom:
                raise RuntimeError("api down")
            return self.reply

    def get(asker, pheno="Autism Spectrum Disorder", model="claude-opus-5",
            prompt="PROMPT v1", kind="synonyms"):
        return ec.fetch(kind, pheno, model, prompt, asker, parse, bool)

    real_dir = ec.cache_dir
    with tempfile.TemporaryDirectory() as tmp:
        ec.cache_dir = lambda: tmp
        try:
            ec.configure(ec.OFF)
            a = Asker()
            get(a), get(a)
            check(a.calls == 2, "off: every pair asks for itself")

            ec.configure(ec.USE)
            ec.forget_memory()
            a = Asker(delay=0.3)
            out = []
            with ec.recording() as main_rec:
                pass
            def worker():
                with ec.recording() as rec:
                    out.append((get(a), rec[0]["source"]))
            threads = [threading.Thread(target=worker) for _ in range(10)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            sources = sorted(s for _, s in out)
            check(a.calls == 1, f"single-flight: 10 simultaneous pairs, {a.calls} call")
            check(all(v == ["a", "b", "c"] for v, _ in out) and
                  sources.count("fresh") == 1 and sources.count("shared") == 9,
                  f"single-flight: one fresh, nine shared ({sources.count('fresh')}/"
                  f"{sources.count('shared')})")

            with ec.recording() as rec:
                get(a)
            check(a.calls == 1 and rec[0]["source"] == "memory", "memory hit")

            ec.forget_memory()
            with ec.recording() as rec:
                get(a, pheno="  autism   spectrum disorder ")
            check(a.calls == 1 and rec[0]["source"] == "disk"
                  and rec[0]["written"], "disk hit after memory is dropped; "
                  "case and spacing do not split the key")

            before = a.calls
            get(a, prompt="PROMPT v2")
            get(a, model="claude-opus-4-1")
            get(a, kind="broad")
            get(a, pheno="Rett syndrome")
            check(a.calls == before + 4, "a new prompt, model, kind or phenotype "
                  "is a different question")

            ec.forget_memory()
            empty = Asker(reply="")
            get(empty, pheno="Unlucky")
            get(empty, pheno="Unlucky")
            check(empty.calls == 2, "an empty answer is never kept")

            ec.forget_memory()
            boom = Asker(delay=0.2, boom=True)
            errs = []
            def failing():
                try:
                    get(boom, pheno="Down")
                except RuntimeError as exc:
                    errs.append(exc)
            threads = [threading.Thread(target=failing) for _ in range(5)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            check(boom.calls == 1 and len(errs) == 5,
                  f"a failed call fails its waiters and is not retried by each "
                  f"({boom.calls} call, {len(errs)} errors)")
            ok = Asker(reply="x,y")
            check(get(ok, pheno="Down") == ["x", "y"], "and is asked again later")

            # A hand-edited or mismatched file is a miss, not an answer.
            ec.forget_memory()
            ident = ec.identity("synonyms", "Tamper", "claude-opus-5", "PROMPT v1")
            key = ec.key_of(ident)
            path = ec._path("synonyms", ident, key)
            os.makedirs(tmp, exist_ok=True)
            import json
            with open(path, "w") as fh:
                json.dump(dict(ident, model="claude-haiku-4-5", response="z"), fh)
            t = Asker(reply="fresh")
            check(get(t, pheno="Tamper") == ["fresh"] and t.calls == 1,
                  "an entry that does not match its key is ignored")

            ec.configure(ec.REFRESH)
            r = Asker(reply="new1,new2")
            first = get(r)
            second = get(r)
            check(first == ["new1", "new2"] and r.calls == 1,
                  "refresh: asked once for the phenotype, then reused")
            ec.configure(ec.USE)
            ec.forget_memory()
            chk = Asker()
            check(get(chk) == ["new1", "new2"] and chk.calls == 0,
                  "refresh overwrote what was kept")
        finally:
            ec.cache_dir = real_dir
            ec.configure(ec.OFF)
            ec.forget_memory()
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
