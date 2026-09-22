#!/usr/bin/env python3
"""Record the search behind a novelty claim, so the claim can be checked.

A design in this project may only say that something has not been studied if it shows the
search that failed to find it. A model's recollection that nothing exists is not evidence,
and "never invent a citation" is only enforceable if the citations a design does make come
from a search result rather than from memory.

For one design, this runs two searches and appends both, with their results, to
data/lit/novelty-log.json:

  1. a regex over title and abstract of the tier A corpus and the P01v2 frame;
  2. a PubMed query, returning the total count and the titles and PMIDs of the top hits,
     ordered by relevance. NCBI orders by date unless told otherwise, and a date-ordered top
     ten is only the ten newest matches.

The PMIDs a design cites as prior work must appear in this log.

Usage:
    python3 build/lit/novelty.py <design_id> <corpus_regex> <pubmed_query> [--top 10]
    python3 build/lit/novelty.py --show <design_id>
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from search import EUTILS, EMAIL, TOOL, esearch, get  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIT = os.path.join(ROOT, "data", "lit")
LOG = os.path.join(LIT, "novelty-log.json")
CORPORA = ("records.jsonl", "frame-P01v2.jsonl")


def corpus_hits(pattern):
    rx = re.compile(pattern, re.I)
    hits, seen = [], set()
    for name in CORPORA:
        path = os.path.join(LIT, name)
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf8"):
            r = json.loads(line)
            if r["pmid"] in seen:
                continue
            if rx.search(r["title"] + " " + r["abstract"]):
                seen.add(r["pmid"])
                hits.append({"pmid": r["pmid"], "year": r["year"], "title": r["title"]})
    return hits


def pubmed_top(query, top):
    ids, total = esearch("pubmed", query, retmax=top, sort="relevance")
    if not ids:
        return total, []
    q = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids), "retmode": "json",
                                "email": EMAIL, "tool": TOOL})
    d = json.loads(get(f"{EUTILS}/esummary.fcgi?{q}"), strict=False)["result"]
    out = []
    for i in ids:
        s = d.get(i, {})
        out.append({"pmid": i, "year": (s.get("pubdate") or "")[:4],
                    "title": s.get("title", ""), "journal": s.get("source", "")})
    return total, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("design", nargs="?")
    ap.add_argument("regex", nargs="?")
    ap.add_argument("query", nargs="?")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--show")
    a = ap.parse_args()

    log = json.load(open(LOG)) if os.path.exists(LOG) else []
    if a.show:
        for e in log:
            if e["design"] == a.show:
                print(json.dumps(e, indent=1))
        return
    if not (a.design and a.regex and a.query):
        ap.error("design, regex and query are required")

    ch = corpus_hits(a.regex)
    total, top = pubmed_top(a.query, a.top)
    entry = {"design": a.design, "date": date.today().isoformat(),
             "corpus_regex": a.regex, "corpus_hits": len(ch), "corpus_sample": ch[:10],
             "pubmed_query": a.query, "pubmed_total": total, "pubmed_top": top}
    log = [e for e in log if not (e["design"] == a.design and e["pubmed_query"] == a.query
                                  and e["corpus_regex"] == a.regex)]
    log.append(entry)
    json.dump(log, open(LOG, "w"), indent=1)

    print(f"== {a.design} ==  corpus: {len(ch)}   pubmed: {total}")
    for h in ch[:5]:
        print(f"   C {h['year']} {h['pmid']:>9} {h['title'][:100]}")
    for h in top:
        print(f"   P {h['year']} {h['pmid']:>9} {h['title'][:100]}")


if __name__ == "__main__":
    main()
