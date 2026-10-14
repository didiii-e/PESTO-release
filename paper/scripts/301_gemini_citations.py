#!/usr/bin/env python3
"""Figure 2e,f on Gemini: the two citation scripts of the Claude figure, run
unchanged with their models and paths swapped (14 October 2026).

  ask     scripts/272_knowledge_citations.py: the model's internal knowledge,
          asked to cite, on the 210 dated Limited pairs, with gemini-4-argon at
          thinking level MEDIUM in place of Opus 5.
  verify  scripts/273_verify_citations.py: every citation of both arms resolved
          against PubMed and judged from its abstract, with gemini-3.8-flash at
          LOW in place of Haiku 4.5. PESTO's citations are read from the Gemini
          runs of Fig. 2 (scripts/299_gemini_fig2_run.py, arm c1a5480df225).

Outputs go to results/gemini_fig2/knowledge_citations/, in the layout the Claude
ones have, so that scripts/_panel_citations.R draws them unchanged. The PubMed
metadata cache of the Claude run is copied in first: it is keyed by PMID and
does not depend on the model.

  python3 scripts/301_gemini_citations.py ask
  python3 scripts/301_gemini_citations.py verify --runs results/gemini_fig2/full/runs
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "scripts"
os.environ.setdefault("PESTO_PROJECT_ROOT", str(ROOT))
OUT = ROOT / "results" / "gemini_fig2" / "knowledge_citations"
FIG2_FP = "c1a5480df225"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["ask", "verify"])
    ap.add_argument("--runs", default=str(ROOT / "results" / "gemini_fig2" / "full" / "runs"))
    args = ap.parse_args()

    probe = load("probe", "298_gemini_pair_probe.py")
    from pesto.services import llm_service
    llm_service._call_gemini = probe.call_gemini
    OUT.mkdir(parents=True, exist_ok=True)

    if args.step == "ask":
        mod = load("cite", "272_knowledge_citations.py")
        mod.MODEL = "gemini-4-argon"
        mod.MODELS = {**mod.MODELS, "gemini-4-argon": "gemini-4-argon"}
        mod.OUT, mod.RUNS = OUT, OUT / "runs.json"
        mod.VERDICTS, mod.REFS = OUT / "verdicts.tsv", OUT / "refs.tsv"
        sys.argv = [sys.argv[0]]
        return mod.main()

    mod = load("verify", "273_verify_citations.py")
    mod.MODELS = {**mod.MODELS, "haiku": "gemini-3.8-flash"}
    mod.OUT, mod.KNOW_RUNS = OUT, OUT / "runs.json"
    mod.RECORDS, mod.JUDGED = OUT / "pubmed_records.json", OUT / "judge_cache.json"
    mod.FLOW, mod.CURRENT_FP = Path(args.runs), FIG2_FP
    claude_records = ROOT / "results" / "knowledge_citations" / "pubmed_records.json"
    if not mod.RECORDS.exists() and claude_records.exists():
        shutil.copy(claude_records, mod.RECORDS)
    sys.argv = [sys.argv[0]]
    return mod.main()


if __name__ == "__main__":
    sys.exit(main())
