#!/usr/bin/env python3
"""Stage 2: describe the harvested corpus without judging it.

Every number here is derived from the records by a rule stated in code. Nothing is read by a
model, nothing is hand-curated, and rerunning this on the same records.jsonl reproduces the
output exactly. That is the point: the map of the field has to be checkable before anything
built on top of it is worth reading.

Topic labels come from matching the tier B phrase vocabulary against title, abstract and author
keywords. A label therefore means "this record uses this vocabulary", never "this record is
about this topic". The two differ, and the difference is the same contamination that made the
tier B blocks unusable as queries; here it matters less, because the population being labelled
has already been restricted to papers that call themselves meta-research.

Output: data/lit/map.json and data/lit/MAP.md

Usage: python3 build/lit/describe.py
"""

import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from search import OUT, TIER_A, TIER_B  # noqa: E402

RECORDS = os.path.join(OUT, "records.jsonl")

# Publication types that describe the container rather than the work, so counting them as
# study designs would put a third of the corpus in a bucket that means nothing.
NOISE_PUBTYPES = {
    "Journal Article", "Research Support, Non-U.S. Gov't", "English Abstract",
    "Research Support, N.I.H., Extramural", "Research Support, U.S. Gov't, P.H.S.",
    "Research Support, N.I.H., Intramural", "research-article",
    "Research Support, U.S. Gov't, Non-P.H.S.",
}


def matcher(phrase):
    """Case-insensitive, hyphen-tolerant, whole-token match for one phrase.

    PubMed treats "p-hacking" and "p hacking" as the same string and so must this, or the
    label counts disagree with the counts that produced the corpus. Word boundaries stop
    "spin" matching "spinal" and "FAIR" matching "fairness".
    """
    body = r"[-\s]+".join(re.escape(w) for w in re.split(r"[-\s]+", phrase.strip()))
    return re.compile(rf"(?<![\w-]){body}(?![\w-])", re.IGNORECASE)


# Broad phrases used for labelling and never for searching.
#
# The search vocabulary is tuned for precision against all of PubMed, where "peer review"
# retrieves every paper that mentions having been peer reviewed. Reused as a labelling
# vocabulary inside a corpus that already only contains meta-research, that same precision
# becomes a defect: `peerrev` labelled 11 records while 159 of them mention peer review, and
# `aitext` labelled 1 while 66 mention a language model. A conclusion drawn from those counts,
# that the field does not study its own quality control, was false and was published for the
# length of one commit.
#
# Adding any of these to the search blocks would reintroduce exactly the contamination the
# protocol exists to avoid. They live here, applied only to records already retrieved.
LABEL_EXTRA = {
    "peerrev": ["peer review", "peer reviewer", "peer reviewers", "referee report",
                "editorial decision", "reviewer report", "reviewer reports"],
    "aitext": ["ChatGPT", "large language model", "large language models", "generative AI",
               "GPT-4", "GPT-3", "LLM", "LLMs", "AI-generated", "AI chatbot"],
    "retract": ["retraction", "retractions", "retracted"],
    "coi": ["conflict of interest", "conflicts of interest", "financial disclosure",
            "financial disclosures", "competing interests"],
    "datashare": ["data availability", "data accessibility", "shared data", "raw data sharing"],
    "repro": ["reproducibility", "replicability", "replication", "reproduce the results"],
    "report": ["CONSORT", "PRISMA", "STROBE", "ARRIVE", "TRIPOD", "SPIRIT", "STARD",
               "reporting completeness", "reporting checklist", "reporting standards"],
    "oa": ["open access", "paywalled", "publication fee", "publication fees"],
    "biblio": ["authorship", "bibliometric", "bibliometrics", "citation analysis",
               "research metrics", "h-index"],
    "stats": ["questionable research practice", "statistical significance",
              "multiple comparisons", "statistical reporting", "underpowered"],
    # "trial registration" is barred from the reg SEARCH block because it is a structured
    # abstract label carried by every registered trial in PubMed. Inside a corpus that is
    # already meta-research, that objection does not apply and the phrase is informative.
    "reg": ["trial registration", "trial registry", "ClinicalTrials.gov", "preregistration",
            "pre-registration", "registered trials"],
    "waste": ["research waste", "research prioritisation", "wasteful research"],
    "equity": ["gender bias", "gender disparities", "gender differences in authorship",
               "underrepresentation", "diversity of authors", "low-income countries"],
}

VOCAB = {block: [(p, matcher(p)) for p in phrases + LABEL_EXTRA.get(block, [])]
         for block, phrases in {**TIER_A, **TIER_B}.items()}


def text_of(r):
    return " ".join([r["title"], r["abstract"], " ".join(r.get("keywords", []))])


def label(r):
    """Every block and phrase whose vocabulary appears in the record. Multi-label by design."""
    txt = text_of(r)
    hits = {}
    for block, phrases in VOCAB.items():
        found = [p for p, rx in phrases if rx.search(txt)]
        if found:
            hits[block] = found
    return hits


def top(counter, n):
    return [{"name": k, "n": v} for k, v in counter.most_common(n)]


def main():
    if not os.path.exists(RECORDS):
        sys.exit(f"no corpus at {RECORDS}; run build/lit/search.py first")
    records = [json.loads(line) for line in open(RECORDS, encoding="utf8")]

    years, journals, mesh, pubtypes = (collections.Counter() for _ in range(4))
    blocks, phrases, per_year_block = collections.Counter(), collections.Counter(), {}
    labelled = 0

    for r in records:
        y = r["year"] if r["year"].isdigit() else ""
        if y:
            years[y] += 1
        if r["journal"]:
            journals[r["journal"]] += 1
        for m in r["mesh"]:
            mesh[m] += 1
        for p in r["pubtypes"]:
            if p and p not in NOISE_PUBTYPES:
                pubtypes[p] += 1

        hits = label(r)
        r["labels"] = sorted(hits)
        if hits:
            labelled += 1
        for block, found in hits.items():
            blocks[block] += 1
            for p in found:
                phrases[f"{block}: {p}"] += 1
            if y:
                per_year_block.setdefault(block, collections.Counter())[y] += 1

    # Co-occurrence: which topics this field studies together. Only pairs, only tier B, and
    # only where both labels are present on the same record.
    pairs = collections.Counter()
    for r in records:
        bs = sorted(b for b in r["labels"] if b in TIER_B)
        for i, a in enumerate(bs):
            for b in bs[i + 1:]:
                pairs[f"{a} + {b}"] += 1

    decade = collections.Counter()
    for y, n in years.items():
        decade[f"{int(y) // 5 * 5}-{int(y) // 5 * 5 + 4}"] += n

    m = {
        "n_records": len(records),
        "n_with_abstract": sum(1 for r in records if r["abstract"]),
        "n_with_mesh": sum(1 for r in records if r["mesh"]),
        "n_labelled": labelled,
        "n_unlabelled": len(records) - labelled,
        "years": dict(sorted(years.items())),
        "half_decades": dict(sorted(decade.items())),
        "blocks": dict(blocks.most_common()),
        "block_by_half_decade": {},
        "phrases": dict(phrases.most_common()),
        "pairs": dict(pairs.most_common(30)),
        "top_journals": top(journals, 30),
        "top_mesh": top(mesh, 40),
        "study_types": top(pubtypes, 25),
    }
    for b, c in per_year_block.items():
        agg = collections.Counter()
        for y, n in c.items():
            agg[f"{int(y) // 5 * 5}-{int(y) // 5 * 5 + 4}"] += n
        m["block_by_half_decade"][b] = dict(sorted(agg.items()))

    json.dump(m, open(os.path.join(OUT, "map.json"), "w"), indent=1)

    with open(os.path.join(OUT, "records-labelled.jsonl"), "w", encoding="utf8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    write_markdown(m)
    print(f"{len(records)} records, {labelled} carrying at least one topic label")
    print(f"-> {OUT}/map.json, {OUT}/MAP.md, {OUT}/records-labelled.jsonl")


def write_markdown(m):
    L = []
    w = L.append
    w("# The meta-research corpus, described\n")
    w(f"{m['n_records']} unique records. {m['n_with_abstract']} carry an abstract, "
      f"{m['n_with_mesh']} carry MeSH indexing. {m['n_labelled']} match at least one topic "
      f"phrase; {m['n_unlabelled']} match none.\n")

    w("\n## Growth\n")
    w("| period | records |")
    w("|---|---|")
    for k, v in m["half_decades"].items():
        w(f"| {k} | {v} |")

    w("\n## Topics\n")
    w("A record can carry several labels, so the column sums past the corpus size.\n")
    w("| topic | records |")
    w("|---|---|")
    for k, v in m["blocks"].items():
        w(f"| {k} | {v} |")

    w("\n## Topic pairs\n")
    w("| pair | records |")
    w("|---|---|")
    for k, v in list(m["pairs"].items())[:20]:
        w(f"| {k} | {v} |")

    w("\n## Journals\n")
    w("| journal | records |")
    w("|---|---|")
    for e in m["top_journals"][:20]:
        w(f"| {e['name']} | {e['n']} |")

    w("\n## MeSH descriptors\n")
    w("| descriptor | records |")
    w("|---|---|")
    for e in m["top_mesh"][:25]:
        w(f"| {e['name']} | {e['n']} |")

    w("\n## Study types\n")
    w("| type | records |")
    w("|---|---|")
    for e in m["study_types"][:15]:
        w(f"| {e['name']} | {e['n']} |")

    open(os.path.join(OUT, "MAP.md"), "w", encoding="utf8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
