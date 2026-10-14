#!/usr/bin/env Rscript
# Fetal cell-type enrichment of PESTO high-evidence genes, every one of the 77
# cell types of the Descartes fetal atlas grouped by cell class, in the style of
# Extended Data Fig. 4, from results/biology/fetal_cell_types_grid.tsv
# (scripts/230_fetal_cell_types.py; top 5% within the panel, Fisher's exact
# test). One star: P < 0.05; two: FDR < 0.05 over the 77 cell types within a
# phenotype.
#
#   Rscript scripts/231_fetal_cell_type_heatmap.R
# writes figures/figure_fetal_cell_types.{png,pdf}.

source(file.path(dirname(sub("--file=", "", grep("--file=", commandArgs(FALSE), value = TRUE)[1])), "_helvetica.R"))
suppressPackageStartupMessages({ library(dplyr); library(readr); library(ggplot2) })

root <- normalizePath(file.path(dirname(sub("--file=", "",
        grep("--file=", commandArgs(FALSE), value = TRUE)[1])), ".."))
SHORT <- c("ASD", "EPI", "SCZ", "BD", "AD", "CHD", "T2D")
CLASS <- c(neural = "Neural", glia = "Glia", muscle = "Muscle", endothelial = "Endothelial",
           fibroblast = "Stromal", adipose = "Stromal", precursor = "Stromal",
           secretory = "Secretory", epithelial = "Epithelial", ciliated = "Epithelial",
           "kidney specific" = "Epithelial", hepatocyte = "Epithelial", immune = "Blood",
           "stem cell" = "Blood", trophoblast = "Placenta", other = "Other")

g <- read_tsv(file.path(root, "results", "biology", "fetal_cell_types_grid.tsv"), show_col_types = FALSE) %>%
  mutate(group = factor(CLASS[cell_class], levels = unique(CLASS)),
         label = gsub("_", " ", cell_type),
         label = paste0(toupper(substring(label, 1, 1)), substring(label, 2)))
order <- g %>% filter(phenotype == "ASD") %>% arrange(group, label) %>% pull(label)
d <- g %>% mutate(phenotype = factor(phenotype, levels = SHORT),
                  label = factor(label, levels = rev(order)),
                  l2 = pmax(pmin(log2(pmax(or, 1e-3)), 3), -3),
                  mark = ifelse(fdr < 0.05, "**", ifelse(p < 0.05, "*", "")))
p <- ggplot(d, aes(phenotype, label, fill = l2)) +
  geom_tile(colour = "white", linewidth = 0.4) +
  geom_text(aes(label = mark), size = 5.8, vjust = 0.8) +  # Helvetica's asterisk is small and set high
  facet_grid(group ~ ., scales = "free_y", space = "free_y", switch = "y") +
  scale_fill_gradient2(low = "#2C6E8F", mid = "grey96", high = "#B33A3A", midpoint = 0,
                       limits = c(-3, 3), breaks = log2(c(0.125, 1, 8)),
                       labels = c("1/8", "1", "8"), name = "odds ratio") +
  scale_x_discrete(position = "top", expand = c(0, 0)) + scale_y_discrete(expand = c(0, 0)) +
  labs(x = NULL, y = NULL) +
  theme_minimal(base_size = 11) +
  theme(panel.grid = element_blank(), axis.text = element_text(colour = "black"),
        axis.text.x = element_text(face = "bold"), legend.position = "bottom",
        strip.placement = "outside", strip.text.y.left = element_text(angle = 0, face = "bold", hjust = 1),
        panel.spacing.y = unit(4, "pt"))
out <- file.path(root, "figures", "figure_fetal_cell_types.png")
ggsave(out, p, width = 7.4, height = 15, dpi = 300, bg = "white")
ggsave(sub("png$", "pdf", out), p, width = 7.4, height = 15, bg = "white")
cat("wrote", out, "\n")
