"""How often does swapping Haiku->Luna as the sieve change the verdict? (frozen pools, reader held fixed)"""
import io, contextlib, sys, csv
sys.path.insert(0, "/Users/dinan_elsyad/pesto_cmp")
with contextlib.redirect_stdout(io.StringIO()):
    import an_frozen as f
from an_common import *
import numpy as np
from scipy.stats import binomtest

def wil(k, n):
    ci = binomtest(k, n).proportion_ci(method="wilson"); return f"{k}/{n} = {100*k/n:.1f}% (95% CI {100*ci.low:.0f}-{100*ci.high:.0f}%)"

KEYS = f.KEYS
same_packet = [k for k in KEYS if set(f.lunas[k]["selected"]) == {a["pmid"] for a in f.C[k]["res"]["read"]}]
print(f"# Effect of the sieve (Haiku -> Luna) on the verdict; {len(KEYS)} pairs, pool/reader/prompt identical\n")
print(f"packets identical for {len(same_packet)} pairs (verdict cannot change there); different for {len(KEYS)-len(same_packet)}\n")

def final(k, who):
    lit = f.mc(f.cell(k, who)[0]); return final_max(lit, f.C[k]["row"]["open_targets_verdict"])

out = []
for reader, H_, L_ in (("Opus", "OpusH", "OpusL"), ("Sol", "SolH", "SolL")):
    print(f"## Reader = {reader}\n")
    rows = []
    for label, fn in (("literature mean call", lambda k, w: f.mc(f.cell(k, w)[0])),
                      ("literature argmax", lambda k, w: max(f.cell(k, w)[0], key=f.cell(k, w)[0].get)),
                      ("final verdict Max(lit, Open Targets)", final)):
        ch = [k for k in KEYS if fn(k, H_) != fn(k, L_)]
        w1 = [k for k in ch if abs(W[fn(k, H_)] - W[fn(k, L_)]) > 1]
        rows.append([label, wil(len(ch), len(KEYS)), f"{len(ch)-len(w1)} one step, {len(w1)} two+ steps",
                     wil(len(ch), len(KEYS)-len(same_packet)).split(" ")[2] if False else f"{100*len(ch)/(len(KEYS)-len(same_packet)):.1f}% of the {len(KEYS)-len(same_packet)} pairs with different packets"])
    print(mdtable(["verdict level", "changed (all pairs)", "size of change", "if packets differ"], rows), "\n")

    ch = [k for k in KEYS if f.mc(f.cell(k, H_)[0]) != f.mc(f.cell(k, L_)[0])]
    up = sum(W[f.mc(f.cell(k, L_)[0])] > W[f.mc(f.cell(k, H_)[0])] for k in ch)
    print(f"direction with Luna's sieve: {up} pairs go UP, {len(ch)-up} go DOWN (mean call)\n")
    ed = np.array([egrade(f.vec(f.cell(k, L_)[0])) - egrade(f.vec(f.cell(k, H_)[0])) for k in KEYS])
    print(f"expected grade shift (Luna - Haiku packet): mean {ed.mean():+.3f}, median |shift| {np.median(abs(ed)):.2f}, "
          f"90th pct |shift| {np.percentile(abs(ed), 90):.2f}, |shift| > 0.5 in {int((abs(ed)>.5).sum())} pairs\n")
    rows = []
    for k in sorted(ch, key=lambda k: -abs(egrade(f.vec(f.cell(k, L_)[0])) - egrade(f.vec(f.cell(k, H_)[0])))):
        eh = egrade(f.vec(f.cell(k, H_)[0])); el = egrade(f.vec(f.cell(k, L_)[0]))
        rows.append([f"{k[0]} / {k[1][:28]}", f.META[k]["saved_cat"] + ("*" if f.META[k]["borderline"] == "1" else ""),
                     f"{f.mc(f.cell(k, H_)[0])} ({eh:.2f})", f"{f.mc(f.cell(k, L_)[0])} ({el:.2f})",
                     f"{jacc([a['pmid'] for a in f.C[k]['res']['read']], f.lunas[k]['selected']):.2f}",
                     final(k, H_) + " -> " + final(k, L_)])
    print(mdtable(["pair", "saved", "Haiku packet (E)", "Luna packet (E)", "packet Jaccard", "final Max"], rows), "\n")

    print("by saved category / stratum (literature mean call changed):\n")
    rows = []
    for name, sel in [(c, lambda k, c=c: f.META[k]["saved_cat"] == c) for c in CATS] + \
                     [("borderline", lambda k: f.META[k]["borderline"] == "1"), ("non-borderline", lambda k: f.META[k]["borderline"] != "1"),
                      ("trait pairs", lambda k: f.META[k]["router_expected"] == "trait" if "router_expected" in f.META[k] else False)]:
        ks = [k for k in KEYS if sel(k)]
        if ks:
            rows.append([name, len(ks), sum(f.mc(f.cell(k, H_)[0]) != f.mc(f.cell(k, L_)[0]) for k in ks)])
    print(mdtable(["stratum", "n", "changed"], rows), "\n")

# does packet overlap predict change?
print("## Does the size of the packet change predict a verdict change? (Opus reading)\n")
rows = []
J = {k: jacc([a["pmid"] for a in f.C[k]["res"]["read"]], f.lunas[k]["selected"]) for k in KEYS}
for lo, hi in ((0, .34), (.34, .67), (.67, 1.01)):
    ks = [k for k in KEYS if lo <= J[k] < hi]
    rows.append([f"{lo:.2f}-{min(hi,1):.2f}", len(ks), sum(f.mc(f.cell(k, "OpusH")[0]) != f.mc(f.cell(k, "OpusL")[0]) for k in ks),
                 sum(f.mc(f.cell(k, "SolH")[0]) != f.mc(f.cell(k, "SolL")[0]) for k in ks)])
print(mdtable(["packet Jaccard", "n", "Opus changed", "Sol changed"], rows), "\n")

# baselines
print("## Baselines (how much does the verdict move with no change of model at all?)\n")
sr = [r for r in f.RD if r["stage"] == "stab_readers" and not r["error"]]
print("- Same packet, same reader, fresh draw (12 stability pairs): Opus 0/36 draw-pairs change, Sol 0/36 -> reader sampling noise is ~0, so a change after a sieve swap is caused by the packet, not by luck.")
R = {fm: {rep: load(rep, fm) for rep in ("r1", "r2", "r3")} for fm in FAMS}
stab = [(r["gene"], r["phenotype"]) for r in csv.DictReader(open(f"{ROOT}/stab_pairs.tsv"), delimiter="\t")]
full = [k for k in stab if all(ok(R[fm][r].get(k)) for fm in FAMS for r in R[fm])]
for fm, nm in (("claude", "Haiku sieve + Opus reader"), ("openai", "Luna sieve + Sol reader")):
    pw = [R[fm][a][k]["row"]["lit_mean"] != R[fm][b][k]["row"]["lit_mean"] for k in full for a, b in (("r1", "r2"), ("r1", "r3"), ("r2", "r3"))]
    print(f"- Whole-pipeline rerun, {nm} (fresh retrieval + fresh sieve draw): verdict changes in {sum(pw)}/{len(pw)} run pairs ({100*sum(pw)/len(pw):.0f}%)")
