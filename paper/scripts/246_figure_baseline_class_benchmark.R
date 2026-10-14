# Baseline PESTO class against later evidence, in two cohorts: the share of
# gene-disease pairs classified Existing or Established at the end date, by their
# class (Novel or Hypothesized) at the start date, with Wilson 95% intervals and
# one-sided Fisher's exact tests (Hypothesized > Novel).
#   Epilepsy: 200 EPIGEN candidate genes, 2010/12/31 -> 2026/10/11; the 73 Dinan
#     screened and 127 more of her frozen order (scripts/248_draw_epigen_extension.py;
#     benchmark/epigen_extension/transitions.tsv)
#   Autism: 200 genes with a de novo loss-of-function variant in Iossifov or De Rubeis
#     2014, 2014/09/30 -> 2026/10/11 (benchmark/asd_denovo2014/transitions.tsv;
#     scripts/245_draw_asd_denovo2014.py)
#
#   Rscript scripts/246_figure_baseline_class_benchmark.R
#     -> figures/figure_baseline_class_benchmark.{png,pdf}

source(file.path(dirname(sub("--file=", "", grep("--file=", commandArgs(FALSE), value = TRUE)[1])), "_helvetica.R"))
suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
  library(readr)
})

root <- normalizePath(file.path(dirname(sub("--file=", "",
         grep("--file=", commandArgs(FALSE), value = TRUE)[1])), ".."))

epi <- read_tsv(file.path(root, "benchmark", "epigen_extension", "transitions.tsv"),
                show_col_types = FALSE) %>%
  transmute(start = c2010, end = c2026)
asd <- read_tsv(file.path(root, "benchmark", "asd_denovo2014", "transitions.tsv"),
                show_col_types = FALSE) %>%
  transmute(start = c2014, end = c2026)

cohorts <- c(epilepsy = "Epilepsy",
             autism = "Autism")

wilson <- function(k, n, z = 1.96) {
  p <- k / n
  centre <- (p + z^2 / (2 * n)) / (1 + z^2 / n)
  half <- z * sqrt(p * (1 - p) / n + z^2 / (4 * n^2)) / (1 + z^2 / n)
  c(centre - half, centre + half)
}

summarise_cohort <- function(d, name) {
  d <- d %>% filter(start %in% c("Novel", "Hypothesized")) %>%
    mutate(high = end %in% c("Existing", "Established"))
  s <- d %>% group_by(start) %>% summarise(k = sum(high), n = n(), .groups = "drop")
  ci <- t(mapply(wilson, s$k, s$n))
  tab <- matrix(c(s$k[s$start == "Hypothesized"], s$n[s$start == "Hypothesized"] - s$k[s$start == "Hypothesized"],
                  s$k[s$start == "Novel"], s$n[s$start == "Novel"] - s$k[s$start == "Novel"]),
                nrow = 2, byrow = TRUE)
  s %>% mutate(cohort = name, p = k / n, lo = ci[, 1], hi = ci[, 2],
               fisher = fisher.test(tab, alternative = "greater")$p.value)
}

d <- bind_rows(summarise_cohort(epi, "epilepsy"), summarise_cohort(asd, "autism")) %>%
  mutate(cohort = factor(cohorts[cohort], levels = cohorts),
         start = factor(start, levels = c("Novel", "Hypothesized")),
         label = sprintf("%d/%d (%.0f%%)", k, n, 100 * p))
print(as.data.frame(d))

p_lab <- function(p) {
  if (p >= 0.001) return(sprintf("P == %.3f", p))
  e <- floor(log10(p))
  sprintf('P == "%.1f" %%*%% 10^%d', p / 10^e, e)
}
tests <- d %>% distinct(cohort, fisher) %>% mutate(lab = vapply(fisher, p_lab, ""))

fig <- ggplot(d, aes(start, p, colour = start)) +
  geom_errorbar(aes(ymin = lo, ymax = hi), width = 0.12, linewidth = 0.9) +
  geom_point(size = 4) +
  geom_text(aes(y = hi, label = label), vjust = -0.9, size = 4.6, colour = "grey20") +
  geom_segment(data = tests, aes(x = 1, xend = 2, y = 0.9, yend = 0.9), inherit.aes = FALSE,
               colour = "grey25", linewidth = 0.5) +
  geom_segment(data = tests, aes(x = 1, xend = 1, y = 0.88, yend = 0.9), inherit.aes = FALSE,
               colour = "grey25", linewidth = 0.5) +
  geom_segment(data = tests, aes(x = 2, xend = 2, y = 0.88, yend = 0.9), inherit.aes = FALSE,
               colour = "grey25", linewidth = 0.5) +
  geom_text(data = tests, aes(x = 1.5, y = 0.955, label = lab), parse = TRUE, inherit.aes = FALSE,
            size = 4.6, colour = "grey20") +
  facet_wrap(~cohort, nrow = 1) +
  scale_colour_manual(values = c(Novel = "#A9573F", Hypothesized = "#BFA45C"), name = "Category at baseline") +
  scale_y_continuous(labels = function(x) paste0(100 * x, "%"), limits = c(0, 1),
                     breaks = seq(0, 1, 0.2), expand = expansion(mult = c(0, 0.02))) +
  labs(x = "PESTO category at baseline", y = "Existing or Established in 2026") +
  theme_classic(base_size = 15) +
  theme(strip.background = element_blank(), strip.text = element_text(face = "bold", size = 15),
        axis.text = element_text(colour = "black"), panel.spacing = unit(22, "mm"),
        legend.position = "top")

out <- file.path(root, "figures", "figure_baseline_class_benchmark")
ggsave(paste0(out, ".png"), fig, width = 9, height = 5.2, dpi = 300, bg = "white")
ggsave(paste0(out, ".pdf"), fig, width = 9, height = 5.2, bg = "white", device = cairo_pdf, symbolfamily = grDevices::cairoSymbolFont(FONT, usePUA = FALSE))
message("wrote ", out, ".{png,pdf}")
