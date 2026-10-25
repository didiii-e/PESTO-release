# Experiment: Claude and OpenAI models through PESTO

One experiment, one branch. Code under test: `95c6dde` of `feature/llm-provider-support`
(the provider layer), working tree clean at launch. Date: 25 October 2026. No source file
is changed by this branch; everything is under `experiments/claude_vs_openai/`.

| path | what |
|---|---|
| `DEVELOPMENT_LOG.md` | the supplementary-material style write-up of all branches and this experiment (S4) |
| `reports/` | the three generated reports every number in S4 is copied from |
| `figures/` | Supplementary Figures S1-S9 (`0_summary.png` ... `8_sieve.png`) |
| `pairs/` | the 60-pair table (`pairs.tsv`, SHA-256 in `manifest.json`), the 12 stability pairs, the 3 pilot pairs |
| `scripts/` | `run_e2e.py` (both families through `pesto --bench`), `frozen.py` (frozen-input stages), `an_*.py` (analysis), `figs.py`, `instr.py` (passive call recorders: they change no prompt, model, setting or logic), `make_supp.py` (builds the log) |
| `manifest.json` | commit, environment, models, prices, flags, budget and spend |
| `frozen_fidelity.json` | check that the frozen-input packets and prompts equal the live run's (59/59) |

Not included: the raw call logs (`ledger.jsonl`, `frozen_*.jsonl`, `runs/`), because they hold article text.
The scripts name their working directory `/Users/dinan_elsyad/pesto_cmp`; change `ROOT` in `an_common.py` and
`instr.py` to run elsewhere. Spend: $26.02 of a $40 cap.
