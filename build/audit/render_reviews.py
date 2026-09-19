#!/usr/bin/env python3
"""Write the published review page for every adjudicated document.

Reviews are published whole, including the findings that were downgraded and the ones the
reviewers disagreed about. The adjudication rule produces a verdict; it does not decide what
the reader is allowed to see.

Output: reviews/<document_id>.qmd, one per adjudicated document, plus reviews.qmd listing them.

Usage: python3 build/audit/render_reviews.py
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
AUDIT = os.path.join(ROOT, "data", "audit")
OUT = os.path.join(ROOT, "reviews")

VERDICT_TEXT = {
    "blocked": ("blocked", "A reviewer produced a fatal finding backed by a verbatim quote and "
                "no reviewer rebutted it. Under the rule, evidence outranks votes, so this "
                "outcome does not depend on the tally."),
    "unsound": ("unsound", "Every reviewer that voted judged the document unsound."),
    "contested": ("contested", "The reviewers disagreed and neither side brought evidence "
                  "decisive enough to settle it. The rule publishes the disagreement rather "
                  "than picking a winner."),
    "changes-required": ("changes required", "No fatal finding survived, but findings at major "
                         "severity stand against the document."),
    "sound": ("sound", "No reviewer raised a finding above minor severity."),
    "no-verdict": ("no verdict", "Every reviewer abstained."),
}

DOC_TITLES = {}


def title_of(doc_id):
    if not DOC_TITLES:
        for p in glob.glob(os.path.join(ROOT, "proposals", "*.qmd")):
            head = open(p, encoding="utf8").read(900)
            tid = ttl = None
            for line in head.splitlines():
                if line.startswith("id: "):
                    tid = line[4:].strip()
                if line.startswith("title: "):
                    ttl = line[7:].strip().strip('"')
            if tid:
                DOC_TITLES[tid] = (ttl or tid, os.path.basename(p)[:-4])
    return DOC_TITLES.get(doc_id, (doc_id, None))


def esc(s):
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def page(doc_id, adj, verdicts):
    ttl, slug = title_of(doc_id)
    label, why = VERDICT_TEXT.get(adj["verdict"], (adj["verdict"], ""))
    L = [f'''---
title: "Review of {doc_id}: {label}"
description: "Independent adversarial review of {doc_id}. Verdict: {label}."
document: {doc_id}
verdict: {adj["verdict"]}
coverage: {adj["coverage"]}
rule_version: {adj["rule_version"]}
date: 2026-09-19
categories: [review]
---
''']
    w = L.append
    link = f"../proposals/{slug}.qmd" if slug else None
    w(f"Review of **{'[' + ttl + '](' + link + ')' if link else ttl}**.\n")
    w(f'::: {{.callout-{"important" if adj["verdict"] in ("blocked", "unsound", "contested") else "note"} appearance="simple"}}')
    w(f"## Verdict: {label}\n")
    w(f"{why}\n")
    w(f"Adjudicated by `build/audit/adjudicate.py` at rule version {adj['rule_version']}. "
      f"Coverage is **{adj['coverage']}**: {', '.join(adj['reviewers_returned'])} returned a "
      f"verdict out of a roster of {', '.join(adj['roster'])}.\n")
    w(f"{adj['n_fatal']} fatal, {adj['n_major']} major, {adj['n_minor']} minor. "
      f"{adj['n_evidenced_severe']} of the severe findings carry a verbatim quote.")
    w(":::\n")

    w("\n## Votes\n")
    w("| reviewer | vote | confidence |")
    w("|---|---|---|")
    for v in verdicts:
        w(f"| `{v['reviewer']}` | **{v['overall_vote']}** | {v.get('confidence')} |")

    w("\n## What each reviewer said\n")
    for v in verdicts:
        w(f"### `{v['reviewer']}`\n")
        w(f"{v.get('rationale', '').strip()}\n")

    for sev in ("fatal", "major", "minor"):
        fs = [f for f in adj["findings"] if f["severity"] == sev]
        if not fs:
            continue
        w(f"\n## {sev.capitalize()} findings\n")
        for i, f in enumerate(fs, 1):
            w(f"### {sev[0].upper()}{i}. {esc(f['problem'])[:120]}\n")
            w(f"**Reviewer** `{f['reviewer']}` &middot; **Section** {esc(f['section'])}\n")
            w(f"{f['problem'].strip()}\n")
            if (f.get("quote") or "").strip():
                w("> " + f["quote"].strip().replace("\n", "\n> ") + "\n")
            if (f.get("what_would_fix_it") or "").strip():
                w(f"**What would fix it.** {f['what_would_fix_it'].strip()}\n")

    if adj["downgraded"]:
        w("\n## Downgraded findings\n")
        w("The rule downgrades a fatal or major finding that names no section or states no "
          "fix, because a severe objection that cannot be acted on is an impression rather "
          "than a finding. They are shown here at the weight they earned rather than "
          "discarded.\n")
        w("| reviewer | claimed | reason | problem |")
        w("|---|---|---|---|")
        for f in adj["downgraded"]:
            w(f"| `{f['reviewer']}` | {f['original_severity']} | {f['downgraded_because']} | "
              f"{esc(f['problem'])[:150]} |")

    w("\n## The raw verdicts\n")
    w(f"`data/audit/{doc_id}/` holds each reviewer's verdict as returned, the prompt both were "
      f"given, and `adjudicated.json`. Nothing on this page is summarized from anything the "
      f"repository does not also carry in full.\n")
    return "\n".join(L) + "\n"


def main():
    docs = sorted(d for d in os.listdir(AUDIT)
                  if os.path.exists(os.path.join(AUDIT, d, "adjudicated.json")))
    if not docs:
        sys.exit("no adjudicated documents")
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for doc_id in docs:
        adj = json.load(open(os.path.join(AUDIT, doc_id, "adjudicated.json"), encoding="utf8"))
        verdicts = [json.load(open(p, encoding="utf8"))
                    for p in sorted(glob.glob(os.path.join(AUDIT, doc_id, "verdict-*.json")))]
        open(os.path.join(OUT, f"{doc_id}.qmd"), "w", encoding="utf8").write(
            page(doc_id, adj, verdicts))
        rows.append((doc_id, adj))
        print(f"  {doc_id}: {adj['verdict']} "
              f"({adj['n_fatal']}F {adj['n_major']}M {adj['n_minor']}m)")
    print(f"-> {OUT}/*.qmd for {len(rows)} documents")


if __name__ == "__main__":
    main()
