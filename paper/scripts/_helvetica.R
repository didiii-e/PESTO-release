# Helvetica in every figure. Sourced at the top of each figure script.
#
# ggplot2 themes, text geoms, patchwork tags and cowplot labels otherwise take
# the device's default family, which on Linux is fontconfig's "sans" (Noto Sans
# here), not Helvetica. Registering a font under "sans" does not help: ragg
# resolves the default family on its own. So the complete themes and the cowplot
# label functions are wrapped with Helvetica as their default family; scripts
# that call them unqualified pick the wrappers up from the global environment.
# On Linux, "Helvetica" resolves to Nimbus Sans, a metric clone; on macOS, to
# Helvetica itself.

suppressPackageStartupMessages(library(ggplot2))

FONT <- "Helvetica"

local({
  for (nm in c("theme_classic", "theme_minimal", "theme_bw", "theme_void", "theme_light",
               "theme_linedraw", "theme_gray", "theme_grey", "theme_dark")) {
    f <- get(nm, envir = asNamespace("ggplot2"))
    assign(nm, local({
      g <- f
      function(..., base_family = FONT) g(..., base_family = base_family)
    }), envir = globalenv())
  }
})
theme_set(ggplot2::theme_grey(base_family = FONT))
for (geom in c("text", "label")) update_geom_defaults(geom, list(family = FONT))

if (requireNamespace("cowplot", quietly = TRUE)) {
  plot_grid <- function(..., label_fontfamily = FONT) cowplot::plot_grid(..., label_fontfamily = label_fontfamily)
  draw_label <- function(..., fontfamily = FONT) cowplot::draw_label(..., fontfamily = fontfamily)
  draw_plot_label <- function(..., family = FONT) cowplot::draw_plot_label(..., family = family)
  theme_cowplot <- function(..., font_family = FONT) cowplot::theme_cowplot(..., font_family = font_family)
}
