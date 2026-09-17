# The grading rule for a data availability statement. Pinned by the P01v2 protocol.
#
# This file exists so the rule is never typed twice. It is sourced by
# studies/P01-advocacy-and-practice/R/analyze.R and by studies/P01v2-confirmatory/R/probes.R,
# and the sibling project's operational rule applies: any number or decision appearing in two
# places is emitted from one and asserted back, never copied.
#
# Editing this file changes a pinned instrument. Do not, without recording a deviation on the
# protocol and re-running both studies.

REPO <- paste0(
  "\\bosf\\.io|\\bzenodo\\b|\\bdryad\\b|\\bfigshare\\b|\\bdataverse\\b|",
  "\\bmendeley data\\b|\\bopendata\\b|\\bgithub\\.com|\\bgitlab\\.com|\\bbitbucket\\b|",
  "\\bcodeocean\\b|\\bopenneuro\\b|\\bdbgap\\b|\\bgeo accession\\b|\\barrayexpress\\b|",
  "\\bsequence read archive\\b|\\bharvard dataverse\\b|\\bborealis\\b|\\b4tu\\b|",
  "\\bpangaea\\b|\\bdatacite\\b|\\bre3data\\b"
)
ON_REQUEST <- paste0(
  "available (from|upon|on)( the)? (corresponding )?(author|authors|first author|request)|",
  "on reasonable request|upon reasonable request|available on request|",
  "by request to|contact the corresponding author"
)
NOT_APPLICABLE <- paste0(
  "^n/?a\\.?$|no datasets? (were|was) (generated|analys|analyz)|",
  "not applicable|no (new )?data (were|was) (generated|created)|",
  "no additional data|does not (have|contain) any (additional )?data"
)
IN_ARTICLE <- paste0(
  "included (in|within) (this|the) (published )?article|",
  "within the (manuscript|article|paper)|",
  "provided within the manuscript|in the supplementary|as supplementary"
)
DOI <- "10\\.[0-9]{4,9}/[^\\s,;]+"
URL <- "https?://[^\\s,;\\)]+"

grade_one <- function(s) {
  if (!nzchar(str_trim(s))) return("none")
  x <- str_to_lower(str_squish(s))
  # Strip the section heading the extractor keeps, so "Data availability" itself is not text.
  x <- str_remove(x, "^(data|code|software)[^a-z]*availability[^a-z]*(statement)?")
  x <- str_remove(x, "^availability of (the )?(data|code|materials)[^a-z]*")
  x <- str_trim(x)
  if (!nzchar(x)) return("declarative")
  # A named repository is a deposit and outranks everything below it.
  if (str_detect(x, REPO)) return("actionable")
  if (str_detect(x, ON_REQUEST)) return("declarative")
  if (str_detect(x, NOT_APPLICABLE)) return("declarative")
  # A DOI or URL counts only when it is not the article's own DOI or the journal's own site.
  loc <- c(str_extract_all(x, DOI)[[1]], str_extract_all(x, URL)[[1]])
  loc <- loc[!str_detect(loc, "doi\\.org/10\\.[0-9]{4,9}/$")]
  if (length(loc) > 0) return("actionable")
  if (str_detect(x, IN_ARTICLE)) return("declarative")
  "declarative"
}
