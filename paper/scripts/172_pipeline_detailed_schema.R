#!/usr/bin/env Rscript
# The pipeline of Fig. 1a, step by step, in two versions drawn by one function.
#
#   detailed_schema()            both branches, every step the code runs, for
#                                Supplementary Note 1 (Supplementary Figure 1)
#   detailed_schema(fulltext = TRUE)
#                                the literature branch alone, with what the
#                                full-text mode adds or changes, for Note 5
#
# Each step of Fig. 1a becomes a group that carries exactly its name in Fig. 1a
# (Term expansion, PubMed searches, Relevance bands, Evidence assessment; Open
# Targets lookup, Trait shortlist, Trait sieve, Trait grading) and holds the
# steps of PESTO-release src/pesto/flow/arms.py (ABSTRACTS, FULLTEXT) and of the
# Open Targets branch in the order the code runs them. The model of each step
# is written inside its box. Colours, stroke and radius come from
# scripts/pipeline_schema.R, so the three schemas read as one family.
#
# Sourced by scripts/170_figure_supp_fulltext.R. Run directly to write both:
#   Rscript scripts/172_pipeline_detailed_schema.R

source(file.path(dirname(sub("--file=", "", grep("--file=", commandArgs(FALSE), value = TRUE)[1])), "_helvetica.R"))
suppressPackageStartupMessages({
  library(ggplot2)
  library(ggforce)
  library(grid)
})

local({
  here <- dirname(sub("--file=", "", grep("--file=", commandArgs(FALSE), value = TRUE)[1]))
  if (is.na(here) || !nzchar(here) || !file.exists(file.path(here, "pipeline_schema.R")))
    here <- "scripts"
  source(file.path(here, "pipeline_schema.R"))
}, envir = globalenv())

DS_FILL <- c(FILL, rule = "#ECECE8", fulltext = "#F6E3CF")
DS_EDGE <- c(EDGE, rule = "#8F8F8A", fulltext = "#C27C35")
DS_FT_INK <- "#9A5A1F"
DS_W <- 12; DS_H <- 12            # a step
DS_MINI_W <- 11; DS_MINI_H <- 7.6 # one of the four term sets
DS_IN <- 1.6                      # between steps of one group
DS_OUT <- 4.4                     # between groups

# One row: a list of groups, each a list of steps. A step is
# c(label, model, kind) plus an optional dashed flag; the term-expansion group
# is a 2 x 2 block.
step <- function(label, model = NA, kind = "llm", dashed = FALSE)
  list(label = label, model = model, kind = kind, dashed = dashed)

literature_groups <- function(fulltext) {
  searches <- list(step("PubMed\nsearches (5)", NA, "source"),
                   step("Deduplicate\nby title", NA, "rule"))
  if (fulltext) searches <- c(searches, list(step("Title\nsieve", "Claude Haiku", "fulltext", TRUE)))
  searches <- c(searches, list(step("Fetch\nabstracts", NA, "rule")))
  list(
    list(name = "Prompt family", steps = list(step("Phenotype\nclassification", "Claude Opus"))),
    list(name = "Term expansion", block = TRUE,
         steps = list(step("Synonyms", "Claude Opus"), step("Broadened\nterm", "Claude Haiku"),
                      step("Content\nwords", "rule", "rule"), step("Gene\nnames", "HGNC", "rule"))),
    list(name = "PubMed searches", steps = searches),
    list(name = "Relevance bands",
         steps = list(step("Relevance\nbands", "Claude Haiku"),
                      step(if (fulltext) "Select\n14 + 6" else "Select\nup to 20", NA, "rule"))),
    list(name = "Evidence assessment",
         steps = list(step("Evidence\nassessment", "Claude Opus"),
                      step("Score and\nverdict", NA, "rule"))))
}

open_targets_groups <- function() list(
  list(name = "Open Targets lookup", steps = list(step("Associated\ntraits", "score > 0.05", "db"))),
  list(name = "Trait shortlist", steps = list(step("20 nearest\ntraits", "BioLORD-2023", "encoder"))),
  list(name = "Trait sieve", steps = list(step("Trait\nsieve", "Claude Haiku"))),
  list(name = "Trait grading", steps = list(step("Trait\ngrading", "Claude Opus"),
                                            step("Verdict\nassignment", NA, "rule"))))

# Lay a row out from x0: boxes, the group brackets, and the arrows between
# consecutive boxes or blocks.
lay_row <- function(groups, x0, y, between = DS_OUT) {
  boxes <- list(); brackets <- list(); arrows <- list(); x <- x0; prev_right <- NA
  for (g in groups) {
    gx0 <- x
    if (isTRUE(g$block)) {
      w <- 2 * DS_MINI_W + DS_IN
      for (i in seq_along(g$steps)) {
        s <- g$steps[[i]]
        cx <- x + DS_MINI_W / 2 + ((i - 1) %% 2) * (DS_MINI_W + DS_IN)
        cy <- y + (if (i <= 2) 1 else -1) * (DS_MINI_H + DS_IN) / 2
        boxes[[length(boxes) + 1]] <- data.frame(x = cx, y = cy, w = DS_MINI_W, h = DS_MINI_H,
          label = s$label, model = s$model, kind = s$kind, dashed = s$dashed, group = g$name,
          stringsAsFactors = FALSE)
      }
      if (!is.na(prev_right)) arrows[[length(arrows) + 1]] <- c(prev_right, x)
      x <- x + w; prev_right <- x
      top <- y + DS_MINI_H + DS_IN / 2
    } else {
      for (s in g$steps) {
        if (!is.na(prev_right)) arrows[[length(arrows) + 1]] <- c(prev_right, x)
        boxes[[length(boxes) + 1]] <- data.frame(x = x + DS_W / 2, y = y, w = DS_W, h = DS_H,
          label = s$label, model = s$model, kind = s$kind, dashed = s$dashed, group = g$name,
          stringsAsFactors = FALSE)
        x <- x + DS_W; prev_right <- x; x <- x + DS_IN
      }
      x <- x - DS_IN
      top <- y + DS_H / 2
    }
    brackets[[length(brackets) + 1]] <- data.frame(x = gx0, xend = x, y = top + 2.2,
                                                   name = g$name, stringsAsFactors = FALSE)
    x <- x + between
  }
  boxes <- do.call(rbind, boxes)
  boxes$xmin <- boxes$x - boxes$w / 2; boxes$xmax <- boxes$x + boxes$w / 2
  boxes$ymin <- boxes$y - boxes$h / 2; boxes$ymax <- boxes$y + boxes$h / 2
  arrows <- as.data.frame(do.call(rbind, arrows)); names(arrows) <- c("x", "xend")
  arrows$y <- y; arrows$yend <- y
  list(boxes = boxes, brackets = do.call(rbind, brackets), arrows = arrows,
       left = x0, right = x - between, y = y)
}

shapes <- function(boxes, prefix) do.call(rbind, lapply(seq_len(nrow(boxes)), function(i) {
  b <- boxes[i, ]
  rect_pts(paste0(prefix, i), b$xmin, b$xmax, b$ymin, b$ymax, kind = b$kind, dashed = b$dashed)
}))

detailed_schema <- function(fulltext = FALSE) {
  if (!fulltext) {
    W <- 186; H <- 76
    lit <- lay_row(literature_groups(FALSE), 17, 52)
    # The Open Targets row spans the literature row, so the two titles share a centre.
    packed <- lay_row(open_targets_groups(), 17, 20, between = 0)
    gap <- ((lit$right - lit$left) - (packed$right - packed$left)) /
      (length(open_targets_groups()) - 1)
    ot <- lay_row(open_targets_groups(), 17, 20, between = gap)
    rows <- list(lit, ot)
    in_x <- 6.5; in_y <- (lit$y + ot$y) / 2
    fork_x <- 14
    join_x <- max(lit$right, ot$right) + 3
    max_box <- data.frame(x = join_x + 8.5, y = in_y, w = 11, h = DS_H, label = "Max\nverdict",
                          model = "rule", kind = "rule", dashed = FALSE, group = "",
                          stringsAsFactors = FALSE)
  } else {
    W <- 176; H <- 60
    lit <- lay_row(literature_groups(TRUE), 17, 40)
    rows <- list(lit)
    in_x <- 6.5; in_y <- lit$y
  }
  input <- data.frame(x = in_x, y = in_y, w = 11, h = DS_H, label = "(Gene,\nPhenotype)",
                      model = NA, kind = "input", dashed = FALSE, group = "",
                      stringsAsFactors = FALSE)
  extra <- input
  if (!fulltext) extra <- rbind(extra, max_box)
  extra$xmin <- extra$x - extra$w / 2; extra$xmax <- extra$x + extra$w / 2
  extra$ymin <- extra$y - extra$h / 2; extra$ymax <- extra$y + extra$h / 2
  input <- extra[1, ]

  boxes <- do.call(rbind, lapply(rows, `[[`, "boxes"))
  boxes <- rbind(boxes, extra)
  brackets <- do.call(rbind, lapply(rows, `[[`, "brackets"))
  arrows <- do.call(rbind, lapply(rows, `[[`, "arrows"))
  plain <- data.frame(x = numeric(0), xend = numeric(0), y = numeric(0), yend = numeric(0))
  if (!fulltext) {
    first <- lapply(rows, function(r) min(r$boxes$xmin))
    plain <- rbind(
      data.frame(x = input$xmax, xend = fork_x, y = in_y, yend = in_y),
      data.frame(x = fork_x, xend = fork_x, y = ot$y, yend = lit$y),
      data.frame(x = c(lit$right, ot$right), xend = join_x, y = c(lit$y, ot$y),
                 yend = c(lit$y, ot$y)),
      data.frame(x = join_x, xend = join_x, y = ot$y, yend = lit$y))
    arrows <- rbind(arrows,
      data.frame(x = fork_x, xend = first[[1]], y = lit$y, yend = lit$y),
      data.frame(x = fork_x, xend = first[[2]], y = ot$y, yend = ot$y),
      data.frame(x = join_x, xend = max_box$x - max_box$w / 2, y = in_y, yend = in_y))
  } else {
    arrows <- rbind(arrows, data.frame(x = input$xmax, xend = min(lit$boxes$xmin),
                                       y = lit$y, yend = lit$y))
  }

  # What the full-text mode adds to a step both modes run, tied to that step.
  adds <- NULL; ties <- NULL
  if (fulltext) {
    b <- lit$boxes
    at <- function(lbl) b[b$label == lbl, ]
    te <- b[b$group == "Term expansion", ]
    spec <- list(
      list(x = mean(range(c(te$xmin, te$xmax))), top = min(te$ymin),
           label = "+ phenotype\nkey words", model = "Claude Haiku"),
      list(x = at("PubMed\nsearches (5)")$x, top = at("PubMed\nsearches (5)")$ymin,
           label = "+ Europe PMC\nbody search", model = "25 articles"),
      list(x = at("Deduplicate\nby title")$x, top = at("Deduplicate\nby title")$ymin,
           label = "no errata or\nretractions", model = NA),
      list(x = at("Fetch\nabstracts")$x, top = at("Fetch\nabstracts")$ymin,
           label = "+ passages\nnear the gene", model = "open access"),
      list(x = at("Select\n14 + 6")$x, top = at("Select\n14 + 6")$ymin,
           label = "14 PubMed\n+ 6 full text", model = "instead of 20"))
    add_y <- lit$y - 21
    adds <- do.call(rbind, lapply(spec, function(s) data.frame(
      x = s$x, y = add_y, w = DS_W, h = DS_H, label = s$label, model = s$model,
      kind = "fulltext", dashed = FALSE, group = "", stringsAsFactors = FALSE)))
    adds$xmin <- adds$x - adds$w / 2; adds$xmax <- adds$x + adds$w / 2
    adds$ymin <- adds$y - adds$h / 2; adds$ymax <- adds$y + adds$h / 2
    ties <- data.frame(x = adds$x, xend = adds$x, y = adds$ymax,
                       yend = sapply(spec, `[[`, "top"))
  }
  all_boxes <- if (is.null(adds)) boxes else rbind(boxes, adds)

  keys <- data.frame(kind = c("llm", "source", "db", "encoder", "rule"),
                     lab = c("LLM agent", "Literature source", "External database",
                             "Text encoder", "Rule or lookup"), stringsAsFactors = FALSE)
  if (fulltext) keys <- rbind(keys[keys$kind %in% c("llm", "source", "rule"), ],
                              data.frame(kind = "fulltext", lab = "Full-text mode only"))
  keys$x <- 2 + (seq_len(nrow(keys)) - 1) * 21
  key_boxes <- do.call(rbind, lapply(seq_len(nrow(keys)), function(i)
    rect_pts(paste0("k", i), keys$x[i], keys$x[i] + 3.4, 0.8, 3.2, kind = keys$kind[i],
             dashed = FALSE)))

  inside_label <- function(d) transform(d, ly = ifelse(is.na(model), y, y + 1.3))
  lab <- inside_label(all_boxes)
  heads <- if (fulltext) data.frame(x = mean(c(lit$left, lit$right)), y = lit$y + DS_H / 2 + 11.5,
                                    lab = "LITERATURE BRANCH")
           else data.frame(x = c(mean(c(lit$left, lit$right)), mean(c(ot$left, ot$right))),
                           y = c(lit$y, ot$y) + DS_H / 2 + 11.5,
                           lab = c("BRANCH 1 - LITERATURE", "BRANCH 2 - OPEN TARGETS"))

  p <- ggplot() +
    geom_text(data = heads, aes(x = x, y = y, label = lab), size = 5.0, fontface = "bold",
              colour = INK) +
    geom_segment(data = brackets, aes(x = x, xend = xend, y = y, yend = y),
                 linewidth = 0.45, colour = "grey45") +
    geom_segment(data = brackets, aes(x = x, xend = x, y = y, yend = y - 0.9),
                 linewidth = 0.45, colour = "grey45") +
    geom_segment(data = brackets, aes(x = xend, xend = xend, y = y, yend = y - 0.9),
                 linewidth = 0.45, colour = "grey45") +
    geom_text(data = brackets, aes(x = (x + xend) / 2, y = y + 2.0, label = name),
              size = 3.9, fontface = "bold", colour = INK) +
    geom_segment(data = plain, aes(x = x, xend = xend, y = y, yend = yend),
                 linewidth = STROKE, colour = INK) +
    geom_segment(data = arrows, aes(x = x, xend = xend, y = y, yend = yend),
                 linewidth = STROKE, colour = INK, arrow = ARROWHEAD)
  if (fulltext) p <- p +
    geom_segment(data = ties, aes(x = x, xend = xend, y = y, yend = yend),
                 linewidth = STROKE, colour = DS_EDGE[["fulltext"]], linetype = "22") +
    annotate("text", x = 1.5, y = adds$y[1], hjust = 0, label = "ADDED BY\nTHE FULL-\nTEXT MODE",
             size = 4.0, fontface = "bold", lineheight = 0.95, colour = DS_FT_INK) +
    annotate("text", x = W - 1, y = 2.0, hjust = 1, size = 3.5, colour = MUTED,
             label = "The Open Targets branch (Supplementary Figure 1) is the same in both modes")
  p +
    geom_shape(data = rbind(shapes(all_boxes, "b")),
               aes(x = x, y = y, group = id, fill = kind, colour = kind,
                   linetype = ifelse(dashed, "dashed", "solid")),
               radius = RADIUS, linewidth = 0.8) +
    scale_linetype_identity() +
    geom_text(data = lab, aes(x = x, y = ly, label = label), size = 3.45, lineheight = 0.92,
              colour = "#16232E") +
    geom_text(data = subset(lab, !is.na(model)),
              aes(x = x, y = ymin + 1.6, label = model), size = 3.0, fontface = "italic",
              colour = MUTED) +
    geom_shape(data = key_boxes, aes(x = x, y = y, group = id, fill = kind, colour = kind),
               radius = unit(1.5, "pt"), linewidth = 0.5) +
    geom_text(data = keys, aes(x = x + 4.2, y = 2.0, label = lab), hjust = 0, size = 3.7,
              colour = "grey15") +
    scale_fill_manual(values = DS_FILL, guide = "none") +
    scale_colour_manual(values = DS_EDGE, guide = "none") +
    coord_fixed(ratio = 1, xlim = c(0, W), ylim = c(0, H), expand = FALSE) +
    theme_void() + theme(plot.margin = margin(4, 6, 2, 2))
}

detailed_schema_size <- function(fulltext = FALSE, width = 15)
  if (fulltext) c(width, width * 60 / 176) else c(width, width * 76 / 186)

if (sys.nframe() == 0) {
  root <- normalizePath(file.path(dirname(sub("--file=", "",
          grep("--file=", commandArgs(FALSE), value = TRUE)[1])), ".."))
  for (ft in c(FALSE, TRUE)) {
    name <- if (ft) "pipeline_detailed_fulltext" else "pipeline_detailed"
    s <- detailed_schema_size(ft)
    p <- detailed_schema(ft)
    ggsave(file.path(root, "figures", paste0(name, ".png")), p, width = s[1], height = s[2],
           dpi = 400, bg = "white")
    ggsave(file.path(root, "figures", paste0(name, ".pdf")), p, width = s[1], height = s[2],
           bg = "white", device = cairo_pdf)
    cat(sprintf("Wrote figures/%s.png and .pdf (%.1f x %.1f in)\n", name, s[1], s[2]))
  }
}
