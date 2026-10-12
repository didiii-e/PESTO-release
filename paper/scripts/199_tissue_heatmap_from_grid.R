#!/usr/bin/env Rscript
# One tissue-enrichment heatmap drawn from results/tissue_enrichment/grid.tsv
# (scripts/198_tissue_enrichment_grid.R), for a chosen setting: stage (adult or
# fetal), whether GTEx cultured cells are in the reference (kept, removed; none
# for fetal), and the top fraction of tissue-specific genes (5%, 10%, 20%).
# One star: P < 0.05; two: FDR < 0.05 over tissues within a phenotype.
#
#   Rscript scripts/199_tissue_heatmap_from_grid.R adult kept 5%
# writes figures/figure_tissue_enrichment_adult_kept_top5.png; a fourth argument
# --clean drops the title and the note on stars (they go in the legend) and
# writes figures/figure_ed4_tissue_enrichment.{png,pdf} instead.

suppressPackageStartupMessages({ library(dplyr); library(readr); library(ggplot2) })

args <- commandArgs(TRUE)
stage <- args[1]; cells <- args[2]; top <- args[3]
clean <- "--clean" %in% args
root <- normalizePath(file.path(dirname(sub("--file=", "",
        grep("--file=", commandArgs(FALSE), value = TRUE)[1])), ".."))
SHORT <- c("ASD", "EPI", "SCZ", "BD", "AD", "CHD", "T2D")
TISSUES <- if (stage == "adult") {
  c("Brain", "Pituitary", "Nerve", "Heart", "Artery", "Muscle", "Adipose", "Liver", "Pancreas",
    "Kidney", "Lung", "Stomach", "Small Intestine", "Colon", "Spleen", "Whole Blood", "Skin",
    "Thyroid", "Adrenal Gland", "Testis")
} else {
  c("Cerebrum", "Cerebellum", "Eye", "Heart", "Muscle", "Lung", "Liver", "Pancreas", "Kidney",
    "Adrenal", "Stomach", "Intestine", "Spleen", "Thymus", "Placenta")
}

d <- read_tsv(file.path(root, "results", "tissue_enrichment", "grid.tsv"), show_col_types = FALSE) %>%
  filter(stage == !!stage, cells == !!cells, top == !!top) %>%
  mutate(phenotype = factor(phenotype, levels = SHORT),
         tissue = factor(tissue, levels = rev(TISSUES)),
         l2 = pmax(pmin(log2(pmax(or, 1e-3)), 3), -3),
         mark = ifelse(fdr < 0.05, "**", ifelse(p < 0.05, "*", "")))
title <- sprintf("%s, top %s tissue-specific genes%s", tools::toTitleCase(stage), top,
                 if (stage == "adult") sprintf(", cultured cells %s", cells) else "")
p <- ggplot(d, aes(phenotype, tissue, fill = l2)) +
  geom_tile(colour = "white", linewidth = 0.5) +
  geom_text(aes(label = mark), size = 5, vjust = 0.75) +
  scale_fill_gradient2(low = "#2C6E8F", mid = "grey96", high = "#B33A3A", midpoint = 0,
                       limits = c(-3, 3), breaks = log2(c(0.125, 1, 8)),
                       labels = c("1/8", "1", "8"), name = "odds ratio") +
  scale_x_discrete(position = "top", expand = c(0, 0)) + scale_y_discrete(expand = c(0, 0)) +
  labs(x = NULL, y = NULL, title = title,
       caption = "* P < 0.05;  ** FDR < 0.05 over tissues within a phenotype") +
  theme_minimal(base_size = 14) +
  theme(panel.grid = element_blank(), axis.text = element_text(colour = "black"),
        axis.text.x = element_text(face = "bold"), plot.title = element_text(face = "bold", size = 13),
        legend.position = "bottom")
if (clean) {
  p <- p + labs(title = NULL, caption = NULL)
  out <- file.path(root, "figures", "figure_ed4_tissue_enrichment.png")
  ggsave(out, p, width = 6.2, height = 7.8, dpi = 400, bg = "white")
  ggsave(sub("png$", "pdf", out), p, width = 6.2, height = 7.8, bg = "white")
} else {
  out <- file.path(root, "figures", sprintf("figure_tissue_enrichment_%s_%s_top%s.png", stage, cells,
                                            sub("%", "", top)))
  ggsave(out, p, width = 6.2, height = 8.2, dpi = 220, bg = "white")
}
cat("wrote", out, "\n")
