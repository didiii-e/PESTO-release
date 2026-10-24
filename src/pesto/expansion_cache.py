"""One model answer per phenotype, asked once and shared by every pair that needs it.

Two calls in a pair's search depend on the phenotype alone and never on the gene:
the synonyms Opus writes for it, and the broadened name Haiku strips it down to.
A hundred genes against one phenotype used to send both a hundred times, got a
hundred slightly different synonym lists back (the Opus calls are not
deterministic), and so searched PubMed under a hundred slightly different
vocabularies. This module makes that one question per phenotype.

Three things make the answer safe to reuse:

  * It is keyed by exactly what was asked: the kind of question, the phenotype,
    the model id the request goes to, and the SHA-256 of the prompt template. Edit
    the prompt or change the model and the old answer is simply not found, so a
    list written under one prompt is never handed to another.
  * What is stored is the model's own reply, not the parsed list, so a later fix
    to the parser applies to answers already on disk, and the file is also the
    record of what the model said.
  * Only a usable answer is stored. An empty list, or a reply with no term in it,
    is what a failed call looks like, and one of those cached would poison every
    gene in the batch. Those are returned to the pair that asked and forgotten.

Concurrency is single-flight. The first pair to need a phenotype asks; the pairs
that arrive while it is asking wait for that one reply rather than sending their
own, which is the difference between one Opus call per phenotype and one per
worker for the first ten. If the call fails they fail with it, rather than ten
workers each retrying a call that has just failed; a batch rerun with --resume
picks those pairs up.

Entries live one per file under <project root>/cache/expansion, written
atomically, so two processes running side by side cannot corrupt each other. The
mode is process-wide:

  off      every pair asks for itself, as before (the default for now)
  use      read the answer if there is one, ask and keep it if there is not
  refresh  ask again once per phenotype in this process and overwrite what was
           kept; the pairs after the first one use the new answer

Each use is recorded on the run: what was asked, which key, where the answer came
from (fresh, memory, disk, shared with a sibling, refreshed) and when it was
written.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone

from . import config

log = logging.getLogger(__name__)

# Bump when something outside the key changes what an answer means (the request
# parameters, say); every older entry then stops matching.
SCHEMA = 1

OFF, USE, REFRESH = "off", "use", "refresh"
MODES = (OFF, USE, REFRESH)

_MODE = config.EXPANSION_CACHE if config.EXPANSION_CACHE in MODES else OFF
_LOCK = threading.Lock()
_MEM = {}            # key -> entry
_FLIGHT = {}         # key -> _Flight, while some pair is asking
_REFRESHED = set()   # keys already re-asked in this process
_LOCAL = threading.local()


def configure(mode):
    """Set the process-wide mode. Forgets what this process had already
    refreshed, so asking for a refresh twice in one process refreshes twice."""
    global _MODE
    if mode not in MODES:
        raise ValueError(f"expansion cache mode must be one of {MODES}, not {mode!r}")
    with _LOCK:
        _MODE = mode
        _REFRESHED.clear()
        if mode == REFRESH:
            _MEM.clear()    # or a held answer would be served instead of re-asked


def mode():
    return _MODE


def forget_memory():
    """Drop what this process holds in memory; the files stay."""
    with _LOCK:
        _MEM.clear()
        _REFRESHED.clear()


def cache_dir():
    return os.path.join(config.PROJECT_ROOT, "cache", "expansion")


def _normal(phenotype):
    return re.sub(r"\s+", " ", (phenotype or "").strip()).casefold()


def identity(kind, phenotype, model, prompt_text):
    """What was asked, as a dict whose hash is the key."""
    return {"schema": SCHEMA, "kind": kind, "phenotype": _normal(phenotype),
            "model": model,
            "prompt_sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()}


def key_of(ident):
    blob = json.dumps(ident, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _path(kind, ident, key):
    slug = re.sub(r"[^a-z0-9]+", "_", ident["phenotype"]).strip("_")[:60] or "x"
    return os.path.join(cache_dir(), f"{kind}__{slug}__{key}.json")


def _read(kind, ident, key, parse, usable):
    """The stored entry if it is for exactly this question and still parses to
    something usable, else None."""
    try:
        with open(_path(kind, ident, key), encoding="utf-8") as fh:
            entry = json.load(fh)
        if any(entry.get(k) != v for k, v in ident.items()):
            return None
        if not usable(parse(entry["response"])):
            return None
        return entry
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write(kind, ident, key, entry):
    path = _path(kind, ident, key)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(entry, fh, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError as exc:
        log.warning("could not save the expansion cache: %s", exc)


class _Flight:
    __slots__ = ("event", "entry", "error")

    def __init__(self):
        self.event = threading.Event()
        self.entry = None
        self.error = None


# --- what each use records on the run --------------------------------------

@contextlib.contextmanager
def recording():
    """Collects, for the calls this thread makes inside it, where each answer
    came from."""
    previous = getattr(_LOCAL, "records", None)
    records = _LOCAL.records = []
    try:
        yield records
    finally:
        _LOCAL.records = previous


def _note(kind, asked, ident, key, source, entry):
    records = getattr(_LOCAL, "records", None)
    if records is None:
        return
    records.append({
        "kind": kind, "phenotype": asked, "source": source,
        "model": ident["model"], "prompt_sha256": ident["prompt_sha256"],
        "key": key, "written": (entry or {}).get("created"),
    })


def describe(info):
    """One line for a trace or a table cell."""
    written = f", written {info['written']}" if info.get("written") else ""
    key = f" #{info['key']}" if info.get("key") else ""
    return (f"{info['kind']}: {info['source']}{key}{written}, "
            f"prompt {info['prompt_sha256'][:12]}")


# --- the one entry point ----------------------------------------------------

def fetch(kind, phenotype, model, prompt_text, ask, parse, usable):
    """The parsed answer to one phenotype-only question.

    `ask()` sends the request and returns the model's reply text. `parse(text)`
    turns a reply into the value, and `usable(value)` says whether that value is
    an answer worth keeping. `model` is the id the request goes to, not an
    alias, because the id is what the answer depends on.
    """
    ident = identity(kind, phenotype, model, prompt_text)
    key = key_of(ident)
    if _MODE == OFF:
        value = parse(ask())
        _note(kind, phenotype, ident, None, "fresh", None)
        return value

    while True:
        with _LOCK:
            entry = _MEM.get(key)
            if entry is not None:
                source, hit = "memory", entry
            else:
                hit = None
                flight = _FLIGHT.get(key)
                leader = flight is None
                if leader:
                    flight = _FLIGHT[key] = _Flight()
        if hit is not None:
            _note(kind, phenotype, ident, key, source, hit)
            return parse(hit["response"])

        if not leader:
            flight.event.wait()
            if flight.error is not None:
                raise flight.error
            if flight.entry is not None:
                _note(kind, phenotype, ident, key, "shared", flight.entry)
                return parse(flight.entry["response"])
            continue    # the answer was not one to keep; ask for ourselves

        try:
            value, entry, source = _lead(kind, phenotype, ident, key, ask,
                                         parse, usable)
            flight.entry = entry
        except BaseException as exc:
            flight.error = exc
            raise
        finally:
            with _LOCK:
                _FLIGHT.pop(key, None)
            flight.event.set()
        _note(kind, phenotype, ident, key, source, entry)
        return value


def _lead(kind, phenotype, ident, key, ask, parse, usable):
    """Answer a question nobody in this process has answered yet."""
    with _LOCK:
        refreshing = _MODE == REFRESH and key not in _REFRESHED
    if not refreshing:
        entry = _read(kind, ident, key, parse, usable)
        if entry is not None:
            with _LOCK:
                _MEM[key] = entry
            return parse(entry["response"]), entry, "disk"

    text = ask()
    value = parse(text)
    if not usable(value):
        return value, None, "uncached"
    entry = dict(ident)
    entry.update({
        "asked": phenotype, "response": text, "value": value,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    _write(kind, ident, key, entry)
    with _LOCK:
        _MEM[key] = entry
        if refreshing:
            _REFRESHED.add(key)
    return value, entry, "refreshed" if refreshing else "fresh"
