#!/usr/bin/env python3
"""Feasibility probes for the P02 design: does meta-research cite retracted work?

Runs against the PMC full text already cached by P01 and P01v2, so it costs nothing to NCBI.
Every number it emits goes into the design and is not retyped.

PA  reference extraction: refs per article and the proportion carrying a resolvable DOI
PB  raw matches against Retraction Watch
PC  the split that decides whether the study is worth running: a citation is only a failure
    when the retraction preceded the citing article, and a paper about retraction cites
    retracted work on purpose

Usage: python3 studies/P02-citing-retracted/probes.py
"""

import csv
import glob
import json
import os
import re
import sys
from datetime import datetime
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CACHES = [os.path.join(ROOT, "studies", "P01-advocacy-and-practice", "data", "_cache"),
          os.path.join(ROOT, "studies", "P01v2-confirmatory", "data", "_cache")]
RW = os.path.join(ROOT, "data", "rw", "retractionwatch.csv")
OUT = os.path.join(HERE, "out")

DOI_RX = re.compile(r"10\.\d{4,9}/\S+")


def norm_doi(d):
    d = (d or "").strip().lower().rstrip(".,;)")
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d


def parse_date(s):
    for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def article_year(art):
    for pd in art.iter("pub-date"):
        y = pd.find("year")
        if y is not None and (y.text or "").strip().isdigit():
            return int(y.text.strip())
    return None


def main():
    rw = {}
    with open(RW, encoding="utf8", errors="ignore") as fh:
        for r in csv.DictReader(fh):
            d = norm_doi(r.get("OriginalPaperDOI"))
            if d and r.get("RetractionNature", "").strip() == "Retraction":
                rw.setdefault(d, parse_date(r.get("RetractionDate", "")))
    print(f"Retraction Watch: {len(rw)} distinct retracted DOIs", file=sys.stderr)

    n_art = n_refs = n_doi_refs = 0
    per_article, matches = [], []
    for cache in CACHES:
        for path in sorted(glob.glob(os.path.join(cache, "*.xml"))):
            try:
                root = ET.parse(path).getroot()
            except ET.ParseError:
                continue
            for art in root.iter("article"):
                back = art.find("back")
                if back is None:
                    continue
                refs = list(back.iter("ref"))
                if not refs:
                    continue
                ids = {x.get("pub-id-type"): (x.text or "") for x in art.iter("article-id")}
                pmcid = ids.get("pmcid") or ids.get("pmc") or ""
                if pmcid and not pmcid.upper().startswith("PMC"):
                    pmcid = "PMC" + pmcid
                year = article_year(art)
                # Counted per reference, not per distinct string. A first version summed the
                # distinct DOI-like strings found per article and divided by the reference
                # count, which produced a "coverage" of 1.41: the plain-text regex matches
                # several times inside one reference, so the numerator was not a subset of
                # the denominator. A rate above 1 is the only reason that was caught.
                dois, refs_with_doi = set(), 0
                for ref in refs:
                    here_dois = set()
                    for pid in ref.iter("pub-id"):
                        if pid.get("pub-id-type") == "doi":
                            d = norm_doi(pid.text)
                            if d:
                                here_dois.add(d)
                    # Some publishers print the DOI as plain text rather than tagging it.
                    for m in DOI_RX.finditer("".join(ref.itertext())):
                        d = norm_doi(m.group(0))
                        if d:
                            here_dois.add(d)
                    if here_dois:
                        refs_with_doi += 1
                    dois |= here_dois
                n_art += 1
                n_refs += len(refs)
                n_doi_refs += refs_with_doi
                hit = dois & rw.keys()
                per_article.append({"pmcid": pmcid, "year": year,
                                    "refs": len(refs), "doi_refs": refs_with_doi,
                                    "retracted_cited": len(hit)})
                for d in hit:
                    matches.append({"pmcid": pmcid, "citing_year": year, "cited_doi": d,
                                    "retraction_date": rw[d].isoformat() if rw[d] else None})

    post = [m for m in matches
            if m["retraction_date"] and m["citing_year"]
            and int(m["retraction_date"][:4]) < m["citing_year"]]
    pre = [m for m in matches
           if m["retraction_date"] and m["citing_year"]
           and int(m["retraction_date"][:4]) >= m["citing_year"]]

    p = {
        "PA": {
            "articles_with_a_reference_list": n_art,
            "total_references": n_refs,
            "references_carrying_a_doi": n_doi_refs,
            "doi_coverage": round(n_doi_refs / max(n_refs, 1), 4),
            "distinct_matchable_dois": sum(a["doi_refs"] for a in per_article),
            "median_refs_per_article": sorted(a["refs"] for a in per_article)[n_art // 2]
            if n_art else 0,
        },
        "PB": {
            "retraction_watch_dois": len(rw),
            "citations_of_retracted_work": len(matches),
            "articles_citing_at_least_one": len({m["pmcid"] for m in matches}),
        },
        "PC": {
            "post_retraction_citations": len(post),
            "pre_retraction_citations": len(pre),
            "undated": len(matches) - len(post) - len(pre),
            "articles_with_a_post_retraction_citation": len({m["pmcid"] for m in post}),
        },
    }
    os.makedirs(OUT, exist_ok=True)
    json.dump(p, open(os.path.join(OUT, "probes.json"), "w"), indent=1)
    with open(os.path.join(OUT, "matches.csv"), "w", newline="", encoding="utf8") as fh:
        w = csv.DictWriter(fh, fieldnames=["pmcid", "citing_year", "cited_doi",
                                           "retraction_date"])
        w.writeheader()
        w.writerows(matches)

    for k, v in p.items():
        print(f"== {k} ==")
        for kk, vv in v.items():
            print(f"  {kk}: {vv}")
    print(f"\n-> {OUT}/probes.json, matches.csv")


if __name__ == "__main__":
    main()
