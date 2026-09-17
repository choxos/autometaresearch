#!/usr/bin/env python3
"""Feasibility probes for P05: do actionable data availability statements resolve?

P01 and P01v2 grade a statement `actionable` when it names a repository or carries a DOI or
URL. That grade is a claim about the statement, not about the data. This probe asks whether
the thing the statement points at is there.

PA  how many locators can be extracted from the actionable statements, and of what kind
PB  what fraction respond, by HTTP status, for a polite sample

Requests are HEAD first and fall back to a ranged GET, one host at a time with a delay, with
a User-Agent naming the project and a contact address. This is a read-only availability check
of the kind the hosts are built to serve, and it is the measurement the study is about.

Usage: python3 studies/P05-does-the-link-resolve/probes.py [--sample N]
"""

import argparse
import collections
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SOURCES = [
    os.path.join(ROOT, "studies", "P01-advocacy-and-practice", "data", "statements.csv"),
    os.path.join(ROOT, "studies", "P01v2-confirmatory", "out", "frame-statements.csv"),
]
OUT = os.path.join(HERE, "out")
UA = "autometaresearch/1.0 (+https://github.com/choxos/autometaresearch; mailto:ahmad.pub@gmail.com)"

DOI_RX = re.compile(r"\b10\.\d{4,9}/[^\s,;\)\]\"'<>]+")
URL_RX = re.compile(r"https?://[^\s,;\)\]\"'<>]+")
REPO_HOST = re.compile(
    r"osf\.io|zenodo|dryad|figshare|dataverse|github\.com|gitlab\.com|bitbucket|"
    r"codeocean|openneuro|mendeley|pangaea|re3data|borealis", re.I)


def clean(u):
    u = u.rstrip(".,;:)]}'\"")
    # A trailing period is almost always sentence punctuation, but a DOI may legitimately end
    # in one. Stripping is the lesser error: a wrongly stripped DOI fails to resolve and is
    # counted as a failure, which biases toward finding MORE breakage, so the direction has to
    # be reported rather than assumed harmless.
    return u


def locators(text):
    out = []
    for m in URL_RX.finditer(text):
        out.append(("url", clean(m.group(0))))
    for m in DOI_RX.finditer(text):
        d = clean(m.group(0))
        if not any(d in u for _, u in out):
            out.append(("doi", d))
    return out


def check(kind, loc, timeout=25):
    url = f"https://doi.org/{loc}" if kind == "doi" else loc
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "*/*"}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.geturl()
    except urllib.error.HTTPError as e:
        # Several repositories refuse HEAD but serve GET. Retry once with a ranged GET so a
        # 405 is not recorded as a dead link.
        if e.code in (403, 405, 501):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                           "Range": "bytes=0-0"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return r.status, r.geturl()
            except urllib.error.HTTPError as e2:
                return e2.code, None
            except Exception as e2:  # noqa: BLE001
                return f"error:{type(e2).__name__}", None
        return e.code, None
    except Exception as e:  # noqa: BLE001
        return f"error:{type(e).__name__}", None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=150,
                    help="locators to actually request; 0 checks none")
    args = ap.parse_args()

    rows = []
    for path in SOURCES:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf8") as fh:
            for r in csv.DictReader(fh):
                if r.get("full_text") == "1" and (r.get("statement") or "").strip():
                    rows.append({"pmcid": r["pmcid"],
                                 "arm": r.get("arm", "tierA"),
                                 "statement": r["statement"]})

    found, kinds, hosts = [], collections.Counter(), collections.Counter()
    for r in rows:
        for kind, loc in locators(r["statement"]):
            found.append({**r, "kind": kind, "locator": loc})
            kinds[kind] += 1
            if kind == "url":
                m = re.match(r"https?://([^/]+)", loc)
                if m:
                    hosts[m.group(1).lower()] += 1

    with_any = len({f["pmcid"] for f in found})
    repo_locs = [f for f in found if REPO_HOST.search(f["locator"])]

    pa = {
        "statements_examined": len(rows),
        "statements_with_a_locator": with_any,
        "locators_found": len(found),
        "by_kind": dict(kinds),
        "locators_on_a_known_repository_host": len(repo_locs),
        "top_hosts": hosts.most_common(15),
    }
    print("== PA ==")
    for k, v in pa.items():
        print(f"  {k}: {v}")

    pb = {"checked": 0}
    if args.sample:
        import random
        random.seed(20260916)
        # One locator per article, so no single paper with twelve links dominates the rate.
        by_article = {}
        for f in found:
            by_article.setdefault(f["pmcid"], []).append(f)
        picks = [random.choice(v) for v in by_article.values()]
        picks = random.sample(picks, min(args.sample, len(picks)))
        results, last_host = [], {}
        for i, f in enumerate(picks, 1):
            host = re.match(r"https?://([^/]+)", f["locator"])
            host = host.group(1).lower() if host else "doi.org"
            wait = 1.0 - (time.time() - last_host.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            status, final = check(f["kind"], f["locator"])
            last_host[host] = time.time()
            results.append({**f, "status": status, "final_url": final})
            print(f"  {i}/{len(picks)} {status}", end="\r", file=sys.stderr)
        print(file=sys.stderr)
        ok = [r for r in results if isinstance(r["status"], int) and 200 <= r["status"] < 400]
        gone = [r for r in results if isinstance(r["status"], int) and r["status"] >= 400]
        err = [r for r in results if not isinstance(r["status"], int)]
        pb = {
            "checked": len(results),
            "resolved": len(ok),
            "http_error": len(gone),
            "network_error": len(err),
            "resolve_rate": round(len(ok) / max(len(results), 1), 4),
            "status_counts": dict(collections.Counter(str(r["status"]) for r in results)),
        }
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "resolve-sample.csv"), "w", newline="",
                  encoding="utf8") as fh:
            w = csv.DictWriter(fh, fieldnames=["pmcid", "arm", "kind", "locator",
                                               "status", "final_url", "statement"])
            w.writeheader()
            for r in results:
                w.writerow({k: r.get(k) for k in w.fieldnames})
        print("\n== PB ==")
        for k, v in pb.items():
            print(f"  {k}: {v}")

    os.makedirs(OUT, exist_ok=True)
    json.dump({"PA": pa, "PB": pb}, open(os.path.join(OUT, "probes.json"), "w"), indent=1)
    print(f"\n-> {OUT}/probes.json")


if __name__ == "__main__":
    main()
