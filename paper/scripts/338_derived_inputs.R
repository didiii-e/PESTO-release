#!/usr/bin/env Rscript
# The small tables the figure scripts read in place of third-party files, which
# are not redistributed with PESTO-release. Run where data/ holds those files.
#
# For Figure 4 and Extended Data Figs. 4 and 5, on the genes of the panel
# (results/fig3_universe550_meancall_scores.tsv) only:
#   results/biology/panel_expression_specificity.tsv  stage, cells, tissue, gene,
#     spec = log2((median TPM in the tissue + 0.1) / (median TPM in the other
#     samples + 0.1)); a symbol on several rows keeps its most expressed row.
#     adult: GTEx v8 median TPM (data/gtex_median_tpm.gct.gz), samples grouped by
#     the part of their name before " - ", with the two cultured-cell samples
#     kept or removed; fetal: Descartes fetal tissues
#     (data/fetal_gene_expression_tissue_with_symbols.csv), each tissue and
#     "Brain" for cerebrum and cerebellum together.
#   results/biology/panel_loeuf.tsv  gene, gnomAD v4 LOEUF (data/loeuf_scores.tsv).
# For Figure 1 and Supplementary Table 1, the gene-phenotype pairs each study
# reported, without their statistics:
#   results/cohort_aou_pairs.tsv    from data/raw/AoU_results.tsv (All of Us-GeneBass)
#   results/cohort_brava_pairs.tsv  from data/raw/Duncan_results.tsv (BRaVa)
#
#   Rscript scripts/338_derived_inputs.R

suppressPackageStartupMessages({ library(dplyr); library(readr) })

root <- normalizePath(file.path(dirname(sub("--file=", "",
        grep("--file=", commandArgs(FALSE), value = TRUE)[1])), ".."))
DATA <- file.path(root, "data")
RESULTS <- file.path(root, "results")
dir.create(file.path(RESULTS, "biology"), showWarnings = FALSE)

ADULT <- c("Brain", "Pituitary", "Nerve", "Heart", "Artery", "Muscle", "Adipose", "Liver",
           "Pancreas", "Kidney", "Lung", "Stomach", "Small Intestine", "Colon", "Spleen",
           "Whole Blood", "Skin", "Thyroid", "Adrenal Gland", "Testis")
FETAL <- c("Cerebrum", "Cerebellum", "Eye", "Heart", "Muscle", "Lung", "Liver", "Pancreas",
           "Kidney", "Adrenal", "Stomach", "Intestine", "Spleen", "Thymus", "Placenta")

panel <- unique(toupper(read_tsv(file.path(RESULTS, "fig3_universe550_meancall_scores.tsv"),
                                 show_col_types = FALSE)$gene))

ratios <- function(mat, genes, groups) {
  keep <- genes %in% panel
  mat <- mat[keep, , drop = FALSE]; genes <- genes[keep]
  best <- tibble(i = seq_along(genes), gene = genes, mx = apply(mat, 1, max)) %>%
    group_by(gene) %>% slice_max(mx, n = 1, with_ties = FALSE) %>% ungroup()
  mat <- mat[best$i, , drop = FALSE]
  bind_rows(lapply(names(groups), function(t) {
    inn <- groups[[t]]; oth <- setdiff(colnames(mat), inn)
    tibble(gene = best$gene, tissue = t,
           spec = log2((apply(mat[, inn, drop = FALSE], 1, median) + 0.1) /
                       (apply(mat[, oth, drop = FALSE], 1, median) + 0.1)))
  }))
}

gtex <- read.delim(gzfile(file.path(DATA, "gtex_median_tpm.gct.gz")), skip = 2,
                   check.names = FALSE, stringsAsFactors = FALSE)
all_cols <- setdiff(names(gtex), c("Name", "Description"))
adult <- bind_rows(lapply(c("kept", "removed"), function(cells) {
  cols <- if (cells == "kept") all_cols else all_cols[!grepl("^Cells", all_cols)]
  grp <- sub(" - .*", "", cols)
  m <- as.matrix(gtex[, cols]); storage.mode(m) <- "numeric"
  ratios(m, toupper(gtex$Description),
         setNames(lapply(ADULT, function(t) cols[grp == t]), ADULT)) %>%
    mutate(stage = "adult", cells = cells)
}))

fetal_raw <- read_csv(file.path(DATA, "fetal_gene_expression_tissue_with_symbols.csv"),
                      show_col_types = FALSE)
fmat <- as.matrix(fetal_raw[, FETAL]); storage.mode(fmat) <- "numeric"
fetal <- ratios(fmat, toupper(fetal_raw$gene_symbol),
                c(setNames(as.list(FETAL), FETAL), list(Brain = c("Cerebrum", "Cerebellum")))) %>%
  mutate(stage = "fetal", cells = "none")

spec <- bind_rows(adult, fetal) %>%
  transmute(stage, cells, tissue, gene, spec = sprintf("%.17g", spec))
write_tsv(spec, file.path(RESULTS, "biology", "panel_expression_specificity.tsv"))

loeuf <- read_tsv(file.path(DATA, "loeuf_scores.tsv"), show_col_types = FALSE) %>%
  transmute(gene = toupper(gene_symbol), loeuf = as.numeric(LOEUF)) %>%
  filter(!is.na(loeuf)) %>%
  distinct(gene, .keep_all = TRUE) %>%
  filter(gene %in% panel) %>%
  mutate(loeuf = sprintf("%.17g", loeuf))
write_tsv(loeuf, file.path(RESULTS, "biology", "panel_loeuf.tsv"))

aou <- read_tsv(file.path(DATA, "raw", "AoU_results.tsv"), show_col_types = FALSE,
                col_types = cols(.default = col_character())) %>%
  select(gene_symbol, description)
write_tsv(aou, file.path(RESULTS, "cohort_aou_pairs.tsv"), na = "")
brava <- read_tsv(file.path(DATA, "raw", "Duncan_results.tsv"), show_col_types = FALSE,
                  col_types = cols(.default = col_character())) %>%
  select(external_gene_name, phenotype, phenotype_full)
write_tsv(brava, file.path(RESULTS, "cohort_brava_pairs.tsv"), na = "")

cat("panel genes", length(panel), "| specificity rows", nrow(spec),
    "| LOEUF", nrow(loeuf), "| AoU pairs", nrow(aou), "| BRaVa pairs", nrow(brava), "\n")
