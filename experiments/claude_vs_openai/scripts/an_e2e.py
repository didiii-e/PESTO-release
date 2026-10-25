"""End-to-end analysis: Claude vs OpenAI, r1 (60 pairs) and the 12-pair stability subset."""
import sys
from collections import Counter, defaultdict
import numpy as np
from scipy import stats
from sklearn.metrics import cohen_kappa_score

sys.path.insert(0, "/Users/dinan_elsyad/pesto_cmp")
from an_common import *                                        # noqa: E402

META = pairs_meta()
C, O = load("r1", "claude"), load("r1", "openai")
KEYS = [k for k in META if ok(C.get(k)) and ok(O.get(k))]
print(f"# End-to-end, r1: {len(KEYS)} of {len(META)} pairs complete in both families\n")
bad = [(f, k) for f, d in (("claude", C), ("openai", O)) for k, r in d.items() if not ok(r)]
print("pairs with errors:", [(f, k[0], k[1][:30], d[k]["error"]) for f, k in bad for d in [C if f == "claude" else O]], "\n")


def col(d, f):
    return [f(d[k]) for k in KEYS]


lit = {"claude": col(C, lambda r: r["row"]["lit_mean"]), "openai": col(O, lambda r: r["row"]["lit_mean"])}
arg = {"claude": col(C, lambda r: r["row"]["lit_argmax"]), "openai": col(O, lambda r: r["row"]["lit_argmax"])}
ot = {"claude": col(C, lambda r: r["row"]["open_targets_verdict"]), "openai": col(O, lambda r: r["row"]["open_targets_verdict"])}
fmax = {f: [final_max(a, b) for a, b in zip(lit[f], ot[f])] for f in FAMS}
P = {"claude": [dist_of(C[k]) for k in KEYS], "openai": [dist_of(O[k]) for k in KEYS]}
E = {f: np.array([egrade(p) for p in P[f]]) for f in FAMS}
n = len(KEYS)


def agree(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if x in W and y in W]
    ex = sum(x == y for x, y in pairs)
    w1 = sum(abs(W[x] - W[y]) <= 1 for x, y in pairs)
    return ex, w1, len(pairs)


def kap(a, b):
    pairs = [(W[x], W[y]) for x, y in zip(a, b) if x in W and y in W]
    if not pairs:
        return float("nan"), float("nan")
    x, y = zip(*pairs)
    return cohen_kappa_score(x, y), cohen_kappa_score(x, y, weights="quadratic")


print("## 1. Category agreement (Claude vs OpenAI)\n")
rows = []
for name, a, b in (("literature, mean call (headline)", lit["claude"], lit["openai"]),
                   ("literature, argmax", arg["claude"], arg["openai"]),
                   ("Open Targets verdict", ot["claude"], ot["openai"]),
                   ("final Max(lit mean, OT)", fmax["claude"], fmax["openai"])):
    ex, w1, m = agree(a, b)
    k, kw = kap(a, b)
    rows.append([name, pct(ex, m), pct(w1, m), f"{k:.2f}", f"{kw:.2f}"])
print(mdtable(["measure", "exact", "within 1", "kappa", "quad. kappa"], rows), "\n")

print("### Confusion, literature mean call (rows Claude, cols OpenAI)\n")
print(cm_table(confusion(lit["claude"], lit["openai"]), "Claude", "OpenAI"), "\n")
print("### Confusion, final Max (rows Claude, cols OpenAI)\n")
print(cm_table(confusion(fmax["claude"], fmax["openai"]), "Claude", "OpenAI"), "\n")
print("### Confusion, Open Targets verdict (rows Claude, cols OpenAI)\n")
print(cm_table(confusion(ot["claude"], ot["openai"]), "Claude", "OpenAI"), "\n")

direction = Counter()
for x, y in zip(lit["claude"], lit["openai"]):
    if x in W and y in W and x != y:
        direction["OpenAI higher" if W[y] > W[x] else "OpenAI lower"] += 1
print("Direction of the literature mean-call disagreements:", dict(direction), "\n")

print("### Agreement by stratum (literature mean call)\n")
strata = defaultdict(list)
for i, k in enumerate(KEYS):
    m = META[k]
    strata["saved " + m["saved_cat"]].append(i)
    strata["borderline" if m["borderline"] == "1" else "non-borderline"].append(i)
    strata["trait pair" if m["trait"] == "1" else "disease pair"].append(i)
rows = []
for s, idx in sorted(strata.items()):
    a = [lit["claude"][i] for i in idx]
    b = [lit["openai"][i] for i in idx]
    ex, w1, m = agree(a, b)
    d = np.nanmean(E["openai"][idx] - E["claude"][idx])
    rows.append([s, m, pct(ex, m), pct(w1, m), f"{d:+.2f}"])
print(mdtable(["stratum", "n", "exact", "within 1", "mean E[grade] OpenAI-Claude"], rows), "\n")

print("## 2. Continuous E[grade] (sum(grade*p), grades 1..4)\n")
m = ~np.isnan(E["claude"]) & ~np.isnan(E["openai"])
sp = stats.spearmanr(E["claude"][m], E["openai"][m])
pr = stats.pearsonr(E["claude"][m], E["openai"][m])
d = E["openai"][m] - E["claude"][m]
print(f"Spearman {sp[0]:.3f} (p={sp[1]:.1e}), Pearson {pr[0]:.3f}; mean diff OpenAI-Claude {d.mean():+.3f}, "
      f"mean |diff| {np.abs(d).mean():.3f}, within 0.5 of each other {int((np.abs(d) <= .5).sum())}/{int(m.sum())}, "
      f">1.0 apart {int((np.abs(d) > 1).sum())}\n")

print("## 3. Probability sharpness\n")
rows = []
for f in FAMS:
    ps = [p for p in P[f] if p is not None]
    ent = np.array([entropy(p) for p in ps])
    top = np.array([p.max() for p in ps])
    onehot = sum(p.max() >= .999 for p in ps)
    ge90 = sum(p.max() >= .9 for p in ps)
    rows.append([f, f"{ent.mean():.2f}", f"{np.median(ent):.2f}", f"{top.mean():.2f}", f"{np.median(top):.2f}",
                 pct(onehot, len(ps)), pct(ge90, len(ps))])
print(mdtable(["family", "mean entropy (bits)", "median", "mean top-p", "median", "exactly one-hot", "top-p >= 0.9"], rows), "\n")

print("## 4. Router (identical phenotype string, two routers)\n")
ra = {f: col(d, lambda r: r["router_arm"]) for f, d in (("claude", C), ("openai", O))}
same = sum(x == y for x, y in zip(ra["claude"], ra["openai"]))
print(f"arm agreement {pct(same, n)}")
truth = [("abstracts-trait" if META[k]["trait"] == "1" else "abstracts") for k in KEYS]
for f in FAMS:
    right = sum(x == t for x, t in zip(ra[f], truth))
    print(f"- {f} router vs the pair-table trait flag: {pct(right, n)}")
dis = [(k, a, b) for k, a, b in zip(KEYS, ra["claude"], ra["openai"]) if a != b]
for k, a, b in dis:
    print(f"  - router disagreement: {k[0]} / {k[1]}: Claude -> {a}, OpenAI -> {b} (table trait flag {META[k]['trait']})")
print()

print("## 5. Retrieval: is a disagreement the model or the retrieval?\n")
rows = []
jp, jr, js, nfo = [], [], [], []
for k in KEYS:
    pc, po = pmids_pool(C[k]), pmids_pool(O[k])
    rc, ro = pmids_read(C[k]), pmids_read(O[k])
    syc = (C[k]["res"]["terms"].get("synonyms") or []) if C[k]["res"] else []
    syo = (O[k]["res"]["terms"].get("synonyms") or []) if O[k]["res"] else []
    jp.append(jacc(pc, po)); jr.append(jacc(rc, ro))
    js.append(jacc([s.lower() for s in syc], [s.lower() for s in syo]))
    nfo.append((len(pc), len(po), len(syc), len(syo)))
nfo = np.array(nfo)
print(f"candidate-pool Jaccard (PMIDs): mean {np.nanmean(jp):.2f}, median {np.nanmedian(jp):.2f}; "
      f"read-set Jaccard: mean {np.nanmean(jr):.2f}, median {np.nanmedian(jr):.2f}; synonym-list Jaccard: mean {np.nanmean(js):.2f}")
print(f"pool size Claude/OpenAI mean {nfo[:, 0].mean():.0f}/{nfo[:, 1].mean():.0f}; synonyms per pair {nfo[:, 2].mean():.1f}/{nfo[:, 3].mean():.1f} "
      f"(note: Claude expands with Opus, OpenAI with Luna, because --model-fast covers that step)\n")
print("### Does the call depend on how much the read sets overlap? (literature mean call)\n")
rows = []
for lo, hi, name in ((0, .34, "read-set Jaccard < 0.34"), (.34, .67, "0.34 - 0.67"), (.67, 1.01, ">= 0.67")):
    idx = [i for i, j in enumerate(jr) if lo <= j < hi]
    a = [lit["claude"][i] for i in idx]; b = [lit["openai"][i] for i in idx]
    ex, w1, m_ = agree(a, b)
    de = np.nanmean(np.abs(E["openai"][idx] - E["claude"][idx])) if idx else float("nan")
    rows.append([name, len(idx), pct(ex, m_), pct(w1, m_), f"{de:.2f}"])
print(mdtable(["stratum", "n", "exact", "within 1", "mean |dE[grade]|"], rows), "\n")
r_ = stats.spearmanr(jr, np.abs(E["openai"] - E["claude"]), nan_policy="omit")
print(f"Spearman(read-set Jaccard, |dE[grade]|) = {r_[0]:.2f} (p={r_[1]:.2g})\n")

print("## 6. Sieve inside the live runs (own pools)\n")
rows = []
for f, d in (("claude (Haiku)", C), ("openai (Luna)", O)):
    tot = pas = hum = s4 = rd = 0
    for k in KEYS:
        b = [v[0] for v in d[k]["res"]["bands"].values()]
        tot += len(b); pas += sum(x >= 2 for x in b); hum += sum(x >= 3 for x in b); s4 += sum(x == 4 for x in b)
        rd += len(d[k]["res"]["read"])
    rows.append([f, tot, pct(pas, tot), pct(hum, tot), pct(s4, tot), f"{rd / len(KEYS):.1f}"])
print(mdtable(["sieve", "articles", "pass (>=2)", "human (>=3)", "strong (4)", "mean read per pair"], rows), "\n")
both = x_ = 0
agree_pass = tot = 0
ca = []; cb = []
for k in KEYS:
    bc = {p: v[0] for p, v in C[k]["res"]["bands"].items()}
    bo = {p: v[0] for p, v in O[k]["res"]["bands"].items()}
    for p in set(bc) & set(bo):
        ca.append(bc[p] >= 2); cb.append(bo[p] >= 2)
if ca:
    print(f"on PMIDs that both retrieved ({len(ca)} article-pairs): pass/reject agreement {np.mean(np.array(ca) == np.array(cb)):.1%}, "
          f"kappa {cohen_kappa_score(ca, cb):.2f}\n")

print("## 7. Cost, latency, reliability (per pair, end to end)\n")
rows = []
for f, d in (("claude", C), ("openai", O)):
    usd = np.array([d[k]["usd"] for k in KEYS]); wall = np.array([d[k]["wall_secs"] for k in KEYS])
    calls = [d[k]["calls"] for k in KEYS]
    attempts = sum(sum(1 for l in d[k]["log"] if "attempt " in l and l.startswith("INFO:")) for k in KEYS)
    retries = sum(sum(1 for l in d[k]["log"] if "Retrying" in l) for k in KEYS)
    refus = sum(sum(1 for l in d[k]["log"] if "refused" in l) for k in KEYS)
    nonend = sum(sum(1 for c in cs if c.get("stop_reason") not in ("end_turn", "stop", None) or c.get("error")) for cs in calls)
    reasoning = sum(c.get("reasoning_tokens") or 0 for cs in calls for c in cs)
    outtok = sum(c.get("output_tokens") or 0 for cs in calls for c in cs)
    rows.append([f, f"${usd.sum():.2f}", f"${usd.mean():.3f}", f"${np.median(usd):.3f}", f"{np.mean(wall):.0f}s", f"{np.median(wall):.0f}s",
                 f"{np.percentile(wall, 90):.0f}s", sum(len(cs) for cs in calls), attempts, retries, refus, nonend,
                 f"{reasoning}/{outtok}"])
print(mdtable(["family", "total", "mean/pair", "median", "mean wall", "median wall", "p90 wall", "calls", "API attempts",
               "retries", "refusals", "non-end_turn / errored calls", "reasoning/output tokens"], rows), "\n")
uc = sum(d_["usd"] for d_ in C.values()); uo = sum(d_["usd"] for d_ in O.values())
print(f"cost ratio Claude/OpenAI (all recorded pairs) = {uc / uo:.1f}x; "
      f"mean wall ratio Claude/OpenAI = {np.mean([C[k]['wall_secs'] for k in KEYS]) / np.mean([O[k]['wall_secs'] for k in KEYS]):.2f}\n")

print("### Where the cost and the time go (mean per pair)\n")
agg = {f: defaultdict(lambda: [0.0, 0.0]) for f in FAMS}
for f, d in (("claude", C), ("openai", O)):
    for k in KEYS:
        for s in d[k]["res"]["trace"]:
            step = {"Synonyms": "expand", "Broadened": "expand", "Bands": "sieve", "ProbabilityRead": "read"}.get(s["block"])
            if step:
                agg[f][step][0] += (s["usd"] or 0) if isinstance(s["usd"], (int, float)) else 0
                agg[f][step][1] += s["seconds"] or 0
        agg[f]["router"][0] += sum(float(r.get("usd") or 0) for r in d[k]["cost_rows"] if r.get("step") == "router")
        agg[f]["router"][1] += d[k]["router_secs"] or 0
        tr_usd = sum((s["usd"] or 0) for s in d[k]["res"]["trace"] if isinstance(s["usd"], (int, float)))
        ot_usd = d[k]["usd"] - tr_usd - sum(float(r.get("usd") or 0) for r in d[k]["cost_rows"] if r.get("step") == "router")
        agg[f]["open targets"][0] += max(ot_usd, 0)
        agg[f]["open targets"][1] += max(d[k]["assess_secs"] - sum(s["seconds"] or 0 for s in d[k]["res"]["trace"]), 0)
rows = []
for step in ("router", "expand", "sieve", "read", "open targets"):
    rows.append([step] + [f"${agg[f][step][0] / n:.4f} / {agg[f][step][1] / n:.1f}s" for f in FAMS])
print(mdtable(["step", "claude $ / s", "openai $ / s"], rows), "\n")

# ---------------------------------------------------------------- disagreements
print("## 8. Disagreement list (literature mean call differs, or final Max differs)\n")
rows = []
for i, k in enumerate(KEYS):
    a, b = lit["claude"][i], lit["openai"][i]
    if a != b or fmax["claude"][i] != fmax["openai"][i]:
        pc, po = P["claude"][i], P["openai"][i]
        rows.append((abs(E["openai"][i] - E["claude"][i]), [
            f"{k[0]} / {k[1][:34]}", META[k]["saved_cat"][:5] + ("*" if META[k]["borderline"] == "1" else ""),
            f"{a} ({'/'.join(f'{int(round(100 * x))}' for x in pc[::-1])})", f"{b} ({'/'.join(f'{int(round(100 * x))}' for x in po[::-1])})",
            f"{E['openai'][i] - E['claude'][i]:+.2f}", f"{jacc(pmids_pool(C[k]), pmids_pool(O[k])):.2f}",
            f"{jacc(pmids_read(C[k]), pmids_read(O[k])):.2f}", f"{ot['claude'][i][:5]}/{ot['openai'][i][:5]}",
            f"{fmax['claude'][i][:5]}/{fmax['openai'][i][:5]}"]))
rows.sort(key=lambda t: -t[0])
print(mdtable(["pair", "saved", "Claude lit (E/Ex/H/N)", "OpenAI lit", "dE", "pool J", "read J", "OT C/O", "Max C/O"], [r for _, r in rows]), "\n")
print("(* = borderline pair)\n")

# ---------------------------------------------------------------- stability
SK = [k for k in META if os.path.exists(f"{ROOT}/stab_pairs.tsv")]
import csv as _csv
stab = [(r["gene"], r["phenotype"]) for r in _csv.DictReader(open(f"{ROOT}/stab_pairs.tsv"), delimiter="\t")]
R = {f: {rep: load(rep, f) for rep in ("r1", "r2", "r3")} for f in FAMS}
full = [k for k in stab if all(ok(R[f][rep].get(k)) for f in FAMS for rep in ("r1", "r2", "r3"))]
if full:
    print(f"## 9. Stability: {len(full)} pairs x 3 end-to-end runs per family\n")
    rows = []
    for f in FAMS:
        all3 = sum(len({R[f][r][k]["row"]["lit_mean"] for r in ("r1", "r2", "r3")}) == 1 for k in full)
        pw = [R[f][a][k]["row"]["lit_mean"] == R[f][b][k]["row"]["lit_mean"] for k in full for a, b in (("r1", "r2"), ("r1", "r3"), ("r2", "r3"))]
        sd = np.mean([np.std([egrade(dist_of(R[f][r][k])) for r in ("r1", "r2", "r3")]) for k in full])
        rj = np.nanmean([jacc(pmids_read(R[f][a][k]), pmids_read(R[f][b][k])) for k in full for a, b in (("r1", "r2"), ("r1", "r3"), ("r2", "r3"))])
        pj = np.nanmean([jacc(pmids_pool(R[f][a][k]), pmids_pool(R[f][b][k])) for k in full for a, b in (("r1", "r2"), ("r1", "r3"), ("r2", "r3"))])
        ra_ = [len({R[f][r][k]["router_arm"] for r in ("r1", "r2", "r3")}) == 1 for k in full]
        otc = sum(len({R[f][r][k]["row"]["open_targets_verdict"] for r in ("r1", "r2", "r3")}) == 1 for k in full)
        rows.append([f, pct(all3, len(full)), pct(sum(pw), len(pw)), f"{sd:.2f}", f"{pj:.2f}", f"{rj:.2f}", pct(sum(ra_), len(full)), pct(otc, len(full))])
    cross = [R["claude"][r][k]["row"]["lit_mean"] == R["openai"][r][k]["row"]["lit_mean"] for k in full for r in ("r1", "r2", "r3")]
    print(mdtable(["family", "same call in all 3 runs", "pairwise run-to-run agreement", "mean sd of E[grade]", "pool J run-to-run",
                   "read-set J run-to-run", "router stable", "OT verdict stable"], rows), "\n")
    print(f"cross-family agreement in the same run index: {pct(sum(cross), len(cross))} "
          f"(compare with each family's run-to-run agreement above)\n")
    rows = []
    for k in full:
        row = [f"{k[0]} / {k[1][:30]}", META[k]["saved_cat"][:5] + ("*" if META[k]["borderline"] == "1" else "")]
        for f in FAMS:
            row.append(" ".join(R[f][r][k]["row"]["lit_mean"][:3] + f"({egrade(dist_of(R[f][r][k])):.1f})" for r in ("r1", "r2", "r3")))
        rows.append(row)
    print(mdtable(["pair", "saved", "Claude r1 r2 r3 (E[grade])", "OpenAI r1 r2 r3 (E[grade])"], rows), "\n")
    cost = {f: sum(R[f][r][k]["usd"] for k in full for r in ("r2", "r3")) for f in FAMS}
    print("stability spend (r2+r3):", {f: f"${v:.2f}" for f, v in cost.items()})
else:
    print("## 9. Stability: no pair has all 6 runs yet\n")
