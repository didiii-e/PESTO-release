"""Frozen-input analysis: sieve (Haiku vs Luna on the identical pool) and readers (Opus vs Sol on identical packets)."""
import json, sys, itertools
from collections import Counter, defaultdict
import numpy as np
from scipy import stats
from sklearn.metrics import cohen_kappa_score

sys.path.insert(0, "/Users/dinan_elsyad/pesto_cmp")
from an_common import *                                        # noqa: E402

META = pairs_meta()
C, O = load("r1", "claude"), load("r1", "openai")
rd = lambda p: [json.loads(l) for l in open(p)] if os.path.exists(p) else []
SV = rd(f"{ROOT}/frozen_sieve.jsonl")
RD = rd(f"{ROOT}/frozen_readers.jsonl")
lunas = {(r["gene"], r["phenotype"]): r for r in SV if r["stage"] == "sieve" and not r["error"]}
KEYS = [k for k in lunas if ok(C.get(k))]
print(f"# Frozen-input comparisons: {len(KEYS)} pairs with a candidate pool\n")

# ------------------------------------------------------------------ sieve
print("## A. Sieve on the identical pool (same articles, synonyms, batches, prompt)\n")
H = {k: {p: v[0] for p, v in C[k]["res"]["bands"].items()} for k in KEYS}
L = {k: {p: int(v) for p, v in lunas[k]["bands"].items()} for k in KEYS}
pairs_ = []
for k in KEYS:
    for p in C[k]["pool"]:
        pm = p["pmid"]
        pairs_.append((k, pm, H[k].get(pm, 2), L[k].get(pm, 2), pm in H[k], pm in L[k]))
missing = Counter(("H" if not a else "") + ("L" if not b else "") for *_, a, b in pairs_)
print(f"{len(pairs_)} articles; articles left unbanded by Haiku/Luna (defaulted to 2, as production does): {dict(missing)}\n")
h = np.array([x[2] for x in pairs_]); l = np.array([x[3] for x in pairs_])
m = np.zeros((4, 4), int)
for a, b in zip(h, l):
    m[a - 1, b - 1] += 1
print(mdtable(["Haiku \\ Luna (band)", "1 none", "2 nonhuman", "3 weak", "4 strong", "n"],
              [[f"{i + 1} {['none', 'nonhuman', 'weak', 'strong'][i]}"] + list(m[i]) + [int(m[i].sum())] for i in range(4)]), "\n")
rows = []
for name, f in (("pass (band >= 2)", lambda x: x >= 2), ("human (band >= 3)", lambda x: x >= 3), ("strong (band 4)", lambda x: x == 4)):
    a, b = f(h), f(l)
    rows.append([name, f"{a.mean():.1%}", f"{b.mean():.1%}", f"{(a == b).mean():.1%}", f"{cohen_kappa_score(a, b):.2f}",
                 int((a & ~b).sum()), int((~a & b).sum())])
print(mdtable(["criterion", "Haiku rate", "Luna rate", "agreement", "kappa", "Haiku-only", "Luna-only"], rows), "\n")
print(f"exact band agreement {np.mean(h == l):.1%}; within one band {np.mean(abs(h - l) <= 1):.1%}; "
      f"weighted kappa {cohen_kappa_score(h, l, weights='quadratic'):.2f}\n")

ja, sizes = [], []
for k in KEYS:
    live = [a["pmid"] for a in C[k]["res"]["read"]]
    ja.append(jacc(live, lunas[k]["selected"]))
    sizes.append((len(live), len(lunas[k]["selected"])))
print(f"packet handed to the reader: Jaccard Haiku-vs-Luna selection mean {np.mean(ja):.2f}, median {np.median(ja):.2f}; "
      f"identical in {sum(j == 1 for j in ja)}/{len(ja)}; mean size {np.mean([s[0] for s in sizes]):.1f} vs {np.mean([s[1] for s in sizes]):.1f}\n")

# stab sieve noise
ss = [r for r in SV if r["stage"] == "stab_sieve" and not r["error"]]
if ss:
    print("### Sieve draw-to-draw stability (same pool; 12 stability pairs; Haiku draw 1 = the live run)\n")
    stab = sorted({(r["gene"], r["phenotype"]) for r in ss})
    rows = []
    for model, label in (("haiku", "Haiku"), ("openai:gpt-6-luna", "Luna")):
        draws = {}
        for k in stab:
            ds = {2: next((r for r in ss if (r["gene"], r["phenotype"]) == k and r["model"] == model and r["rep"] == 2), None),
                  3: next((r for r in ss if (r["gene"], r["phenotype"]) == k and r["model"] == model and r["rep"] == 3), None)}
            first = H[k] if model == "haiku" else L[k]
            draws[k] = [first] + [{p: int(v) for p, v in d["bands"].items()} for d in ds.values() if d]
        ex, pa, hk, kp = [], [], [], []
        for k, dr in draws.items():
            pool = [a["pmid"] for a in C[k]["pool"]]
            for x, y in itertools.combinations(dr, 2):
                bx = np.array([x.get(p, 2) for p in pool]); by = np.array([y.get(p, 2) for p in pool])
                ex.append(np.mean(bx == by)); pa.append(np.mean((bx >= 2) == (by >= 2)))
                if len(set(bx >= 2)) > 1 or len(set(by >= 2)) > 1:
                    kp.append(cohen_kappa_score(bx >= 2, by >= 2))
        rows.append([label, len(ex), f"{np.mean(ex):.1%}", f"{np.mean(pa):.1%}", f"{np.mean(kp):.2f}"])
    print(mdtable(["sieve", "draw pairs", "exact band agreement", "pass/reject agreement", "mean kappa(pass)"], rows), "\n")

# ------------------------------------------------------------------ readers
print("## B. Readers on identical packets\n")
R = {(r["gene"], r["phenotype"], r["packet"], r["model"], r["rep"]): r for r in RD if not r["error"] and r["stage"] == "readers"}


def cell(k, who):
    """The reader's answer for pair k: who in OpusH (the live Claude read), SolH, OpusL, SolL, ClaudeE2E, OpenAIE2E."""
    g, p = k
    if who == "OpusH":
        r = C[k]["res"]["verdict"]; return r["dist"], r["call"]
    if who == "OpenAI":
        r = O[k]["res"]["verdict"]; return r["dist"], r["call"]
    same = set(lunas[k]["selected"]) == {a["pmid"] for a in C[k]["res"]["read"]}
    packet = "H" if (who == "SolH" or same) else "L"
    model = "openai:gpt-6.1-sol" if who.startswith("Sol") else "opus5"
    if who == "OpusL" and same:
        return cell(k, "OpusH")
    row = R.get((g, p, packet, model, 1))
    return (row["dist"], row["argmax"]) if row else (None, None)


def mc(d):
    return cli_mean(d) if d else None


def cli_mean(dist):
    tot = sum(dist.values()) or 1
    r = sum(W[c] * v for c, v in dist.items()) / tot
    return CATS[max(1, min(4, round(r))) - 1]


def vec(d):
    return np.array([d[c] for c in CATS]) / (sum(d.values()) or 1) if d else None


def compare(a_who, b_who, label, keys=None):
    keys = keys or KEYS
    xs, ys = [], []
    for k in keys:
        da, _ = cell(k, a_who); db, _ = cell(k, b_who)
        if da and db:
            xs.append((mc(da), vec(da))); ys.append((mc(db), vec(db)))
    if not xs:
        return [label, 0, "-", "-", "-", "-", "-", "-"]
    ca = [x[0] for x in xs]; cb = [y[0] for y in ys]
    ea = np.array([egrade(x[1]) for x in xs]); eb = np.array([egrade(y[1]) for y in ys])
    ex = sum(a == b for a, b in zip(ca, cb)); w1 = sum(abs(W[a] - W[b]) <= 1 for a, b in zip(ca, cb))
    k_ = cohen_kappa_score([W[a] for a in ca], [W[b] for b in cb], weights="quadratic")
    return [label, len(xs), pct(ex, len(xs)), pct(w1, len(xs)), f"{k_:.2f}", f"{stats.spearmanr(ea, eb)[0]:.3f}",
            f"{stats.pearsonr(ea, eb)[0]:.3f}", f"{(eb - ea).mean():+.2f}"]


hdr = ["comparison (A vs B)", "n", "exact (mean call)", "within 1", "quad. kappa", "Spearman E", "Pearson E", "mean E B-A"]
rows = [
    compare("OpusH", "SolH", "READER only: Opus vs Sol on the Haiku packet"),
    compare("OpusL", "SolL", "READER only: Opus vs Sol on the Luna packet"),
    compare("OpusH", "OpusL", "SIEVE only (Opus reading): Haiku packet vs Luna packet"),
    compare("SolH", "SolL", "SIEVE only (Sol reading): Haiku packet vs Luna packet"),
    compare("OpusH", "SolL", "READER+SIEVE: Opus on Haiku packet vs Sol on Luna packet (same pool)"),
    compare("OpusH", "OpenAI", "FULL PIPELINE: Claude e2e vs OpenAI e2e (own retrieval)"),
]
print(mdtable(hdr, rows), "\n")
print("(For the 3 pairs where both sieves choose the same packet the Luna-packet answer is the Haiku-packet answer.)\n")

print("### Frozen readers' sharpness (same packets)\n")
rows = []
for who, label in (("OpusH", "Opus, Haiku packet (live Claude read)"), ("SolH", "Sol, Haiku packet"), ("SolL", "Sol, Luna packet"), ("OpusL", "Opus, Luna packet")):
    vs = [vec(cell(k, who)[0]) for k in KEYS if cell(k, who)[0]]
    ent = [entropy(v) for v in vs]; top = [v.max() for v in vs]
    rows.append([label, len(vs), f"{np.mean(ent):.2f}", f"{np.mean(top):.2f}", pct(sum(t >= .999 for t in top), len(vs))])
print(mdtable(["reader / packet", "n", "mean entropy", "mean top-p", "exactly one-hot"], rows), "\n")

print("### Confusion on the Haiku packet (rows Opus, cols Sol)\n")
a = [mc(cell(k, "OpusH")[0]) for k in KEYS if cell(k, "SolH")[0]]
b = [mc(cell(k, "SolH")[0]) for k in KEYS if cell(k, "SolH")[0]]
print(cm_table(confusion(a, b), "Opus", "Sol"), "\n")

print("### Frozen reader disagreements on the Haiku packet (mean call differs)\n")
rows = []
for k in KEYS:
    da, _ = cell(k, "OpusH"); db, _ = cell(k, "SolH")
    if da and db and mc(da) != mc(db):
        rows.append((abs(egrade(vec(db)) - egrade(vec(da))), [f"{k[0]} / {k[1][:30]}", META[k]["saved_cat"][:5] + ("*" if META[k]["borderline"] == "1" else ""),
                     f"{mc(da)} ({egrade(vec(da)):.2f})", f"{mc(db)} ({egrade(vec(db)):.2f})", len(C[k]["res"]["read"])]))
rows.sort(key=lambda t: -t[0])
print(mdtable(["pair", "saved", "Opus (E)", "Sol (E)", "packet n"], [r for _, r in rows]), "\n")

# stab readers
sr = [r for r in RD if r["stage"] == "stab_readers" and not r["error"]]
if sr:
    print("### Reader draw-to-draw stability (same packet; 12 stability pairs)\n")
    rows = []
    for model, label in (("opus5", "Opus"), ("openai:gpt-6.1-sol", "Sol")):
        agree = []; sds = []
        for k in sorted({(r["gene"], r["phenotype"]) for r in sr}):
            draws = [r for r in sr if (r["gene"], r["phenotype"]) == k and r["model"] == model]
            first = cell(k, "OpusH" if model == "opus5" else "SolH")[0]
            ds = ([first] if first else []) + [r["dist"] for r in draws]
            for x, y in itertools.combinations(ds, 2):
                agree.append(mc(x) == mc(y))
            sds.append(np.std([egrade(vec(d)) for d in ds]))
        rows.append([label, len(agree), pct(sum(agree), len(agree)), f"{np.mean(sds):.2f}"])
    print(mdtable(["reader", "draw pairs", "same mean call", "mean sd of E[grade]"], rows), "\n")

tot = sum(r["usd"] for r in SV + RD)
print(f"frozen-stage spend: ${tot:.2f} (sieve ${sum(r['usd'] for r in SV):.2f}, readers ${sum(r['usd'] for r in RD):.2f})")
