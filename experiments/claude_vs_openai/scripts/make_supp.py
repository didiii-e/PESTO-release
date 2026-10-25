"""Build the supplementary-material style development log (Markdown + .docx).

  python make_supp.py            writes SUPPLEMENT.md and PESTO_development_log.docx here

Every table in section S4 is copied from the generated reports (report_e2e.md,
report_frozen.md, report_sieve_effect.md), never retyped. Sections S1-S3 take
their numbers from the commit messages of their branches and from the test runs
recorded there. Needs python-docx for the .docx.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "https://github.com/didiii-e/PESTO-release"
FIGS = os.path.join(HERE, "figs")


def tree(branch):
    return f"{REPO}/tree/{branch}"


def commit(sha):
    return f"{REPO}/commit/{sha}"


def link_branch(branch):
    return f"[`{branch}`]({tree(branch)})"


def link_commit(sha, label=None):
    return f"[`{sha}`]({commit(sha)})" + (f" {label}" if label else "")


# --------------------------------------------------------------- report access
def report(name):
    return open(os.path.join(HERE, name), encoding="utf-8").read().splitlines()


def section(lines, heading_prefix):
    """The body under the heading that starts with `heading_prefix`, up to the next
    heading of the same or a higher level, with its own headings pushed down one."""
    start = next(i for i, l in enumerate(lines) if l.startswith(heading_prefix))
    level = len(lines[start]) - len(lines[start].lstrip("#"))
    out = []
    for l in lines[start + 1:]:
        if l.startswith("#") and (len(l) - len(l.lstrip("#"))) <= level:
            break
        out.append("##" + l if l.startswith("#") else l)
    return "\n".join(out).strip("\n")


E2E, FRZ, SEV = report("report_e2e.md"), report("report_frozen.md"), report("report_sieve_effect.md")


def body_of(lines):
    """A whole report without its title line, headings pushed down two levels."""
    return "\n".join(("##" + l if l.startswith("#") else l) for l in lines[1:]).strip("\n")


def fig(n, name, caption):
    return f"![Supplementary Figure S{n}. {caption}]({os.path.join(FIGS, name)})"


# ----------------------------------------------------------------------- text
DOC = []
add = DOC.append

add("# Supplementary Material: PESTO development log")
add("*Features and experiments, each on its own branch, with the results obtained*")

add(f"""
**Repository.** [{REPO}]({REPO}) (fork of the PESTO release repository). **Compiled** 25 October 2026.

**Convention.** One branch is one feature or one experiment. Each entry below gives the branch, the commit it starts from,
its commits, what it does, how it was checked, the results, and what is not yet established. Nothing here has been
merged; every branch is pushed and waiting. Sections S1 to S3 are code features. Section S4 is an experiment (a
comparison of Claude and OpenAI models run through PESTO); its code, reports, tables and figures are on its branch.
The numbers in S4 are copied from the generated report files, not retyped.

**How to read the statuses.** *Pushed* means the branch is on the fork. *Validated* means the offline test suites listed
for it pass. A statement that a result is *not established* means it was not measured.
""")

add("### Table S0. Branches")
add(f"""
| ID | Kind | Branch | Starts from | Head | Status |
|---|---|---|---|---|---|
| S1 | Feature: runtime | {link_branch("efficiency/cost-and-runtime")} | `main` @ {link_commit("874eb71")} | {link_commit("18fda64")} | Pushed. Validated (replay 139/139, runtime checks 0 failures). Conflicts with S2 (see S5). |
| S2 | Feature: OpenAI and Anthropic providers | {link_branch("feature/llm-provider-support")} | `main` @ {link_commit("874eb71")} | {link_commit("95c6dde")} for the provider work; the branch head {link_commit("314e6d5")} also carries S3 | Pushed. Validated (see S2). |
| S3 | Feature: `--reasoning LEVEL` | {link_branch("feature/reasoning-level")} | S2 @ {link_commit("95c6dde")} | {link_commit("314e6d5")} | Pushed. Validated (23 new checks plus every earlier suite). Stacked on S2. |
| S4 | Experiment: Claude vs OpenAI through PESTO | {link_branch("experiment/claude-vs-openai-benchmark")} | S2 @ {link_commit("95c6dde")} (the exact commit benchmarked) | see branch | Pushed. Complete, $26.02 spent of a $40 cap. |
""")

# =============================================================== S1
add("---")
add("## S1. Runtime: about 2x faster per pair, same models, prompts, cost and answers")
add(f"""
**Branch** {link_branch("efficiency/cost-and-runtime")}. **Commits** {link_commit("d54910d", "Runtime: about 2x faster per pair")} (24 Oct 2026),
{link_commit("18fda64", "Reproducibility and robustness follow-ups")} (24 Oct 2026). **Starts from** `main` @ {link_commit("874eb71")}.

**Purpose.** Make one PESTO run cheaper and faster without changing what it answers (request from Jeremy). The default
pipeline is unchanged: the same searches, prompts and models, and the same arm fingerprint.

**What changed, by where the time went.**
- Open Targets runs alongside the literature branch instead of after it. This is the largest single saving.
- A disease-name embedding cache (one vector per name and encoder, per machine), saving 2 to 3 s per pair.
- Phenotype expansion starts without waiting for the local expanders.
- One PubMed `esummary` pass over the unique PMIDs, kept in a bounded LRU cache (10,000 records); pooled keep-alive connections.
- Banding calls to Haiku in parallel (16 workers instead of 6); the batches, prompts and model are the same.
- Opt-in only, not default: the `abstracts-fast` arms (title sieve, batches of twenty) and `--expansion-cache`
  (one expansion per phenotype). Both change the fingerprint or the answers' provenance, so neither is on by default.
- Per-stage timing in every run; default pair workers 20 to 10; encoder revisions pinned; a failed `esummary` is no longer cached as "no record".

**Results (live Anthropic, PubMed with an NCBI key, Open Targets).**

| measurement | original | optimized |
|---|---|---|
| One pair, nothing cached (12 runs per version; DDX41, BRCA1, MEF2C, SLTM, interleaved) | 46 s | 24 s (1.9x) |
| Group of 20 mixed pairs, 10 at a time | 117 s | 80 s (1.5x) |
| Cost of that 20-pair group | $3.10 | $3.09 |

Agreement on the same 20 mixed pairs: literature verdict identical for 18/20 and one level apart for 2/20 (none two or more apart);
Open Targets verdict identical for 18/20 and one level apart for 2/20; P(Established) r = 0.997, mean difference 1.9 points. For
scale, the optimized code run twice on 20 autism genes agrees with itself on 17/20 and with the published `pesto.tsv` rows on 16/20,
which is the size of normal Opus sampling variation.

**Table S1. Pair workers (20 mixed pairs, live APIs, NCBI key, no cache, two runs per setting in forward and reverse order).**

| workers | batch (s) | pairs/min | steady pairs/min | pair median (s) | pair p90 (s) |
|---|---|---|---|---|---|
| 2 | 254.8 | 4.7 | 5.1 | 22.4 | 28.8 |
| 4 | 130.8 | 9.2 | 10.2 | 23.0 | 28.2 |
| 6 | 97.2 | 12.4 | 14.4 | 24.2 | 32.6 |
| 8 | 78.5 | 15.4 | 17.7 | 27.1 | 33.0 |
| 10 | 72.4 | 16.7 | 21.7 | 27.8 | 34.2 |
| 20 | 60.0 | 20.0 | 25.0 | 49.0 | 54.8 |

Throughput keeps rising to 20 workers (about 15% over 10 in steady state), but pair latency doubles because the shared NCBI
rate gate queues calls (median wait 2.0 s per call at 20 workers against 0.22 s at 10). Ten workers keeps near-peak throughput
with latency at its floor; no SDK retries, timeouts or failed pairs occurred at any setting.

**Validation.** `tests/replay.py` 139/139 unchanged (this branch adds the two opt-in arms, hence 139 and not 137);
`tests/runtime_checks.py` (new, offline) 0 failures.

**Not established.** The 140-pair average-precision comparison was not run (about $21 for the optimized code alone), so n = 20
can rule out breakage but not a small accuracy shift. The expansion cache is untested at 100 to 200 genes. The 20-pair group
timings were read from run logs and not rerun for the figures.
""")

# =============================================================== S2
add("---")
add("## S2. Provider support: run PESTO on OpenAI models as well as Anthropic's")
add(f"""
**Branch** {link_branch("feature/llm-provider-support")}. **Starts from** `main` @ {link_commit("874eb71")}.
**Commits** (24 to 25 Oct 2026):
{link_commit("275b902", "Tests: pin the Anthropic request behaviour of the LLM layer")};
{link_commit("447e435", "Fix: retry without temperature when the API refuses it for a model")};
{link_commit("2bf9b41", "Provider support: run PESTO on OpenAI models as well as Anthropic's")};
{link_commit("95c6dde", "Fix: --bench with an explicit --arm crashed every pair on `routed`")}.

**Purpose.** Let PESTO call OpenAI models without changing anything about how it calls Claude.

**What it does.**
- A model is named by a spec: a bare name is Anthropic, as it always was; `openai:NAME[@effort]` is OpenAI (Responses API,
  explicit reasoning effort; `gpt-6.1-sol` defaults to medium and `gpt-6-luna` to low).
- `--model` and `--model-fast` take either, and so do the new `--router-model`, `--ot-gate-model` and `--ot-reader-model`.
- A provider interface with two adapters. The Anthropic adapter is the call PESTO has always made, moved unchanged. The OpenAI
  adapter reports retries, refusals and truncation in PESTO's own words and counts reasoning tokens as output.
- A run asks for the key of each provider it will call and no other, before anything is fetched or paid for.
- Open Targets gate and reader models are configurable and are part of the cache key, so an answer is reused only by the models
  that gave it; the published pair leaves every existing key unchanged.
- OpenAI list prices were added; a model with no price is reported as unpriced and never charged at another model's rate.

**Two defects found and fixed on the way (separate commits).**
- Claude Haiku 4.5 now answers a request that carries a temperature with a 400 ("Extra inputs are not permitted"), as Opus 4 and
  later always did, so every Haiku call of a run failed. The model is now remembered and called without it, with a warning.
- Introduced and fixed within this branch: `--bench` with an explicit `--arm` raised `UnboundLocalError` on `routed` for every
  pair. Released code did not have it.

**Table S2. Validation (all offline: no network, no key).**

| suite | what it checks | result |
|---|---|---|
| `tests/anthropic_requests.py` | the exact Anthropic request, streaming, retries, errors and token counts, against a recording made before the refactor | 21/21 unchanged |
| `tests/anthropic_temperature.py` | the temperature fallback; fails without the fix | 3/3 |
| `tests/llm_providers.py` | specs, keys, OpenAI adapter against real SDK response objects, Open Targets keys and records, pricing, CLI, router | 59/59 |
| `tests/replay.py` | recorded blocks and fingerprints | 137/137 unchanged |

**Not established.** OpenAI models are candidates to be benchmarked, not validated replacements for Haiku and Opus. Section S4 is
that benchmark, and it measures agreement with Claude, not accuracy.
""")

# =============================================================== S3
add("---")
add("## S3. `--reasoning LEVEL`: one reasoning level for a run, passed to OpenAI or Claude")
add(f"""
**Branch** {link_branch("feature/reasoning-level")}. **Commit** {link_commit("314e6d5", "Add --reasoning LEVEL")} (25 Oct 2026).
**Stacked on S2**: it needs the provider layer, so merge S2 first. (The S2 branch head also contains this commit.)
**Origin.** Suggestion from Jeremy: add the reasoning level as a parameter of PESTO, passed down to OpenAI or Claude.

**Design decisions** (chosen by the project owner): one global flag; a level written in a model's own spec wins over it;
opt-in for Claude; a shared level vocabulary.

**What it does.**
- `--reasoning {{none,low,medium,high,max}}` sets the default level for every model the run calls: the literature steps, the
  `--arm auto` router and both Open Targets models. OpenAI receives it as `reasoning.effort`; Claude as `output_config.effort`
  (which Claude had no way to set before). `xhigh` exists for both and is spelled only in a spec (`MODEL@xhigh`).
- The level is part of the canonical model name, so it enters every fingerprint and cache key; a run is never reused at a different level.
- Claude gets extra output room per level (4k for `low` up to 64k for `max`), because thinking counts against the output cap.
- Claude has no off level, so `none` is refused for Claude (and for `gpt-6.1-sol`, whose lowest level is `low`).
  An unrunnable level stops the run before anything is fetched, naming the flag and the model.
- A refusal of the level by the API is raised, never retried without it, so a run cannot record a level it did not have.

**Finding from live calls: Claude Haiku 4.5 takes no reasoning level.** The API answers 400 "This model does not support the
effort parameter". PESTO's default arm uses Haiku for banding, broadening and the Open Targets gate, so a global flag would have
failed mid-run. The flag therefore leaves a model that has no level alone and says so on stderr; the fingerprint records that it
ran without one. Writing `claude-haiku-4-5@low` yourself is refused up front.

**Table S3. Live checks (one tiny prompt each: "Reply with the single word: ok").**

| spec | result | input / output tokens | list-price cost |
|---|---|---|---|
| `claude-haiku-4-5` | answered | 14 / 4 | $0.000034 |
| `claude-haiku-4-5@low` | refused: 400, effort not supported by the model | n/a | n/a |
| `claude-opus-5@low` | answered | 16 / 4 | $0.00018 |
| `claude-opus-5@max` | answered | 16 / 4 | $0.00018 |
| `openai:gpt-6-luna@max` | answered | 13 / 5 | $0.0000038 |

**Evidence that a run without the flag is unchanged.** Every arm's fingerprint and model list, the Open Targets defaults, the
router and the alias table are byte-identical to the previous commit (compared programmatically); the Anthropic request
recording (21/21) and the replay (137/137) are unchanged; no prompt or fixture changed.

**Validation.** `tests/reasoning_level.py` (new): 23 checks covering parsing and canonical form, the Claude request with and
without a level, both SDK shapes, the API-refusal backstop, the temperature retry, fingerprints, precedence, the router and Open
Targets, early refusals and key requirements. All earlier suites pass unchanged.

**Not established.** No full pair has been run with the flag, and no experiment on how reasoning level changes verdicts has been
run. Opus 5's API default is already `high`, so `--reasoning high` on Claude should behave like no flag but is cached separately.
""")

# =============================================================== S4
add("---")
add("## S4. Experiment: Claude and OpenAI models through PESTO")
add(f"""
**Branch** {link_branch("experiment/claude-vs-openai-benchmark")}. **Code under test** S2 @ {link_commit("95c6dde")}, working tree clean at launch.
Date: 25 October 2026. The branch holds the instrumentation and analysis scripts, the pair tables, the three generated reports,
the figures and the run manifest.

**Question.** If PESTO is run end to end on OpenAI models instead of Claude, how often does the verdict change, and where does a
change come from (retrieval, the sieve that picks what the reader sees, the reader, or sampling)?

**Design.**
- 60 gene-phenotype pairs: 15 each of saved Established, Existing, Hypothesized and Novel; 22 borderline; 14 on the trait arm.
  The table's SHA-256 is `bb2643c71bee3ab0c5f62335f23fdb0c069e39f7da81e192d0b073027b670f98`.
- Two families, same table, same order, run concurrently through the real `pesto --bench` path, `--arm auto`, `--no-cache`, 3 workers.
- No date ceiling: `--max-date` skips Open Targets, which is one of the comparison axes. Both families therefore read the current
  PubMed at the same time of day, and retrieval overlap is reported.
- Stages: (1) end to end, 60 pairs by 2 families; (2) frozen-input: re-run one stage on the other family's recorded inputs so
  the stage is isolated; (3) stability: 12 pairs by 2 extra end-to-end runs per family.
- Nothing about prompts, models, reasoning settings or logic was changed during the benchmark. The instrumentation only wraps
  calls to record them.

**Table S4. Models and settings.**

| role | Claude family | OpenAI family |
|---|---|---|
| reader, synonyms, router, Open Targets reader | `claude-opus-5` | `openai:gpt-6.1-sol` (effort medium) |
| sieve, broaden, Open Targets gate | `claude-haiku-4-5` | `openai:gpt-6-luna` (effort low) |
| list price per million tokens in / out | Opus $5.00 / $25.00; Haiku $1.00 / $5.00 | Sol $2.00 / $10.00; Luna $0.10 / $0.50 |

Environment: Python 3.12.5 on macOS 15.1 (arm64); anthropic SDK 2.3.0; openai SDK 3.37.0; torch 2.4.0. Offline suites passed
before launch (21/21, 3/3, 59/59, 137/137). Total spend $26.02 against a $40 hard stop (about $11.2 end to end, $4.7 stability,
$10.1 frozen-input stages).

**Verification that the two families saw identical prompts.** The reader prompt was verified identical between families on
84/84 reader calls, and across all 8 prompt templates on 2,115 logged calls; the frozen-input stage asserts that the packet it
hands the reader matches the live read for 59/59 pairs and that the prompt is byte-identical for 59/59 pairs. The prompt text
therefore does not explain any difference below.

### S4.1 End to end, 60 pairs by 2 families
""")

add("**Key results.** The headline literature call agrees exactly on 49/60 pairs (82%) and within one level on 58/60 (97%), "
    "quadratic kappa 0.89. Open Targets agrees on 56/59 (95%). The final verdict, Max(literature, Open Targets), agrees on 53/60 (88%) "
    "and within one level on 59/60. Continuous expected grade correlates at Spearman 0.948. The router chose the same arm on 60/60 "
    "pairs. Claude's probabilities are much less sharp (mean entropy 1.05 against 0.23 bits; 0/60 one-hot against 22/60). "
    "OpenAI cost 5.4 times less per pair at equal wall time.")
add(fig(1, "0_summary.png", "Summary of the Claude and OpenAI comparison."))

for num, title, prefix in [
    (1, "Category agreement", "## 1."), (2, "Continuous expected grade", "## 2."),
    (3, "Probability sharpness", "## 3."), (4, "Router", "## 4."),
    (5, "Retrieval: model or retrieval?", "## 5."), (6, "Sieve inside the live runs", "## 6."),
    (7, "Cost, latency and reliability", "## 7."), (8, "Disagreement list", "## 8."),
    (9, "Stability", "## 9."),
]:
    add(f"#### S4.1.{num} {title}")
    add(section(E2E, prefix))
    if num == 1:
        add(fig(2, "1_agreement.png", "Agreement between the Claude and OpenAI families."))
        add(fig(3, "2_confusion.png", "Confusion between the two families."))
    if num == 2:
        add(fig(4, "3_grade_scatter.png", "Expected grade, Claude against OpenAI, per pair."))
    if num == 3:
        add(fig(5, "4_sharpness.png", "Probability sharpness of the two families."))
    if num == 7:
        add(fig(6, "5_cost_time.png", "Cost and time per pair."))
    if num == 9:
        add(fig(7, "6_stability.png", "Run-to-run stability."))

add("""
### S4.2 Frozen-input comparisons: isolating one stage
Everything below goes through production code (`harness.band`, `harness.select_bands`, `arm.read.run`, `arm.judge.run`) on the
inputs the Claude run recorded, so only the named stage differs. 59 of the 60 pairs have a candidate pool.
""")
add(body_of(FRZ))
add(fig(8, "7_decomposition.png", "Where the disagreement comes from: reader, sieve, or the whole pipeline."))

add("""
### S4.3 Effect of the sieve on the verdict
The same frozen pools, with the reader held fixed, comparing what the Haiku sieve and the Luna sieve hand to the reader.
""")
add(body_of(SEV))
add(fig(9, "8_sieve.png", "Effect of swapping the sieve on the verdict."))

add("""
### S4.4 Limitations of this experiment
- **Agreement, not accuracy.** The experiment measures how often OpenAI models agree with Claude through PESTO. It does not
  measure which family is closer to the truth, and a lower agreement does not mean OpenAI is worse.
- **Sampling is not controlled.** Opus and Haiku run at the API default temperature (the API refuses a fixed one), and OpenAI
  reasoning models take no sampling parameters. The stability stage (S4.1.9) measures the resulting run-to-run variation.
- **Reasoning settings were the defaults** (`gpt-6.1-sol` medium, `gpt-6-luna` low) and were not varied. The `--reasoning` flag
  (S3) exists so that they can be.
- **Different synonym models.** `--model-fast` also covers the synonym step, so Claude expands with Opus and OpenAI with Luna
  (9.1 against 4.7 synonyms per pair). That is a stage difference between the families, reported in S4.1.5.
- **Claude reasoning tokens are not reported by the API**, so the 0 in the reliability table is "not reported", not "none used".
- **Live literature.** Both families read the current PubMed, so results move over time; the two families ran at the same time of day.
- **n = 60**, 15 per saved category; confidence intervals are in S4.3 where they were computed.

### S4.5 Reproduction
Run from the repository root at the commit above, with keys for both providers (see the README):
`run_e2e.py --rep r1 --pairs pairs.tsv --out runs/r1`; `frozen.py` for the frozen-input stages; then `an_e2e.py`, `an_frozen.py`
and `an_sieve_effect.py` for the three reports and `figs.py` for the figures. The scripts use `instr.py`, which only records calls.
The scripts refer to their working directory as `/Users/dinan_elsyad/pesto_cmp`; change `ROOT` in `an_common.py` and `instr.py` to
reproduce elsewhere. The raw call logs (`ledger.jsonl`, `frozen_*.jsonl`, `runs/`) contain article text and are not in the branch.
""")

# =============================================================== S5
add("---")
add("## S5. How the branches relate, and what merging them involves")
add(f"""
- **S3 depends on S2.** S3 is the single commit {link_commit("314e6d5")} on top of S2's {link_commit("95c6dde")}. Merge S2, then S3. The S2
  branch already contains S3, so merging {link_branch("feature/llm-provider-support")} alone brings both; {link_branch("feature/reasoning-level")} exists so
  that S3 can be reviewed and merged on its own.
- **S4 depends on S2** for the code it ran, and adds only files under `experiments/`; it changes no source.
- **S1 and S2 conflict.** They were built independently from the same `main` commit and both touch the LLM layer and the
  Open Targets code. A trial merge (`git merge-tree`, 25 Oct 2026) reports content conflicts in `src/pesto/cli.py`,
  `src/pesto/ot_matcher.py` and `src/pesto/services/llm_service.py`. Both implement the same Haiku temperature fallback
  (S1 in `llm_service.py`, S2 in the Anthropic adapter); the S2 version is the one that survives the move to adapters. The
  `ot_matcher.py` conflict is substantive: S1 asks the Open Targets gate and reader together, and S2 makes those two models configurable.
  This needs a deliberate resolution, not a mechanical one, and whichever branch merges second should be rebased on the first.
- **Test counts differ between branches by design.** S1 reports replay 139/139 (it adds two arms); S2 and S3 report 137/137.
""")


MD = "\n\n".join(DOC) + "\n"
MD = (MD.replace("{'OpenAI higher': 4, 'OpenAI lower': 7}", "OpenAI higher on 4 pairs, OpenAI lower on 7")
        .replace("{'claude': '$4.00', 'openai': '$0.74'}", "Claude $4.00, OpenAI $0.74")
        .replace("{'': 3693}", "none (all 3693 were banded)"))
open(os.path.join(HERE, "SUPPLEMENT.md"), "w", encoding="utf-8").write(MD)


# ======================================================================= docx
def to_docx(md, path):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor

    doc = Document()
    for s in doc.sections:
        s.left_margin = s.right_margin = Inches(0.8)
        s.top_margin = s.bottom_margin = Inches(0.8)
    st = doc.styles["Normal"]
    st.font.name = "Arial"
    st.font.size = Pt(10)
    st.paragraph_format.space_after = Pt(6)

    def hyperlink(par, text, url, mono=False):
        rid = par.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                                 is_external=True)
        h = OxmlElement("w:hyperlink")
        h.set(qn("r:id"), rid)
        r = OxmlElement("w:r")
        rpr = OxmlElement("w:rPr")
        c = OxmlElement("w:color")
        c.set(qn("w:val"), "1155CC")
        u = OxmlElement("w:u")
        u.set(qn("w:val"), "single")
        rpr.append(c)
        rpr.append(u)
        if mono:
            f = OxmlElement("w:rFonts")
            f.set(qn("w:ascii"), "Consolas")
            f.set(qn("w:hAnsi"), "Consolas")
            rpr.append(f)
        r.append(rpr)
        t = OxmlElement("w:t")
        t.text = text
        t.set(qn("xml:space"), "preserve")
        r.append(t)
        h.append(r)
        par._p.append(h)

    TOKEN = re.compile(r"(\[`?[^\]]+?`?\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)")

    def inline(par, text, size=None, bold=False):
        for part in TOKEN.split(text):
            if not part:
                continue
            m = re.fullmatch(r"\[(`?)([^\]]+?)`?\]\(([^)]+)\)", part)
            if m:
                hyperlink(par, m.group(2), m.group(3), mono=bool(m.group(1)))
                continue
            if part.startswith("**") and part.endswith("**"):
                r = par.add_run(part[2:-2])
                r.bold = True
            elif part.startswith("`") and part.endswith("`"):
                r = par.add_run(part[1:-1])
                r.font.name = "Consolas"
            elif part.startswith("*") and part.endswith("*") and len(part) > 2:
                r = par.add_run(part[1:-1])
                r.italic = True
            else:
                r = par.add_run(part)
                r.bold = bold or None
            if size:
                r.font.size = Pt(size)

    def shade(cell, fill):
        tcpr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), fill)
        tcpr.append(shd)

    def table(rows):
        cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
        header, data = cells[0], [r for r in cells[2:]]
        n = len(header)
        size = 7 if n >= 11 else 8 if n >= 7 else 9
        t = doc.add_table(rows=1, cols=n)
        t.style = "Table Grid"
        for i, h in enumerate(header):
            c = t.rows[0].cells[i]
            c.text = ""
            inline(c.paragraphs[0], h, size=size, bold=True)
            shade(c, "E8EEF7")
        for r in data:
            row = t.add_row().cells
            for i in range(n):
                row[i].text = ""
                inline(row[i].paragraphs[0], r[i] if i < len(r) else "", size=size)
        doc.add_paragraph()

    lines = md.splitlines()
    i = 0
    while i < len(lines):
        l = lines[i]
        if not l.strip() or l.strip() == "---":
            i += 1
            continue
        if l.startswith("|"):
            blk = []
            while i < len(lines) and lines[i].startswith("|"):
                blk.append(lines[i])
                i += 1
            table(blk)
            continue
        m = re.match(r"(#+)\s+(.*)", l)
        if m:
            level = min(len(m.group(1)), 5)
            h = doc.add_heading(level=level - 1 if level > 1 else 0)
            inline(h, m.group(2))
            i += 1
            continue
        m = re.match(r"!\[(.*?)\]\((.*?)\)", l)
        if m:
            doc.add_picture(m.group(2), width=Inches(6.2))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            cap = doc.add_paragraph()
            cap.alignment = WD_ALIGN_PARAGRAPH.LEFT
            inline(cap, "**" + m.group(1).split(".")[0] + ".**" + m.group(1)[len(m.group(1).split(".")[0]) + 1:], size=9)
            i += 1
            continue
        if re.match(r"\s*[-*]\s+", l):
            par = doc.add_paragraph(style="List Bullet")
            text = re.sub(r"^\s*[-*]\s+", "", l)
            i += 1
            while i < len(lines) and lines[i].startswith("  ") and not re.match(r"\s*[-*]\s+", lines[i]):
                text += " " + lines[i].strip()
                i += 1
            inline(par, text)
            continue
        # a paragraph, possibly wrapped over several lines
        text = l.strip()
        i += 1
        while (i < len(lines) and lines[i].strip() and not lines[i].startswith(("|", "#", "!", "- ", "* ", "---"))
               and not re.match(r"\s*[-*]\s+", lines[i])):
            text += " " + lines[i].strip()
            i += 1
        par = doc.add_paragraph()
        inline(par, text)
    doc.save(path)


if "--md-only" not in sys.argv:
    to_docx(MD, os.path.join(HERE, "PESTO_development_log.docx"))
    print("wrote SUPPLEMENT.md and PESTO_development_log.docx")
else:
    print("wrote SUPPLEMENT.md")
