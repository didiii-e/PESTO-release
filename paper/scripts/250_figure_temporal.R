# The temporal figure: (a) illustrative PESTO trajectories of six pairs
# (scripts/249_figure_trajectories6.R) above (b) the baseline-class benchmark in the
# epilepsy and autism cohorts (scripts/246_figure_baseline_class_benchmark.R). Both
# panels are built by those scripts, which also rewrite their own figures.
#
#   Rscript scripts/250_figure_temporal.R
#     -> figures/figure_temporal.{png,pdf}, copied to figures/figure3.{png,pdf} (Figure 3 of v3)

source(file.path(dirname(sub("--file=", "", grep("--file=", commandArgs(FALSE), value = TRUE)[1])), "_helvetica.R"))
suppressPackageStartupMessages({
  library(ggplot2)
  library(cowplot)
})

root <- normalizePath(file.path(dirname(sub("--file=", "",
         grep("--file=", commandArgs(FALSE), value = TRUE)[1])), ".."))

panel <- function(script) {
  e <- new.env()
  sys.source(file.path(root, "scripts", script), envir = e)
  e$fig
}
a <- panel("249_figure_trajectories6.R")
b <- panel("246_figure_baseline_class_benchmark.R") +
  theme(plot.margin = margin(5, 22, 5, 5, unit = "mm"))

fig <- plot_grid(a, b, ncol = 1, rel_heights = c(1, 1.05), labels = c("A", "B"), align = "v", axis = "lr",
                 label_size = 20, label_fontface = "bold")
out <- file.path(root, "figures", "figure_temporal")
ggsave(paste0(out, ".png"), fig, width = 10, height = 10, dpi = 300, bg = "white")
ggsave(paste0(out, ".pdf"), fig, width = 10, height = 10, bg = "white", device = cairo_pdf, symbolfamily = grDevices::cairoSymbolFont(FONT, usePUA = FALSE))
for (ext in c(".png", ".pdf")) file.copy(paste0(out, ext), file.path(root, "figures", paste0("figure3", ext)), overwrite = TRUE)
message("wrote ", out, ".{png,pdf} and figures/figure3.{png,pdf}")
