#!/usr/bin/env Rscript
# Supplementary Figure for Note 5 - the full-text mode.
#
#   a  the literature branch of Supplementary Figure 1 with what the full-text
#      mode adds (scripts/172_pipeline_detailed_schema.R, fulltext = TRUE)
#   b  returned label on the body-only benchmark, abstracts and fulltext
#   c  key PMIDs (the GWAS articles naming the gene) cited in the answer
#   d  literature-branch cost per pair on that benchmark
#   e  average precision on the 140 pairs of Fig. 2d (40 Limited 2023-2025 vs
#      100 Absent), abstracts and fulltext run the same day
#      (scripts/166_modes_benchmark_140.py, scripts/167_modes_benchmark_scores.py)
#
# Panels b-d read the body-only tables of PESTO-release/paper/results
# (bodyonly_summary.tsv, bodyonly_verdicts.tsv; scripts/150_bodyonly_data.py).
#
# Writes figures/figure_supp_fulltext.{png,pdf}.
# Usage: Rscript scripts/170_figure_supp_fulltext.R

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
  library(patchwork)
  library(readr)
})

root <- normalizePath(file.path(dirname(sub("--file=", "",
         grep("--file=", commandArgs(FALSE), value = TRUE)[1])), ".."))
if (is.na(root) || !dir.exists(root)) root <- normalizePath(".")
source(file.path(root, "scripts", "172_pipeline_detailed_schema.R"))

# The body-only tables live in PESTO-release/paper/results; run from there, they are local.
RELEASE <- if (file.exists(file.path(root, "results", "bodyonly_summary.tsv"))) file.path(root, "results") else
  file.path(dirname(root), "PESTO-release", "paper", "results")
MODES <- file.path(root, "results", "modes_benchmark_140")
FIGURES <- file.path(root, "figures")

VERDICTS <- c("Novel", "Hypothesized", "Existing", "Established")
VCOL <- c(Novel = "#A9573F", Hypothesized = "#BFA45C",
          Existing = "#5B7F95", Established = "#2E5F4F")
ARMS <- c("abstracts", "fulltext")
ACOL <- c(abstracts = "#000000", fulltext = "#0072B2")
GROUPS <- c("GWAS, gene in body only", "negative control")

base_theme <- theme_classic(base_size = 16) +
  theme(axis.text = element_text(colour = "black", size = 14),
        axis.title = element_text(size = 15),
        plot.title = element_text(size = 15, hjust = 0.5))

summ <- read_tsv(file.path(RELEASE, "bodyonly_summary.tsv"), show_col_types = FALSE) %>%
  mutate(arm = factor(arm, levels = ARMS))
verd <- read_tsv(file.path(RELEASE, "bodyonly_verdicts.tsv"), show_col_types = FALSE) %>%
  mutate(arm = factor(arm, levels = ARMS),
         group = factor(group, levels = GROUPS,
                        labels = c(sprintf("GWAS association,\ngene in body only (n = %d)",
                                           summ$positives[1]),
                                   sprintf("negative\ncontrols (n = %d)", summ$negatives[1]))),
         verdict = factor(verdict, levels = VERDICTS))

panel_b <- ggplot(verd, aes(arm, n, fill = verdict)) +
  geom_col(width = 0.7, position = "fill") +
  facet_wrap(~ group) +
  scale_fill_manual(values = VCOL, drop = FALSE, name = NULL) +
  scale_y_continuous(labels = function(x) paste0(100 * x),
                     expand = expansion(mult = c(0, 0.02))) +
  labs(x = NULL, y = "% of pairs", title = "Returned label") +
  base_theme +
  theme(strip.background = element_blank(), strip.text = element_text(size = 13),
        legend.position = "bottom", legend.text = element_text(size = 13))

panel_c <- ggplot(summ, aes(arm, 100 * pmids_cited / pmids_total, fill = arm)) +
  geom_col(width = 0.6) +
  geom_text(aes(label = sprintf("%d/%d", pmids_cited, pmids_total)),
            vjust = -0.4, size = 4.6, colour = "grey25") +
  scale_fill_manual(values = ACOL, guide = "none") +
  scale_y_continuous(limits = c(0, 100), expand = expansion(mult = c(0, 0.04))) +
  labs(x = NULL, y = "% of key PMIDs cited", title = "Deciding articles cited") +
  base_theme

panel_d <- ggplot(summ, aes(arm, usd_mean, fill = arm)) +
  geom_col(width = 0.6) +
  geom_errorbar(aes(ymin = usd_mean - usd_sd, ymax = usd_mean + usd_sd),
                width = 0.18, linewidth = 0.5, colour = "grey25") +
  geom_text(aes(y = usd_mean + usd_sd, label = sprintf("$%.3f", usd_mean)),
            vjust = -0.6, size = 4.6, colour = "grey25") +
  scale_fill_manual(values = ACOL, guide = "none") +
  scale_y_continuous(labels = function(x) sprintf("$%.2f", x),
                     expand = expansion(mult = c(0, 0.15))) +
  labs(x = NULL, y = "USD per pair (mean ± s.d.)", title = "Literature branch cost") +
  base_theme

ap <- read_tsv(file.path(MODES, "ap.tsv"), show_col_types = FALSE) %>%
  filter(run == "rerun", method %in% c("PESTO", "PESTO full text")) %>%
  mutate(arm = factor(ifelse(method == "PESTO", "abstracts", "fulltext"), levels = ARMS))
tests <- read_tsv(file.path(MODES, "tests.tsv"), show_col_types = FALSE)
p_ft <- tests$p_two_sided[tests$a == "PESTO full text" & tests$b == "PESTO"]
panel_e <- ggplot(ap, aes(arm, ap, fill = arm)) +
  geom_col(width = 0.6) +
  geom_errorbar(aes(ymin = lo, ymax = hi), width = 0.18, linewidth = 0.5, colour = "grey25") +
  geom_hline(yintercept = 40 / 140, linetype = "dashed", colour = "grey55", linewidth = 0.4) +
  annotate("segment", x = 1, xend = 2, y = 1.06, yend = 1.06, linewidth = 0.4,
           colour = "grey30") +
  annotate("text", x = 1.5, y = 1.11, label = sprintf("P = %.2f", p_ft), size = 4.6,
           colour = "grey25") +
  scale_fill_manual(values = ACOL, guide = "none") +
  scale_y_continuous(limits = c(0, 1.15), breaks = seq(0, 1, 0.2),
                     expand = expansion(mult = c(0, 0))) +
  labs(x = NULL, y = "Average precision", title = "Recent Limited vs Absent") +
  base_theme

schema <- wrap_elements(full = detailed_schema(fulltext = TRUE))
bottom <- (panel_b | panel_c | panel_d | panel_e) + plot_layout(widths = c(2, 1, 1, 1))
fig <- schema / bottom + plot_layout(heights = c(0.9, 1.05)) +
  plot_annotation(tag_levels = "a") &
  theme(plot.tag = element_text(face = "bold", size = 20))

out <- file.path(FIGURES, "figure_supp_fulltext")
ggsave(paste0(out, ".png"), fig, width = 16, height = 11.5, dpi = 400, bg = "white")
ggsave(paste0(out, ".pdf"), fig, width = 16, height = 11.5, bg = "white", device = cairo_pdf)
cat("Wrote", paste0(out, ".png"), "and .pdf\n")
