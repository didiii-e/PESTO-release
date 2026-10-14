#!/usr/bin/env python3
"""Figure 2 on Claude and on Gemini, pair by pair (14 October 2026).

Joins, for the 1,043 pairs of Figure 2 (results/gemini_fig2/pairs.tsv), the
evidence score of the Claude run behind each panel and that of the Gemini run
(results/gemini_fig2/full/pesto.tsv), and computes for both models the measures
the paper reports on Fig. 2:

  agreement            verdicts identical, within one level, score correlation
  per group            % of each verdict in each GenCC class and ASC group
  GenCC                AUC of Definitive and Strong against Moderate and Limited,
                       on the score and on the verdict (the latter is the 0.70 of
                       the main text and Note 3), average precision of
                       the 400 curated pairs against the 100 Absent, Spearman of
                       score with class (Absent 0 to Definitive 4)
  ASC                  % of autism candidate genes called Established
  dated Limited        per 3-year window, mean score of each method and average
                       precision against the 100 Absent, for PESTO and for the
                       model's internal knowledge (panels c and d)
  citations            panels e and f, from each model's pair_summary.tsv

Scores are the confidence-weighted mean on the 1-4 scale; a verdict is that mean
rounded, as in the figure. Bootstrap intervals: 2,000 resamples of pairs, seed 1.

  python3 scripts/303_gemini_fig2_comparison.py
Writes results/gemini_fig2/comparison/pairs.tsv, groups.tsv, metrics.tsv,
windows.tsv, citations.tsv.
"""
from __future__ import annotations

import csv
import json
import os
import random
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(ROOT, "results")
G = os.path.join(R, "gemini_fig2")
OUT = os.path.join(G, "comparison")
V = ["Novel", "Hypothesized", "Existing", "Established"]
P = ("p_novel", "p_hypothesized", "p_existing", "p_established")
CLASS_RANK = {"Absent": 0, "Limited": 1, "Moderate": 2, "Strong": 3, "Definitive": 4}
WINDOWS = [(2011, 2013), (2014, 2016), (2017, 2019), (2020, 2022), (2023, 2025)]
B = 2000


def tsv(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def save(name, rows):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter="\t")
        w.writeheader()
        w.writerows(rows)


def from_p(r):
    return sum(float(r[k]) * (i + 1) for i, k in enumerate(P)) / 100


def call(s):
    return V[max(0, min(3, int(s + 0.5) - 1))]


def claude_scores():
    s = {}
    for r in tsv(os.path.join(ROOT, "benchmark", "gencc_clingen_g2p", "pesto.tsv")):
        if r["p_novel"]:
            s[(r["gene"], r["phenotype"])] = from_p(r)
    for r in tsv(os.path.join(R, "fig2a_extra40", "combined_n100.tsv")):
        if r["source"] != "original":
            s[(r["gene"], r["phenotype"])] = float(r["current"])
    for d in ("fig2a_absent_extra20", "fig2a_absent_extra20b", "fig2a_absent_extra30"):
        for r in tsv(os.path.join(R, d, "pesto.tsv")):
            if not r["error"]:
                s[(r["gene"], r["phenotype"])] = float(r["lit_score"])
    for f in ("asd", "asd_extra101", "extra50_random"):
        for r in tsv(os.path.join(ROOT, "benchmark", f, "pesto.tsv")):
            if r["p_novel"]:
                s.setdefault((r["gene"].upper(), r["phenotype"]), from_p(r))
    with open(os.path.join(R, "prior_year10", "pesto.json"), encoding="utf-8") as fh:
        for r in json.load(fh):
            d = r["distribution"]
            s.setdefault((r["gene"], r["phenotype"]),
                         sum(d.get(c, 0) * (i + 1) for i, c in enumerate(V)) / 100)
    return s


def ranks(x):
    order = sorted(range(len(x)), key=lambda i: x[i])
    rk = [0.0] * len(x)
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and x[order[j + 1]] == x[order[i]]:
            j += 1
        for k in range(i, j + 1):
            rk[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return rk


def pearson(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a) ** 0.5
    vb = sum((y - mb) ** 2 for y in b) ** 0.5
    return cov / (va * vb) if va and vb else float("nan")


def spearman(a, b):
    return pearson(ranks(a), ranks(b))


def auc(score, y):
    pos = [s for s, t in zip(score, y) if t]
    neg = [s for s, t in zip(score, y) if not t]
    win = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return win / (len(pos) * len(neg))


def ap(score, y):
    """Average precision with tied scores grouped, as in scripts/21_figure2.R."""
    order = sorted(range(len(score)), key=lambda i: -score[i])
    s = [score[i] for i in order]
    t = [y[i] for i in order]
    total, tp, prev_recall, out = sum(t), 0, 0.0, 0.0
    for k in range(len(s)):
        tp += t[k]
        if k == len(s) - 1 or s[k + 1] != s[k]:
            recall, precision = tp / total, tp / (k + 1)
            out += (recall - prev_recall) * precision
            prev_recall = recall
    return out


def boot(fun, rows, rng):
    vals = []
    for _ in range(B):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]
        try:
            vals.append(fun(sample))
        except ZeroDivisionError:
            continue
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]


def main():
    claude = claude_scores()
    gemini = {(r["gene"], r["phenotype"]): from_p(r) for r in tsv(os.path.join(G, "full", "pesto.tsv"))}
    rows = []
    for p in tsv(os.path.join(G, "pairs.tsv")):
        k = (p["gene"], p["phenotype"])
        rows.append({"gene": p["gene"], "phenotype": p["phenotype"], "panels": p["panels"], "truth": p["truth"],
                     "claude_score": round(claude[k], 4), "gemini_score": round(gemini[k], 4),
                     "claude_verdict": call(claude[k]), "gemini_verdict": call(gemini[k])})
    save("pairs.tsv", rows)

    same = sum(r["claude_verdict"] == r["gemini_verdict"] for r in rows)
    one = sum(abs(V.index(r["claude_verdict"]) - V.index(r["gemini_verdict"])) <= 1 for r in rows)
    higher = sum(V.index(r["gemini_verdict"]) > V.index(r["claude_verdict"]) for r in rows)
    lower = sum(V.index(r["gemini_verdict"]) < V.index(r["claude_verdict"]) for r in rows)
    rho = spearman([r["claude_score"] for r in rows], [r["gemini_score"] for r in rows])
    r_ = pearson([r["claude_score"] for r in rows], [r["gemini_score"] for r in rows])
    print(f"{len(rows)} pairs: same verdict {same}, within one level {one}, Gemini higher {higher}, lower {lower}; "
          f"Spearman {rho:.3f}, Pearson {r_:.3f}")

    groups = []
    for panel in ("a", "b", "cd"):
        sub = [r for r in rows if panel in r["panels"].split(",")]
        for truth in sorted({r["truth"] if panel != "cd" else "Limited (dated)" for r in sub}):
            g = [r for r in sub if (r["truth"] if panel != "cd" else "Limited (dated)") == truth]
            for model in ("claude", "gemini"):
                c = Counter(r[f"{model}_verdict"] for r in g)
                groups.append({"panel": panel, "group": truth, "model": model, "n": len(g),
                               **{v: round(100 * c[v] / len(g), 1) for v in V},
                               "mean_score": round(sum(r[f"{model}_score"] for r in g) / len(g), 3)})
    save("groups.tsv", groups)

    rng = random.Random(1)
    gencc = [r for r in rows if "a" in r["panels"].split(",")]
    asc = [r for r in rows if "b" in r["panels"].split(",")]
    metrics = []

    def add(name, fun, data):
        for model in ("claude", "gemini"):
            f = (lambda m: (lambda d: fun(d, m)))(model)
            lo, hi = boot(f, data, rng)
            metrics.append({"metric": name, "model": model, "value": round(f(data), 4),
                            "lo": round(lo, 4), "hi": round(hi, 4), "n": len(data)})

    upper = [r for r in gencc if r["truth"] in ("Definitive", "Strong", "Moderate", "Limited")]
    add("AUC, Definitive+Strong vs Moderate+Limited",
        lambda d, m: auc([r[f"{m}_score"] for r in d], [r["truth"] in ("Definitive", "Strong") for r in d]), upper)
    add("AUC on verdicts, Definitive+Strong vs Moderate+Limited",
        lambda d, m: auc([V.index(r[f"{m}_verdict"]) for r in d], [r["truth"] in ("Definitive", "Strong") for r in d]),
        upper)
    add("Average precision, curated vs Absent",
        lambda d, m: ap([r[f"{m}_score"] for r in d], [int(r["truth"] != "Absent") for r in d]), gencc)
    add("Spearman, score vs GenCC class",
        lambda d, m: spearman([r[f"{m}_score"] for r in d], [CLASS_RANK[r["truth"]] for r in d]), gencc)
    add("Absent called Novel (%)",
        lambda d, m: 100 * sum(r[f"{m}_verdict"] == "Novel" for r in d) / len(d),
        [r for r in gencc if r["truth"] == "Absent"])
    add("Autism candidate called Established (%)",
        lambda d, m: 100 * sum(r[f"{m}_verdict"] == "Established" for r in d) / len(d),
        [r for r in asc if r["truth"] == "ASD candidate"])
    add("Autism known called Established (%)",
        lambda d, m: 100 * sum(r[f"{m}_verdict"] == "Established" for r in d) / len(d),
        [r for r in asc if r["truth"] == "ASD known"])
    add("Not in ASD list called Novel (%)",
        lambda d, m: 100 * sum(r[f"{m}_verdict"] == "Novel" for r in d) / len(d),
        [r for r in asc if r["truth"] == "Not in ASD list"])
    save("metrics.tsv", metrics)

    # Panels c and d, both methods, both models.
    years = {(r["gene"], r["phenotype"]): int(r["year"]) for r in tsv(os.path.join(R, "prior_year10", "knowledge.tsv"))
             if r["year"]}
    know_c = {(r["gene"], r["phenotype"]): float(r["lit_score"]) for r in tsv(os.path.join(R, "prior_year10", "knowledge.tsv"))
              if r["lit_score"]}
    for r in tsv(os.path.join(R, "ablation_fig2", "knowledge.tsv")):
        if r["draw"] == "1" and r["lit_score"]:
            know_c[(r["gene"], r["phenotype"])] = float(r["lit_score"])
    for d in ("fig2a_absent_extra20", "fig2a_absent_extra20b", "fig2a_absent_extra30"):
        for r in tsv(os.path.join(R, d, "knowledge.tsv")):
            if r["lit_score"]:
                know_c[(r["gene"], r["phenotype"])] = float(r["lit_score"])
    know_g = {(r["gene"], r["phenotype"]): from_p(r) for r in tsv(os.path.join(G, "knowledge", "pesto.tsv"))}
    absent = [(r["gene"], r["phenotype"]) for r in gencc if r["truth"] == "Absent"]
    by_key = {(r["gene"], r["phenotype"]): r for r in rows}
    windows = []
    for lo_y, hi_y in WINDOWS:
        lim = [r for r in rows if "cd" in r["panels"].split(",") and lo_y <= years[(r["gene"], r["phenotype"])] <= hi_y]
        for model, lit, kn in (("claude", "claude_score", know_c), ("gemini", "gemini_score", know_g)):
            for method in ("PESTO", "Model knowledge"):
                pos = [r[lit] if method == "PESTO" else kn[(r["gene"], r["phenotype"])] for r in lim]
                neg = [by_key[k][lit] if method == "PESTO" else kn[k] for k in absent]
                windows.append({"window": f"{lo_y}-{hi_y}", "model": model, "method": method, "n": len(pos),
                                "mean_score": round(sum(pos) / len(pos), 3),
                                "ap": round(ap(pos + neg, [1] * len(pos) + [0] * len(neg)), 3)})
    save("windows.tsv", windows)

    cites = []
    for model, path in (("claude", os.path.join(R, "knowledge_citations", "pair_summary.tsv")),
                        ("gemini", os.path.join(G, "knowledge_citations", "pair_summary.tsv"))):
        ps = tsv(path)
        for lo_y, hi_y in WINDOWS:
            for arm in ("pesto", "knowledge"):
                sub = [r for r in ps if r["arm"] == arm and lo_y <= int(r["year"]) <= hi_y]
                present = [r for r in sub if r["present"] == "True"]
                cites.append({"window": f"{lo_y}-{hi_y}", "model": model, "arm": arm, "n": len(sub),
                              "curated_paper_cited": sum(r["any_gencc"] == "True" for r in sub),
                              "curated_pmid_exact": sum(r["any_gencc_exact_pmid"] == "True" for r in sub),
                              "existing_or_established": len(present),
                              "backed_by_human_genetic_paper": sum(r["any_A"] == "True" for r in present)})
    save("citations.tsv", cites)
    print("wrote", os.path.relpath(OUT, ROOT))
    for m in metrics:
        print(f"  {m['metric']:45s} {m['model']:7s} {m['value']:.3f} ({m['lo']:.3f}-{m['hi']:.3f})")


if __name__ == "__main__":
    main()
