"""Wall time of a pair, grouped so a run can say where the seconds went.

The trace already times each block. This module folds those into the stages
the efficiency work cares about: expand, PubMed, fetch, sieve, bands, read,
and Open Targets. Overlapping Open Targets with literature means `wall` is
less than the sum of the stages; both numbers are kept.
"""
from __future__ import annotations

from ..services import pubmed_service

STAGES = (
    # `Expand` is the elapsed time of the whole stage, which is what counts now
    # that its blocks overlap. The per-block names are the fallback for a run
    # saved before it was recorded, and are not added to it.
    ("expand", ("Expand", "Synonyms", "SynonymsGeneral", "Broadened",
                "ContentWords", "GeneNames", "Anchors")),
    ("pubmed", ("NameSearch", "GeneticsNameSearch", "BroadSearch",
                "VariantSearch", "WordSearch", "FullTextSearch", "ESummary",
                "DedupeByTitle", "DedupeByTitleNoNotices")),
    ("sieve", ("TitleKick", "TitleKickSparingFullText")),
    ("fetch", ("FetchAbstracts", "FetchAbstractsAndExcerpts", "SkipAbstracts")),
    ("bands", ("Bands", "BandsGeneral")),
    ("select", ("ByStrength", "ByStrengthThenFullText", "KeepAll")),
    ("read", ("ProbabilityRead", "ProbabilityReadGeneral", "BareProbabilityRead",
              "OpenProbabilityRead", "NoveltyScoreRead", "KnowledgeRead")),
    ("judge", ("Argmax", "ScoreRule")),
)


def stage_times(trace, ot_seconds=0.0, wall=0.0):
    """Seconds per stage, plus the per-block rows and the NCBI pace."""
    by = {name: 0.0 for name, _ in STAGES}
    by["open_targets"] = round(float(ot_seconds or 0), 1)
    known = {block: name for name, blocks in STAGES for block in blocks}
    blocks = []
    steps = list(getattr(trace, "steps", ()) or ())
    elapsed = any(s.block == "Expand" for s in steps)
    for step in steps:
        sec = float(getattr(step, "seconds", 0) or 0)
        name = known.get(step.block)
        if name == "expand" and elapsed and step.block != "Expand":
            name = None
        if name:
            by[name] = round(by[name] + sec, 1)
        blocks.append({
            "block": step.block,
            "seconds": sec,
            "calls": getattr(step, "calls", 0) or 0,
            "note": getattr(step, "note", "") or "",
        })
    by["wall"] = round(float(wall or 0), 1)
    by["ncbi_per_second"] = pubmed_service.pubmed_rate()
    by["ncbi_key"] = bool(pubmed_service.NCBI_API_KEY)
    by["blocks"] = blocks
    return by


def format_stages(timing):
    """One line for stderr or the text answer."""
    if not timing:
        return ""
    parts = [f"wall {timing.get('wall', 0):g}s"]
    for name, _ in STAGES:
        sec = timing.get(name) or 0
        if sec:
            parts.append(f"{name} {sec:g}")
    ot = timing.get("open_targets") or 0
    if ot:
        parts.append(f"open_targets {ot:g}")
    pace = timing.get("ncbi_per_second")
    key = "key" if timing.get("ncbi_key") else "no key"
    if pace:
        parts.append(f"pubmed {pace:g}/s ({key})")
    return "  timing  " + "  ".join(parts)
