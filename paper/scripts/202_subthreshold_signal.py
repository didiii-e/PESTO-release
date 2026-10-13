"""Do genes PESTO calls Hypothesized carry more sub-threshold rare-variant signal
than genes it calls Novel? (Programme item 1, paper/biology_program.md.)

Plan fixed before looking at the data:
- PESTO calls: the mean call of the 550-gene panel of Fig. 3, for the phenotype of
  each study (results/fig3_universe550_meancall_scores.tsv).
- Gene-level P values from exome studies with genome-wide results in the repo:
  SCHEMA (schizophrenia; case-control plus de novo meta P), Epi25 (all epilepsy,
  group EPI; PTV and damaging missense P combined by ACAT), BipEx (bipolar
  disorder, group "Bipolar Disorder"; PTV and damaging missense against gnomAD
  non-psychiatric controls, combined by ACAT). BipEx was not used to build the
  panel; SCHEMA and Epi25 were, so the genes they declared significant are removed.
- Primary test: one-sided Mann-Whitney, -log10 P higher in Hypothesized than in
  Novel genes, per study; combined over studies by Stouffer.
- Adjusted test: least squares of -log10 P on the call (Novel as reference),
  log10(1 + PubMed records, NCBI gene2pubmed) and LOEUF, per study and pooled with
  a study term.
- All tests of the PESTO call are one-sided (more signal than Novel), the
  direction being pre-specified; covariate terms are reported two-sided.
- Secondary: Spearman correlation of -log10 P with the ordered call
  (Novel < Hypothesized < Existing < Established), and the share of genes at P < 0.05.

Added after the first look, because disease-list genes are both more often
Hypothesized and richer in signal: the same tests within disease-list genes and
within the 200 random genes separately, a rank test stratified by study and
gene origin (Stouffer, weighted by sample size), and the adjusted model with a
disease-gene term. Then, adjusting for publications, LOEUF and gene origin
without assuming linearity (see nonlinear()).

Updated after that to the latest exome-browser releases (data/genelists/browser_2026/,
downloaded 10 Oct 2026; the first version, commit a87575d8, used BipEx 1):
- SCHEMA2: the file used before already held SCHEMA2 (87,959 cases), so nothing
  changes but the name;
- BipEx2 (64,435 cases) replaces BipEx 1 (13,933 cases); PTV and missense P
  combined by ACAT; still not used to build the panel, so no gene is removed;
- ASC2 (autism) is added: its signal is the TADA false discovery rate (ranked as
  if a P value; "P < 0.05" means FDR < 0.05), QC-flagged genes dropped, and the
  ASC list genes of the panel and any gene at FDR < 0.001 removed.

Writes results/biology/subthreshold_signal_genes.tsv (one row per gene and study),
results/biology/subthreshold_signal_tests.tsv,
results/biology/subthreshold_signal_by_origin.tsv and
results/biology/subthreshold_signal_nonlinear.tsv.
"""
from __future__ import annotations

import gzip
import json
import os

import numpy as np
import pandas as pd
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "results", "biology")
PUBCOUNTS = os.path.join(OUT, "gene_pubmed_counts_human.tsv")
ORDER = ["Novel", "Hypothesized", "Existing", "Established"]


def acat(ps):
    ps = np.clip(np.asarray([p for p in ps if pd.notna(p)], float), 1e-300, 1 - 1e-15)
    if len(ps) == 0:
        return np.nan
    t = np.mean(np.tan((0.5 - ps) * np.pi))
    return 0.5 - np.arctan(t) / np.pi


def pubmed_counts():
    if os.path.exists(PUBCOUNTS):
        return pd.read_csv(PUBCOUNTS, sep="\t", dtype={"entrez_id": str})
    n = {}
    with gzip.open(os.path.join(DATA, "raw", "gene2pubmed.gz"), "rt") as f:
        next(f)
        for line in f:
            if line.startswith("9606\t"):
                gid = line.split("\t", 2)[1]
                n[gid] = n.get(gid, 0) + 1
    d = pd.DataFrame(sorted(n.items()), columns=["entrez_id", "pubmed_records"])
    d.to_csv(PUBCOUNTS, sep="\t", index=False)
    return d


def hgnc_table():
    h = pd.read_csv(os.path.join(DATA, "hgnc_complete_set.txt"), sep="\t", dtype=str,
                    usecols=["symbol", "prev_symbol", "alias_symbol", "entrez_id", "ensembl_gene_id"])
    lookup = {}
    for col in ("alias_symbol", "prev_symbol", "symbol"):
        for _, r in h.iterrows():
            for s in str(r[col]).split("|") if pd.notna(r[col]) else []:
                lookup[s] = r["symbol"]
    return h.set_index("symbol"), lookup


def epi25_genes(ref):
    return set().union(*(ref[k] for k in ("epi25_all", "epi25_dee", "epi25_gge", "epi25_nafe")))


def disease_list_genes(ref, scores):
    asc = pd.read_csv(os.path.join(DATA, "raw", "ASC_GeneList_12082026.txt"))["Gene"].str.strip()
    other = scores.loc[scores["set"].isin(["pcgc_sig60", "gencc9_ad", "t2d_zhao2025", "bipex2_ptv_fdr05"]), "gene"]
    return set(asc) | set(ref["schema_scz"]) | epi25_genes(ref) | set(other)


def by_origin(d, disease):
    d = d.assign(disease_gene=d["gene"].isin(disease).astype(float))
    rows, zs, ws = [], [], []
    for (study, dg), g in d.groupby(["study", "disease_gene"], sort=False):
        h, n = g.loc[g["call"] == "Hypothesized", "mlogp"], g.loc[g["call"] == "Novel", "mlogp"]
        p = stats.mannwhitneyu(h, n, alternative="greater").pvalue
        zs.append(stats.norm.isf(p))
        ws.append(np.sqrt(len(h) * len(n) / (len(h) + len(n))))
        rows.append({"study": study, "genes": "disease list" if dg else "random",
                     "n_Hypothesized": len(h), "n_Novel": len(n),
                     "share_p05_Hypothesized": round((10 ** -h < 0.05).mean(), 3),
                     "share_p05_Novel": round((10 ** -n < 0.05).mean(), 3),
                     "mw_hyp_vs_novel_p": p})
    zs, ws = np.array(zs), np.array(ws)
    rows.append({"study": "all", "genes": "stratified",
                 "mw_hyp_vs_novel_p": stats.norm.sf((ws * zs).sum() / np.sqrt((ws ** 2).sum()))})
    cc = d.dropna(subset=["loeuf"])
    for study, g in list(cc.groupby("study", sort=False)) + [("all", cc)]:
        extra = []
        if study == "all":
            for st in g["study"].unique()[1:]:
                g = g.assign(**{"study_" + st: (g["study"] == st).astype(float)})
            extra = [c for c in g.columns if c.startswith("study_")]
        fit = ols(g, ["is_Hypothesized", "is_Existing", "is_Established", "log_pubs", "loeuf",
                      "disease_gene"] + extra)
        b, se, p = fit["is_Hypothesized"]
        rows.append({"study": study, "genes": "adjusted incl. disease-gene term",
                     "adj_hyp_beta": round(b, 3), "adj_hyp_se": round(se, 3), "adj_hyp_p": p})
    return pd.DataFrame(rows)


def rcs(x, k=4):
    """Restricted cubic spline basis (Harrell), knots at the usual quantiles."""
    x = np.asarray(x, float)
    t = np.quantile(x, {3: [.1, .5, .9], 4: [.05, .35, .65, .95], 5: [.05, .275, .5, .725, .95]}[k])
    pos = lambda v: np.clip(v, 0, None) ** 3
    cols = [x]
    for j in range(k - 2):
        cols.append((pos(x - t[j]) - pos(x - t[-2]) * (t[-1] - t[j]) / (t[-1] - t[-2])
                     + pos(x - t[-1]) * (t[-2] - t[j]) / (t[-1] - t[-2])) / (t[-1] - t[0]) ** 2)
    return np.column_stack(cols)


def nonlinear(d, disease):
    """Hypothesized against Novel without assuming linearity: (1) least squares on the
    within-study rank of -log10 P with splines of publications and LOEUF, a
    disease-gene term and a study term; (2) Mann-Whitney within strata of study x
    gene origin x tertile of publications x tertile of LOEUF, combined by Stouffer."""
    d = d.dropna(subset=["loeuf"]).assign(disease_gene=d["gene"].isin(disease).astype(float))
    d["rank_p"] = d.groupby("study")["mlogp"].rank(pct=True)
    rows = []
    for study, g in list(d.groupby("study", sort=False)) + [("all", d)]:
        g = g.copy()
        cols = {}
        for name, x in (("pubs", g["log_pubs"]), ("loeuf", g["loeuf"])):
            for i, c in enumerate(rcs(x).T):
                cols[f"{name}_s{i}"] = c
        if study == "all":
            for st in g["study"].unique()[1:]:
                cols["study_" + st] = (g["study"] == st).astype(float).to_numpy()
        g = g.assign(**cols)
        fit = ols(g.assign(mlogp=g["rank_p"]),
                  ["is_Hypothesized", "is_Existing", "is_Established", "disease_gene"] + list(cols))
        b, se, p = fit["is_Hypothesized"]
        rows.append({"study": study, "method": "rank regression, splines",
                     "effect": round(b, 3), "se": round(se, 3), "p": p})
    d["pubs_t"] = d.groupby("study")["log_pubs"].transform(lambda x: pd.qcut(x, 3, labels=False, duplicates="drop"))
    d["loeuf_t"] = d.groupby("study")["loeuf"].transform(lambda x: pd.qcut(x, 3, labels=False, duplicates="drop"))
    for study, g in list(d.groupby("study", sort=False)) + [("all", d)]:
        zs, ws, n_strata = [], [], 0
        for _, s in g.groupby(["study", "disease_gene", "pubs_t", "loeuf_t"]):
            h, n = s.loc[s["call"] == "Hypothesized", "mlogp"], s.loc[s["call"] == "Novel", "mlogp"]
            if len(h) < 2 or len(n) < 2:
                continue
            p = stats.mannwhitneyu(h, n, alternative="greater").pvalue
            zs.append(stats.norm.isf(min(max(p, 1e-12), 1 - 1e-12)))
            ws.append(np.sqrt(len(h) * len(n) / (len(h) + len(n))))
            n_strata += 1
        zs, ws = np.array(zs), np.array(ws)
        rows.append({"study": study, "method": f"stratified Mann-Whitney ({n_strata} strata)",
                     "effect": np.nan, "se": np.nan,
                     "p": stats.norm.sf((ws * zs).sum() / np.sqrt((ws ** 2).sum()))})
    return pd.DataFrame(rows)


BIPEX2_LIST = set(pd.read_csv(os.path.join(ROOT, "benchmark", "fig3_add_t2d_bipex2", "manifest_bipex2_genes.txt"), header=None)[0])


def studies(ref):
    new = os.path.join(DATA, "genelists", "browser_2026")
    schema = pd.read_csv(os.path.join(new, "SCHEMA2_gene_results.tsv.bgz"), sep="\t", compression="gzip")
    schema = schema.assign(p=schema["case_control_plus_de_novo_p_value"])[["gene_id", "p"]]

    epi = pd.read_csv(os.path.join(DATA, "genelists", "Epi25_gene_results.tsv.bgz"),
                      sep="\t", compression="gzip")
    epi = epi[epi["group"] == "EPI"]
    epi = epi.assign(p=[acat(x) for x in zip(epi["ptv_pval"], epi["damaging_missense_pval"])])

    bip = pd.read_csv(os.path.join(new, "BipEx2_gene_results.tsv.bgz"), sep="\t", compression="gzip")
    bip = bip.assign(p=[acat(x) for x in zip(bip["ptv_p_value"], bip["mis_p_value"])])

    asc = pd.read_csv(os.path.join(new, "ASC2_gene_results.tsv.bgz"), sep="\t", compression="gzip")
    asc = asc[~asc["qc_flagged"].astype(bool)]
    asc = asc.assign(p=asc["false_discovery_rate"].clip(lower=1e-300))
    asc_list = pd.read_csv(os.path.join(DATA, "raw", "ASC_GeneList_12082026.txt"))["Gene"].str.strip()
    asc_sig = set(asc_list) | set(asc.loc[asc["false_discovery_rate"] < 0.001, "gene_id"])

    return [
        ("SCHEMA2", "schizophrenia", schema, set(ref["schema_scz"])),
        ("Epi25", "epilepsy", epi[["gene_id", "p"]], epi25_genes(ref)),
        ("BipEx2", "bipolar disorder", bip[["gene_id", "p"]], BIPEX2_LIST),
        ("ASC2", "Autism Spectrum Disorder", asc[["gene_id", "p"]], asc_sig),
    ]


def ols(df, terms):
    """Least squares; terms constant in df (an empty call category) are dropped
    and reported as NaN."""
    dropped = [t for t in terms if df[t].nunique() < 2]
    kept = [t for t in terms if t not in dropped]
    out = ols_fit(df, kept)
    out.update({t: (np.nan, np.nan, np.nan) for t in dropped})
    return out


def ols_fit(df, terms):
    X = np.column_stack([np.ones(len(df))] + [df[t].to_numpy(float) for t in terms])
    y = df["mlogp"].to_numpy(float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = len(y) - X.shape[1]
    se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * (resid @ resid) / dof)
    t = beta / se
    return {name: (beta[i + 1], se[i + 1],
                   stats.t.sf(t[i + 1], dof) if name.startswith("is_") else 2 * stats.t.sf(abs(t[i + 1]), dof))
            for i, name in enumerate(terms)}


def main():
    os.makedirs(OUT, exist_ok=True)
    scores = pd.read_csv(os.path.join(ROOT, "results", "fig3_universe550_meancall_scores.tsv"), sep="\t")
    ref = json.load(open(os.path.join(DATA, "genelists", "reference_sets.json")))
    hgnc, lookup = hgnc_table()
    pubs = pubmed_counts().set_index("entrez_id")["pubmed_records"]
    loeuf = pd.read_csv(os.path.join(DATA, "loeuf_scores.tsv"), sep="\t").drop_duplicates("gene_symbol") \
        .set_index("gene_symbol")["LOEUF"]

    rows = []
    for study, pheno, res, sig in studies(ref):
        p_by_ens = res.dropna(subset=["p"]).drop_duplicates("gene_id").set_index("gene_id")["p"]
        s = scores[scores["phenotype"] == pheno]
        for _, r in s.iterrows():
            sym = lookup.get(r["gene"], r["gene"])
            ens = hgnc["ensembl_gene_id"].get(sym)
            ent = hgnc["entrez_id"].get(sym)
            rows.append({"study": study, "phenotype": pheno, "gene": r["gene"], "call": r["mean_call"],
                         "significant_in_study": r["gene"] in sig or sym in sig or ens in sig,
                         "p": p_by_ens.get(ens, np.nan),
                         "pubmed_records": pubs.get(ent, 0) if isinstance(ent, str) else np.nan,
                         "loeuf": loeuf.get(r["gene"], loeuf.get(sym, np.nan))})
    genes = pd.DataFrame(rows)
    genes.to_csv(os.path.join(OUT, "subthreshold_signal_genes.tsv"), sep="\t", index=False)

    d = genes[~genes["significant_in_study"]].dropna(subset=["p"]).copy()
    d["mlogp"] = -np.log10(d["p"])
    d["log_pubs"] = np.log10(1 + d["pubmed_records"].fillna(0))
    d["rank"] = d["call"].map({c: i for i, c in enumerate(ORDER)})
    for c in ORDER[1:]:
        d["is_" + c] = (d["call"] == c).astype(float)

    tests, zs = [], []
    for study, g in list(d.groupby("study", sort=False)) + [("pooled", d)]:
        row = {"study": study, "n_genes": len(g)}
        for c in ORDER:
            sub = g[g["call"] == c]
            row[f"n_{c}"] = len(sub)
            row[f"median_mlogp_{c}"] = round(sub["mlogp"].median(), 3) if len(sub) else np.nan
            row[f"share_p05_{c}"] = round((sub["p"] < 0.05).mean(), 3) if len(sub) else np.nan
        h, n = g.loc[g["call"] == "Hypothesized", "mlogp"], g.loc[g["call"] == "Novel", "mlogp"]
        if study != "pooled":
            mw = stats.mannwhitneyu(h, n, alternative="greater")
            row["mw_hyp_vs_novel_p"] = mw.pvalue
            zs.append(stats.norm.isf(mw.pvalue))
        else:
            row["mw_hyp_vs_novel_p"] = stats.norm.sf(sum(zs) / np.sqrt(len(zs)))
        rho = stats.spearmanr(g["rank"], g["mlogp"])
        row["spearman_rho"], row["spearman_p"] = round(rho.statistic, 3), rho.pvalue
        cc = g.dropna(subset=["loeuf"])
        if study == "pooled":
            for st in cc["study"].unique()[1:]:
                cc = cc.assign(**{"study_" + st: (cc["study"] == st).astype(float)})
            extra = [c for c in cc.columns if c.startswith("study_")]
        else:
            extra = []
        fit = ols(cc, ["is_Hypothesized", "is_Existing", "is_Established", "log_pubs", "loeuf"] + extra)
        for k in ("is_Hypothesized", "is_Existing", "is_Established", "log_pubs", "loeuf"):
            b, se, p = fit[k]
            row[f"adj_{k}_beta"], row[f"adj_{k}_p"] = round(b, 3), p
        tests.append(row)
    t = pd.DataFrame(tests)
    t.to_csv(os.path.join(OUT, "subthreshold_signal_tests.tsv"), sep="\t", index=False)
    disease = disease_list_genes(ref, scores)
    o = by_origin(d, disease)
    o.to_csv(os.path.join(OUT, "subthreshold_signal_by_origin.tsv"), sep="\t", index=False)
    nl = nonlinear(d, disease)
    nl.to_csv(os.path.join(OUT, "subthreshold_signal_nonlinear.tsv"), sep="\t", index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 60):
        print(t.T.to_string())
        print()
        print(o.to_string(index=False))
        print()
        print(nl.to_string(index=False))


if __name__ == "__main__":
    main()
