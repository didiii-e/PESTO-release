# What PESTO and the model's internal knowledge can cite, on the 200 dated
# GenCC Limited pairs of Fig. 2c,d (2010 set aside, as there).
#
# source() this file, then:
#   cd <- citation_data(results_dir)
#   citation_panel_e(cd, theme)     Fig. 2e
#   citation_panel_f(cd, theme)     Fig. 2f
#   citation_panel_fate(cd, theme)  Supplementary Figure 7 (Note 2)
#   citation_counts(cd)             the numbers the text quotes
#
# PESTO cites only articles it read, so its PMIDs are the papers. The model's
# internal knowledge is split: the PMID it gave is the paper, or the paper it
# described qualifies but the PMID it gave points elsewhere.
#   e     all pairs: do the citations include a PMID GenCC curators submitted
#         for the pair? Exact McNemar per window, same pairs for both.
#   f     pairs the configuration itself calls Existing or Established, i.e.
#         where it asserts human genetic evidence: does a cited paper hold such
#         evidence for the pair, as judged by Claude Haiku 4.5 from the abstract
#         (label A)? Fisher's exact test per window, the two sets of pairs
#         being different.
#   fate  what each reference of the model's internal knowledge is in PubMed.
#
# Reads results/knowledge_citations/pair_summary.tsv and ref_checks.tsv, from
# scripts/272_knowledge_citations.py and scripts/273_verify_citations.py.

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
  library(tidyr)
  library(readr)
})

CIT_YEARS <- c("2011-2013", "2014-2016", "2017-2019", "2020-2022", "2023-2025")
CIT_YEAR_LAB <- c("2011-2013" = "2011–13", "2014-2016" = "2014–16",
                  "2017-2019" = "2017–19", "2020-2022" = "2020–22",
                  "2023-2025" = "2023–25")
CIT_PESTO <- "#2E5F4F"
CIT_KNOW <- "#7A4E6A"
CIT_KNOW_LIGHT <- "#C9AFC0"
CIT_FILL <- c("Model knowledge, PMID correct",
              "Model knowledge, paper qualifies, PMID wrong", "PESTO")
CIT_FILL_COL <- setNames(c(CIT_KNOW, CIT_KNOW_LIGHT, CIT_PESTO), CIT_FILL)
CIT_FATE <- c(pmid_correct = "Real article, PMID correct",
              pmid_wrong_paper_real = "Real article, PMID points elsewhere",
              no_pmid_resolved = "Real article, no PMID given",
              pmid_wrong_unresolved = "Not found, PMID points elsewhere",
              no_pmid_unresolved = "Not found, no PMID given")
CIT_FATE_COL <- setNames(c(CIT_KNOW, CIT_KNOW_LIGHT, "#9DB3C2", "#A9573F", "#D9A08A"),
                         CIT_FATE)
CIT_DODGE <- 0.78

cit_wilson <- function(k, n, z = 1.96) {
  if (n == 0) return(c(NA_real_, NA_real_))
  p <- k / n
  centre <- (p + z^2 / (2 * n)) / (1 + z^2 / n)
  half <- z * sqrt(p * (1 - p) / n + z^2 / (4 * n^2)) / (1 + z^2 / n)
  c(centre - half, centre + half)
}

cit_stars <- function(p) ifelse(p < 0.001, "***", ifelse(p < 0.01, "**",
                                ifelse(p < 0.05, "*", "ns")))

citation_data <- function(results_dir) {
  dir <- file.path(results_dir, "knowledge_citations")
  pairs <- read_tsv(file.path(dir, "pair_summary.tsv"), show_col_types = FALSE) %>%
    filter(bin %in% CIT_YEARS) %>%
    mutate(bin = factor(bin, levels = CIT_YEARS))
  refs <- read_tsv(file.path(dir, "ref_checks.tsv"), show_col_types = FALSE,
                   col_types = cols(.default = col_character())) %>%
    filter(bin %in% CIT_YEARS) %>%
    mutate(bin = factor(bin, levels = CIT_YEARS))
  stopifnot(all(table(pairs$bin, pairs$arm) == 40))
  stopifnot(all(refs$label[refs$resolved_pmid != "" & !is.na(refs$resolved_pmid)]
                %in% c("A", "B", "C")))
  judged <- refs %>%
    group_by(gene, phenotype, arm) %>%
    summarise(any_A = any(label == "A", na.rm = TRUE),
              any_A_exact_pmid = any(label == "A" & status == "pmid_correct", na.rm = TRUE),
              .groups = "drop")
  pairs <- pairs %>%
    select(-any_A) %>%
    left_join(judged, by = c("gene", "phenotype", "arm")) %>%
    mutate(any_A = coalesce(any_A, FALSE),
           any_A_exact_pmid = coalesce(any_A_exact_pmid, FALSE))
  list(pairs = pairs, refs = refs)
}

# d: one row per pair and arm, with `hit` (a qualifying paper, any PMID) and
# `exact` (reached through the PMID given).
cit_split <- function(d) {
  counts <- d %>%
    group_by(bin, arm) %>%
    summarise(n = n(), k = sum(hit), exact = sum(exact), .groups = "drop") %>%
    complete(bin, arm, fill = list(n = 0L, k = 0L, exact = 0L))
  bars <- bind_rows(
    counts %>% filter(arm == "pesto") %>%
      mutate(fill = "PESTO", value = ifelse(n > 0, k / n, 0)),
    counts %>% filter(arm == "knowledge") %>%
      mutate(fill = CIT_FILL[1], value = ifelse(n > 0, exact / n, 0)),
    counts %>% filter(arm == "knowledge") %>%
      mutate(fill = CIT_FILL[2], value = ifelse(n > 0, (k - exact) / n, 0))
  ) %>%
    mutate(fill = factor(fill, levels = rev(CIT_FILL)))
  totals <- counts %>% rowwise() %>%
    mutate(value = ifelse(n > 0, k / n, 0),
           lo = cit_wilson(k, n)[1], hi = cit_wilson(k, n)[2]) %>%
    ungroup()
  list(bars = bars, totals = totals, counts = counts)
}

cit_e_data <- function(cd) {
  cd$pairs %>% transmute(bin, gene, phenotype, arm,
                         hit = any_gencc, exact = any_gencc_exact_pmid)
}

cit_f_data <- function(cd) {
  cd$pairs %>% filter(present) %>%
    transmute(bin, gene, phenotype, arm, hit = any_A, exact = any_A_exact_pmid)
}

# Exact McNemar on the same pairs, the model's internal knowledge credited with
# every curated paper it described, whatever PMID it gave.
cit_e_tests <- function(cd) {
  cit_e_data(cd) %>%
    select(bin, gene, phenotype, arm, hit) %>%
    pivot_wider(names_from = arm, values_from = hit) %>%
    group_by(bin) %>%
    summarise(b = sum(pesto & !knowledge), c = sum(!pesto & knowledge), .groups = "drop") %>%
    mutate(p = mapply(function(b, c) if (b + c == 0) 1 else
                        binom.test(min(b, c), b + c)$p.value, b, c))
}

cit_f_tests <- function(cd) {
  cit_split(cit_f_data(cd))$counts %>%
    select(bin, arm, n, k) %>%
    pivot_wider(names_from = arm, values_from = c(n, k)) %>%
    rowwise() %>%
    mutate(p = fisher.test(matrix(c(k_pesto, n_pesto - k_pesto,
                                    k_knowledge, n_knowledge - k_knowledge),
                                  nrow = 2))$p.value) %>%
    ungroup()
}

cit_xpos <- function(bin, arm) {
  as.integer(bin) + ifelse(arm == "pesto", 1, -1) * CIT_DODGE / 4
}

cit_split_panel <- function(sb, tests, ylab, theme_base, show_n = FALSE) {
  bars <- sb$bars %>% mutate(x = cit_xpos(bin, arm))
  totals <- sb$totals %>% mutate(x = cit_xpos(bin, arm))
  br <- tests %>%
    mutate(x = as.integer(bin),
           y = sapply(bin, function(b) max(totals$hi[totals$bin == b], na.rm = TRUE)) + 0.05,
           lab = cit_stars(p))
  g <- ggplot() +
    geom_col(data = bars, aes(x = x, y = value, fill = fill),
             position = "stack", width = CIT_DODGE / 2 * 0.92) +
    geom_errorbar(data = totals, aes(x = x, ymin = lo, ymax = hi),
                  width = 0.12, linewidth = 0.45, colour = "grey25") +
    geom_segment(data = br, aes(x = x - CIT_DODGE / 4, xend = x + CIT_DODGE / 4,
                                y = y, yend = y),
                 colour = "grey25", linewidth = 0.4) +
    # Helvetica's asterisk is small and set high, so stars are drawn larger and lower than "ns".
    geom_text(data = br, aes(x = x, y = y, label = lab),
              vjust = ifelse(br$lab == "ns", -0.45, 0.25), size = ifelse(br$lab == "ns", 4.2, 6.7),
              colour = "grey25")
  if (show_n) {
    g <- g + geom_text(data = totals, aes(x = x, y = 0, label = n),
                       vjust = 1.6, size = 3.3, colour = "grey35")
  }
  g +
    scale_fill_manual(values = CIT_FILL_COL, breaks = CIT_FILL) +
    scale_x_continuous(breaks = seq_along(CIT_YEARS), labels = CIT_YEAR_LAB[CIT_YEARS],
                       expand = expansion(add = 0.5)) +
    scale_y_continuous(labels = function(v) paste0(100 * v, "%"),
                       breaks = seq(0, 1, 0.2), expand = expansion(mult = c(0, 0))) +
    coord_cartesian(ylim = c(0, 1.12), clip = "off") +
    labs(x = "Year of first report in GenCC", y = ylab) +
    guides(fill = guide_legend(ncol = 1), y = guide_axis(cap = "upper")) +
    theme_base +
    theme(aspect.ratio = 1,
          axis.text.x = element_text(angle = 45, hjust = 1,
                                     margin = margin(t = if (show_n) 14 else 2)))
}

citation_panel_e <- function(cd, theme_base) {
  cit_split_panel(cit_split(cit_e_data(cd)), cit_e_tests(cd),
                  "Pairs citing a GenCC curated paper", theme_base)
}

citation_panel_f <- function(cd, theme_base) {
  cit_split_panel(cit_split(cit_f_data(cd)), cit_f_tests(cd),
                  "Existing or Established calls\nbacked by a cited paper",
                  theme_base, show_n = TRUE)
}

citation_panel_fate <- function(cd, theme_base) {
  fate <- cd$refs %>% filter(arm == "knowledge") %>%
    mutate(fate = factor(CIT_FATE[status], levels = rev(CIT_FATE))) %>%
    count(bin, fate) %>%
    group_by(bin) %>% mutate(share = n / sum(n), total = sum(n)) %>% ungroup()
  stopifnot(!any(is.na(fate$fate)))
  ggplot(fate, aes(x = bin, y = share, fill = fate)) +
    geom_col(width = 0.66) +
    geom_text(data = distinct(fate, bin, total), inherit.aes = FALSE,
              aes(x = bin, y = 1, label = paste0("n=", total)),
              vjust = -0.5, size = 3.4, colour = "grey25") +
    scale_fill_manual(values = CIT_FATE_COL, breaks = unname(CIT_FATE)) +
    scale_x_discrete(labels = CIT_YEAR_LAB) +
    scale_y_continuous(labels = function(v) paste0(100 * v, "%"),
                       breaks = seq(0, 1, 0.2), expand = expansion(mult = c(0, 0))) +
    coord_cartesian(ylim = c(0, 1.1), clip = "off") +
    labs(x = "Year of first report in GenCC",
         y = "References from model knowledge") +
    guides(fill = guide_legend(ncol = 1)) +
    theme_base
}

citation_counts <- function(cd) {
  e <- cit_split(cit_e_data(cd))$counts %>% left_join(cit_e_tests(cd) %>% select(bin, p), by = "bin")
  f <- cit_split(cit_f_data(cd))$counts %>% left_join(cit_f_tests(cd) %>% select(bin, p), by = "bin")
  k <- cd$refs %>% filter(arm == "knowledge")
  list(e = e, f = f,
       knowledge_refs = nrow(k),
       knowledge_pmid_wrong = sum(startsWith(k$status, "pmid_wrong")),
       knowledge_pmid_correct = sum(k$status == "pmid_correct"),
       knowledge_unresolved = sum(endsWith(k$status, "unresolved")),
       pesto_refs = sum(cd$refs$arm == "pesto"),
       pesto_read = sum(cd$refs$arm == "pesto" & cd$refs$status == "pmid_correct"))
}
