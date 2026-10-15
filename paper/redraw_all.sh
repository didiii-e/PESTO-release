#!/usr/bin/env bash
# Redraw every figure and table of the manuscript from paper/results/.
# Calls no model and needs no API key. Outputs go to paper/figures/ and
# paper/results/.
set -euo pipefail
cd "$(dirname "$0")"
export PESTO_PROJECT_ROOT="$PWD"
PY="${PYTHON:-python3}"
mkdir -p figures

echo "== Figure 1, Extended Data Fig. 1"
Rscript scripts/20_figure1.R
Rscript scripts/25_figure_ed1.R
"$PY" scripts/142_fig1_text_numbers.py > results/fig1_text_numbers.txt

echo "== Extended Data Table 1, Supplementary Table 1"
"$PY" scripts/19_build_ed1_v2_table.py
Rscript scripts/22_figure_ed1_v3.R
"$PY" scripts/145_supplementary_table1.py

echo "== Figure 2, Extended Data Fig. 2"
Rscript scripts/21_figure2.R
"$PY" scripts/143_ed2_titles_data.py
Rscript scripts/144_figure_ed2_titles.R

echo "== Figure 3"
Rscript scripts/250_figure_temporal.R

echo "== Figure 4, Extended Data Figs. 4 and 5, Supplementary Figure 6, Supplementary Note 6 tables"
Rscript scripts/117_figure3_chd_top5.R --loeuf-decile --brain-decile --or --top5-brain --cell-panel
Rscript scripts/198_tissue_enrichment_grid.R
Rscript scripts/236_extended_data_panel670.R .
Rscript scripts/231_fetal_cell_type_heatmap.R
if [ -f data/raw/ASC_GeneList_12082026.txt ]; then
  "$PY" scripts/269_publication_adjusted_enrichment.py
else
  echo "skip 269_publication_adjusted_enrichment.py: needs data/raw/ASC_GeneList_12082026.txt"
fi

echo "== Supplementary Figures 1 and 2, Supplementary Note 1 table"
Rscript scripts/172_pipeline_detailed_schema.R
Rscript scripts/156_figure_supp_abstract_fix.R
"$PY" scripts/183_reproducibility_stats.py

echo "== Supplementary Figure 4 (manual benchmark of the Open Targets branch)"
"$PY" scripts/320_figure_supp_ot_manual.py

echo "== Supplementary Figure 5, Extended Data Fig. 3"
Rscript scripts/122_figure2_current_vs_score.R
"$PY" scripts/127_fig2_roc_candidate.py
ED3=1 Rscript scripts/128_figure2_roc_candidate.R

echo "== Supplementary Figure 7 (full-text mode)"
"$PY" scripts/150_bodyonly_data.py
Rscript scripts/170_figure_supp_fulltext.R

echo "== Supplementary Figure 3 (references from model knowledge)"
Rscript scripts/280_figure_supp_citations.R

echo "== Supplementary Figure 9 (Figure 2 with Gemini models)"
"$PY" scripts/302_gemini_fig2_mirror.py --draw

echo "== Supplementary Figure 10 (Claude and Gemini compared)"
"$PY" scripts/303_gemini_fig2_comparison.py
Rscript scripts/304_figure_gemini_comparison.R
