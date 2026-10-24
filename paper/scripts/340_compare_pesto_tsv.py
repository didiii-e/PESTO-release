"""Compare two pesto.tsv tables the way the paper already scores runs.

Exact four-level agreement, within one level, Spearman on the 1-4 evidence
score. If both tables have the 140-pair Fig. 2d labels (or --labels), also
print average precision. No model call.

Default: the three reproducibility_aou50 runs against each other, which is
the bar a faster arm has to meet (literature ICC 0.989, 43/50 identical).

  python3 paper/scripts/340_compare_pesto_tsv.py
  python3 paper/scripts/340_compare_pesto_tsv.py a.tsv b.tsv
  python3 paper/scripts/340_compare_pesto_tsv.py --fast-vs-published FAST.tsv
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AOU = os.path.join(ROOT, "results", "reproducibility_aou50")
ORDER = ("Novel", "Hypothesized", "Existing", "Established")
RANK = {k: i + 1 for i, k in enumerate(ORDER)}
WEIGHT = {"Established": 4, "Existing": 3, "Hypothesized": 2, "Novel": 1}


def read_tsv(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def key(row):
    return (row.get("gene") or "").upper(), row.get("phenotype") or ""


def num(row, *names):
    for name in names:
        raw = row.get(name, "")
        if raw in ("", None):
            continue
        try:
            return float(raw)
        except ValueError:
            continue
    return None


def score(row):
    parts = [num(row, "p_established"), num(row, "p_existing"),
             num(row, "p_hypothesized"), num(row, "p_novel")]
    if all(p is not None for p in parts):
        return (4 * parts[0] + 3 * parts[1] + 2 * parts[2] + parts[3]) / 100.0
    call = (row.get("lit_mean") or row.get("lit_argmax") or "").strip()
    return float(RANK[call]) if call in RANK else None


def verdict(row):
    return (row.get("lit_mean") or row.get("lit_argmax") or "").strip()


def spearman(xs, ys):
    def ranks(vals):
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        out = [0.0] * len(vals)
        i = 0
        while i < len(vals):
            j = i
            while j + 1 < len(vals) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            mid = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = mid
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    num_ = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) *
                    sum((b - my) ** 2 for b in ry))
    return num_ / den if den else 0.0


def average_precision(y, s):
    order = sorted(range(len(s)), key=lambda i: -s[i])
    hit, ap = 0, 0.0
    pos = sum(y)
    if not pos:
        return 0.0
    for k, i in enumerate(order, 1):
        if y[i]:
            hit += 1
            ap += hit / k
    return ap / pos


def compare(a_path, b_path, labels=None):
    a = {key(r): r for r in read_tsv(a_path)}
    b = {key(r): r for r in read_tsv(b_path)}
    shared = sorted(set(a) & set(b))
    if not shared:
        raise SystemExit(f"no shared pairs between {a_path} and {b_path}")
    exact = within = 0
    sa, sb = [], []
    disagreements = []
    for k in shared:
        va, vb = verdict(a[k]), verdict(b[k])
        if va == vb:
            exact += 1
        if va in RANK and vb in RANK and abs(RANK[va] - RANK[vb]) <= 1:
            within += 1
        xa, xb = score(a[k]), score(b[k])
        if xa is not None and xb is not None:
            sa.append(xa)
            sb.append(xb)
        if va != vb:
            disagreements.append((k[0], k[1], va, vb))
    n = len(shared)
    out = {
        "n": n,
        "exact": exact,
        "exact_frac": exact / n,
        "within_one": within,
        "within_one_frac": within / n,
        "spearman": spearman(sa, sb) if len(sa) >= 3 else None,
        "disagreements": disagreements,
    }
    if labels:
        y, s_a, s_b = [], [], []
        for k in shared:
            lab = labels.get(k)
            xa, xb = score(a[k]), score(b[k])
            if lab is None or xa is None or xb is None:
                continue
            y.append(1 if lab != "Absent" else 0)
            s_a.append(xa)
            s_b.append(xb)
        if y:
            out["ap_a"] = average_precision(y, s_a)
            out["ap_b"] = average_precision(y, s_b)
    return out


def print_cmp(name_a, name_b, stats):
    print(f"{name_a} vs {name_b}")
    print(f"  n={stats['n']}  exact={stats['exact']}/{stats['n']}"
          f" ({stats['exact_frac']:.3f})  "
          f"within_one={stats['within_one']}/{stats['n']}"
          f" ({stats['within_one_frac']:.3f})"
          + (f"  spearman={stats['spearman']:.3f}"
             if stats["spearman"] is not None else ""))
    if "ap_a" in stats:
        print(f"  AP {name_a}={stats['ap_a']:.3f}  {name_b}={stats['ap_b']:.3f}")
    for gene, pheno, va, vb in stats["disagreements"][:12]:
        print(f"  {gene}\t{pheno}\t{va}\t{vb}")
    extra = len(stats["disagreements"]) - 12
    if extra > 0:
        print(f"  ... {extra} more")


def load_labels(path):
    out = {}
    for row in read_tsv(path):
        if "label" in row:
            out[key(row)] = row["label"]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", nargs="?")
    ap.add_argument("b", nargs="?")
    ap.add_argument("--labels", metavar="TSV")
    ap.add_argument("--fast-vs-published", metavar="TSV",
                    help="compare a new abstracts-fast pesto.tsv to "
                         "reproducibility_aou50/run1/pesto.tsv")
    args = ap.parse_args()
    labels = load_labels(args.labels) if args.labels else None
    if args.fast_vs_published:
        published = os.path.join(AOU, "run1", "pesto.tsv")
        stats = compare(published, args.fast_vs_published, labels)
        print_cmp("aou50-run1", args.fast_vs_published, stats)
        return 0
    if args.a and args.b:
        stats = compare(args.a, args.b, labels)
        print_cmp(args.a, args.b, stats)
        return 0
    runs = [os.path.join(AOU, f"run{i}", "pesto.tsv") for i in (1, 2, 3)]
    for i, a in enumerate(runs):
        for b in runs[i + 1:]:
            print_cmp(os.path.relpath(a, ROOT), os.path.relpath(b, ROOT),
                      compare(a, b, labels))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
