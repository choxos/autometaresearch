#!/usr/bin/env python3
"""P01 harvest: pull the data availability statement out of every corpus record in PMC.

Python does the retrieval and the text extraction; every decision about what a statement
means is made in R, in `R/analyze.R`, so that the grading rule and the model live together
and can be read as one argument.

The output is one CSV row per record with a PMCID, carrying the raw statement text and the
JATS route it was found by. Nothing is graded here.

Usage: python3 studies/P01-advocacy-and-practice/extract.py [--refresh]
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "build", "lit"))
from search import get, EUTILS, EMAIL, TOOL, _text  # noqa: E402

CORPUS = os.path.join(ROOT, "data", "lit", "records-labelled.jsonl")
CACHE = os.path.join(HERE, "data", "_cache")
OUT = os.path.join(HERE, "data", "statements.csv")

# The places a data availability statement lives in JATS, in the order they are tried, and
# only within <front> and <back>. A publisher picks one and is consistent, but the corpus
# spans hundreds of publishers, so all of them are needed. `route` is written to the output
# because a result that depends on which route a publisher uses is a result about publishers,
# and the route has to be visible to check that.
#
# Two things this deliberately does not do. It does not fall back to a free-text search of
# the body for "data are available", because a sentence in a discussion is not a statement.
# And it does not treat the absence of a section as proof the authors shared nothing; it is
# proof the article carries no statement, which is the outcome actually being measured.
TITLE_RX = re.compile(
    r"(data|code|software)\s+(and\s+(code|materials?|software)\s+)?availability"
    r"|availability\s+of\s+(the\s+)?(data|code|materials)"
    r"|data\s+sharing\s+statement"
    r"|data\s+access(ibility)?\s+statement",
    re.I,
)


def statement_from(art):
    """The statement text and the route it came from, or ("", "none").

    Only <front> and <back> are searched, never <body>, and that restriction is the whole
    correctness argument. A first version walked the entire article and produced a result
    that was an artifact: a meta-research paper ABOUT data availability carries sections
    called "Data availability over time" and "Extraction of data availability status" in its
    own methods and results, and reading those as the paper's own statement graded the paper
    actionable because they are full of repository URLs. Four of the 43 exposed records were
    contaminated this way, and the exposed arm hit the fuzzy title routes three times more
    often than the unexposed arm, which is what the bias looks like from outside.

    A data availability statement is front or back matter. A numbered section of the
    narrative is the paper's argument, not its disclosure. One publisher even tags a numbered
    methods section `sec-type="data-availability"` (PMC8441137), so the type attribute alone
    does not save this; the location does. PMC11078384 shows the fix is not merely subtractive:
    its real statement is in <front> and was being shadowed by its own results section.
    """
    for part in ("front", "back"):
        parent = art.find(part)
        if parent is None:
            continue
        # 1. A section or notes block explicitly typed by the publisher.
        for tag in ("sec", "notes"):
            for node in parent.iter(tag):
                t = (node.get("sec-type") or node.get("notes-type") or "").lower()
                if "data-availability" in t or "data-access" in t or t == "availability":
                    return _text(node), f"{part}-{tag}-type"
        # 2. A section or notes block whose title says what it is.
        for tag in ("sec", "notes"):
            for node in parent.iter(tag):
                title = node.find("title")
                if title is not None and TITLE_RX.search(_text(title)):
                    return _text(node), f"{part}-{tag}-title"
        # 3. A custom-meta pair, used by a few publishers for the same purpose.
        for cm in parent.iter("custom-meta"):
            name = _text(cm.find("meta-name"))
            if name and TITLE_RX.search(name):
                return _text(cm.find("meta-value")), f"{part}-custom-meta"
    return "", "none"


def has_body(art):
    """Whether PMC actually holds the full text, as opposed to metadata with an abstract.

    A record with no <body> cannot have a statement extracted and must be excluded rather
    than counted as a record without one. Conflating the two would put every abstract-only
    deposit in the "no statement" arm and bias the whole result.
    """
    body = art.find("body")
    return body is not None and len(_text(body)) > 500


def fetch(pmcids, refresh=False):
    os.makedirs(CACHE, exist_ok=True)
    size = 20
    for i in range(0, len(pmcids), size):
        batch = pmcids[i:i + size]
        digest = hashlib.sha1(",".join(batch).encode()).hexdigest()[:12]
        path = os.path.join(CACHE, f"pmc_{i:06d}_{digest}.xml")
        if os.path.exists(path) and os.path.getsize(path) > 500 and not refresh:
            xml = open(path, encoding="utf8", errors="ignore").read()
        else:
            xml = get(f"{EUTILS}/efetch.fcgi",
                      data=f"db=pmc&id={','.join(batch)}&retmode=xml"
                           f"&email={EMAIL}&tool={TOOL}")
            open(path, "w", encoding="utf8").write(xml)
        print(f"  {min(i + size, len(pmcids))}/{len(pmcids)}", end="\r", file=sys.stderr)
        yield xml
    print(file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    records = [json.loads(l) for l in open(CORPUS, encoding="utf8")]
    by_pmcid = {r["pmcid"]: r for r in records if r["pmcid"]}
    pmcids = sorted(by_pmcid)
    print(f"{len(records)} corpus records, {len(pmcids)} with a PMCID", file=sys.stderr)

    found = {}
    for xml in fetch(pmcids, args.refresh):
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as e:
            print(f"    unparseable batch: {e}", file=sys.stderr)
            continue
        for art in root.iter("article"):
            ids = {i.get("pub-id-type"): (i.text or "").strip()
                   for i in art.iter("article-id")}
            pmcid = ids.get("pmcid") or ids.get("pmc") or ""
            if pmcid and not pmcid.upper().startswith("PMC"):
                pmcid = "PMC" + pmcid
            if pmcid not in by_pmcid:
                continue
            text, route = statement_from(art)
            found[pmcid] = {"statement": re.sub(r"\s+", " ", text).strip(),
                            "route": route, "full_text": int(has_body(art))}

    with open(OUT, "w", encoding="utf8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["pmcid", "pmid", "year", "journal", "pubtypes", "labels",
                    "topic_datashare", "retrieved", "full_text", "route", "statement"])
        for pmcid in pmcids:
            r = by_pmcid[pmcid]
            f = found.get(pmcid)
            w.writerow([
                pmcid, r["pmid"], r["year"], r["journal"],
                ";".join(r["pubtypes"]), ";".join(r["labels"]),
                int("datashare" in r["labels"]),
                int(f is not None),
                f["full_text"] if f else 0,
                f["route"] if f else "not-retrieved",
                f["statement"] if f else "",
            ])

    n_ret = sum(1 for f in found.values())
    n_body = sum(1 for f in found.values() if f["full_text"])
    n_stmt = sum(1 for f in found.values() if f["statement"])
    print(f"retrieved {n_ret}/{len(pmcids)}; with full text {n_body}; "
          f"with a statement {n_stmt}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
