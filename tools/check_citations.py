#!/usr/bin/env python3
"""Every PMID a proposal cites must come from a recorded search.

Standard item S11: a PMID cited as prior work must appear in data/lit/novelty-log.json, either in a
search's relevance-ordered top hits or in its corpus sample, or be a record of the harvested corpus.
A citation that appears in neither was written from memory, and in a project about research integrity
a citation from memory is the failure the rule exists to stop.

Also checks that each proposal's front matter has the fields the agenda listing reads, and that status
is one of the values the design standard defines.

Usage: python3 tools/check_citations.py   (exit 1 on any failure)
"""

import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "data", "lit", "novelty-log.json")
CORPORA = [os.path.join(ROOT, "data", "lit", f) for f in ("records.jsonl", "frame-P01v2.jsonl")]
STATUSES = {"design", "protocol", "protocol-pending-validation", "protocol-reduced",
            "blocked-by-review", "agenda", "reported"}
REQUIRED = ("title", "id", "status", "date", "reviewed")
PMID = re.compile(r"PMIDs?\s+((?:\d{7,8}(?:,\s*|\s+and\s+)?)+)")


def known_pmids():
    known = set()
    if os.path.exists(LOG):
        for e in json.load(open(LOG, encoding="utf8")):
            known |= {h["pmid"] for h in e["pubmed_top"]}
            known |= {h["pmid"] for h in e["corpus_sample"]}
    for path in CORPORA:
        if os.path.exists(path):
            for line in open(path, encoding="utf8"):
                known.add(json.loads(line)["pmid"])
    return known


def front_matter(text):
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    out = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip().strip('"')
    return out


def main():
    known = known_pmids()
    failures = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "proposals", "*.qmd"))):
        name = os.path.basename(path)
        text = open(path, encoding="utf8").read()
        fm = front_matter(text)
        for k in REQUIRED:
            if k not in fm:
                print(f"FAIL {name}: front matter lacks '{k}'")
                failures += 1
        if fm.get("status") not in STATUSES:
            print(f"FAIL {name}: status '{fm.get('status')}' is not a defined status")
            failures += 1
        cited = set()
        for m in PMID.finditer(text):
            cited |= set(re.findall(r"\d{7,8}", m.group(1)))
        unknown = sorted(cited - known)
        for p in unknown:
            print(f"FAIL {name}: PMID {p} is cited but appears in no recorded search or corpus")
            failures += 1
    n = len(glob.glob(os.path.join(ROOT, "proposals", "*.qmd")))
    print(f"\n{n} proposals checked, {failures} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
