"""Print the cheaper-Opus experiment. Do not run it on this pass.

Runtime work on this branch keeps claude-opus-5 as the reader and the Open
Targets grader. Swapping those for Haiku (or Gemini, as in 298/303) is a
separate cost experiment, after abstracts-fast matches published verdicts.

The paper already has the harnesses:

  140 pairs, literature only, cost and AP
    python3 paper/scripts/166_modes_benchmark_140.py abstracts
    pesto --bench paper/results/modes_benchmark_140/abstracts/input.tsv \\
          --model claude-haiku-4-5 --no-cache --ot-encoder none --workers 10 \\
          --out paper/results/modes_benchmark_140/haiku_reader/pesto.tsv
    python3 paper/scripts/167_modes_benchmark_scores.py

  1,043 Figure 2 pairs (Claude vs challenger)
    python3 paper/scripts/300_gemini_fig2_pairs.py
    python3 paper/scripts/303_gemini_fig2_comparison.py

Open Targets grading was already tried with Haiku: 100% sensitivity at 52%
specificity (src/pesto/ot_matcher.py). Do not cheapen that grader first.

This script only prints the recipe. Pass --run-probe GENE PHENOTYPE to send
one pair through --model-fast and --model unchanged, as a sanity check that
the flags still work; that is not the cheaper-reader test.
"""
from __future__ import annotations

import argparse
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-probe", nargs=2, metavar=("GENE", "PHENOTYPE"),
                    help="one pair with the current (Opus) models; not a cheap swap")
    args = ap.parse_args()
    print(__doc__)
    if not args.run_probe:
        return 0
    from pesto import cli
    gene, phenotype = args.run_probe
    return cli.main(["--gene", gene, "--phenotype", phenotype, "--verbose"])


if __name__ == "__main__":
    raise SystemExit(main())
