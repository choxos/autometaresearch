#!/usr/bin/env python3
"""Stage 3: write the generated site pages from the described corpus.

Two pages are generated and neither is edited by hand: `landscape.qmd`, the map of what the
field studies, and `corpus.qmd`, every record with the labels that were derived for it. Both
come from data/lit/map.json and data/lit/records-labelled.jsonl, so a rerun after a larger
harvest replaces them wholesale and no stale number survives.

The site executes nothing at render time. Quarto receives finished markdown.

Usage: python3 build/render_site.py
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIT = os.path.join(ROOT, "data", "lit")

BLOCK_TITLES = {
    "metares": "Names itself meta-research",
    "report": "Reporting quality and guideline adherence",
    "reg": "Registration, outcome switching and publication bias",
    "repro": "Reproducibility and replication",
    "datashare": "Data and code sharing, FAIR",
    "retract": "Retraction, misconduct and integrity",
    "biblio": "Authorship, citation and metrics",
    "oa": "Open access, preprints and predatory publishing",
    "waste": "Research waste and prioritization",
    "stats": "Statistical practice, spin and p-hacking",
    "coi": "Conflicts of interest and funding",
    "peerrev": "Peer review",
    "equity": "Equity and representation",
    "aitext": "Generative AI in research writing and review",
}


def table(header, rows):
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join(["---"] * len(header)) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def render_landscape(m):
    counts = m["blocks"]
    by_period = m["block_by_half_decade"]
    periods = sorted(m["half_decades"])
    recent = [p for p in periods if p >= "2015-2019"]

    L = ["""---
title: "The landscape"
subtitle: "What the self-identified meta-research literature studies, and what it does not"
toc: true
---

Every number on this page is derived from the corpus by a rule written in
`build/lit/describe.py` and reproduced by running it. Nothing here was read by a model or
chosen by hand. The labels are vocabulary matches, so a label means the record uses a topic's
words, not that a human judged the record to be about that topic.
"""]
    w = L.append

    since_2020 = sum(n for y, n in m["years"].items() if y >= "2020")
    w("\n## The field is young and it is accelerating\n")
    w(f"The corpus holds {m['n_records']} records. {since_2020} of them, "
      f"{100 * since_2020 / m['n_records']:.0f} percent, were published in 2020 or later.\n")
    w(table(["period", "records"], [[p, m["half_decades"][p]] for p in periods]))
    w("\nThe earliest records are scattered and mostly editorial. The shape changes around "
      "2015, which is when the vocabulary itself settles: a paper published before then that "
      "does this kind of work rarely calls it meta-research, so this corpus does not contain "
      "it. That is a limitation of a tier A search and it is stated again in "
      "[the protocol](methods.qmd).\n")

    w("\n## What it studies\n")
    w("A record can carry several labels, so the column sums past the corpus size. "
      f"{m['n_unlabelled']} records match no topic phrase at all.\n")
    rows = [[BLOCK_TITLES.get(b, b), f"`{b}`", n,
             f"{100 * n / m['n_records']:.1f}%"] for b, n in counts.items()]
    w(table(["topic", "code", "records", "share"], rows))

    w("\n## Where the vocabulary is thin\n")
    thin = [(b, n) for b, n in counts.items() if b != "metares" and n < 50]
    w("Blocks carry different numbers of phrases and phrases of different breadth, so a count "
      "here measures how much of a topic's vocabulary this corpus uses and not how much "
      "attention the topic receives. The counts are not comparable across blocks and a small "
      "one is not evidence of a gap.\n")
    if thin:
        w(table(["topic", "records"],
                [[BLOCK_TITLES.get(b, b), n] for b, n in thin]))
    else:
        w("Every block is named in at least fifty records.\n")
    w("\nAn earlier version of this page read a field-level conclusion off this table, that "
      "meta-research does not study peer review or generative AI. It was wrong, and it was "
      "wrong because the labelling vocabulary had been borrowed from the search vocabulary, "
      "where narrowness is a virtue. Broad phrases for labelling now live separately in "
      "`build/lit/describe.py` and the counts above are the corrected ones. The episode is "
      "left on the page rather than quietly fixed, because a project about research "
      "transparency that silently corrects its own record is arguing against itself.\n")

    w("\n## Topics studied together\n")
    w("Pairs of topic labels on the same record, most frequent first. The pairs are what a "
      "new study would have to be novel against.\n")
    w(table(["pair", "records"],
            [[k.replace("+", "and"), v] for k, v in list(m["pairs"].items())[:20]]))

    w("\n## Topics over time\n")
    w("Records per half decade, from 2015. A topic that flattens while the corpus grows is "
      "losing share of the field's attention, not gaining it.\n")
    rows = []
    for b, n in counts.items():
        if b == "metares":
            continue
        per = by_period.get(b, {})
        rows.append([BLOCK_TITLES.get(b, b)] + [per.get(p, 0) for p in recent])
    w(table(["topic"] + recent, rows))

    w("\n## Where it is published\n")
    w(table(["journal", "records"],
            [[e["name"], e["n"]] for e in m["top_journals"][:20]]))
    w("\nOne journal carries more than a tenth of the corpus. A field concentrated in a single "
      "venue inherits that venue's editorial priorities, which is itself a meta-research "
      "question and one this corpus does not answer.\n")

    w("\n## How it is indexed\n")
    w(f"MeSH descriptors on the {m['n_with_mesh']} records that carry MeSH indexing.\n")
    w(table(["descriptor", "records"],
            [[e["name"], e["n"]] for e in m["top_mesh"][:25]]))

    w("\n## What kind of studies these are\n")
    w("Publication types, with the container types that describe every journal article "
      "removed.\n")
    w(table(["type", "records"],
            [[e["name"], e["n"]] for e in m["study_types"][:15]]))
    w("\nReviews, meta-analyses and systematic reviews together outnumber every other declared "
      "type. Many of the records typed as meta-analysis are meta-epidemiological studies, "
      "which PubMed has no separate type for, so this table separates declared types and not "
      "study designs.\n")

    open(os.path.join(ROOT, "landscape.qmd"), "w", encoding="utf8").write("\n".join(L) + "\n")


def render_corpus(records):
    """Every record, filterable in the browser. No render-time execution, no dependencies."""
    rows = [{
        "t": r["title"],
        "y": r["year"],
        "j": r["journal_abbrev"] or r["journal"],
        "l": [b for b in r.get("labels", []) if b != "metares"],
        "p": r["pmid"],
        "d": r["doi"],
    } for r in sorted(records, key=lambda r: (r["year"], r["title"]), reverse=True)]

    payload = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    page = f"""---
title: "The corpus"
subtitle: "Every record, with the labels derived for it"
toc: false
---

{len(rows)} records, newest first. Type to filter on title, journal, year or topic code. The
topic codes are defined on [the landscape page](landscape.qmd); a record with no code matched
no topic phrase.

```{{=html}}
<input id="q" type="search" placeholder="filter, for example: retract 2024 BMJ"
       style="width:100%;padding:.6rem .8rem;margin:1rem 0;font-size:1rem;
              border:1px solid var(--bs-border-color,#ccc);border-radius:4px;
              background:inherit;color:inherit">
<div id="n" style="opacity:.7;font-size:.9rem;margin-bottom:.5rem"></div>
<div id="rows"></div>
<script>
const R = {payload};
const box = document.getElementById('rows'), q = document.getElementById('q'),
      n = document.getElementById('n');
const esc = s => String(s).replace(/[&<>]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;'}})[c]);
function link(r) {{
  if (r.p) return 'https://pubmed.ncbi.nlm.nih.gov/' + r.p + '/';
  if (r.d) return 'https://doi.org/' + r.d;
  return '';
}}
function draw(list) {{
  n.textContent = list.length + ' of ' + R.length + ' records';
  box.innerHTML = list.slice(0, 400).map(r => {{
    const u = link(r);
    const title = u ? '<a href="' + u + '">' + esc(r.t) + '</a>' : esc(r.t);
    const tags = r.l.map(x => '<code>' + esc(x) + '</code>').join(' ');
    return '<div style="padding:.55rem 0;border-bottom:1px solid var(--bs-border-color,#eee)">'
      + title + '<div style="opacity:.7;font-size:.88rem">' + esc(r.y) + ' &middot; '
      + esc(r.j) + ' ' + tags + '</div></div>';
  }}).join('') + (list.length > 400
    ? '<p style="opacity:.7;margin-top:1rem">Showing the first 400. Narrow the filter to see the rest.</p>'
    : '');
}}
q.addEventListener('input', () => {{
  const terms = q.value.toLowerCase().split(/\\s+/).filter(Boolean);
  draw(!terms.length ? R : R.filter(r => {{
    const hay = (r.t + ' ' + r.j + ' ' + r.y + ' ' + r.l.join(' ')).toLowerCase();
    return terms.every(t => hay.includes(t));
  }}));
}});
draw(R);
</script>
```
"""
    open(os.path.join(ROOT, "corpus.qmd"), "w", encoding="utf8").write(page)


def main():
    map_path = os.path.join(LIT, "map.json")
    rec_path = os.path.join(LIT, "records-labelled.jsonl")
    for p in (map_path, rec_path):
        if not os.path.exists(p):
            sys.exit(f"missing {p}; run build/lit/describe.py first")
    m = json.load(open(map_path))
    records = [json.loads(line) for line in open(rec_path, encoding="utf8")]
    render_landscape(m)
    render_corpus(records)
    print(f"wrote landscape.qmd and corpus.qmd from {m['n_records']} records")


if __name__ == "__main__":
    main()
