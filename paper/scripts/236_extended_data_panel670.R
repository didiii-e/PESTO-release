#!/usr/bin/env Rscript
# Extended Data Figs. 4 and 5 for the 670-gene panel (results/panel670/, built by
# scripts/233_run_panel570.sh panel670 fig3_add_t2d_bipex2 fig3_add_random100).
#   Extended Data Fig. 4: a, the 20 adult GTEx tissues (as scripts/199, adult,
#     cultured cells kept, top 5%); b, the 33 adult cell types of
#     scripts/214_cell_type_heatmaps.R (every Human Protein Atlas brain type, then
#     the main cell type of each tissue of panel a, plus retina and fibroblasts).
#   Extended Data Fig. 5: fetal cell types and tissues (Descartes atlas), the rows
#     of scripts/235_fetal_old_new_heatmap.R, for this panel only.
# One star P < 0.05; two FDR < 0.05 over the rows tested within a phenotype (20
# tissues, 154 adult or 77 fetal cell types, 15 fetal tissues).
#
#   Rscript scripts/236_extended_data_panel670.R [workspace, default panel670]
# writes figures/figure_ed4_<workspace>.{png,pdf} and figures/figure_ed5_<workspace>.{png,pdf}.
# With "." as workspace (PESTO-release/paper), the tables are read from results/ and
# the figures written as figures/figure_ed4.{png,pdf} and figures/figure_ed5.{png,pdf}.

suppressPackageStartupMessages({ library(dplyr); library(readr); library(ggplot2); library(cowplot) })

root <- normalizePath(file.path(dirname(sub("--file=", "",
        grep("--file=", commandArgs(FALSE), value = TRUE)[1])), ".."))
WS <- if (length(commandArgs(TRUE))) commandArgs(TRUE)[1] else "panel670"
RES <- if (WS == ".") file.path(root, "results") else file.path(root, "results", WS, "results")
STEM <- function(n) if (WS == ".") n else paste0(n, "_", WS)
SHORT <- c("ASD", "EPI", "SCZ", "BD", "AD", "CHD", "T2D")
FILL <- scale_fill_gradient2(low = "#2C6E8F", mid = "grey96", high = "#B33A3A", midpoint = 0,
                             limits = c(-3, 3), breaks = log2(c(0.125, 1, 8)),
                             labels = c("1/8", "1", "8"), name = "odds ratio")
cap <- function(x) { x <- gsub("_", " ", x); paste0(toupper(substring(x, 1, 1)), substring(x, 2)) }
prep <- function(d) d %>% mutate(phenotype = factor(phenotype, levels = SHORT),
                                 l2 = pmax(pmin(log2(pmax(or, 1e-3)), 3), -3),
                                 mark = ifelse(fdr < 0.05, "**", ifelse(p < 0.05, "*", "")))
heat <- function(d, facet = TRUE, text = 4.6, base = 13) {
  p <- ggplot(d, aes(phenotype, row, fill = l2)) +
    geom_tile(colour = "white", linewidth = 0.5) +
    geom_text(aes(label = mark), size = text, vjust = 0.75) + FILL +
    scale_x_discrete(position = "top", expand = c(0, 0)) + scale_y_discrete(expand = c(0, 0)) +
    labs(x = NULL, y = NULL) + theme_minimal(base_size = base) +
    theme(panel.grid = element_blank(), axis.text = element_text(colour = "black"),
          axis.text.x = element_text(face = "bold"), legend.position = "bottom",
          strip.placement = "outside", strip.switch.pad.grid = unit(4, "mm"),
          strip.text.y.left = element_text(angle = 90, face = "bold", margin = margin(r = 4, l = 4)),
          panel.spacing.y = unit(6, "pt"))
  if (facet) p <- p + facet_grid(group ~ ., scales = "free_y", space = "free_y", switch = "y")
  p
}

TISSUES <- c("Brain", "Pituitary", "Nerve", "Heart", "Artery", "Muscle", "Adipose", "Liver", "Pancreas",
             "Kidney", "Lung", "Stomach", "Small Intestine", "Colon", "Spleen", "Whole Blood", "Skin",
             "Thyroid", "Adrenal Gland", "Testis")
tis <- read_tsv(file.path(RES, "tissue_enrichment", "grid.tsv"), show_col_types = FALSE) %>%
  filter(stage == "adult", cells == "kept", top == "5%", tissue %in% TISSUES) %>%
  mutate(row = factor(tissue, levels = rev(TISSUES))) %>% prep()

BRAIN <- c("brain excitatory neurons", "brain inhibitory neurons", "other brain neurons", "astrocytes",
           "oligodendrocytes", "oligodendrocyte progenitor cells", "microglia", "bergmann glia",
           "ependymal cells", "choroid plexus epithelial cells")
OTHER <- c("retinal ganglion cells", "somatotrophs", "schwann cells", "cardiomyocytes",
           "vascular endothelial cells", "vascular smooth muscle cells", "myonuclei", "adipocytes",
           "fibroblasts", "hepatocytes", "pancreatic islet cells", "pancreatic acinar cells",
           "proximal tubule cells", "alveolar cells type 2", "parietal cells", "enterocytes",
           "colonocytes", "t-cells", "b-cells", "macrophages", "basal keratinocytes",
           "adrenal cortex cells", "sertoli cells")
LAB <- c("brain excitatory neurons" = "Excitatory neurons", "brain inhibitory neurons" = "Inhibitory neurons",
         "oligodendrocyte progenitor cells" = "Oligodendrocyte precursors",
         "choroid plexus epithelial cells" = "Choroid plexus epithelium",
         "somatotrophs" = "Pituitary somatotrophs", "vascular smooth muscle cells" = "Vascular smooth muscle",
         "myonuclei" = "Skeletal muscle fibres", "proximal tubule cells" = "Kidney proximal tubule",
         "parietal cells" = "Gastric parietal cells", "t-cells" = "T cells", "b-cells" = "B cells")
lab <- function(x) ifelse(x %in% names(LAB), LAB[x], cap(x))
cel <- read_tsv(file.path(RES, "biology", "cell_types_grid.tsv"), show_col_types = FALSE) %>%
  filter(cell_type %in% c(BRAIN, OTHER)) %>%
  mutate(group = factor(ifelse(cell_type %in% BRAIN, "Brain", "Other tissues"), c("Brain", "Other tissues")),
         row = factor(lab(cell_type), levels = rev(lab(c(BRAIN, OTHER))))) %>% prep()

ed4 <- plot_grid(heat(tis, facet = FALSE), heat(cel), ncol = 2, rel_widths = c(1, 1.1),
                 labels = c("a", "b"), label_size = 20, label_fontface = "bold", align = "h", axis = "t")
out <- file.path(root, "figures", paste0(STEM("figure_ed4"), ".png"))
ggsave(out, ed4, width = 13.5, height = 11.5, dpi = 400, bg = "white")
ggsave(sub("png$", "pdf", out), ed4, width = 13.5, height = 11.5, bg = "white")
cat("wrote", out, "\n")

CELLS <- list("Neurons" = c("excitatory_neuron", "inhibitory_neuron", "inhibitory_interneuron",
                            "limbic_system_neuron", "Purkinje_neuron", "granule_neuron"),
              "Glia" = c("astrocyte", "oligodendrocyte", "microglial_cell", "Schwann_cell"),
              "Heart" = c("cardiomyocyte", "endocardial_cell", "epicardial_adipose_cell",
                          "vascular_endothelial_cell"),
              "Pancreas, liver" = c("islet_endocrine_cell", "acinar_cell", "hepatoblast"))
FT <- c("Cerebrum", "Cerebellum", "Heart", "Pancreas", "Placenta")
fg <- read_tsv(file.path(RES, "biology", "fetal_cell_types_grid.tsv"), show_col_types = FALSE)
ft <- read_tsv(file.path(RES, "tissue_enrichment", "grid.tsv"), show_col_types = FALSE) %>%
  filter(stage == "fetal", top == "5%", tissue %in% FT)
fetal <- bind_rows(
  bind_rows(lapply(names(CELLS), function(g) fg %>% filter(cell_type %in% CELLS[[g]]) %>%
                     transmute(group = g, row = cap(cell_type), phenotype, or, p, fdr))),
  ft %>% transmute(group = "Tissues", row = paste(tissue, "(tissue)"), phenotype, or, p, fdr)) %>%
  mutate(group = factor(group, levels = c(names(CELLS), "Tissues")),
         row = factor(row, levels = rev(c(unlist(lapply(CELLS, cap)), paste(FT, "(tissue)"))))) %>% prep()
ed5 <- heat(fetal) + theme(strip.text.y.left = element_text(angle = 0, face = "bold", hjust = 1))
out <- file.path(root, "figures", paste0(STEM("figure_ed5"), ".png"))
ggsave(out, ed5, width = 7.2, height = 8.6, dpi = 400, bg = "white")
ggsave(sub("png$", "pdf", out), ed5, width = 7.2, height = 8.6, bg = "white")
cat("wrote", out, "\n")
