#!/usr/bin/env python3
"""OpenAlex probes shared by P03 and P06.

P03 needs citation counts on the tier A corpus. P06 needs to know how many of those records
have a preprint version. Both answers come from the same records, so both are fetched in one
pass of about 37 calls rather than twice.

Output: data/lit/openalex.jsonl, one line per matched record, and a printed summary.

Usage: python3 studies/_shared/openalex_probe.py
"""

import collections
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
# Which corpus to resolve. Passing a stem rather than copying this file: a sed-edited copy
# in a temp directory resolved ROOT from its own location and looked for the corpus in the
# temp tree, which is the obvious failure and took a run to notice.
STEM = sys.argv[1] if len(sys.argv) > 1 else "records"
CORPUS = os.path.join(ROOT, "data", "lit", f"{STEM}.jsonl")
OUT = os.path.join(ROOT, "data", "lit", f"openalex-{STEM}.jsonl")
SUMMARY = os.path.join(ROOT, "data", "lit", f"openalex-{STEM}-summary.json")
MAILTO = "ahmad.pub@gmail.com"
UA = f"autometaresearch/1.0 (mailto:{MAILTO})"

# OpenAlex asks for a mailto and gives the polite pool in return. 50 ids per filter is the
# documented ceiling for an OR list.
BATCH = 50
SELECT = ("id,doi,ids,publication_year,cited_by_count,type,"
          "primary_location,locations,open_access,authorships,referenced_works_count")


def get(url, tries=4):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf8"))
        except Exception as e:  # noqa: BLE001
            if attempt == tries - 1:
                raise
            print(f"    retry {attempt + 1} after {e}", file=sys.stderr)
            time.sleep(2 ** attempt)
    return {}


def main():
    records = [json.loads(l) for l in open(CORPUS, encoding="utf8")]
    pmids = [r["pmid"] for r in records if r["pmid"]]
    print(f"{len(pmids)} PMIDs to resolve", file=sys.stderr)

    out = []
    for i in range(0, len(pmids), BATCH):
        batch = pmids[i:i + BATCH]
        q = urllib.parse.urlencode({
            "filter": "pmid:" + "|".join(batch),
            "select": SELECT, "per-page": 100, "mailto": MAILTO,
        })
        d = get(f"https://api.openalex.org/works?{q}")
        out.extend(d.get("results", []))
        print(f"  {min(i + BATCH, len(pmids))}/{len(pmids)}", end="\r", file=sys.stderr)
        time.sleep(0.15)
    print(file=sys.stderr)

    with open(OUT, "w", encoding="utf8") as fh:
        for w in out:
            fh.write(json.dumps(w, ensure_ascii=False) + "\n")

    cites = sorted(w.get("cited_by_count", 0) for w in out)
    # A preprint version means a location whose source is a repository, other than the
    # primary. PMC is a repository too, so a bare repository count would say "almost all of
    # them" and mean nothing; the preprint servers are named explicitly.
    PREPRINT = ("biorxiv", "medrxiv", "arxiv", "ssrn", "osf", "preprints.org",
                "research square", "zenodo", "psyarxiv", "metaarxiv")
    with_preprint, by_server = 0, collections.Counter()
    for w in out:
        names = set()
        for loc in (w.get("locations") or []):
            src = (loc.get("source") or {})
            nm = (src.get("display_name") or "").lower()
            if any(p in nm for p in PREPRINT):
                names.add(nm)
        if names:
            with_preprint += 1
            for nm in names:
                by_server[nm] += 1

    oa = collections.Counter((w.get("open_access") or {}).get("oa_status") for w in out)
    n = len(out)
    summary = {
        "pmids_queried": len(pmids),
        "matched_in_openalex": n,
        "match_rate": round(n / max(len(pmids), 1), 4),
        "citations_median": cites[n // 2] if n else 0,
        "citations_mean": round(sum(cites) / max(n, 1), 2),
        "citations_zero": sum(1 for c in cites if c == 0),
        "citations_p90": cites[int(n * 0.9)] if n else 0,
        "citations_max": cites[-1] if n else 0,
        "records_with_a_preprint_version": with_preprint,
        "preprint_rate": round(with_preprint / max(n, 1), 4),
        "top_preprint_servers": by_server.most_common(8),
        "oa_status": dict(oa),
    }
    json.dump(summary, open(SUMMARY, "w"), indent=1)
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
