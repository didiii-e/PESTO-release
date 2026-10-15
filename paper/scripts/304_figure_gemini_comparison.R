#!/usr/bin/env Rscript
# Figure 2 on Claude and on Gemini, compared (Supplementary Material).
#   a  verdicts by GenCC class (Fig. 2a) and ASC group (Fig. 2b), the two models
#      side by side
#   b  verdict of each of the 1,043 pairs under each model
#   c  evidence score of each pair under each model
#   d  the measures the paper reports on Fig. 2, both models, 95% bootstrap CI
#   e  model's internal knowledge and PESTO by window of first report (Fig. 2c),
#      both models
# Reads results/gemini_fig2/comparison/ (scripts/303_gemini_fig2_comparison.py).
#   Rscript scripts/304_figure_gemini_comparison.R
suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(ggplot2)
  library(patchwork)
  library(readr)
})
source(file.path(dirname(sub("--file=", "", grep("--file=", commandArgs(FALSE), value = TRUE)[1])), "_helvetica.R"))

root <- normalizePath(file.path(dirname(sub("--file=", "",
         grep("--file=", commandArgs(FALSE), value = TRUE)[1])), ".."))
CMP <- file.path(root, "results", "gemini_fig2", "comparison")
FIGURES <- file.path(root, "figures")

VERDICTS <- c("Novel", "Hypothesized", "Existing", "Established")
VCOL <- c(Novel = "#A9573F", Hypothesized = "#BFA45C",
          Existing = "#5B7F95", Established = "#2E5F4F")
MCOL <- c(Claude = "#35586B", Gemini = "#B07A4B")
MODEL_LAB <- c(claude = "Claude", gemini = "Gemini")

base_theme <- theme_classic(base_size = 15) +
  theme(axis.text = element_text(colour = "black", size = 12),
        axis.title = element_text(size = 13),
        legend.title = element_blank(),
        legend.text = element_text(size = 12),
        strip.background = element_blank(),
        strip.text = element_text(size = 12),
        plot.tag = element_text(face = "bold", size = 18))

groups <- read_tsv(file.path(CMP, "groups.tsv"), show_col_types = FALSE)
pairs <- read_tsv(file.path(CMP, "pairs.tsv"), show_col_types = FALSE)
metrics <- read_tsv(file.path(CMP, "metrics.tsv"), show_col_types = FALSE)
windows <- read_tsv(file.path(CMP, "windows.tsv"), show_col_types = FALSE)

GROUP_LEV <- c("Definitive", "Strong", "Moderate", "Limited", "Absent",
               "ASD known", "ASD candidate", "Novel candidate", "Not in ASD list")
panel_a <- groups %>%
  filter(panel %in% c("a", "b")) %>%
  pivot_longer(all_of(VERDICTS), names_to = "verdict", values_to = "pct") %>%
  mutate(group = factor(group, levels = GROUP_LEV),
         model = factor(MODEL_LAB[model], levels = names(MCOL)),
         verdict = factor(verdict, levels = VERDICTS)) %>%
  ggplot(aes(x = model, y = pct, fill = verdict)) +
  geom_col(width = 0.8) +
  facet_wrap(~ group, nrow = 1, labeller = label_wrap_gen(width = 10)) +
  scale_fill_manual(values = VCOL, breaks = VERDICTS) +
  scale_y_continuous(expand = expansion(mult = c(0, 0.02))) +
  labs(x = NULL, y = "% of pairs") +
  base_theme +
  theme(axis.text.x = element_text(angle = 45, hjust = 1),
        legend.position = "bottom")

panel_b <- pairs %>%
  count(claude_verdict, gemini_verdict) %>%
  complete(claude_verdict = VERDICTS, gemini_verdict = VERDICTS, fill = list(n = 0)) %>%
  mutate(claude_verdict = factor(claude_verdict, levels = VERDICTS),
         gemini_verdict = factor(gemini_verdict, levels = VERDICTS)) %>%
  ggplot(aes(x = claude_verdict, y = gemini_verdict, fill = n)) +
  geom_tile(colour = "white") +
  geom_text(aes(label = n, colour = n > 150), size = 4.2) +
  scale_colour_manual(values = c(`TRUE` = "white", `FALSE` = "grey15"), guide = "none") +
  scale_fill_gradient(low = "grey95", high = "#35586B", guide = "none") +
  labs(x = "Claude verdict", y = "Gemini verdict") +
  coord_equal() +
  base_theme +
  theme(axis.text.x = element_text(angle = 30, hjust = 1))

rho <- cor(pairs$claude_score, pairs$gemini_score, method = "spearman")
panel_c <- ggplot(pairs, aes(x = claude_score, y = gemini_score)) +
  geom_abline(slope = 1, intercept = 0, linetype = "dashed", colour = "grey55") +
  geom_point(alpha = 0.25, size = 1.1, colour = "#35586B") +
  annotate("text", x = 1.05, y = 3.95, hjust = 0, vjust = 1, size = 4.2,
           label = sprintf("Spearman \u03c1 = %.2f\nn = %d pairs", rho, nrow(pairs))) +
  scale_x_continuous(limits = c(1, 4), breaks = 1:4, labels = c("Novel", "Hypoth.", "Existing", "Estab.")) +
  scale_y_continuous(limits = c(1, 4), breaks = 1:4, labels = c("Novel", "Hypoth.", "Existing", "Estab.")) +
  coord_equal() +
  labs(x = "Claude evidence score", y = "Gemini evidence score") +
  base_theme

METRIC_LAB <- c(
  "AUC, Definitive+Strong vs Moderate+Limited" = "AUC, Definitive+Strong\nvs Moderate+Limited (score)",
  "AUC on verdicts, Definitive+Strong vs Moderate+Limited" = "AUC, Definitive+Strong\nvs Moderate+Limited (verdict)",
  "Average precision, curated vs Absent" = "Average precision,\ncurated vs Absent",
  "Spearman, score vs GenCC class" = "Spearman, score vs\nGenCC class",
  "Absent called Novel (%)" = "GenCC Absent\ncalled Novel (%)",
  "Not in ASD list called Novel (%)" = "Not in ASD list\ncalled Novel (%)",
  "Autism known called Established (%)" = "ASD known called\nEstablished (%)",
  "Autism candidate called Established (%)" = "ASD candidate called\nEstablished (%)")
m <- metrics %>%
  mutate(scale = ifelse(grepl("%", metric), "Percentage", "Index"),
         metric = factor(METRIC_LAB[metric], levels = rev(unname(METRIC_LAB))),
         model = factor(MODEL_LAB[model], levels = names(MCOL)))
dot <- function(d, xlab) {
  ggplot(d, aes(x = value, y = metric, colour = model)) +
    geom_errorbarh(aes(xmin = lo, xmax = hi), height = 0.25,
                   position = position_dodge(width = 0.6)) +
    geom_point(size = 2.6, position = position_dodge(width = 0.6)) +
    scale_colour_manual(values = MCOL) +
    labs(x = xlab, y = NULL) +
    base_theme +
    theme(legend.position = "none")
}
panel_d <- wrap_elements(full = dot(filter(m, scale == "Index"), "Value") |
                                 dot(filter(m, scale == "Percentage"), "% of pairs"))

WIN_LAB <- c("2011-2013" = "2011–13", "2014-2016" = "2014–16", "2017-2019" = "2017–19",
             "2020-2022" = "2020–22", "2023-2025" = "2023–25")
panel_e <- windows %>%
  mutate(model = factor(MODEL_LAB[model], levels = names(MCOL)),
         method = factor(method, levels = c("Model knowledge", "PESTO")),
         window = factor(WIN_LAB[window], levels = WIN_LAB)) %>%
  ggplot(aes(x = window, y = ap, colour = model, group = model)) +
  geom_line(linewidth = 0.8) +
  geom_point(size = 2.4) +
  facet_wrap(~ method, nrow = 1) +
  scale_colour_manual(values = MCOL) +
  scale_y_continuous(limits = c(0.6, 1)) +
  labs(x = "Year of first report in GenCC", y = "Average precision\nagainst the 100 Absent") +
  base_theme +
  theme(axis.text.x = element_text(angle = 30, hjust = 1), legend.position = "bottom")

fig <- wrap_plots(A = panel_a, B = panel_b, C = panel_c, D = panel_d, E = panel_e,
                  design = "AAAA\nBBCC\nDDDD\nEEEE") +
  plot_layout(heights = c(1.1, 1, 0.9, 0.9)) +
  plot_annotation(tag_levels = "A")
ggsave(file.path(FIGURES, "figure_supp_gemini_comparison.png"), fig, width = 13, height = 17, dpi = 300, bg = "white")
ggsave(file.path(FIGURES, "figure_supp_gemini_comparison.pdf"), fig, width = 13, height = 17, bg = "white")
cat("Wrote", file.path(FIGURES, "figure_supp_gemini_comparison.png"), "and .pdf\n")
