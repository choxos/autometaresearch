#!/usr/bin/env python3
"""Probe P3: run the pinned extractor over the P01v2 frame.

Imports `statement_from` and `has_body` from the P01 study rather than reimplementing them.
That import is the point: section 6.1 of the design pins the extractor, and a probe that
measured a copy of it would be measuring the wrong thing.

Output: out/frame-statements.csv, same columns as the P01 study, plus the arm.

Usage: python3 studies/P01v2-confirmatory/extract_frame.py
"""

import csv
import hashlib
import os
import re
import sys
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "build", "lit"))
sys.path.insert(0, os.path.join(ROOT, "studies", "P01-advocacy-and-practice"))
from search import get, EUTILS, EMAIL, TOOL  # noqa: E402
from extract import statement_from, has_body  # noqa: E402

TARGETS = os.path.join(HERE, "out", "p3-targets.tsv")
CACHE = os.path.join(HERE, "data", "_cache")
OUT = os.path.join(HERE, "out", "frame-statements.csv")


def main():
    with open(TARGETS, encoding="utf8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    by_pmcid = {r["pmcid"]: r for r in rows}
    pmcids = sorted(by_pmcid)
    print(f"{len(pmcids)} PMC records to fetch", file=sys.stderr)

    os.makedirs(CACHE, exist_ok=True)
    found, size = {}, 20
    for i in range(0, len(pmcids), size):
        batch = pmcids[i:i + size]
        digest = hashlib.sha1(",".join(batch).encode()).hexdigest()[:12]
        path = os.path.join(CACHE, f"pmc_{i:06d}_{digest}.xml")
        if os.path.exists(path) and os.path.getsize(path) > 500:
            xml = open(path, encoding="utf8", errors="ignore").read()
        else:
            xml = get(f"{EUTILS}/efetch.fcgi",
                      data=f"db=pmc&id={','.join(batch)}&retmode=xml"
                           f"&email={EMAIL}&tool={TOOL}")
            open(path, "w", encoding="utf8").write(xml)
        print(f"  {min(i + size, len(pmcids))}/{len(pmcids)}", end="\r", file=sys.stderr)
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as e:
            print(f"\n    unparseable batch {path}: {e}", file=sys.stderr)
            continue
        for art in root.iter("article"):
            ids = {x.get("pub-id-type"): (x.text or "").strip()
                   for x in art.iter("article-id")}
            pmcid = ids.get("pmcid") or ids.get("pmc") or ""
            if pmcid and not pmcid.upper().startswith("PMC"):
                pmcid = "PMC" + pmcid
            if pmcid not in by_pmcid:
                continue
            text, route = statement_from(art)
            found[pmcid] = {"statement": re.sub(r"\s+", " ", text).strip(),
                            "route": route, "full_text": int(has_body(art))}
    print(file=sys.stderr)

    with open(OUT, "w", encoding="utf8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["pmcid", "pmid", "arm", "year", "journal",
                    "retrieved", "full_text", "route", "statement"])
        for pmcid in pmcids:
            r, f = by_pmcid[pmcid], found.get(pmcid)
            w.writerow([pmcid, r["pmid"], r["arm"], r["year"], r["journal"],
                        int(f is not None), f["full_text"] if f else 0,
                        f["route"] if f else "not-retrieved",
                        f["statement"] if f else ""])

    print(f"retrieved {len(found)}/{len(pmcids)}; "
          f"with full text {sum(1 for f in found.values() if f['full_text'])}; "
          f"with a statement {sum(1 for f in found.values() if f['statement'])}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
