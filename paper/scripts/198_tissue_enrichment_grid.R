#!/usr/bin/env Rscript
# Tissue-specific enrichment of PESTO high-evidence genes under every
# combination of two choices: whether the two GTEx cultured-cell samples
# (Cells - Cultured fibroblasts, Cells - EBV-transformed lymphocytes) enter the
# reference, and which top fraction of tissue-specific genes is tested (5%,
# 10% as in Fig. 3b, 20%). Fetal tissues have no cultured cells and vary with
# the threshold only.
#
# The test is that of Fig. 3b (scripts/117_figure3_chd_top5.R) applied to each
# tissue: on the 550-gene panel, specificity for tissue T is
# log2((median TPM in T + 0.1) / (median TPM in the other samples + 0.1));
# genes in the top fraction within the panel are compared, for each phenotype,
# between high-evidence genes (mean score > 2.5) and the rest by Fisher's
# exact test; FDR is Benjamini–Hochberg over tissues within a phenotype. GTEx
# samples are grouped by the part of their name before " - ". With the cells
# kept, the brain column reproduces Fig. 3b exactly.
#
# Writes results/tissue_enrichment/grid.tsv (every tissue, phenotype and
# setting), grid_key.tsv (the pairs the text could cite) and
# figures/figure_tissue_enrichment_grid.png. Exploratory; the paper is not changed.
#
#   Rscript scripts/198_tissue_enrichment_grid.R

suppressPackageStartupMessages({
  library(dplyr); library(readr); library(tidyr); library(ggplot2); library(cowplot)
})

root <- normalizePath(file.path(dirname(sub("--file=", "",
        grep("--file=", commandArgs(FALSE), value = TRUE)[1])), ".."))
OUT <- file.path(root, "results", "tissue_enrichment"); dir.create(OUT, showWarnings = FALSE)
PHENOS <- c("Autism Spectrum Disorder", "epilepsy", "schizophrenia", "bipolar disorder",
            "Alzheimer's disease", "congenital heart disease", "type 2 diabetes")
SHORT <- c("Autism Spectrum Disorder" = "ASD", epilepsy = "EPI", schizophrenia = "SCZ",
           "bipolar disorder" = "BD", "Alzheimer's disease" = "AD",
           "congenital heart disease" = "CHD", "type 2 diabetes" = "T2D")
ADULT <- c("Brain", "Pituitary", "Nerve", "Heart", "Artery", "Muscle", "Adipose", "Liver",
           "Pancreas", "Kidney", "Lung", "Stomach", "Small Intestine", "Colon", "Spleen",
           "Whole Blood", "Skin", "Thyroid", "Adrenal Gland", "Testis")
FETAL <- c("Cerebrum", "Cerebellum", "Eye", "Heart", "Muscle", "Lung", "Liver", "Pancreas",
           "Kidney", "Adrenal", "Stomach", "Intestine", "Spleen", "Thymus", "Placenta")
FRACTIONS <- c(`5%` = 20, `10%` = 10, `20%` = 5)   # ntile count: top 1 / n

scores <- read_tsv(file.path(root, "results", "fig3_universe550_meancall_scores.tsv"),
                   show_col_types = FALSE) %>%
  filter(phenotype %in% PHENOS, !is.na(lit_score)) %>%
  transmute(gene = toupper(gene), phenotype, score = as.numeric(lit_score))
panel <- unique(scores$gene)

# Ratios for the panel genes only; a symbol on several rows keeps its most
# expressed row, as in Fig. 3b.
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

enrich <- function(spec, n_tiles) {
  scores %>% inner_join(spec, by = "gene", relationship = "many-to-many") %>%
    group_by(tissue) %>%
    group_modify(function(sub, key) {
      dec <- sub %>% distinct(gene, spec) %>% mutate(top = ntile(spec, n_tiles) == n_tiles)
      sub <- sub %>% inner_join(dec %>% select(gene, top), by = "gene")
      bind_rows(lapply(split(sub, sub$phenotype), function(s) {
        r <- s$score > 2.5
        ft <- fisher.test(matrix(c(sum(r & s$top), sum(!r & s$top), sum(r & !s$top),
                                   sum(!r & !s$top)), nrow = 2, byrow = TRUE))
        tibble(phenotype = s$phenotype[1], or = unname(ft$estimate), lo = ft$conf.int[1],
               hi = ft$conf.int[2], p = ft$p.value, k_top = sum(r & s$top), n_top = sum(s$top))
      }))
    }) %>% ungroup() %>% group_by(phenotype) %>% mutate(fdr = p.adjust(p, "BH")) %>% ungroup()
}

gtex <- read.delim(gzfile(file.path(root, "data", "gtex_median_tpm.gct.gz")), skip = 2,
                   check.names = FALSE, stringsAsFactors = FALSE)
all_cols <- setdiff(names(gtex), c("Name", "Description"))
fetal_raw <- read_csv(file.path(root, "data", "fetal_gene_expression_tissue_with_symbols.csv"),
                      show_col_types = FALSE)
fmat <- as.matrix(fetal_raw[, FETAL]); storage.mode(fmat) <- "numeric"
fetal_spec <- ratios(fmat, toupper(fetal_raw$gene_symbol), setNames(as.list(FETAL), FETAL))

runs <- list()
for (cells in c("kept", "removed")) {
  cols <- if (cells == "kept") all_cols else all_cols[!grepl("^Cells", all_cols)]
  grp <- sub(" - .*", "", cols)
  m <- as.matrix(gtex[, cols]); storage.mode(m) <- "numeric"
  spec <- ratios(m, toupper(gtex$Description), setNames(lapply(ADULT, function(t) cols[grp == t]), ADULT))
  for (f in names(FRACTIONS)) {
    runs[[length(runs) + 1]] <- enrich(spec, FRACTIONS[[f]]) %>%
      mutate(stage = "adult", cells = cells, top = f)
  }
}
for (f in names(FRACTIONS)) {
  runs[[length(runs) + 1]] <- enrich(fetal_spec, FRACTIONS[[f]]) %>%
    mutate(stage = "fetal", cells = "none", top = f)
}
grid <- bind_rows(runs) %>% mutate(phenotype = SHORT[phenotype])
write_tsv(grid, file.path(OUT, "grid.tsv"))

KEY <- tribble(~phenotype, ~tissue,
               "ASD", "Brain", "EPI", "Brain", "SCZ", "Brain", "BD", "Brain",
               "CHD", "Brain", "CHD", "Heart", "T2D", "Pancreas", "AD", "Nerve", "AD", "Brain")
key <- grid %>% filter(stage == "adult") %>% inner_join(KEY, by = c("phenotype", "tissue")) %>%
  transmute(phenotype, tissue, cells, top,
            value = sprintf("%.2f (P %s%s)", or, formatC(p, format = "g", digits = 2),
                            ifelse(fdr < 0.05, ", FDR<0.05", ""))) %>%
  mutate(setting = paste0("cells ", cells, ", top ", top)) %>%
  select(phenotype, tissue, setting, value) %>%
  pivot_wider(names_from = setting, values_from = value)
write_tsv(key, file.path(OUT, "grid_key.tsv"))
print(as.data.frame(key), right = FALSE)

heat <- function(d, tissues, title) {
  d <- d %>% mutate(phenotype = factor(phenotype, levels = SHORT),
                    tissue = factor(tissue, levels = rev(tissues)),
                    l2 = pmax(pmin(log2(pmax(or, 1e-3)), 3), -3),
                    mark = ifelse(fdr < 0.05, "**", ifelse(p < 0.05, "*", "")))
  ggplot(d, aes(phenotype, tissue, fill = l2)) +
    geom_tile(colour = "white", linewidth = 0.4) +
    geom_text(aes(label = mark), size = 3.2, vjust = 0.75) +
    scale_fill_gradient2(low = "#2C6E8F", mid = "grey96", high = "#B33A3A", midpoint = 0,
                         limits = c(-3, 3), guide = "none") +
    scale_x_discrete(position = "top", expand = c(0, 0)) + scale_y_discrete(expand = c(0, 0)) +
    labs(x = NULL, y = NULL, title = title) + theme_minimal(base_size = 10) +
    theme(panel.grid = element_blank(), axis.text = element_text(colour = "black"),
          axis.text.x = element_text(face = "bold"), plot.title = element_text(face = "bold", size = 10))
}
panels <- list()
for (cells in c("kept", "removed")) for (f in names(FRACTIONS))
  panels[[length(panels) + 1]] <- heat(filter(grid, stage == "adult", cells == !!cells, top == f),
                                       ADULT, sprintf("Adult, cells %s, top %s", cells, f))
for (f in names(FRACTIONS))
  panels[[length(panels) + 1]] <- heat(filter(grid, stage == "fetal", top == f), FETAL,
                                       sprintf("Fetal, top %s", f))
p <- plot_grid(plotlist = panels, ncol = 3)
ggsave(file.path(root, "figures", "figure_tissue_enrichment_grid.png"), p, width = 13, height = 16,
       dpi = 200, bg = "white")
