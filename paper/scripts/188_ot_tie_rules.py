"""What the Fig. 1 results would be if Open Targets let its closest ties reach
Existing instead of capping every tie at Hypothesized. Replays the stored
tagged-shortlist records; no model call, nothing in the paper is changed.

Three rules for a pair with no EXACT trait (an EXACT trait decides as now):
  current   every tie (PARENT_FIRST, CHILD_FIRST, CLOSE_VERY, CLOSE_MODERATE,
            SYMPTOM_SPECIFIC, SYMPTOM_MODERATE) caps at Hypothesized
  close     CLOSE_VERY earns its score band up to Existing; the rest as now
  close_pc  CLOSE_VERY, PARENT_FIRST and CHILD_FIRST up to Existing
The verdict is the best band over the qualifying ties. Score bands are those
of scoring.open_targets_verdict: Hypothesized above 0.05 and below 0.2,
Existing from 0.2 to 0.5, Established above 0.5.

For each rule: the Open Targets and Max counts of the 950 RVAS associations
(Fig. 1b, abstract and Results), the negative controls and the Fisher test
against them (Fig. 1b), literature–Open Targets concordance (Fig. 1c), the
Spearman correlation of burden significance with Max (Fig. 1d), and the pairs
that change. Writes results/ot_tie_rules/summary.tsv and changed_pairs.tsv.

  python3 scripts/188_ot_tie_rules.py
"""
from __future__ import annotations

import csv
import glob
import json
import math
import os
import sys

from scipy.stats import fisher_exact, spearmanr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "results", "all_runs_auto.tsv")
if not os.path.exists(RUNS):  # the name it has in PESTO-release/paper
    RUNS = os.path.join(ROOT, "results", "all_runs_auto_v7.tsv")
RVAS_OT = os.path.join(ROOT, "results", "auto_cohort_ot_v7")
CONTROLS = os.path.join(ROOT, "results", "bench_fig1c_absent50_hgnc_pesto_v7.tsv")
CONTROLS_OT = os.path.join(ROOT, "results", "auto_fig1c_absent50_hgnc_v7")
OUT = os.path.join(ROOT, "results", "ot_tie_rules")
LEVELS = ["Novel", "Hypothesized", "Existing", "Established"]
RANK = {v: i for i, v in enumerate(LEVELS)}
TIES = {"PARENT_FIRST", "CHILD_FIRST", "CLOSE_VERY", "CLOSE_MODERATE",
        "SYMPTOM_SPECIFIC", "SYMPTOM_MODERATE"}
RULES = {"current": set(), "close": {"CLOSE_VERY"},
         "close_pc": {"CLOSE_VERY", "PARENT_FIRST", "CHILD_FIRST"}}


def band(score):
    if score is None or score <= 0.05:
        return 0
    if score < 0.2:
        return 1
    if score <= 0.5:
        return 2
    return 3


def records(folder):
    out = {}
    for f in glob.glob(os.path.join(folder, "open_targets_match_*.json")):
        d = json.load(open(f))
        out[(d["gene"], d["phenotype"])] = d
    return out


def verdict(rec, rule):
    """Replay as ot_matcher.replay_tagged with the gate on, then apply `rule`."""
    short = rec.get("shortlist") or []
    by_id = {g.get("disease_id"): g for g in rec.get("graded") or []}
    dropped = set(rec.get("gate_dropped_ids") or [])
    used = [t for t in short if t.get("disease_id") not in dropped] or short
    tagged = [(t, (by_id.get(t.get("disease_id")) or {}).get("tag")) for t in used]
    exact = [t for t, g in tagged if g == "EXACT"]
    if exact:
        return band(max(t.get("score") or 0 for t in exact)), "EXACT"
    best, tag = 0, None
    for t, g in tagged:
        if g in TIES:
            b = band(t.get("score"))
            b = min(b, 2 if g in RULES[rule] else 1)
            if b > best:
                best, tag = b, g
    return best, tag


def main():
    rows = [r for r in csv.DictReader(open(RUNS), delimiter="\t")
            if r["source"] in ("AoU", "BRAVA") and r["verdict"] in RANK]
    pairs = {}
    for r in rows:
        pairs.setdefault((r["gene"], r["phenotype"]), r)
    rec = records(RVAS_OT)
    controls = [r for r in csv.DictReader(open(CONTROLS), delimiter="\t")
                if r["lit_mean"] in RANK]
    crec = records(CONTROLS_OT)

    # The replay must give back the stored verdicts under the current rule.
    agree = sum(LEVELS[verdict(rec[k], "current")[0]] == r["ot_verdict"]
                for k, r in pairs.items() if k in rec and r["ot_verdict"] in RANK)
    have = sum(1 for k, r in pairs.items() if k in rec and r["ot_verdict"] in RANK)
    print(f"replay check: {agree} of {have} RVAS Open Targets verdicts reproduced")

    summary, changed = [], []
    for rule in RULES:
        ot, mx, lit, burden = [], [], [], []
        for k, r in pairs.items():
            if k not in rec:
                continue
            o, tag = verdict(rec[k], rule)
            li = RANK[r["verdict"]]
            ot.append(o)
            lit.append(li)
            mx.append(max(o, li))
            p = r.get("burden_pvalue")
            if p not in (None, "", "NA"):
                try:
                    pv = float(p)
                    if pv > 0:
                        burden.append((max(o, li), -math.log10(pv)))
                except ValueError:
                    pass
            if rule != "current":
                o0, _ = verdict(rec[k], "current")
                if o != o0:
                    changed.append({"rule": rule, "gene": k[0], "phenotype": k[1],
                                    "deciding_tag": tag, "literature": LEVELS[li],
                                    "ot_before": LEVELS[o0], "ot_after": LEVELS[o],
                                    "max_before": LEVELS[max(o0, li)],
                                    "max_after": LEVELS[max(o, li)]})
        cmax = []
        for r in controls:
            k = (r["gene"], r["phenotype"])
            o = verdict(crec[k], rule)[0] if k in crec else RANK.get(r["open_targets_verdict"], 0)
            cmax.append(max(o, RANK[r["lit_mean"]]))
        n = len(mx)
        low = sum(v <= 1 for v in mx)
        clow = sum(v <= 1 for v in cmax)
        _, pf = fisher_exact([[clow, len(cmax) - clow], [low, n - low]])
        exact_c = sum(a == b for a, b in zip(lit, ot)) / n
        one_c = sum(abs(a - b) <= 1 for a, b in zip(lit, ot)) / n
        rho = spearmanr([b for b, _ in burden], [p for _, p in burden])[0]
        row = {"rule": rule, "n": n}
        row.update({f"ot_{LEVELS[i]}": ot.count(i) for i in range(4)})
        row.update({f"max_{LEVELS[i]}": mx.count(i) for i in range(4)})
        row.update({"max_novel_or_hyp": low, "controls_novel_or_hyp": f"{clow}/{len(cmax)}",
                    "fisher_p": f"{pf:.2g}", "concord_exact": round(exact_c, 3),
                    "concord_within_one": round(one_c, 3), "spearman_burden_max": round(rho, 3),
                    "n_burden": len(burden)})
        summary.append(row)

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "summary.tsv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]), delimiter="\t")
        w.writeheader()
        w.writerows(summary)
    with open(os.path.join(OUT, "changed_pairs.tsv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(changed[0]) if changed else ["rule"], delimiter="\t")
        w.writeheader()
        w.writerows(changed)
    for row in summary:
        print(row)
    for rule in ("close", "close_pc"):
        ch = [c for c in changed if c["rule"] == rule]
        mch = [c for c in ch if c["max_before"] != c["max_after"]]
        print(f"{rule}: {len(ch)} Open Targets verdicts change, {len(mch)} Max verdicts change")
        for c in mch[:40]:
            print("  ", c["gene"], "|", c["phenotype"], "|", c["deciding_tag"], "|",
                  c["max_before"], "->", c["max_after"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
