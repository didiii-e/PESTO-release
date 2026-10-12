#!/usr/bin/env bash
# Rebuild results/panel570/ and rerun Fig. 3, Extended Data Fig. 4 and the
# programme analyses on the 570-gene panel: the 550 genes of Fig. 3 plus the 9
# type 2 diabetes genes of Zhao et al. 2025 and 11 BipEx 2.0 genes
# (benchmark/fig3_add_t2d_bipex2/). Nothing the paper uses is touched: the
# workspace holds a copy of scripts/, which compute their root from their own
# location, its own results/ and figures/, and a link to data/.
#
# Two edits are made to the copy of scripts/202_subthreshold_signal.py: the new
# lists count as disease lists, and the BipEx 2.0 genes count as used to build
# the panel in the BipEx 2.0 test of analysis 1.
#
#   bash scripts/233_run_panel570.sh && python3 scripts/232_compare_panel570.py
#   bash scripts/233_run_panel570.sh panel670 fig3_add_t2d_bipex2 fig3_add_random100 \
#     && python3 scripts/232_compare_panel570.py panel670
# The first argument names the workspace under results/, the others the
# benchmark/ folders whose genes are added (random draws count as random genes).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="${1:-panel570}"; shift || true
BENCHES="${*:-fig3_add_t2d_bipex2}"
W="$ROOT/results/$NAME"
mkdir -p "$W/results/biology" "$W/results/tissue_enrichment" "$W/figures"
rm -rf "$W/scripts" && cp -r "$ROOT/scripts" "$W/scripts" && rm -rf "$W/scripts/attic" "$W/scripts/__pycache__"
ln -sfn ../../data "$W/data"
cp "$ROOT/results/biology/gene_pubmed_counts_human.tsv" "$W/results/biology/"

python3 - "$ROOT" "$W" $BENCHES <<'EOF'
import sys
import pandas as pd
root, w, *benches = sys.argv[1:]
s = pd.read_csv(f"{root}/results/fig3_universe550_meancall_scores.tsv", sep="\t")
r = pd.concat([pd.read_csv(f"{root}/benchmark/{b}/pesto.tsv", sep="\t").assign(source=b)
               for b in benches], ignore_index=True)
weights = {"p_established": 4, "p_existing": 3, "p_hypothesized": 2, "p_novel": 1}
r["lit_score"] = sum(r[k] * v for k, v in weights.items()) / sum(r[k] for k in weights)
new = pd.DataFrame({"gene": r.gene, "phenotype": r.phenotype, "lit_score": r.lit_score,
                    "mean_call": r.lit_mean, "argmax": r.lit_argmax, "lit_mean": r.lit_mean,
                    "reaching": r.lit_score > 2.5, "source": r.source, "set": r.set})
assert not set(new.gene) & set(s.gene) and not new.duplicated(["gene", "phenotype"]).any()
pd.concat([s, new], ignore_index=True).to_csv(
    f"{w}/results/fig3_universe550_meancall_scores.tsv", sep="\t", index=False)

p = f"{w}/scripts/202_subthreshold_signal.py"
t = open(p).read()
a = 'other = scores.loc[scores["set"].isin(["pcgc_sig60", "gencc9_ad"]), "gene"]'
assert t.count(a) == 1
t = t.replace(a, a.replace('"gencc9_ad"]', '"gencc9_ad", "t2d_zhao2025", "bipex2_ptv_fdr05"]'))
a = '("BipEx2", "bipolar disorder", bip[["gene_id", "p"]], set()),'
assert t.count(a) == 1
t = t.replace(a, a.replace("set()", "BIPEX2_LIST"))
t = t.replace("def studies(ref):", 'BIPEX2_LIST = set(pd.read_csv("' + root
              + '/benchmark/fig3_add_t2d_bipex2/manifest_bipex2_genes.txt", header=None)[0])\n\n\ndef studies(ref):', 1)
open(p, "w").write(t)
EOF

cd "$W"
python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('m', 'scripts/116_fig3_chd_top5.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); m.go()" > results/run_116_go.log 2>&1
Rscript scripts/117_figure3_chd_top5.R --loeuf-decile --brain-decile --or --top5-brain > results/run_117.log 2>&1
Rscript scripts/198_tissue_enrichment_grid.R > results/run_198.log 2>&1
Rscript scripts/199_tissue_heatmap_from_grid.R adult kept 5% --clean > results/run_199.log 2>&1
for s in 159_fig3a_composition_check 202_subthreshold_signal 211_cell_type_specificity \
         212_developmental_timing 213_ppi_modules 230_fetal_cell_types; do
  python3 "scripts/$s.py" > "results/run_${s%%_*}.log" 2>&1
done
for s in 214_cell_type_heatmaps 215_gtex_subregions 231_fetal_cell_type_heatmap; do
  Rscript "scripts/$s.R" > "results/run_${s%%_*}.log" 2>&1
done
echo "done: $W"
