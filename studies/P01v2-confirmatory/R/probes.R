# Probes P4 and P5 for the P01v2 design.
#
# P4  grade distribution under the pinned rule, per arm, on the realized frame
# P5  the detectable odds ratio at 80 percent power from the realized counts
#
# Both numbers go into section 7 of the design and are written there from out/probes.json,
# never retyped. The grading rule is sourced from studies/_shared/R/grade.R so that this probe
# measures the pinned instrument rather than a copy of it.
#
# IMPORTANT: the comparison arm here is NOT screened. Screening needs the P6 pilot, which needs
# a human reference standard. Everything below is an estimate on an unscreened frame.
#
# A first version of this comment asserted that the unscreened comparison rate is an UPPER bound
# on the screened one, reasoning that primary studies carry journal-mandated statements. The
# probe says the opposite and the probe is right: the unscreened comparison rate is 0.038 while
# R01's rate among screened meta-research was 0.205. Screening removes primary studies, which
# deposit far less often than meta-research does, so screening RAISES the comparison rate and
# the unscreened figure is a LOWER bound.
#
# That matters because the detectable effect depends on the baseline, so power is computed
# across a range of plausible screened rates rather than at the unscreened one alone. This is
# the failure the design standard names: a number that is reasoned about rather than computed
# comes out backwards, and only computing it shows that.

suppressPackageStartupMessages({ library(dplyr); library(readr); library(stringr) })

here <- function(...) file.path("studies/P01v2-confirmatory", ...)
source("studies/_shared/R/grade.R")

d <- read_csv(here("out", "frame-statements.csv"), show_col_types = FALSE) %>%
  mutate(statement = coalesce(statement, "")) %>%
  filter(full_text == 1) %>%
  mutate(grade = vapply(statement, grade_one, character(1)),
         actionable = as.integer(grade == "actionable"))

tab <- d %>% count(arm, grade) %>% group_by(arm) %>%
  mutate(pct = round(100 * n / sum(n), 1)) %>% ungroup()
print(as.data.frame(tab))

n1 <- sum(d$arm == "exposed")
n0 <- sum(d$arm == "comparison")
p0 <- mean(d$actionable[d$arm == "comparison"])
p1_obs <- mean(d$actionable[d$arm == "exposed"])

# Detectable p1 at 80 percent power with unequal allocation. power.prop.test assumes equal
# group sizes and would understate what 520 against 3435 can do, so the two-proportion normal
# approximation is solved directly for p1.
detectable_p1 <- function(n1, n0, p0, power = 0.8, alpha = 0.05) {
  za <- qnorm(1 - alpha / 2); zb <- qnorm(power)
  f <- function(p1) {
    pbar <- (p1 * n1 + p0 * n0) / (n1 + n0)
    num <- abs(p1 - p0) - za * sqrt(pbar * (1 - pbar) * (1 / n1 + 1 / n0))
    den <- sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
    num / den - zb
  }
  uniroot(f, c(p0 + 1e-4, 0.999))$root
}

or_of <- function(p1, p0) (p1 / (1 - p1)) / (p0 / (1 - p0))
p1_det <- detectable_p1(n1, n0, p0)

# Power across plausible screened comparison rates. Screening shrinks both arms, so the counts
# are scaled by an assumed yield and the yield is varied too; both are assumptions and are
# reported as such rather than buried.
grid <- expand.grid(p0_s = c(0.038, 0.10, 0.15, 0.205, 0.25), yield = c(0.5, 0.7, 1.0))
grid$n1_s <- round(n1 * grid$yield); grid$n0_s <- round(n0 * grid$yield)
grid$det_or <- mapply(function(a, b, c) round(or_of(detectable_p1(a, b, c), c), 2),
                      grid$n1_s, grid$n0_s, grid$p0_s)
cat("\n== P5 sensitivity: detectable OR by screened baseline rate and screening yield ==\n")
print(reshape(grid[, c("p0_s", "yield", "det_or")], idvar = "p0_s",
              timevar = "yield", direction = "wide"), row.names = FALSE)

cat("\n== P5 ==\n")
cat("exposed n =", n1, " comparison n =", n0, "\n")
cat("comparison actionable rate (UNSCREENED) =", round(p0, 4), "\n")
cat("observed exposed actionable rate (UNSCREENED) =", round(p1_obs, 4), "\n")
cat("smallest detectable exposed rate at 80% power =", round(p1_det, 4), "\n")
cat("detectable odds ratio =", round(or_of(p1_det, p0), 3), "\n")

# What R01's point estimate would look like here, as the reference the design is built against.
cat("R01 point estimate 4.40 corresponds to an exposed rate of",
    round((4.40 * p0 / (1 - p0)) / (1 + 4.40 * p0 / (1 - p0)), 4), "at this baseline\n")

# Merge into probes.json rather than overwrite: P1 and P2 were written by probes.py.
pj <- here("out", "probes.json")
p <- jsonlite::fromJSON(pj, simplifyVector = FALSE)
p$P3 <- list(
  exposed_fetched = sum(d$arm == "exposed"), comparison_fetched = sum(d$arm == "comparison"),
  routes = as.list(table(ifelse(str_detect(d$route, "title"), "fuzzy-title", d$route)))
)
p$P4 <- list(
  screened = FALSE,
  exposed = as.list(table(d$grade[d$arm == "exposed"])),
  comparison = as.list(table(d$grade[d$arm == "comparison"])),
  comparison_actionable_rate = round(p0, 4),
  exposed_actionable_rate = round(p1_obs, 4)
)
p$P5 <- list(
  n_exposed = n1, n_comparison = n0,
  detectable_exposed_rate = round(p1_det, 4),
  detectable_odds_ratio_at_unscreened_baseline = round(or_of(p1_det, p0), 3),
  detectable_odds_ratio_grid = lapply(seq_len(nrow(grid)), function(i)
    as.list(grid[i, c("p0_s", "yield", "n1_s", "n0_s", "det_or")])),
  worst_case_detectable_or = max(grid$det_or),
  power = 0.8, alpha = 0.05
)
writeLines(jsonlite::toJSON(p, auto_unbox = TRUE, pretty = TRUE), pj)
write_csv(tab, here("out", "p4-grades.csv"))
cat("\n-> out/probes.json (P3, P4, P5 merged), out/p4-grades.csv\n")
