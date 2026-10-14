#!/usr/bin/env Rscript
# Supplementary Figure 7 (Supplementary Material Note 2): what the references
# listed by the model's internal knowledge are in PubMed, on the 200 dated
# GenCC Limited pairs of Fig. 2e, by 3-year window of first report.
#
# Usage: Rscript scripts/280_figure_supp_citations.R

source(file.path(dirname(sub("--file=", "", grep("--file=", commandArgs(FALSE), value = TRUE)[1])), "_helvetica.R"))
suppressPackageStartupMessages({
  library(ggplot2)
})

root <- normalizePath(file.path(dirname(sub("--file=", "",
         grep("--file=", commandArgs(FALSE), value = TRUE)[1])), ".."))
if (is.na(root) || !dir.exists(root)) root <- normalizePath(".")
RESULTS <- file.path(root, "results")
FIGURES <- file.path(root, "figures")

source(file.path(root, "scripts", "_panel_citations.R"))

base_theme <- theme_classic(base_size = 14) +
  theme(
    axis.text = element_text(colour = "black", size = 12),
    axis.title = element_text(size = 13),
    legend.title = element_blank(),
    legend.text = element_text(size = 12)
  )

fig <- citation_panel_fate(citation_data(RESULTS), base_theme) +
  theme(axis.text.x = element_text(angle = 20, hjust = 1),
        legend.position = "right")

ggsave(file.path(FIGURES, "figure_supp_citations.png"), fig,
       width = 9, height = 4.6, dpi = 300, bg = "white")
ggsave(file.path(FIGURES, "figure_supp_citations.pdf"), fig,
       width = 9, height = 4.6, bg = "white", device = cairo_pdf)
cat("Wrote figures/figure_supp_citations.png and .pdf\n")
