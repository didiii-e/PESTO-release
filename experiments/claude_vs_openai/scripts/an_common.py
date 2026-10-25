import csv, gzip, json, math, os, re, sys
import numpy as np

ROOT = "/Users/dinan_elsyad/pesto_cmp"
CATS = ["Novel", "Hypothesized", "Existing", "Established"]
W = {c: i + 1 for i, c in enumerate(CATS)}
FAMS = ("claude", "openai")


def pairs_meta():
    rows = list(csv.DictReader(open(f"{ROOT}/pairs.tsv"), delimiter="\t"))
    return {(r["gene"], r["phenotype"]): r for r in rows}


def load(rep, fam):
    path = f"{ROOT}/runs/{rep}/pairs_{rep}_{fam}.jsonl.gz"
    out = {}
    if not os.path.exists(path):
        return out
    for l in gzip.open(path, "rt"):
        r = json.loads(l)
        out[(r["gene"], r["phenotype"])] = r        # a later (resumed) record wins
    return out


def load_calls(rep, fam):
    path = f"{ROOT}/runs/{rep}/calls_{rep}_{fam}.jsonl.gz"
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in gzip.open(path, "rt")]


def dist_of(r):
    row = r["row"]
    try:
        v = [float(row[k]) for k in ("p_novel", "p_hypothesized", "p_existing", "p_established")]
    except (KeyError, ValueError, TypeError):
        return None
    s = sum(v)
    return np.array(v) / s if s else None


def egrade(p):
    return float(np.dot(p, [1, 2, 3, 4])) if p is not None else float("nan")


def entropy(p):
    if p is None:
        return float("nan")
    q = p[p > 0]
    return float(-(q * np.log2(q)).sum())


def rank(c):
    return W.get(c)


def final_max(lit, ot):
    a, b = rank(lit), rank(ot)
    cands = [x for x in (a, b) if x]
    return CATS[max(cands) - 1] if cands else ""


def jacc(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if (a | b) else float("nan")


def ok(r):
    return r is not None and r["error"] is None and r["row"].get("lit_mean")


def pmids_pool(r):
    return [a["pmid"] for a in (r["pool"] or [])]


def pmids_read(r):
    return [a["pmid"] for a in (r["res"]["read"] if r["res"] else [])]


def mdtable(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def pct(x, n):
    return f"{x}/{n} ({100 * x / n:.0f}%)" if n else "-"


def confusion(a, b, labels=CATS):
    m = np.zeros((4, 4), dtype=int)
    for x, y in zip(a, b):
        if x in W and y in W:
            m[W[x] - 1, W[y] - 1] += 1
    return m


def cm_table(m, rowname, colname):
    hdr = [f"{rowname} \\ {colname}"] + CATS + ["n"]
    rows = [[CATS[i]] + list(m[i]) + [int(m[i].sum())] for i in range(4)]
    return mdtable(hdr, rows)


def quant(x, qs=(50, 90)):
    x = [v for v in x if v == v]
    if not x:
        return "-"
    return " / ".join(f"{np.percentile(x, q):.2f}" for q in qs)
