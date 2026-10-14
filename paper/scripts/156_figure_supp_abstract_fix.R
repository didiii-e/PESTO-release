#!/usr/bin/env Rscript
# Supplementary Figure 1 - first-section versus complete structured abstracts.
#
# Twenty runs spread over Figures 1-3, replayed on the same records with whole
# abstracts (scripts/155_abstract_fix_check.py). Each point is a pair: evidence
# score as published (first abstract section) against the replay (all
# sections), coloured by the published verdict; pairs whose rounded verdict
# changed are labelled. Category boundaries at 1.5, 2.5 and 3.5 are drawn.
#
# Reads results/abstract_fix_check.tsv. Writes
# figures/figure_supp_abstract_fix.{png,pdf}.
#
# Usage: Rscript scripts/156_figure_supp_abstract_fix.R

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
  library(readr)
})

root <- normalizePath(file.path(dirname(sub("--file=", "",
         grep("--file=", commandArgs(FALSE), value = TRUE)[1])), ".."))
if (is.na(root) || !dir.exists(root)) root <- normalizePath(".")

VERDICTS <- c("Novel", "Hypothesized", "Existing", "Established")
VCOL <- c(Novel = "#A9573F", Hypothesized = "#BFA45C",
          Existing = "#5B7F95", Established = "#2E5F4F")

d <- read_tsv(file.path(root, "results", "abstract_fix_check.tsv"), show_col_types = FALSE) %>%
  mutate(old_call = factor(old_call, levels = VERDICTS),
         changed = as.character(old_call) != new_call,
         label = ifelse(changed, paste0(gene, ": ", old_call, " → ", new_call), NA))
# Labels are placed by hand: the changed pairs sit near the edges, where an
# automatic placer pushes them off the panel. The two low labels go one below and one above.
lab <- d %>% filter(changed) %>% arrange(old_mean) %>%
  mutate(low = new_mean < 2,
         lx = ifelse(low, old_mean + 0.55, 3.95),
         ly = ifelse(low, new_mean + ifelse(row_number() == 1, -0.2, 0.25), new_mean - 1.1),
         hj = ifelse(low, 0, 1))

rho <- cor(d$old_mean, d$new_mean, method = "spearman")
same <- sum(!d$changed)
# The signed-rank P is quoted in the text from scripts/155_abstract_fix_check.py;
# R's normal approximation gives a slightly different value, so it is not drawn.
stats <- sprintf("%d of %d verdicts unchanged\nSpearman \u03c1 = %.2f", same, nrow(d), rho)

p <- ggplot(d, aes(old_mean, new_mean)) +
  geom_hline(yintercept = c(1.5, 2.5, 3.5), colour = "grey88", linewidth = 0.4) +
  geom_vline(xintercept = c(1.5, 2.5, 3.5), colour = "grey88", linewidth = 0.4) +
  geom_abline(slope = 1, intercept = 0, linetype = "dashed", colour = "grey50") +
  geom_point(aes(fill = old_call), shape = 21, size = 3.2, colour = "white", stroke = 0.4) +
  geom_segment(data = lab, aes(x = old_mean, y = new_mean, xend = lx, yend = ly),
               colour = "grey60", linewidth = 0.35) +
  geom_text(data = lab, aes(x = lx, y = ly, label = label, hjust = hj), size = 3.2,
            colour = "grey20", vjust = 0.5) +
  annotate("text", x = 1.02, y = 3.98, label = stats, hjust = 0, vjust = 1, size = 3.5,
           colour = "grey20") +
  scale_fill_manual(values = VCOL, drop = FALSE, name = "Published verdict") +
  scale_x_continuous(limits = c(1, 4), breaks = 1:4, labels = VERDICTS) +
  scale_y_continuous(limits = c(1, 4), breaks = 1:4, labels = VERDICTS) +
  coord_equal() +
  labs(x = "Evidence score, first abstract section (published)",
       y = "Evidence score, complete abstracts") +
  theme_classic(base_size = 13) +
  theme(axis.text = element_text(colour = "black"),
        legend.position = "right")

out <- file.path(root, "figures", "figure_supp_abstract_fix")
ggsave(paste0(out, ".png"), p, width = 7.6, height = 5.6, dpi = 300, bg = "white")
ggsave(paste0(out, ".pdf"), p, width = 7.6, height = 5.6, bg = "white", device = cairo_pdf)
cat("Wrote", paste0(out, ".png"), "and .pdf\n")
cat(stats, "\n")
