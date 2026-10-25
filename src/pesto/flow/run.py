"""Running an arm: the only place the order of the stages is written down.

The stages are fixed and the blocks are not. That is the trade this whole module
makes: what varies between arms varies inside a declaration that can be read at a
glance, and the sequence itself exists once, here, rather than in six scripts
that had each drifted a little from the others.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .types import Corpus, Labels, Query, Step, Trace, Verdict

# An answer the model could not format is not one to trust for its numbers:
# the reading is asked again, and only the last answer is kept.
READ_TRIES = 3


@dataclass
class Result:
    query: Query
    arm: str
    fingerprint: str
    verdict: Verdict = None
    corpus: Corpus = None
    labels: Labels = None
    counts: dict = field(default_factory=dict)
    trace: Trace = Trace()
    raw: str = ""
    terms: dict = field(default_factory=dict)
    # Where each phenotype-only model answer came from (fresh, a kept one, shared
    # with a sibling pair, refreshed), so a run says which expansion it searched.
    expansion: list = field(default_factory=list)
    cached: bool = False
    max_date: str = ""


def run(arm, query, synonyms=None, workers=6, cache=False, runs_dir=None,
        reuse=True):
    """One pair through one arm.

    `synonyms` is only read by an expander told to replay a recorded list; an
    arm that expands live ignores it, which is the difference between a
    benchmark whose search must not move and a fresh question.

    `cache` reuses a saved run only when the arm's fingerprint matches, so a
    pipeline that has changed in any declared way is never answered from one
    that has not. `reuse=False` keeps the saving and skips the reading: the pair
    is run again and its saved run replaced, which is what refreshing the
    expansion needs.

    The arm's max_date is set on the PubMed client here, for every search the
    run makes. The ceiling is process-wide, so concurrent runs must share it.
    """
    arm.validate()
    if cache and reuse:
        from . import store
        saved = store.load(query, arm, runs_dir)
        if saved is not None:
            saved.cached = True
            return saved
    from ..services import pubmed_service
    pubmed_service.MAX_PUBDATE = arm.max_date or None
    res = Result(query=query, arm=arm.name, fingerprint=arm.fingerprint(),
                 max_date=arm.max_date)
    clock = _stopwatch(res)

    terms = {}
    local = [b for b in arm.expand if not getattr(b, "model", None)]
    remote = [b for b in arm.expand if getattr(b, "model", None)]
    expand_t0 = time.time()

    from .. import expansion_cache
    from ..cost import capturing, thread_pool

    def expand_one(block, seen):
        t0 = time.time()
        with capturing() as usage, expansion_cache.recording() as picked:
            part = block.run(query, seen, synonyms)
        spent = usage.summary(getattr(block, "model", None))
        return block, part, time.time() - t0, spent, picked

    # A model-written expander that reads only the phenotype (the synonyms, the
    # broadened name) does not need the local ones, so it is sent first and
    # runs while they are computed; the HGNC alias table alone takes most of a
    # second to load. One that reads a local term (the anchors read the gene
    # names) is sent only once they exist. Each is handed the terms as they
    # stand when it starts, and the answers are merged below in declaration
    # order, so nothing it returns differs from before.
    independent = [b for b in remote
                   if not getattr(b, "reads_local_terms", True)]
    dependent = [b for b in remote if b not in independent]
    expand_pool = (thread_pool(max_workers=max(1, min(len(remote), workers)))
                   if remote else None)
    futures = {}
    try:
        for block in independent:
            futures[id(block)] = expand_pool.submit(expand_one, block, {})
        for block in local:
            with clock(block):
                terms.update(block.run(query, terms, synonyms))
        for block in dependent:
            futures[id(block)] = expand_pool.submit(
                expand_one, block, dict(terms))
    except BaseException:
        if expand_pool is not None:
            expand_pool.shutdown(wait=False, cancel_futures=True)
        raise
    # Passes that read no model-written term go out now, while Opus is still
    # writing synonyms. They run the same query they would have run after, and
    # are merged below in the order they are declared in, so the corpus is the
    # same; only the waiting overlaps. They see the local terms as they stand.
    early_pool, early = None, {}
    if remote:
        ahead = [i for i, s in enumerate(arm.sources)
                 if not s.deferred
                 and not getattr(s, "waits_for_expansion", True)]
        if ahead:
            early_pool = ThreadPoolExecutor(max_workers=len(ahead))
            snapshot = dict(terms)

            def search_early(block):
                t0 = time.time()
                return block, block.run(query, snapshot), time.time() - t0

            early = {i: early_pool.submit(search_early, arm.sources[i])
                     for i in ahead}
    if remote:
        try:
            expanded = [futures[id(b)].result() for b in remote]
        finally:
            expand_pool.shutdown(wait=True)
        for block, part, seconds, spent, picked in expanded:
            terms.update(part)
            res.expansion.extend(picked)
            res.trace = res.trace.then(Step(
                block.kind, block.fingerprint(),
                model=spent["model"] or getattr(block, "model", None),
                note="; ".join(expansion_cache.describe(i) for i in picked),
                seconds=round(seconds, 1),
                input_tokens=spent["input_tokens"],
                output_tokens=spent["output_tokens"],
                usd=spent["usd"],
                calls=spent["calls"]))
    # The blocks above overlap, so their seconds do not add up to the time the
    # stage took; this is the elapsed time of the whole stage.
    res.trace = res.trace.then(Step(
        "Expand", "", seconds=round(time.time() - expand_t0, 1)))
    res.terms = terms

    # Passes that only look at the question go together; the merge order is the
    # order they are declared in, never the order they answer in, so an
    # article's rank records which query reached it first.
    eager = [s for s in arm.sources if not s.deferred]
    late = [s for s in arm.sources if s.deferred]
    corpus = Corpus()
    if eager:
        def search_one(block):
            t0 = time.time()
            part = block.run(query, terms)
            return block, part, time.time() - t0

        # Declaration order throughout: an early pass is slotted back where it
        # was declared, whenever it finished.
        positions = {id(s): i for i, s in enumerate(arm.sources)}
        waiting = [s for s in eager if positions[id(s)] not in early]
        try:
            with ThreadPoolExecutor(
                    max_workers=max(1, min(len(waiting), workers))) as pool:
                done = dict(zip((positions[id(s)] for s in waiting),
                                pool.map(search_one, waiting)))
            for i, fut in early.items():
                done[i] = fut.result()
        finally:
            if early_pool is not None:
                early_pool.shutdown(wait=True)
        found = [done[positions[id(s)]] for s in eager]
        for block, part, seconds in found:
            res.trace = res.trace.then(Step(block.kind, block.fingerprint(),
                                            seconds=round(seconds, 1),
                                            note=f"{len(part)} articles"))
            corpus = corpus.merged(part)
    from ..services import pubmed_service
    if late and pubmed_service.MAX_PUBDATE:
        # A fallback pass asks what the corpus holds, and under a date ceiling
        # an article past it does not count (GeneReviews carries the series'
        # date in PubMed's own filter, so only its summary says). Without a
        # ceiling the summaries wait for the single pass below.
        corpus = Corpus.of(
            pubmed_service.articles_with_summaries(corpus.as_dicts()),
            corpus.provided)
    for block in late:
        if not block.applies(corpus, terms):
            res.trace = res.trace.then(Step(block.kind, block.fingerprint(),
                                            note="not applicable"))
            continue
        with clock(block):
            corpus = corpus.merged(block.run(query, terms))
    # Titles once, after every search has named its PMIDs. Each pass used to
    # call esummary itself, repeating the overlapping ids.
    t0 = time.time()
    from ..services import pubmed_service
    corpus = Corpus.of(pubmed_service.articles_with_summaries(corpus.as_dicts()),
                       corpus.provided)
    res.trace = res.trace.then(Step(
        "ESummary", "", seconds=round(time.time() - t0, 1),
        note=f"{len(corpus)} articles"))
    with clock(arm.dedupe):
        corpus = arm.dedupe.run(corpus)
    res.counts["found"] = len(corpus)

    chain = list(arm.annotate)
    chain.insert(min(arm.hydrate_at, len(chain)), arm.hydrate)
    labels = Labels()
    for block in chain:
        if block is arm.hydrate:
            with clock(block):
                # A hydrate block that only fetches abstracts needs the corpus
                # and nothing else. One that reads full text has to know which
                # gene it is looking for, and says so rather than having the
                # query pushed at every block that does not want it.
                corpus = (block.run(corpus, query)
                          if getattr(block, "wants_query", False)
                          else block.run(corpus))
            continue
        with clock(block):
            # Annotators see what the expansion produced, not just the query:
            # the grader that is told the disease's other names reads them here.
            part = block.run(query, corpus, terms)
        labels = labels.merged(part)
        gone = part.dropped()
        if gone:
            alive = corpus.keep(p for p in corpus.pmids if p not in gone)
            # An annotator may narrow the corpus but not empty it: a filter that
            # rejects everything has failed at its job, not answered it.
            corpus = alive if len(alive) else corpus
            res.counts[block.kind.lower()] = len(gone)

    with clock(arm.select):
        corpus = arm.select.run(corpus, labels)
    res.counts["read"] = len(corpus)
    res.corpus, res.labels = corpus, labels

    for attempt in range(1, READ_TRIES + 1):
        with clock(arm.read):
            text, _ = arm.read.run(query, corpus)
        if not arm.judge.garbled(text):
            break
    else:
        res.trace = res.trace.then(Step(arm.read.kind, arm.read.fingerprint(),
                                        note=f"answer garbled {READ_TRIES} times; "
                                             "the last one is read as well as it can be"))
    res.raw = text
    with clock(arm.judge):
        res.verdict = arm.judge.run(query, text, corpus)
    if cache:
        from . import store
        store.save(res, runs_dir)
    return res


def _stopwatch(res):
    """Times a block and files what it was, so the run can be read back."""
    class _Timer:
        def __init__(self, block):
            self.block = block

        def __enter__(self):
            from ..cost import capturing
            self.t = time.time()
            self.usage = capturing()
            self.usage.__enter__()
            return self

        def __exit__(self, *exc):
            self.usage.__exit__(*exc)
            spent = self.usage.summary(getattr(self.block, "model", None))
            res.trace = res.trace.then(Step(
                self.block.kind, self.block.fingerprint(),
                model=spent["model"] or getattr(self.block, "model", None),
                seconds=round(time.time() - self.t, 1),
                input_tokens=spent["input_tokens"],
                output_tokens=spent["output_tokens"],
                usd=spent["usd"],
                calls=spent["calls"]))
    return _Timer
