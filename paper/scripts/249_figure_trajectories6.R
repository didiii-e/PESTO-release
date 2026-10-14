# Illustrative PESTO trajectories for six pairs of the two baseline-class cohorts,
# one per outcome type: in epilepsy KCNC1 (Hypothesized, then Established), CHRNA1
# (Novel throughout) and TRAPPC4 (Novel, then Established); in autism GRIA2
# (Hypothesized, then Established), MYH2 (Novel throughout) and LRRTM2 (Hypothesized
# throughout). Each pair is scored with PubMed capped at Dinan's grid of dates
# (every five years 1975-2005, every two years 2010-2024; benchmark/trajectories6/),
# plus the cohort runs at the autism start date (2014/09/30) and on 2026/10/11. The
# score is the confidence-weighted mean of the four levels (1 Novel to 4
# Established), on the category bands of Fig. 2c; the dashed line marks the start date
# of the cohort.
#
#   Rscript scripts/249_figure_trajectories6.R
#     -> figures/figure_trajectories6.{png,pdf}

source(file.path(dirname(sub("--file=", "", grep("--file=", commandArgs(FALSE), value = TRUE)[1])), "_helvetica.R"))
suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
  library(readr)
})

root <- normalizePath(file.path(dirname(sub("--file=", "",
         grep("--file=", commandArgs(FALSE), value = TRUE)[1])), ".."))
B <- file.path(root, "benchmark")

score_of <- function(d) {
  d %>% mutate(score = (p_novel + 2 * p_hypothesized + 3 * p_existing + 4 * p_established) /
                 (p_novel + p_hypothesized + p_existing + p_established))
}
read_run <- function(path, when) {
  read_tsv(path, show_col_types = FALSE) %>% score_of() %>%
    transmute(gene, phenotype, when = when, score, class = lit_mean)
}

grid <- bind_rows(lapply(Sys.glob(file.path(B, "trajectories6", "pesto_[0-9][0-9][0-9][0-9].tsv")), function(f) {
  read_run(f, as.numeric(sub(".*pesto_([0-9]{4}).tsv", "\\1", f)) + 1)
}))
genes <- unique(grid$gene)
extra <- bind_rows(
  read_run(file.path(B, "asd_denovo2014", "pesto_2014.tsv"), 2014 + 9 / 12),
  read_run(file.path(B, "asd_denovo2014", "pesto_2026.tsv"), 2026 + 9.4 / 12),
  read_run(file.path(B, "epigen_extension", "pesto_2026.tsv"), 2026 + 9.4 / 12)
) %>% filter(gene %in% genes) %>% semi_join(distinct(grid, gene, phenotype), by = c("gene", "phenotype"))
d <- bind_rows(grid, extra) %>% arrange(gene, when)

start <- c(epilepsy = 2011, "Autism Spectrum Disorder" = 2014 + 9 / 12)
d <- d %>%
  mutate(disease = factor(ifelse(phenotype == "epilepsy", "Epilepsy", "Autism"), levels = c("Epilepsy", "Autism")),
         t0 = start[phenotype]) %>%
  group_by(gene) %>%
  mutate(start_class = class[which.min(abs(when - t0))]) %>%
  ungroup()
print(as.data.frame(d %>% distinct(gene, disease, start_class)))

nudge <- c(KCNC1 = 0.13, TRAPPC4 = -0.13)
ends <- d %>% group_by(gene) %>% slice_max(when, n = 1) %>% ungroup() %>%
  mutate(label_y = score + ifelse(gene %in% names(nudge), nudge[gene], 0))
vlines <- tibble(disease = factor(c("Epilepsy", "Autism"), levels = c("Epilepsy", "Autism")),
                 t0 = c(2011, 2014 + 9 / 12))
# Category bands as in Fig. 2c: the verdict is the rounded score, so the bands
# change at 1.5, 2.5 and 3.5; pairs share one neutral colour, the class at
# baseline being shown in panel b.
bands <- tibble(ymin = c(0.9, 1.5, 2.5, 3.5), ymax = c(1.5, 2.5, 3.5, 4.1),
                fill = c("#F3F3F3", "#E8E8E8", "#F3F3F3", "#E8E8E8"))
LINE <- "#3E5468"

fig <- ggplot(d, aes(when, score, group = gene)) +
  geom_rect(data = bands, aes(xmin = -Inf, xmax = Inf, ymin = ymin, ymax = ymax, fill = fill),
            inherit.aes = FALSE, colour = NA) +
  scale_fill_identity() +
  geom_hline(yintercept = c(1.5, 2.5, 3.5), linewidth = 0.25, colour = "grey78") +
  geom_vline(data = vlines, aes(xintercept = t0), linetype = "dashed", colour = "grey45",
             linewidth = 0.5, inherit.aes = FALSE) +
  geom_line(linewidth = 1, colour = LINE) +
  geom_point(size = 2, colour = LINE) +
  geom_text(data = ends, aes(y = label_y, label = gene), hjust = -0.15, size = 4.4, fontface = "italic",
            colour = LINE) +
  facet_wrap(~disease, nrow = 1) +
  scale_x_continuous(breaks = c(1975, 1985, 1995, 2005, 2015, 2025),
                     expand = expansion(mult = c(0.01, 0.02))) +
  scale_y_continuous(breaks = c(1.2, 2, 3, 3.8), labels = c("Novel", "Hypothesized", "Existing", "Established"),
                     expand = expansion(mult = c(0, 0))) +
  coord_cartesian(ylim = c(0.9, 4.1), clip = "off") +
  labs(x = "Publication cutoff year", y = NULL) +
  theme_classic(base_size = 15) +
  theme(strip.background = element_blank(), strip.text = element_text(face = "bold", size = 15),
        axis.text = element_text(colour = "black"), axis.ticks.y = element_blank(),
        axis.title.x = element_text(margin = margin(t = 8)),
        panel.spacing = unit(22, "mm"), plot.margin = margin(5, 22, 5, 5, unit = "mm"))

out <- file.path(root, "figures", "figure_trajectories6")
ggsave(paste0(out, ".png"), fig, width = 10, height = 4.8, dpi = 300, bg = "white")
ggsave(paste0(out, ".pdf"), fig, width = 10, height = 4.8, bg = "white", device = cairo_pdf, symbolfamily = grDevices::cairoSymbolFont(FONT, usePUA = FALSE))
message("wrote ", out, ".{png,pdf}")
