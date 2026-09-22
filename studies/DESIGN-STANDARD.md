# What a design document here must satisfy

Five documents have been through adversarial review in this project. All five were blocked:
P01v2, P02, P03, P05 and P06, each by two reviewers from different providers, each on
evidenced fatal findings that were checked against primary source and found correct. The
findings are not evenly spread. The same mistakes recur under different names, and every item
below names the document that produced it.

This follows the sibling project `ITC-open-problems/studies/DESIGN-STANDARD.md`, whose
governing rule is kept unchanged: **the difference between a design and a protocol is a set of
computed numbers.** That standard was written after its program repeated its own mistakes. This
one is written for the same reason, at the point where outcome peeking had happened twice and
extraction artifacts three times.

A design that satisfies this list is still a design. It becomes a protocol when its probes have
run and their numbers are written in, and it is registered only when the probes are complete,
the validation gates have passed, and two reviews are attached.

---

## S1. Never look at the outcome by the exposure before registration

R01 fitted its model against a one-page proposal. P01v2 was written to fix that and then its own
probe P4 tabulated the primary outcome by arm on the confirmatory sample, a crude odds ratio of
5.6, before the document called itself confirmatory. Both reviewers found it independently.

**Required.** Probes measure the frame and the instruments only. A probe that cross-tabulates
the primary outcome by the primary exposure on the analysis sample is forbidden. If an
instrument must be piloted on real outcomes, the pilot draws a slice that is removed from the
analysis sample before the probe runs, and the removal is recorded.

## S2. Use a validated instrument, and read identifiers from markup

P01v2's extractor missed statements that sat in `<body>` and discarded `xlink:href`, so a real
GitHub deposit graded as declarative. Five of P05's seven "hard 404s" were URLs cut short by a
regex over flattened text; the deposits were fine.

**Required.** Where a validated tool exists, use it: `rtransparency` for transparency indicators,
`rfair` for FAIR assessment and identifier parsing. Both are maintained by this project's author
and that is disclosed in every design that uses them. Identifiers come from structured markup
(`ext-link/@xlink:href`, `pub-id[@pub-id-type='doi']`) or from `rfair::id_parse`, never from a
regex over text with the markup stripped. A hand-written extractor needs an audit in both
directions before use: what it misses and what it invents.

## S3. Carry the instrument's error into the analysis

`rtransparency::rt_accuracy` reports sensitivity 0.765 and specificity 0.990 for data sharing.
A quarter of real sharing is missed. That is a design fact, not a footnote.

**Required.** Any design using a detector with known sensitivity and specificity states them
and specifies a misclassification analysis (probabilistic bias analysis or a corrected
estimator) as a preregistered sensitivity analysis. A detector with no published accuracy on
the target literature, such as `rt_ai_pmc`, needs its own validation gate.

## S4. Identify the unit before counting it

P06's unit was a preprint paired with its journal version. Its probe counted any record with a
repository location, primary locations included, and never established a single pair. P05's
hypothesis was about statements graded actionable; its probe sampled every non-empty statement.

**Required.** The probe that sizes the sample must construct the unit of analysis as defined,
and report how many candidates failed construction and why.

## S5. The probe population is the study population

P02 computed feasibility across two caches without applying its own eligibility criteria. P06
added 66 and 75 when three PMIDs were in both, because the frame file still held the tier A
overlaps that the P01v2 probe had excluded in memory.

**Required.** Eligibility is applied before any feasibility number is computed. Each record is
counted once, by a stated identifier, after deduplication across every source that feeds it.

## S6. Every number is emitted, and prose about a number is checked against it

P03 said excluding 2025 and 2026 would drop 76 percent of its sample; that was false for the
window it named. P06 said 108 was below 80. The agenda miscounted its own documents. A probe
comment asserted the unscreened rate was an upper bound when it was a lower one.

**Required.** Any number that appears in both code and prose is written from the code's output.
A sentence that reasons about a computed number (above, below, larger, most) is checked against
the number before the document is committed.

## S7. Dates, not years; and a cross-section cannot show a trajectory

P02 compared calendar years, so 41 same-year citations defaulted to pre-retraction. P05 read an
age slope off a single cross-section and treated it as decay.

**Required.** Temporal ordering uses full dates, with an explicit third class for pairs that
cannot be ordered. A claim about change over time needs repeated measurement of the same units
or a design that identifies the slope; otherwise it is stated as a cohort difference.

## S8. Validate the contrast that is analyzed, against a written rubric

P03 gated a four-category classifier on overall kappa, which does not validate the binary
comparison its model uses, against a human reference standard that had no coding rubric.

**Required.** The validation gate is computed on the contrast that enters the model. The human
reference standard has a written rubric with decision rules and worked examples, published with
the design, and it is produced by the author rather than by a model.

## S9. Make the comparison arm concrete

P02 promised articles matched on journal and year and specified no ratio, no replacement rule
and no handling of unmatched strata.

**Required.** Matching variables, ratio, with or without replacement, the treatment of
unmatched units, and the weighting that follows are all stated.

## S10. Account for time at risk

P03 read zero citations as "nobody used it" when most of its 2026 zeros were articles too new to
have been cited.

**Required.** Count outcomes that accrue over time carry exposure time or a censoring rule, and
a fixed follow-up window is preferred to raw totals.

## S11. Novelty is a search result, relevance-ordered

P05 claimed a gap that Federer and colleagues had already filled. A candidate for this round
tested a hypothesis that PMID 36109655 had already tested in its title. The novelty log was
first built on NCBI's default date ordering, so each "top ten" was the ten newest hits.

**Required.** Every claim that something has not been studied shows its corpus regex and its
PubMed query verbatim, run through `build/lit/novelty.py` with relevance ordering, and cites the
log entry. A PMID cited as prior work must appear in `data/lit/novelty-log.json` or in the
harvested corpus; `tools/check_citations.py` enforces this in CI and fails the build on any
PMID that came from neither. The author's
own repositories and papers are checked first: a design that re-runs the author's work with a
new population is not a new design.

## S12. Power for the model that will be fitted

P01v2 computed power from a two-proportion normal approximation for a mixed model with a journal
random effect, and read a confidence interval containing 1 as evidence of absence.

**Required.** Power or precision is computed for the specified model, by simulation where no
closed form fits. A design that wants to claim absence of an effect states the equivalence
margin or precision target that would license the claim.

---

## Two operational rules

**Pin by hash.** An instrument is pinned by a commit hash written into the document together
with the `git show` command that resolves it. A prose pin ("the commit this was published in")
is not a pin.

**Status says what it is.** `design` until the probes run; `protocol` once their numbers are
written in; `blocked-by-review` when review finds an unrebutted evidenced fatal flaw; `agenda`
when public data cannot answer the question. A document is never labeled for the stage it is
hoping to reach.
