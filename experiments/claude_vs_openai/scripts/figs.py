"""Simple figures: Claude vs OpenAI. Reads benchmark outputs only; changes nothing."""
import io, contextlib, sys, os, csv
sys.path.insert(0, "/Users/dinan_elsyad/pesto_cmp")
with contextlib.redirect_stdout(io.StringIO()):
    import an_frozen as f
from an_common import *
import numpy as np
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = f"{ROOT}/figs"; os.makedirs(OUT, exist_ok=True)
CL, OA = "#D97757", "#10A37F"          # Claude orange, OpenAI green
GREY = "#8a8a8a"
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.dpi": 130, "savefig.bbox": "tight", "axes.titleweight": "bold"})
C, O = f.C, f.O
K = [k for k in C if ok(C[k]) and ok(O.get(k))]
n = len(K)
save = lambda name: (plt.savefig(f"{OUT}/{name}.png"), plt.close())


def agree(a, b):
    ex = np.mean([x == y for x, y in zip(a, b)])
    w1 = np.mean([abs(W[x] - W[y]) <= 1 for x, y in zip(a, b)])
    return ex * 100, w1 * 100


# 1 ---- agreement by measure
lit_c = [C[k]["row"]["lit_mean"] for k in K]; lit_o = [O[k]["row"]["lit_mean"] for k in K]
ot_k = [k for k in K if C[k]["row"]["open_targets_verdict"] in W and O[k]["row"]["open_targets_verdict"] in W]
ot_c = [C[k]["row"]["open_targets_verdict"] for k in ot_k]; ot_o = [O[k]["row"]["open_targets_verdict"] for k in ot_k]
fin_c = [final_max(C[k]["row"]["lit_mean"], C[k]["row"]["open_targets_verdict"]) for k in K]
fin_o = [final_max(O[k]["row"]["lit_mean"], O[k]["row"]["open_targets_verdict"]) for k in K]
meas = [("Literature\n(mean call)", lit_c, lit_o), ("Open Targets", ot_c, ot_o), ("Final\n(Max of both)", fin_c, fin_o)]
fig, ax = plt.subplots(figsize=(6.5, 4))
x = np.arange(3); w = .36
ex = [agree(a, b)[0] for _, a, b in meas]; w1 = [agree(a, b)[1] for _, a, b in meas]
b1 = ax.bar(x - w / 2, ex, w, color=CL, label="exact same category")
b2 = ax.bar(x + w / 2, w1, w, color=GREY, label="within one category")
for bars in (b1, b2):
    for r in bars:
        ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 1, f"{r.get_height():.0f}%", ha="center", fontsize=10)
ax.set_xticks(x, [m[0] for m in meas]); ax.set_ylabel("% of pairs")
ax.set_ylim(0, 128); ax.set_title("How often Claude and OpenAI agree"); ax.legend(frameon=False, loc="upper center", ncol=2)
save("1_agreement")

# 2 ---- confusion heat map
fig, ax = plt.subplots(figsize=(5.2, 4.4))
m = confusion(lit_c, lit_o)
ax.imshow(m, cmap="Oranges", vmin=0, vmax=m.max() * 1.1)
for i in range(4):
    for j in range(4):
        ax.text(j, i, m[i, j], ha="center", va="center", color="white" if m[i, j] > m.max() * .55 else "black", fontsize=13)
ax.set_xticks(range(4), CATS, rotation=30, ha="right"); ax.set_yticks(range(4), CATS)
ax.set_xlabel("OpenAI call"); ax.set_ylabel("Claude call")
ax.set_title(f"Literature call, {n} pairs"); [s.set_visible(True) for s in ax.spines.values()]
save("2_confusion")

# 3 ---- E[grade] scatter
fig, ax = plt.subplots(figsize=(5.4, 5.2))
ec = np.array([egrade(dist_of(C[k])) for k in K]); eo = np.array([egrade(dist_of(O[k])) for k in K])
cols = {"Novel": "#4C78A8", "Hypothesized": "#F2A93B", "Existing": "#B279A2", "Established": "#54A24B"}
for cat in CATS:
    idx = [i for i, k in enumerate(K) if f.META[k]["saved_cat"] == cat]
    ax.scatter(ec[idx], eo[idx], s=38, color=cols[cat], alpha=.85, label=f"saved {cat}", edgecolor="white", linewidth=.5)
ax.plot([1, 4], [1, 4], color="black", lw=1, ls="--")
ax.set_xlim(.9, 4.1); ax.set_ylim(.9, 4.1); ax.set_aspect("equal")
ax.set_xlabel("Claude expected grade"); ax.set_ylabel("OpenAI expected grade")
rho = stats.spearmanr(ec, eo)[0]
ax.set_title(f"Expected grade (1 Novel ... 4 Established)\nSpearman {rho:.2f}"); ax.legend(frameon=False, fontsize=9, loc="upper left")
ax.set_xticks([1, 2, 3, 4]); ax.set_yticks([1, 2, 3, 4])
save("3_grade_scatter")

# 4 ---- sharpness
fig, ax = plt.subplots(figsize=(6, 4))
tc = [dist_of(C[k]).max() for k in K]; to = [dist_of(O[k]).max() for k in K]
bins = np.linspace(.3, 1, 15)
ax.hist(tc, bins, color=CL, alpha=.8, label="Claude")
ax.hist(to, bins, color=OA, alpha=.7, label="OpenAI")
ax.set_xlabel("probability given to the top category"); ax.set_ylabel("pairs")
ax.set_title("OpenAI commits; Claude hedges"); ax.legend(frameon=False, loc="upper left")
ax.text(.31, ax.get_ylim()[1] * .55, f"median top-p\nClaude {np.median(tc):.2f}\nOpenAI {np.median(to):.2f}", fontsize=10)
save("4_sharpness")

# 5 ---- cost and time by step (means per pair, from report_e2e.md section 7)
steps = ["router", "expand", "sieve", "read", "open targets", "other"]
cost = {"Claude": [.0024, .0081, .0282, .0543, .0351, .158 - .1281], "OpenAI": [.0004, .0001, .0031, .0124, .0078, .029 - .0238]}
secs = {"Claude": [1.3, 4.1, 2.9, 8.3, 18.4, 41 - 35], "OpenAI": [1.2, 2.7, 6.6, 4.6, 21.0, 42 - 36.1]}
pal = ["#C9C9C9", "#9DB8D6", "#E8B96A", "#D97757", "#6B8F71", "#EEEEEE"]
fig, axs = plt.subplots(1, 2, figsize=(9, 3.8))
for ax, d, ttl, unit in ((axs[0], cost, "Cost per pair", "$"), (axs[1], secs, "Time per pair", "seconds")):
    for yi, fam in enumerate(("Claude", "OpenAI")):
        left = 0
        for s, v, c in zip(steps, d[fam], pal):
            ax.barh(yi, v, left=left, color=c, label=s if yi == 0 else None, edgecolor="white")
            left += v
        ax.text(left * 1.02, yi, f"${left:.3f}" if unit == "$" else f"{left:.0f}s", va="center", fontsize=10)
    ax.set_yticks([0, 1], ["Claude", "OpenAI"]); ax.invert_yaxis(); ax.set_title(ttl); ax.set_xlabel(unit)
    ax.set_xlim(0, ax.get_xlim()[1] * 1.15)
h, l = axs[0].get_legend_handles_labels(); fig.legend(h, l, frameon=False, ncol=6, loc="lower center", bbox_to_anchor=(.5, -.08), fontsize=9)
fig.suptitle("5.4x cheaper, same speed", y=1.02, fontweight="bold")
save("5_cost_time")

# 6 ---- stability
stab = [(r["gene"], r["phenotype"]) for r in csv.DictReader(open(f"{ROOT}/stab_pairs.tsv"), delimiter="\t")]
R = {fm: {rep: load(rep, fm) for rep in ("r1", "r2", "r3")} for fm in FAMS}
full = [k for k in stab if all(ok(R[fm][r].get(k)) for fm in FAMS for r in ("r1", "r2", "r3"))]
vals = {}
for fm in FAMS:
    a3 = np.mean([len({R[fm][r][k]["row"]["lit_mean"] for r in R[fm]}) == 1 for k in full]) * 100
    pw = np.mean([R[fm][a][k]["row"]["lit_mean"] == R[fm][b][k]["row"]["lit_mean"]
                  for k in full for a, b in (("r1", "r2"), ("r1", "r3"), ("r2", "r3"))]) * 100
    vals[fm] = (a3, pw)
cross = np.mean([R["claude"][r][k]["row"]["lit_mean"] == R["openai"][r][k]["row"]["lit_mean"] for k in full for r in R["claude"]]) * 100
fig, ax = plt.subplots(figsize=(6.2, 4))
labels = ["Claude vs itself\n(run to run)", "OpenAI vs itself\n(run to run)", "Claude vs OpenAI\n(same run)"]
v = [vals["claude"][1], vals["openai"][1], cross]
bars = ax.bar(labels, v, color=[CL, OA, GREY], width=.55)
for r in bars:
    ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 1, f"{r.get_height():.0f}%", ha="center")
ax.set_ylim(0, 110); ax.set_ylabel("% same literature call")
ax.set_title(f"Run-to-run noise vs cross-family gap\n({len(full)} pairs x 3 runs)")
save("6_stability")

# 7 ---- where do differences come from (frozen decomposition)
rows = [("Reader only\n(Opus vs Sol, same packet)", "OpusH", "SolH"),
        ("Sieve only, Opus reading\n(Haiku vs Luna packet)", "OpusH", "OpusL"),
        ("Sieve only, Sol reading\n(Haiku vs Luna packet)", "SolH", "SolL"),
        ("Whole pipeline\n(own retrieval, sieve, reader)", "OpusH", "OpenAI")]
fig, ax = plt.subplots(figsize=(7, 3.8))
vals = []
for lab, a, b in rows:
    ks = [k for k in f.KEYS if f.cell(k, a)[0] and f.cell(k, b)[0]]
    vals.append(100 * np.mean([f.mc(f.cell(k, a)[0]) != f.mc(f.cell(k, b)[0]) for k in ks]))
bars = ax.barh([r[0] for r in rows], vals, color=[CL, GREY, GREY, "#444444"])
for r in bars:
    ax.text(r.get_width() + .4, r.get_y() + r.get_height() / 2, f"{r.get_width():.0f}%", va="center")
ax.invert_yaxis(); ax.set_xlim(0, max(vals) * 1.25); ax.set_xlabel("% of pairs where the call changes")
ax.set_title("Swapping any single component moves 12-19% of calls")
save("7_decomposition")

# 8 ---- sieve: Haiku vs Luna on the identical pool
H = np.array([x[2] for x in f.pairs_]); Lb = np.array([x[3] for x in f.pairs_])
fig, axs = plt.subplots(1, 2, figsize=(10, 3.8), gridspec_kw={"width_ratios": [1.2, 1]})
ax = axs[0]
names = ["none", "non-\nhuman", "weak\nhuman", "strong\nhuman"]
hc = [np.mean(H == i) * 100 for i in range(1, 5)]; lc = [np.mean(Lb == i) * 100 for i in range(1, 5)]
x = np.arange(4)
ax.bar(x - .2, hc, .4, color=CL, label="Haiku (Claude)"); ax.bar(x + .2, lc, .4, color=OA, label="Luna (OpenAI)")
ax.set_xticks(x, names); ax.set_ylabel("% of articles"); ax.legend(frameon=False)
ax.set_title(f"Same {len(H):,} articles, different bands")
ax = axs[1]
mm = np.zeros((4, 4), int)
for a, b in zip(H, Lb):
    mm[a - 1, b - 1] += 1
mp = mm / mm.sum(1, keepdims=True) * 100
ax.imshow(mp, cmap="Blues", vmin=0, vmax=100)
for i in range(4):
    for j in range(4):
        ax.text(j, i, f"{mp[i, j]:.0f}", ha="center", va="center", color="white" if mp[i, j] > 55 else "black")
ax.set_xticks(range(4), ["1", "2", "3", "4"]); ax.set_yticks(range(4), ["1", "2", "3", "4"])
ax.set_xlabel("Luna band"); ax.set_ylabel("Haiku band")
ax.set_title(f"Row %, exact agreement {np.mean(H == Lb) * 100:.0f}%")
save("8_sieve")

# 9 ---- summary panel
import matplotlib.image as mpimg
names = ["1_agreement", "3_grade_scatter", "4_sharpness", "5_cost_time", "6_stability", "7_decomposition"]
fig, axs = plt.subplots(2, 3, figsize=(18, 10))
for ax, nm in zip(axs.ravel(), names):
    ax.imshow(mpimg.imread(f"{OUT}/{nm}.png")); ax.axis("off")
plt.tight_layout(); plt.savefig(f"{OUT}/0_summary.png", dpi=150); plt.close()
print("done", sorted(os.listdir(OUT)))
