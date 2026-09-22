#!/usr/bin/env python3
"""Stage 1: harvest citation records for the meta-research search blocks.

Searches PubMed and PMC for each phrase in title, abstract and author keywords, then
fetches the full citation record for every hit. PMC is searched as well as PubMed because
PMC carries records PubMed does not index: author manuscripts, a few non-MEDLINE journals,
and deposited preprints.

Adapted from the sibling project TTE-open-problems, whose partitioning, caching and
deduplication are reused unchanged in spirit. What differs: the phrase set, a --counts mode
that sizes the corpus before anything is downloaded, and a recursive date bisection that
cannot truncate silently.

Output: data/lit/records.jsonl, one JSON object per unique article, carrying every block
that retrieved it and the databases it came from.

Usage:
    python3 build/lit/search.py --counts            # size the corpus, download nothing
    python3 build/lit/search.py --counts --tier A
    python3 build/lit/search.py --blocks metares,retract
    python3 build/lit/search.py --check             # 5 records, assert the fields parse
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from xml.etree import ElementTree as ET

EMAIL = "ahmad.pub@gmail.com"
TOOL = "autometaresearch"
UA = f"{TOOL}/1.0 (mailto:{EMAIL})"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "lit")
CACHE = os.path.join(OUT, "_cache")

# Search blocks, in two tiers.
#
# Tier A is the field naming itself. A paper that calls its own work meta-research is
# meta-research, and precision is close to total. It is small, and it is the seed.
#
# Tier B is the field by subject matter. These blocks retrieve two populations that no
# boolean query separates: studies ABOUT a practice, and studies that merely performed it.
# "data sharing" returns trials that shared their data alongside surveys of how often trials
# share data, and only the second kind belongs here. That separation is a classification
# problem, handled downstream on the abstract, not here. Tier B is therefore sized first and
# harvested only once its scope has been chosen.
#
# Each block carries every surface form, because PubMed does not stem inside a quoted phrase.
# A quoted phrase PubMed cannot find in its phrase index is broken into words and ANDed, which
# is how "g-formula" retrieves infant formula in the sibling project; any phrase whose count
# looks implausibly large is suffering that, and --counts is what exposes it.
TIER_A = {
    "metares": [
        "meta-research", "metaresearch", "meta research",
        "metascience", "meta-science",
        "research on research", "science of science",
        "meta-epidemiological", "meta-epidemiology",
    ],
}

TIER_B = {
    "repro": [
        "reproducibility crisis", "replication crisis",
        "replication study", "replication studies",
        "reproducibility of research", "computational reproducibility",
        "analytic reproducibility", "analytical reproducibility",
        "reproducible research",
    ],
    "report": [
        "reporting quality", "quality of reporting", "completeness of reporting",
        "adherence to reporting", "reporting guideline", "reporting guidelines",
        "CONSORT statement", "PRISMA statement", "STROBE statement",
        "ARRIVE guidelines", "SPIRIT statement", "TRIPOD statement",
        "CHEERS statement", "STARD statement",
    ],
    "datashare": [
        "data sharing", "data availability statement", "data availability statements",
        "code sharing", "code availability", "open data",
        "FAIR principles", "FAIR data", "data reuse", "individual participant data sharing",
    ],
    "oa": [
        "open access publishing", "open access articles", "open access journals",
        "preprint", "preprints", "preprint server",
        "article processing charge", "article processing charges", "predatory journal",
        "predatory journals",
    ],
    # "trial registration" is deliberately absent. Measured 2026-09-16 it returns 156 828
    # PubMed records, five sixths of everything this block retrieved, and the phrase is not
    # being word-ANDed: it is the label of a structured abstract section, so every registered
    # trial in PubMed carries it verbatim. The phrase identifies trials that were registered,
    # never studies of registration. The forms below are the ones a study of registration
    # practice uses and a registered trial does not.
    "reg": [
        "prospective registration", "prospectively registered", "retrospectively registered",
        "registration status", "outcome switching", "outcome reporting bias",
        "selective outcome reporting", "publication bias",
        "registered reports", "protocol availability", "registry entry",
    ],
    "retract": [
        "retracted publication", "retracted publications", "retracted article",
        "retracted articles", "retraction notice", "research misconduct",
        "scientific misconduct", "paper mill", "paper mills", "research integrity",
        "image duplication", "scientific plagiarism",
    ],
    "peerrev": [
        "peer review process", "peer review quality", "open peer review",
        "reviewer bias", "editorial peer review", "post-publication peer review",
        "peer reviewer agreement",
    ],
    "stats": [
        "p-hacking", "questionable research practices", "researcher degrees of freedom",
        "HARKing", "garden of forking paths", "selective reporting of analyses",
        "spin in abstracts", "spin in reporting", "statistical significance misuse",
        "misinterpretation of p-values", "multiplicity of analyses",
    ],
    "coi": [
        "conflict of interest disclosure", "conflicts of interest disclosure",
        "undisclosed conflicts", "industry sponsorship", "industry funding",
        "financial ties", "funding source bias", "sponsorship bias",
    ],
    "waste": [
        "research waste", "avoidable waste", "waste in research",
        "redundant research", "unnecessary duplication of research",
        "value of information in research", "research prioritization",
    ],
    "biblio": [
        "honorary authorship", "ghost authorship", "gift authorship",
        "authorship practices", "citation bias", "citation distortion",
        "bibliometric analysis", "altmetric", "journal impact factor",
    ],
    "equity": [
        "gender disparities in authorship", "gender gap in authorship",
        "representation in clinical trials", "diversity in clinical trials",
        "geographic representation of authors", "authorship inequity",
        "global health authorship",
    ],
    "aitext": [
        "AI-generated text", "ChatGPT in academic writing", "large language models in research",
        "LLM-generated text", "AI-assisted peer review", "generative AI in research",
    ],
}

BLOCKS = {**TIER_A, **TIER_B}
TIER_OF = {**{k: "A" for k in TIER_A}, **{k: "B" for k in TIER_B}}

# The study-of-literature qualifier, applied to tier B under --qualified.
#
# It names the object of study. A study of data sharing examines published articles; a trial
# that shared its data examines patients. ANDing the topic block with this set separates them
# far better than any topic phrase does: measured 2026-09-16 it took `reg` from 189 588 to
# 8 205 and `datashare` from 15 418 to 767.
#
# It buys that precision with recall, and the loss is not small: a meta-research paper that
# describes its sample as "we examined 300 trials" carries none of these phrases. Both counts
# are therefore recorded, so the qualified corpus is always reported against the raw number it
# was drawn from rather than presented as the whole field.
#
# "bibliometric" is excluded from the qualifier on purpose: it is itself a phrase in the
# `biblio` block, and a qualifier containing a term from the block it filters cannot filter it.
QUALIFIER = [
    "published articles", "published studies", "published trials", "journal articles",
    "publications", "sample of articles", "cross-sectional study of",
    "we searched PubMed", "we searched MEDLINE", "we searched Embase",
    "research articles", "abstracts of", "meta-epidemiological", "sample of trials",
]

# NCBI allows 3 requests/second without an API key.
THROTTLE = 0.36
_last = [0.0]


def get(url, data=None, tries=5):
    for attempt in range(tries):
        wait = THROTTLE - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(
                url,
                data=data.encode() if data else None,
                headers={"User-Agent": UA, "Accept": "*/*"},
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read().decode("utf8", "ignore")
        except Exception as e:  # noqa: BLE001 - transient NCBI failures are routine
            if attempt == tries - 1:
                raise
            print(f"    retry {attempt + 1} after {e}", file=sys.stderr)
            time.sleep(2 ** attempt)
    return ""


CEILING = 9999  # NCBI will not return more than this many ids for one query


def esearch(db, term, retmax=CEILING, sort=None):
    """Ids and total count for a term.

    `sort` is None for harvesting, where order is irrelevant because every id is fetched. It
    must be "relevance" for anything that reads only the top of the list: NCBI's default order
    is by date, so an unsorted top ten is simply the ten newest matches. The novelty log was
    first built on date-sorted top tens, which surfaced mostly irrelevant 2026 papers and would
    have let a claim of "no prior work" rest on a list that never looked for it.
    """
    params = {"db": db, "term": term, "retmax": retmax, "retmode": "json",
              "email": EMAIL, "tool": TOOL}
    if sort:
        params["sort"] = sort
    q = urllib.parse.urlencode(params)
    # strict=False: NCBI echoes the query back with raw control characters,
    # which the default decoder rejects.
    d = json.loads(get(f"{EUTILS}/esearch.fcgi?{q}"), strict=False)["esearchresult"]
    return d.get("idlist", []), int(d["count"])


def _or(db, variants):
    parts = []
    for v in variants:
        parts.append(f'"{v}"[Title/Abstract]')
        if db == "pubmed":
            parts.append(f'"{v}"[Other Term]')
    return " OR ".join(parts)


def term_for(db, variants, qualified=False):
    """One query string for a block, over title, abstract and author keywords.

    Tier A is never qualified. A paper that calls itself meta-research needs no further
    evidence that research is what it studies, and qualifying it would only lose records.
    """
    t = _or(db, variants)
    return f"({t}) AND ({_or(db, QUALIFIER)})" if qualified else t


def _range_ids(db, term, lo, hi, gaps):
    """Ids for a term within a publication-date range, bisecting until under the ceiling.

    The sibling project partitions by year and then by month and stops there, so a single
    month above the ceiling truncates without saying so. Meta-research blocks are large and
    concentrated in recent years, which is exactly where that would happen. Bisecting to a
    single day has no such floor, and when even one day is over the ceiling the range is
    recorded in `gaps` rather than passed off as complete.
    """
    sub = f'({term}) AND ("{lo:%Y/%m/%d}"[PDAT] : "{hi:%Y/%m/%d}"[PDAT])'
    ids, total = esearch(db, sub)
    if total <= CEILING:
        return ids, total
    if lo >= hi:
        gaps.append({"day": f"{lo:%Y-%m-%d}", "hits": total, "retrieved": len(ids)})
        return ids, total
    mid = lo + (hi - lo) // 2
    lids, ltot = _range_ids(db, term, lo, mid, gaps)
    rids, rtot = _range_ids(db, term, mid + timedelta(days=1), hi, gaps)
    return lids + rids, ltot + rtot


def collect_ids(db, term):
    """Every id for a term. Returns (unique ids, reported total, partition sum, gaps)."""
    ids, total = esearch(db, term)
    if total <= CEILING:
        return ids, total, total, []
    gaps = []
    seen, harvested = _range_ids(db, term, date(1900, 1, 1), date.today(), gaps)
    return list(dict.fromkeys(seen)), total, harvested, gaps


def _text(node):
    """Flatten an element's text, including markup children like <i> and <sup>."""
    return re.sub(r"\s+", " ", "".join(node.itertext())).strip() if node is not None else ""


def article_ids(art, paths):
    """The record's own identifiers, from its ArticleIdList and nowhere else.

    A blanket art.iter("ArticleId") also walks ReferenceList and CommentsCorrectionsList, so
    the DOI and PMCID that come back belong to the last work the article happens to cite.
    Restrict to the declared paths.
    """
    ids = {}
    for path in paths:
        for i in art.findall(path):
            t, v = i.get("IdType"), (i.text or "").strip()
            if t and v and t not in ids:
                ids[t] = v
    pmc = ids.get("pmc", "")
    if pmc and not pmc.upper().startswith("PMC"):
        ids["pmc"] = "PMC" + pmc
    return ids


def parse_pubmed(xml):
    root = ET.fromstring(xml)
    out = []
    for art in root.iter("PubmedBookArticle"):
        rec = parse_pubmed_book(art)
        if rec:
            out.append(rec)
    for art in root.iter("PubmedArticle"):
        cit = art.find("MedlineCitation")
        a = cit.find(".//Article")
        if a is None:
            continue
        ids = article_ids(art, ("PubmedData/ArticleIdList/ArticleId",))
        j = a.find("Journal")
        year = ""
        for tag in (".//ArticleDate/Year", ".//JournalIssue/PubDate/Year",
                    ".//JournalIssue/PubDate/MedlineDate"):
            v = _text(a.find(tag)) or _text(cit.find(tag))
            if v:
                year = v[:4]
                break
        abstract = " ".join(
            (seg.get("Label", "") + ": " if seg.get("Label") else "") + _text(seg)
            for seg in a.iter("AbstractText")
        ).strip()
        out.append({
            "pmid": _text(cit.find("PMID")),
            "pmcid": ids.get("pmc", ""),
            "doi": ids.get("doi", "").lower(),
            "title": _text(a.find("ArticleTitle")),
            "abstract": abstract,
            "journal": _text(j.find("Title")) if j is not None else "",
            "journal_abbrev": _text(j.find("ISOAbbreviation")) if j is not None else "",
            "year": year,
            "pubtypes": [_text(p) for p in a.iter("PublicationType")],
            "keywords": [_text(k) for k in cit.iter("Keyword")],
            "mesh": [_text(m.find("DescriptorName")) for m in cit.iter("MeshHeading")],
            "authors": [
                (_text(au.find("LastName")) + " " + _text(au.find("Initials"))).strip()
                for au in a.iter("Author")
            ][:12],
            "language": _text(a.find(".//Language")),
        })
    return out


def parse_pubmed_book(art):
    """Bookshelf records, which PubMed returns as PubmedBookArticle.

    Worth parsing rather than dropping: several of the standing guidance documents this
    field cites, including NICE and Cochrane methods series, are indexed here and nowhere
    else in PubMed.
    """
    cit = art.find("BookDocument")
    if cit is None:
        return None
    ids = article_ids(art, ("BookDocument/ArticleIdList/ArticleId",
                            "PubmedBookData/ArticleIdList/ArticleId"))
    book = cit.find("Book")
    title = _text(cit.find("ArticleTitle")) or _text(book.find("BookTitle") if book is not None else None)
    abstract = " ".join(
        (seg.get("Label", "") + ": " if seg.get("Label") else "") + _text(seg)
        for seg in cit.iter("AbstractText")
    ).strip()
    return {
        "pmid": _text(cit.find("PMID")),
        "pmcid": ids.get("pmc", ""),
        "doi": ids.get("doi", "").lower(),
        "title": title,
        "abstract": abstract,
        "journal": _text(book.find("BookTitle")) if book is not None else "",
        "journal_abbrev": _text(book.find("Publisher/PublisherName")) if book is not None else "",
        "year": (_text(book.find("PubDate/Year")) if book is not None else "")[:4],
        "pubtypes": [_text(p) for p in cit.iter("PublicationType")] or ["Book Chapter"],
        "keywords": [_text(k) for k in cit.iter("Keyword")],
        "mesh": [],
        "authors": [
            (_text(au.find("LastName")) + " " + _text(au.find("Initials"))).strip()
            for au in cit.iter("Author")
        ][:12],
        "language": _text(cit.find(".//Language")),
    }


def parse_pmc(xml):
    """PMC efetch returns full JATS; take only the front matter we need."""
    out = []
    root = ET.fromstring(xml)
    for art in list(root.iter("article")) + list(root.iter("book")):
        meta = art.find(".//article-meta")
        if meta is None:
            continue
        ids = {i.get("pub-id-type"): (i.text or "").strip() for i in meta.iter("article-id")}
        # PMC's own JATS labels the accession "pmcid"; "pmc" appears in publisher-deposited
        # files. Take either, and always store it prefixed.
        pmcid = ids.get("pmcid") or ids.get("pmc") or ""
        if pmcid and not pmcid.upper().startswith("PMC"):
            pmcid = "PMC" + pmcid
        jm = art.find(".//journal-meta")
        jtitle = _text(jm.find(".//journal-title")) if jm is not None else ""
        abbrev = ""
        if jm is not None:
            for jid in jm.iter("journal-id"):
                if jid.get("journal-id-type") in ("nlm-ta", "iso-abbrev"):
                    abbrev = _text(jid)
                    break
        year = ""
        for pd in meta.iter("pub-date"):
            y = _text(pd.find("year"))
            if y:
                year = y
                break
        out.append({
            "pmid": ids.get("pmid", ""),
            "pmcid": pmcid,
            "doi": ids.get("doi", "").lower(),
            "title": _text(meta.find(".//article-title")),
            "abstract": " ".join(_text(ab) for ab in meta.iter("abstract")).strip(),
            "journal": jtitle,
            "journal_abbrev": abbrev,
            "year": year,
            "pubtypes": [art.get("article-type", "")],
            "keywords": [_text(k) for k in meta.iter("kwd")],
            "mesh": [],
            "authors": [
                (_text(c.find("surname")) + " " + _text(c.find("given-names"))).strip()
                for c in meta.iter("name")
            ][:12],
            "language": "",
        })
    return out


def efetch(db, ids, parser, tag):
    """Fetch records in batches by explicit id, caching each batch.

    The cache file is named for the CONTENT of the batch, not its position. Keying on
    position alone is wrong the moment the query changes: batch 3 of the old id list and
    batch 3 of the new one get the same filename, so the second run reads the first run's
    records back and reports its own, larger, id count while parsing the older set. That
    failure is silent, because every count the run prints comes from esearch and is correct;
    only the parsed records are stale. Hashing the ids makes a changed batch a different
    file, so a changed query simply misses the cache and refetches.
    """
    recs, size, total = [], 200, len(ids)
    os.makedirs(CACHE, exist_ok=True)
    for i in range(0, total, size):
        digest = hashlib.sha1(",".join(ids[i:i + size]).encode()).hexdigest()[:12]
        path = os.path.join(CACHE, f"{tag}_{i:06d}_{digest}.xml")
        if os.path.exists(path) and os.path.getsize(path) > 200:
            xml = open(path, encoding="utf8", errors="ignore").read()
        else:
            xml = get(f"{EUTILS}/efetch.fcgi",
                      data=urllib.parse.urlencode(
                          {"db": db, "id": ",".join(ids[i:i + size]),
                           "retmode": "xml", "email": EMAIL, "tool": TOOL}))
            open(path, "w", encoding="utf8").write(xml)
        try:
            recs.extend(parser(xml))
        except ET.ParseError as e:
            print(f"    unparseable batch {path}: {e}", file=sys.stderr)
        print(f"    {min(i + size, total)}/{total}", end="\r", file=sys.stderr)
    print(file=sys.stderr)
    return recs


def key(r):
    """Identity for deduplication: PMID wins, then DOI, then PMCID, then title."""
    if r.get("pmid"):
        return "pmid:" + r["pmid"]
    if r.get("doi"):
        return "doi:" + r["doi"]
    if r.get("pmcid"):
        return "pmcid:" + r["pmcid"]
    return "title:" + re.sub(r"[^a-z0-9]+", "", r["title"].lower())[:80]


def merge(store, rec, block, db):
    k = key(rec)
    cur = store.get(k)
    if cur is None:
        rec["found_by"] = [block]
        rec["dbs"] = [db]
        store[k] = rec
        return
    # PubMed records are richer, so let them fill gaps left by a PMC-only hit.
    for f, v in rec.items():
        if v and not cur.get(f):
            cur[f] = v
    if block not in cur["found_by"]:
        cur["found_by"].append(block)
    if db not in cur["dbs"]:
        cur["dbs"].append(db)


def selected(args):
    if args.blocks:
        names = [b.strip() for b in args.blocks.split(",") if b.strip()]
        unknown = [n for n in names if n not in BLOCKS]
        if unknown:
            sys.exit(f"unknown block(s): {', '.join(unknown)}")
        return {n: BLOCKS[n] for n in names}
    if args.tier:
        return {k: v for k, v in BLOCKS.items() if TIER_OF[k] == args.tier.upper()}
    return BLOCKS


def run_counts(blocks, dbs, qualified=False):
    """Size every block before anything is downloaded.

    Per-phrase counts are printed as well as the block total, because a phrase PubMed has
    silently ANDed into words shows up here as an order-of-magnitude outlier and nowhere
    else. Read the table before trusting any block.
    """
    rows = []
    for slug, variants in blocks.items():
        for db in dbs:
            per_phrase = []
            for v in variants:
                q = f'"{v}"[Title/Abstract]' + (f' OR "{v}"[Other Term]' if db == "pubmed" else "")
                _, n = esearch(db, q, retmax=0)
                per_phrase.append({"phrase": v, "hits": n})
                print(f"  {slug:10s} {db:7s} {n:7d}  {v}", file=sys.stderr)
            _, raw_total = esearch(db, term_for(db, variants), retmax=0)
            qual_total = raw_total
            if qualified and TIER_OF[slug] == "B":
                _, qual_total = esearch(db, term_for(db, variants, True), retmax=0)
            print(f"  {slug:10s} {db:7s} {raw_total:7d} raw, {qual_total:7d} qualified"
                  "  == BLOCK TOTAL (deduplicated by NCBI)", file=sys.stderr)
            rows.append({"block": slug, "tier": TIER_OF[slug], "db": db,
                         "block_hits": raw_total, "qualified_hits": qual_total,
                         "phrase_sum": sum(p["hits"] for p in per_phrase),
                         "phrases": per_phrase})
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "counts.json")
    json.dump({"run_date": date.today().isoformat(), "qualified": qualified, "rows": rows},
              open(path, "w"), indent=1)

    print(f"\n{'block':10s} {'tier':4s} {'pubmed':>8s} {'qual':>8s} {'pmc':>8s} {'qual':>8s}")
    by_block = {}
    for r in rows:
        by_block.setdefault(r["block"], {})[r["db"]] = r
    for slug in blocks:
        b = by_block.get(slug, {})
        pm, pc = b.get("pubmed", {}), b.get("pmc", {})
        print(f"{slug:10s} {TIER_OF[slug]:4s} {pm.get('block_hits', 0):8d} "
              f"{pm.get('qualified_hits', 0):8d} {pc.get('block_hits', 0):8d} "
              f"{pc.get('qualified_hits', 0):8d}")
    print(f"\n-> {path}")
    return rows


def run_check(dbs):
    """Smallest thing that fails if parsing breaks: 5 tier A records, every field present."""
    db = dbs[0]
    ids, _ = esearch(db, term_for(db, TIER_A["metares"]), retmax=5)
    assert len(ids) == 5, f"expected 5 ids, got {len(ids)}"
    recs = efetch(db, ids, parse_pubmed if db == "pubmed" else parse_pmc, "check")
    assert recs, "no records parsed"
    required = ("pmid", "title", "year", "journal")
    for r in recs:
        for f in required:
            assert r.get(f), f"record {r.get('pmid') or r.get('pmcid')} missing {f}"
        assert isinstance(r["mesh"], list) and isinstance(r["pubtypes"], list)
    assert any(r["abstract"] for r in recs), "no abstract on any of 5 records"
    assert len({key(r) for r in recs}) == len(recs), "dedup key collision on distinct records"
    print(f"check ok: {len(recs)} records parsed from {db}, all required fields present")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts", action="store_true",
                    help="report hit counts per phrase and per block, download nothing")
    ap.add_argument("--check", action="store_true", help="fetch 5 records and assert they parse")
    ap.add_argument("--tier", choices=["A", "B", "a", "b"], help="restrict to one tier")
    ap.add_argument("--blocks", help="comma-separated block names")
    ap.add_argument("--db", choices=["pubmed", "pmc", "both"], default="both")
    ap.add_argument("--qualified", action="store_true",
                    help="AND tier B blocks with the study-of-literature qualifier")
    ap.add_argument("--out", metavar="NAME",
                    help="write to data/lit/<NAME>.jsonl instead of the tier A corpus; "
                         "required with --qualified")
    ap.add_argument("--refresh", action="store_true", help="ignore the XML cache")
    args = ap.parse_args()

    dbs = ("pubmed", "pmc") if args.db == "both" else (args.db,)

    if args.check:
        run_check(dbs)
        return
    if args.counts:
        run_counts(selected(args), dbs, args.qualified)
        return

    if args.refresh and os.path.isdir(CACHE):
        for f in os.listdir(CACHE):
            os.remove(os.path.join(CACHE, f))

    # A qualified harvest is a separate sample and must never be merged into the tier A
    # corpus. Study P01v2 rests entirely on the two populations not touching: its confirmatory
    # sample is defined as the qualified frame minus every tier A PMID, and one accidental
    # merge destroys that definition permanently and silently, because the merged records look
    # exactly like the ones that belong there. This ran once without the guard and was stopped
    # by hand mid-fetch. A guard is cheaper than the vigilance it replaces.
    if args.qualified and not args.out:
        sys.exit("--qualified writes a separate sample; pass --out NAME "
                 "(it will be written to data/lit/<NAME>.jsonl)")
    if args.out and re.search(r"[^A-Za-z0-9._-]", args.out):
        sys.exit("--out NAME must be a plain file stem")

    os.makedirs(OUT, exist_ok=True)
    blocks = selected(args)
    store, log = {}, []

    # An existing corpus is extended, not replaced, so blocks can be harvested in separate
    # runs as scope is decided. found_by accumulates across runs for the same reason.
    records_path = os.path.join(OUT, f"{args.out}.jsonl" if args.out else "records.jsonl")
    if os.path.exists(records_path):
        for line in open(records_path, encoding="utf8"):
            r = json.loads(line)
            store[key(r)] = r
        print(f"loaded {len(store)} existing records", file=sys.stderr)

    for slug, variants in blocks.items():
        for db in dbs:
            term = term_for(db, variants, args.qualified and TIER_OF[slug] == "B")
            ids, total, harvested, gaps = collect_ids(db, term)
            print(f"{slug:10s} {db:7s} {total:6d} hits, {len(ids):6d} ids retrieved",
                  file=sys.stderr)
            if len(ids) < total:
                print(f"    WARNING: {total - len(ids)} records not retrieved "
                      f"(partition sum {harvested})", file=sys.stderr)
            for g in gaps:
                print(f"    TRUNCATED: {g['day']} has {g['hits']} hits, "
                      f"{g['retrieved']} retrieved", file=sys.stderr)
            recs = efetch(db, ids, parse_pubmed if db == "pubmed" else parse_pmc,
                          f"{slug}_{db}")
            for r in recs:
                merge(store, r, slug, db)
            log.append({"block": slug, "tier": TIER_OF[slug], "variants": variants, "db": db,
                        "qualified": args.qualified and TIER_OF[slug] == "B",
                        "term": term, "hits": total, "ids": len(ids), "parsed": len(recs),
                        "gaps": gaps})

    with open(records_path, "w", encoding="utf8") as fh:
        for r in store.values():
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    log_path = os.path.join(OUT, f"{args.out}-search-log.json" if args.out
                            else "search-log.json")
    prior = json.load(open(log_path)) if os.path.exists(log_path) else []
    json.dump(prior + [{"run_date": date.today().isoformat(), "entries": log}],
              open(log_path, "w"), indent=1)

    print(f"\n{len(store)} unique records -> {records_path}")
    for e in log:
        print(f"  {e['block']:10s} {e['db']:7s} hits={e['hits']:6d} "
              f"ids={e['ids']:6d} parsed={e['parsed']:6d}")


if __name__ == "__main__":
    main()
