# P01: does a meta-research paper's own topic predict whether it shares its own data?
#
# Protocol: proposals/P01-advocacy-and-practice.qmd, published 2026-09-16 before this ran.
# Input:    data/statements.csv, written by extract.py. Nothing is graded there.
# Output:   out/*.csv, out/*.txt, out/validation-sample.csv
#
# Everything that decides what a statement means is here, so the grading rule and the model
# can be read as one argument.

suppressPackageStartupMessages({
  library(dplyr); library(readr); library(stringr); library(lme4); library(ordinal)
})

set.seed(20260916)
here <- function(...) file.path("studies/P01-advocacy-and-practice", ...)
dir.create(here("out"), showWarnings = FALSE, recursive = TRUE)
sink_all <- file(here("out", "log.txt"), open = "wt")

say <- function(...) {
  msg <- paste0(...)
  cat(msg, "\n"); cat(msg, "\n", file = sink_all)
}

raw <- read_csv(here("data", "statements.csv"), show_col_types = FALSE) %>%
  mutate(statement = coalesce(statement, ""))

say("== Retrieval ==")
say("records with a PMCID: ", nrow(raw))
say("retrieved from PMC:    ", sum(raw$retrieved == 1))
say("carrying full text:    ", sum(raw$full_text == 1))

# ---------------------------------------------------------------------------------------
# Exclusion.
#
# A record PMC holds as metadata only cannot have a statement extracted. Counting it as a
# record without one would put every abstract-only deposit in the no-statement arm and bias
# the result. Excluded, and the count is reported rather than absorbed.
# ---------------------------------------------------------------------------------------
d <- raw %>% filter(full_text == 1)
say("excluded, no full text: ", nrow(raw) - nrow(d))
say("analysis set:           ", nrow(d))

# ---------------------------------------------------------------------------------------
# Grading, by the three levels named in the protocol.
#
#   none         no statement at all
#   declarative  a statement that shares nothing: on request, within the article, N/A
#   actionable   a repository, accession, DOI or URL a reader can follow without asking
#
# "within the article and its supplementary files" grades as declarative. That is the
# protocol's own wording and it is not obviously right; supplementary material is retrievable
# by anyone with journal access. It is kept because the protocol fixed it in advance, and a
# sensitivity analysis below regrades it as actionable so the reader can see what the choice
# is worth.
#
# Order matters, and the first ordering was wrong. The on-request test ran before every
# pointer test, on the reasoning that "available from the corresponding author at
# name@university.edu" contains something that looks like a locator and is a refusal. That is
# right for a bare URL and wrong for a named repository: PMC13224738 deposits its code on
# GitHub and OSF and also says the raw Scopus data cannot be released, and it is a paper that
# shared what it could. A named repository is unambiguous evidence of a deposit and now
# outranks a co-occurring on-request clause; a bare URL still does not.
#
# Six of 574 statements carry both, five of them a named repository, and all six are in the
# unexposed arm. The correction therefore raises the comparison rate and works against the
# hypothesis, which is the direction that makes it worth trusting.
# ---------------------------------------------------------------------------------------
REPO <- paste0(
  "osf\\.io|zenodo|dryad|figshare|dataverse|mendeley data|opendata|",
  "github\\.com|gitlab\\.com|bitbucket|codeocean|openneuro|",
  "dbgap|geo accession|arrayexpress|clinicalvars|sequence read archive|",
  "harvard dataverse|borealis|4tu|pangaea|datacite|re3data"
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

d <- d %>%
  mutate(
    grade = vapply(statement, grade_one, character(1)),
    grade = factor(grade, levels = c("none", "declarative", "actionable"), ordered = TRUE),
    actionable = as.integer(grade == "actionable"),
    any_statement = as.integer(grade != "none"),
    year_n = suppressWarnings(as.numeric(year)),
    year_c = year_n - 2020,
    # Article type, collapsed. A comment or an editorial has no data to share and its
    # presence in the no-statement arm is not evidence about sharing behavior.
    art_type = case_when(
      str_detect(pubtypes, "Comment|Editorial|Letter|News|Biography|Historical") ~ "comment",
      str_detect(pubtypes, "Review|Meta-Analysis|Systematic Review") ~ "review",
      TRUE ~ "research"
    ),
    art_type = relevel(factor(art_type), ref = "research"),
    journal = factor(journal),
    exposed = factor(topic_datashare, levels = c(0, 1),
                     labels = c("other topic", "transparency topic"))
  ) %>%
  filter(!is.na(year_n))

say("")
say("== Grading ==")
print(table(d$grade)); capture.output(table(d$grade), file = sink_all, append = TRUE)
say("")
say("== Exposure ==")
print(table(d$exposed)); capture.output(table(d$exposed), file = sink_all, append = TRUE)
say("")
say("== Crosstab, grade by exposure ==")
ct <- table(d$exposed, d$grade)
print(ct); capture.output(ct, file = sink_all, append = TRUE)
print(round(prop.table(ct, 1), 3))
capture.output(round(prop.table(ct, 1), 3), file = sink_all, append = TRUE)

# ---------------------------------------------------------------------------------------
# What this design can detect.
#
# Computed and reported whatever it says, per the protocol. With 47 exposed records in the
# corpus and fewer after exclusions, this is the number that decides how a null should be
# read, so it is printed before the model rather than after.
# ---------------------------------------------------------------------------------------
n1 <- sum(d$exposed == "transparency topic")
n0 <- sum(d$exposed == "other topic")
p0 <- mean(d$actionable[d$exposed == "other topic"])
find_p2 <- function(target_n1) {
  f <- function(p2) {
    if (p2 <= 0 || p2 >= 1 || abs(p2 - p0) < 1e-4) return(Inf)
    power.prop.test(p1 = p0, p2 = p2, sig.level = 0.05, power = 0.8)$n - target_n1
  }
  up <- tryCatch(uniroot(f, c(p0 + 0.01, 0.99))$root, error = function(e) NA_real_)
  up
}
p2_det <- find_p2(n1)
say("")
say("== Detectable effect ==")
say("exposed n = ", n1, ", unexposed n = ", n0)
say("baseline actionable rate in the unexposed arm = ", round(p0, 3))
say("smallest actionable rate in the exposed arm detectable at 80% power, alpha .05 = ",
    ifelse(is.na(p2_det), "not estimable", round(p2_det, 3)))
say("that is a risk difference of ",
    ifelse(is.na(p2_det), "not estimable", round(p2_det - p0, 3)),
    ", which is the floor on what a null result here can rule out")

# ---------------------------------------------------------------------------------------
# Primary model.
#
# Journal is a random intercept because a journal's own policy decides whether any statement
# appears, and a fixed effect on several hundred journals will not estimate. The estimate is
# therefore within-journal wherever a journal published both kinds of paper, and that is the
# comparison the question actually asks for.
# ---------------------------------------------------------------------------------------
say("")
say("== Primary model: actionable ~ exposure + year + article type + (1 | journal) ==")
m1 <- glmer(actionable ~ exposed + year_c + art_type + (1 | journal),
            family = binomial, data = d,
            control = glmerControl(optimizer = "bobyqa",
                                   optCtrl = list(maxfun = 2e5)))
s1 <- summary(m1)
print(s1); capture.output(print(s1), file = sink_all, append = TRUE)

co <- s1$coefficients
or <- exp(cbind(OR = co[, 1],
                lower = co[, 1] - 1.96 * co[, 2],
                upper = co[, 1] + 1.96 * co[, 2]))
or[, 2:3] <- exp(cbind(co[, 1] - 1.96 * co[, 2], co[, 1] + 1.96 * co[, 2]))
say("")
say("Odds ratios:")
print(round(or, 3)); capture.output(round(or, 3), file = sink_all, append = TRUE)

# ---------------------------------------------------------------------------------------
# Secondary, preregistered: the ordinal model on all three levels. Fitted because the
# protocol said so, not because the binary result came out a particular way.
# ---------------------------------------------------------------------------------------
say("")
say("== Secondary, preregistered: ordinal model on none < declarative < actionable ==")
m2 <- tryCatch(
  clmm(grade ~ exposed + year_c + art_type + (1 | journal), data = d, Hess = TRUE),
  error = function(e) { say("ordinal model failed: ", conditionMessage(e)); NULL })
if (!is.null(m2)) {
  print(summary(m2)); capture.output(print(summary(m2)), file = sink_all, append = TRUE)
}

# ---------------------------------------------------------------------------------------
# Sensitivity: regrade "within the article and its supplementary files" as actionable.
# The protocol fixed it as declarative; this shows what that choice was worth.
# ---------------------------------------------------------------------------------------
d2 <- d %>%
  mutate(actionable_s = as.integer(
    actionable == 1 | (grade == "declarative" & str_detect(str_to_lower(statement), IN_ARTICLE))))
say("")
say("== Sensitivity: supplementary material counted as actionable ==")
say("actionable under this rule: ", sum(d2$actionable_s), " (primary rule: ", sum(d$actionable), ")")
m3 <- glmer(actionable_s ~ exposed + year_c + art_type + (1 | journal),
            family = binomial, data = d2,
            control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5)))
c3 <- summary(m3)$coefficients
say("exposure OR = ", round(exp(c3["exposedtransparency topic", 1]), 3),
    " (", round(exp(c3["exposedtransparency topic", 1] - 1.96 * c3["exposedtransparency topic", 2]), 3),
    " to ", round(exp(c3["exposedtransparency topic", 1] + 1.96 * c3["exposedtransparency topic", 2]), 3), ")")


# ---------------------------------------------------------------------------------------
# Sensitivity: publisher-typed routes only.
#
# The first version of the extractor read a paper's own methods and results as its statement
# and inflated the effect; the fix restricted extraction to <front> and <back>. Residual
# doubt remains about the title-matched routes, which are the ones the repaired bug used, and
# which are still about twice as common in the exposed arm. This refits on records whose
# statement carries a publisher-assigned sec-type or notes-type, where no title matching of
# ours is involved at all. If the effect lives in the title routes it dies here.
# ---------------------------------------------------------------------------------------
say("")
say("== Sensitivity: publisher-typed routes only, no title matching ==")
d_typed <- d %>% filter(route == "none" | str_detect(route, "-type$"))
say("records: ", nrow(d_typed), " of ", nrow(d),
    "; exposed: ", sum(d_typed$exposed == "transparency topic"))
m4 <- glmer(actionable ~ exposed + year_c + art_type + (1 | journal),
            family = binomial, data = d_typed,
            control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5)))
c4 <- summary(m4)$coefficients
k <- "exposedtransparency topic"
say("exposure OR = ", round(exp(c4[k, 1]), 3),
    " (", round(exp(c4[k, 1] - 1.96 * c4[k, 2]), 3),
    " to ", round(exp(c4[k, 1] + 1.96 * c4[k, 2]), 3),
    "), p = ", signif(c4[k, 4], 3))

# ---------------------------------------------------------------------------------------
# The author's own papers are in this corpus and in the exposed arm.
#
# A tier A search for meta-research retrieves the work of anyone who does meta-research,
# including whoever is running this study. Reported rather than silently dropped, and refit
# without them, because a reader is entitled to know the direction of that interest.
# ---------------------------------------------------------------------------------------
own <- str_detect(str_to_lower(d$statement), "choxos|sofi-mahmudi")
say("")
say("== The author's own papers ==")
say("records whose statement names the author's repositories: ", sum(own))
say("of which exposed: ", sum(own & d$exposed == "transparency topic"),
    ", actionable: ", sum(own & d$actionable == 1))
d_noown <- d[!own, ]
m5 <- glmer(actionable ~ exposed + year_c + art_type + (1 | journal),
            family = binomial, data = d_noown,
            control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5)))
c5 <- summary(m5)$coefficients
say("exposure OR excluding them = ", round(exp(c5[k, 1]), 3),
    " (", round(exp(c5[k, 1] - 1.96 * c5[k, 2]), 3),
    " to ", round(exp(c5[k, 1] + 1.96 * c5[k, 2]), 3), ")")

# ---------------------------------------------------------------------------------------
# Validation sample. The protocol calls for 100 statements graded by hand to measure where
# the rule disagrees. The rule is not adjusted after seeing the outcome, so this file is
# written for grading and the agreement is reported when it comes back.
# ---------------------------------------------------------------------------------------
val <- d %>%
  filter(grade != "none") %>%
  slice_sample(n = 100) %>%
  transmute(pmcid, pmid, journal, year, route,
            rule_grade = as.character(grade),
            hand_grade = "",
            statement = str_sub(statement, 1, 1200))
write_csv(val, here("out", "validation-sample.csv"))

write_csv(d %>% select(pmcid, pmid, year, journal, art_type, route, exposed, grade,
                       actionable, any_statement, labels),
          here("out", "graded.csv"))

rates <- d %>%
  group_by(exposed, grade) %>% summarise(n = n(), .groups = "drop") %>%
  group_by(exposed) %>% mutate(pct = round(100 * n / sum(n), 1)) %>% ungroup()
write_csv(rates, here("out", "rates.csv"))

by_year <- d %>%
  group_by(year_n) %>%
  summarise(n = n(), actionable = sum(actionable), any = sum(any_statement), .groups = "drop") %>%
  filter(n >= 5)
write_csv(by_year, here("out", "by-year.csv"))

say("")
say("Wrote out/graded.csv, out/rates.csv, out/by-year.csv, out/validation-sample.csv")
close(sink_all)
