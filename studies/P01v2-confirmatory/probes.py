#!/usr/bin/env python3
"""Probes P1 to P5 for the P01v2 design.

The sibling project's rule: the difference between a design and a protocol is a set of
computed numbers, and a design that asserts those numbers instead of computing them is a
named failure mode. Every number this emits goes into a numbered section of
`proposals/P01v2-advocacy-and-practice-protocol.qmd` and is written there from
`out/probes.json`, never retyped.

P1  frame size after removing every tier A PMID
P2  PMCID coverage of what survives
P3  full-text rate and extraction route distribution   (needs extract; separate step)
P4  grade distribution on the comparison arm           (needs P3)
P5  detectable odds ratio from the realized counts     (computed in R, needs P4)

Usage: python3 studies/P01v2-confirmatory/probes.py
"""

import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LIT = os.path.join(ROOT, "data", "lit")
OUT = os.path.join(HERE, "out")

EXPOSED_BLOCK = "datashare"
COMPARISON_BLOCKS = ("report", "reg", "repro")

# Publication types excluded by section 4.2. An article with no data of its own belongs to a
# different population, and its absence of a statement is not evidence about sharing behavior.
EXCLUDED_PUBTYPES = ("Comment", "Editorial", "Letter", "News", "Biography",
                     "Historical Article", "Retracted Publication", "Retraction of Publication")


def load(path):
    with open(path, encoding="utf8") as fh:
        return [json.loads(line) for line in fh]


def main():
    tier_a = load(os.path.join(LIT, "records.jsonl"))
    frame = load(os.path.join(LIT, "frame-P01v2.jsonl"))

    # The independence condition, applied first so no later step can reintroduce a record.
    # PMID is the key; a frame record without one cannot be checked against tier A and is
    # dropped rather than assumed new.
    tier_a_pmids = {r["pmid"] for r in tier_a if r["pmid"]}
    no_pmid = [r for r in frame if not r["pmid"]]
    overlap = [r for r in frame if r["pmid"] in tier_a_pmids]
    indep = [r for r in frame if r["pmid"] and r["pmid"] not in tier_a_pmids]

    def arm_of(r):
        blocks = set(r["found_by"])
        if EXPOSED_BLOCK in blocks:
            return "exposed"
        if blocks & set(COMPARISON_BLOCKS):
            return "comparison"
        return None

    eligible, excluded_type, excluded_lang = [], 0, 0
    for r in indep:
        if any(p in EXCLUDED_PUBTYPES for p in r["pubtypes"]):
            excluded_type += 1
            continue
        if r["language"] and r["language"].lower() not in ("eng", "english", ""):
            excluded_lang += 1
            continue
        eligible.append(r)

    arms = collections.Counter(arm_of(r) for r in eligible)
    with_pmcid = collections.Counter(arm_of(r) for r in eligible if r["pmcid"])

    # Tier A's own PMC rate, as the reference the design's discarded assumption came from.
    tier_a_pmc = sum(1 for r in tier_a if r["pmcid"]) / len(tier_a)

    p = {
        "P1": {
            "frame_records": len(frame),
            "dropped_no_pmid": len(no_pmid),
            "dropped_overlap_with_tier_a": len(overlap),
            "independent": len(indep),
            "excluded_pubtype": excluded_type,
            "excluded_language": excluded_lang,
            "eligible_before_screening": len(eligible),
            "eligible_exposed": arms["exposed"],
            "eligible_comparison": arms["comparison"],
            "by_block": dict(collections.Counter(
                b for r in eligible for b in r["found_by"])),
        },
        "P2": {
            "with_pmcid_exposed": with_pmcid["exposed"],
            "with_pmcid_comparison": with_pmcid["comparison"],
            "pmcid_rate_exposed": round(with_pmcid["exposed"] / max(arms["exposed"], 1), 4),
            "pmcid_rate_comparison": round(
                with_pmcid["comparison"] / max(arms["comparison"], 1), 4),
            "tier_a_pmcid_rate_for_reference": round(tier_a_pmc, 4),
        },
    }

    os.makedirs(OUT, exist_ok=True)
    json.dump(p, open(os.path.join(OUT, "probes.json"), "w"), indent=1)

    # The PMCID list P3 will fetch. Written here so that the set P3 uses is fixed by P1 and P2
    # and cannot drift if the frame is reharvested.
    with open(os.path.join(OUT, "p3-targets.tsv"), "w", encoding="utf8") as fh:
        fh.write("pmcid\tpmid\tarm\tyear\tjournal\n")
        for r in eligible:
            if r["pmcid"]:
                fh.write(f"{r['pmcid']}\t{r['pmid']}\t{arm_of(r)}\t{r['year']}\t"
                         f"{r['journal']}\n")

    for name, block in p.items():
        print(f"== {name} ==")
        for k, v in block.items():
            print(f"  {k}: {v}")
    print(f"\n-> {OUT}/probes.json and p3-targets.tsv")


if __name__ == "__main__":
    main()
