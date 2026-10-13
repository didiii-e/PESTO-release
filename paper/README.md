# Reproducing the paper

Everything needed to redraw the figures and tables of *Large language model
classifies prior evidence in gene–phenotype associations*. The scripts compute
the project root as the parent of `scripts/`, so they read and write under this
directory.

## Redraw everything

```bash
pip install pesto-genetics scipy openpyxl    # or `pip install -e ..` from a clone
# R 4.x with: ggplot2 dplyr tidyr readr patchwork cowplot ggforce ggpubr
#             gridExtra gtable jsonlite
bash redraw_all.sh
```

This calls no model and needs no API key. It takes about two minutes.

| Item | Script(s) | Output |
|---|---|---|
| Figure 1 | `20_figure1.R` (+ `pipeline_schema.R`) | `figures/figure1_v7.png` |
| Numbers quoted for Figure 1 | `142_fig1_text_numbers.py` | `results/fig1_text_numbers.txt` |
| Extended Data Fig. 1 | `25_figure_ed1.R` | `figures/figure_ed1.png` |
| Extended Data Table 1 | `19_build_ed1_v2_table.py`, `22_figure_ed1_v3.R` | `figures/table_ed1_v3.png` |
| Supplementary Table 1 | `145_supplementary_table1.py` | `results/supplementary_table1.xlsx` |
| Figure 2 | `21_figure2.R` (+ `_panel_citations.R` for e,f; reads `results/knowledge_citations/pair_summary.tsv` and `ref_checks.tsv`) | `figures/figure2.png` |
| Extended Data Fig. 2 | `143_ed2_titles_data.py`, `144_figure_ed2_titles.R` | `figures/figure_ed2_titles.png` |
| Figure 3 | `250_figure_temporal.R` (draws `249_figure_trajectories6.R` for a and `246_figure_baseline_class_benchmark.R` for b; reads `benchmark/trajectories6/`, `benchmark/epigen_extension/` and `benchmark/asd_denovo2014/`) | `figures/figure3.png` |
| Figure 4 | `117_figure3_chd_top5.R --loeuf-decile --brain-decile --or --top5-brain --cell-panel` (+ `_panel_dendrogram.R`; panel c reads `results/biology/cell_types_grid.tsv`) | `figures/figure4.png` |
| Extended Data Fig. 4a (tissues) | `198_tissue_enrichment_grid.R`, `199_tissue_heatmap_from_grid.R adult kept 5% --clean` | `figures/figure_ed4_tissue_enrichment.png` |
| Supplementary Note 5, sensitivity of the tissue analyses (table) | `198_tissue_enrichment_grid.R` | `results/tissue_enrichment/grid_key.tsv` |
| Supplementary Note 5, adjustment for publications per gene (table) | `269_publication_adjusted_enrichment.py` (+ `_biology_panel.py`, `202_subthreshold_signal.py`; needs the ASC gene list `data/raw/ASC_GeneList_12082026.txt`, not redistributed) | `results/biology/publication_adjusted_enrichment.tsv` |
| Supplementary Figure 1 (the pipeline, step by step) | `172_pipeline_detailed_schema.R` (+ `pipeline_schema.R`) | `figures/pipeline_detailed.png` |
| Supplementary Note 1, run-to-run variability (table) | `183_reproducibility_stats.py` | `results/reproducibility_aou50/summary.tsv` |
| Supplementary Figure 1 | `122_figure2_current_vs_score.R` | `figures/figure2_current_vs_score.png` |
| Supplementary Figure 2 | `127_fig2_roc_candidate.py`, `128_figure2_roc_candidate.R` | `figures/figure2_roc_candidate.png` |
| Supplementary Figure 3 | `150_bodyonly_data.py`, `151_figure_supp_bodyonly.R` | `figures/figure_supp_bodyonly.png` |

Redrawn here, Figures 2 and 3, Extended Data Fig. 2, Extended Data Table 1 and
both tables are identical to the published ones pixel for pixel or byte for byte.
Figure 1 and Extended Data Fig. 1 differ only in where the jittered points fall,
which was random and is now seeded. The Supplementary Figures differ only in
their labels, which carry the arms' current names.

## Names in the tables

The result tables record the names the arms had when they were run. The package
declares them under new names, and accepts the old ones as aliases:

| In the tables | In the package |
|---|---|
| `current` | `abstracts` (PESTO in the manuscript) |
| `current-general` | `abstracts-trait` |
| `prior` | `knowledge` (model internal knowledge) |
| `titles` | `titles` (PESTO-titles) |
| `current-bare`, `current-open`, `score` | `abstracts-bare`, `abstracts-open`, `abstracts-score` |
| `currentv2-cheap` | `fulltext` |

## How the tables were produced

The other scripts in `scripts/` drew the benchmark pairs and asked the models.
They are kept as the record of how every table in `results/` was made. Running
them again costs money and, because Claude Opus does not accept a temperature,
will not reproduce each answer exactly.

| Step | Scripts |
|---|---|
| One arm over a table of pairs | `run_arm.py` (or `pesto --bench`) |
| Figure 1 cohort and negative controls | `11_build_all_runs_auto.py`, `12_draw_cohort_absent.py`, `13_draw_random_absent.py`, `14_replay_ot.py`, `16_rematch_ot_cohort.py`, `17_replay_ot_prompt.py`, `00_aggregate_runs.py` (rebuilds `results/all_runs.tsv` from earlier runs that are not included; the table itself is) |
| Figure 2 benchmarks | `draw_figure2_benchmark.py`, `score_figure2_uncontested.py`, `16_consolidate_benchmark.py`, `123_fig2a_extra30.py`, `85_`/`94_`/`100_draw_fig2a_absent*.py`, `86_`/`95_`/`101_score_fig2a_absent*.py`, `80_prior_year_sample.py`, `102_prior_year10_extra10bin.py`, `103_prior_year10_fill3year.py`, `40_ablation_fig2.py` |
| Figure 2e,f, references named by each arm | `272_knowledge_citations.py` (the closed-book model asked for its references on the 210 dated GenCC Limited pairs), `273_verify_citations.py` (each reference resolved against PubMed and judged for relevance; reads the `current` runs of Fig. 2c from Zenodo), `275_judge_audit_sample.py` (sample of the relevance judgments for a human check); writes `results/knowledge_citations/` |
| Extended Data Fig. 2 | `104_score_fig2a_absent70_titles.py`, `78_fig2_ed5_data.py` |
| Figure 4 gene universe and enrichments | `82_fig3_four_phenos.py`, `92_fig3_random50.py`, `104_fig3_alzheimer.py`, `106_fig3_random50b.py`, `115_fig3_chd.py`, `108_fig3_go_nocc.py`, `110_fig3_nocc_meancall.py`, `113_fig3_top5_parent.py`, `116_fig3_chd_top5.py`, `86_go_matrix_5pheno.py`, `42_fig3_cd_bars.py` |
| Figure 3, the two cohorts | `248_draw_epigen_extension.py` (200 EPIGEN epilepsy genes: the 73 of D. Elsyad's frozen order in `experiments/biological_proximity_pilot/replication_epigen_v2/` and 127 more) and `245_draw_asd_denovo2014.py` (200 of the 480 autism de novo loss-of-function genes of 2014; reads denovo-db 1.6.1, not redistributed), scored with `--max-date` at the start date and 2026/10/11; `252_build_transitions.py` builds `transitions.tsv`; `247_baseline_class_adjusted.py` adjusts for articles per gene (reads NCBI `gene2pubmed.gz`, not redistributed) and writes `results/baseline_class_adjusted.tsv` |
| Figure 3a, trajectories | `benchmark/trajectories6/pairs.tsv` scored with `--max-date` at every date of the grid |
| Figure 4, the 670-gene panel | `benchmark/fig3_add_t2d_bipex2/` (the type 2 diabetes and BipEx 2.0 genes) and `benchmark/fig3_add_random100/` (`234_draw_random100.py`) scored with `--max-date 2026/09/01`; `233_run_panel570.sh` appends them to the 550-gene table and reruns the analyses, giving `results/fig3_universe550_meancall_scores.tsv` (670 genes despite its name) |
| Figure 4c, cell types | `211_cell_type_specificity.py` (+ `_biology_panel.py`, `202_subthreshold_signal.py`); reads the Human Protein Atlas single-cell table `rna_single_cell_type.tsv.zip` (proteinatlas.org, not redistributed) and writes `results/biology/cell_types_grid.tsv` |
| Supplementary Figures 1 and 2 | `121_score_fig2ab.py`, `125_bare_fig2ab.py`, `126_open_fig2ab.py` |
| Supplementary Figure 3 benchmark | `139_build_bench_bodyonly.py` (first 22 pairs), `153_extend_bench_bodyonly.py` (18 more, same criteria), `138_score_bodyonly.py` |
| Supplementary Note 1, run-to-run variability | `181_reproducibility_aou50.py` (three fresh runs of 50 All of Us–GeneBass associations; only each run's `pesto.tsv` and `cost.tsv` are kept here) |
| Supplementary Note 1, Open Targets tie rules (sensitivity) | `188_ot_tie_rules.py` (replays the stored Open Targets grades, no model call; reads `results/auto_cohort_ot_v7/` and `results/auto_fig1c_absent50_hgnc_v7/` from Zenodo, writes `results/ot_tie_rules/`) |

Their inputs and the saved model answers (one JSON per pair, with the corpus,
the prompts and the response) are on Zenodo,
[doi:10.5281/zenodo.23288837](https://doi.org/10.5281/zenodo.23288837):

```bash
bash fetch_data.sh        # about 105 MB, extracted into paper/
```

The saved model answers of the Figure 3 runs (`runs/` of `benchmark/asd_denovo2014/`,
`benchmark/epigen_extension/` and `benchmark/trajectories6/`) are not yet in this
archive; they go into its next version.

Not redistributed: the PEPPER gene features used to draw the random genes of
Figure 4 (`92_fig3_random50.py` says where to put them), the GWAS Catalog used to
build the body-only benchmark, and the embedding weights, which download from
HuggingFace on first use.
