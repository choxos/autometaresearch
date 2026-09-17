#!/usr/bin/env python3
"""Turn independent reviewer verdicts into a published verdict, by a fixed rule.

Adapted in spirit from the sibling project's `build/adjudicate.mjs`, whose design principles
carry over unchanged:

  - An unsubstantiated severe finding is not evidence. It is downgraded, not counted.
  - Evidence beats votes. A lone reviewer holding an unrebutted verbatim quote is not
    silently outvoted by reviewers holding opinions.
  - Disagreement is published as disagreement. The rule never resolves a contested document
    into a clean verdict; it labels it contested and shows both sides.

What does not carry over is the schema. That project adjudicates whether a methodological
problem is still open; this one adjudicates whether a document is sound enough to act on.

Bump RULE_VERSION for any rule change, and change a rule only when a case in
`tests/test_adjudicate.py` fails under the old rule and passes under the new one. Check both
directions before keeping it.

Usage: python3 build/audit/adjudicate.py <document_id>
"""

import glob
import json
import os
import sys

RULE_VERSION = 1

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
AUDIT = os.path.join(ROOT, "data", "audit")

# The reviewers that are expected to run. A verdict states coverage against this roster, so a
# reader can tell "both reviewers agree" from "the only reviewer that answered agrees".
#
# The sibling project's CLAUDE.md warns that declaring a reviewer that casts no opinion leaves
# a guard permanently inert. Do not add a name here until it has actually returned a verdict.
ROSTER = ("chatgpt", "grok")


def downgrade(finding):
    """R1: a fatal or major finding must name a section and say what would fix it.

    A severe objection that cannot be acted on is an impression, not a finding. Downgrading
    rather than discarding keeps it visible: the reviewer still said it, and the published
    verdict still shows it, at the weight it earned.
    """
    sev = finding.get("severity")
    if sev not in ("fatal", "major"):
        return finding, None
    if not (finding.get("section") or "").strip():
        return {**finding, "severity": "minor"}, "no section named"
    if not (finding.get("what_would_fix_it") or "").strip():
        return {**finding, "severity": "minor"}, "no fix stated"
    return finding, None


def adjudicate(verdicts):
    """Verdicts in, one published verdict out."""
    reviewers = sorted({v["reviewer"] for v in verdicts})
    findings, downgrades = [], []
    for v in verdicts:
        for f in v.get("findings", []):
            kept, why = downgrade(f)
            kept = {**kept, "reviewer": v["reviewer"],
                    "original_severity": f.get("severity")}
            if why:
                downgrades.append({**kept, "downgraded_because": why})
            findings.append(kept)

    fatal = [f for f in findings if f["severity"] == "fatal"]
    major = [f for f in findings if f["severity"] == "major"]
    evidenced = [f for f in fatal + major if (f.get("quote") or "").strip()]
    votes = {v["reviewer"]: v["overall_vote"] for v in verdicts}
    cast = [x for x in votes.values() if x != "abstain"]

    # R2: coverage is stated, never assumed. A single returned verdict cannot produce
    # agreement, and calling it agreement is the failure this field exists to prevent.
    coverage = "complete" if set(reviewers) >= set(ROSTER) else "partial"

    # R3: evidence beats votes. An unrebutted evidenced fatal finding blocks, whatever the
    # vote tally says, because a quote from the document is a fact about the document and a
    # vote is a judgment about it.
    evidenced_fatal = [f for f in fatal if (f.get("quote") or "").strip()]

    if not cast:
        verdict = "no-verdict"
    elif evidenced_fatal:
        verdict = "blocked"
    elif "unsound" in cast and len(set(cast)) > 1:
        # R4: a contest is published as a contest. The rule does not pick a winner.
        verdict = "contested"
    elif all(x == "unsound" for x in cast):
        verdict = "unsound"
    elif fatal or major:
        verdict = "changes-required"
    elif all(x == "sound" for x in cast):
        verdict = "sound"
    else:
        verdict = "changes-required"

    return {
        "rule_version": RULE_VERSION,
        "verdict": verdict,
        "coverage": coverage,
        "roster": list(ROSTER),
        "reviewers_returned": reviewers,
        "votes": votes,
        "n_fatal": len(fatal),
        "n_major": len(major),
        "n_minor": len([f for f in findings if f["severity"] == "minor"]),
        "n_evidenced_severe": len(evidenced),
        "downgraded": downgrades,
        "findings": findings,
    }


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: adjudicate.py <document_id>")
    doc = sys.argv[1]
    paths = sorted(glob.glob(os.path.join(AUDIT, doc, "verdict-*.json")))
    if not paths:
        sys.exit(f"no verdicts under {os.path.join(AUDIT, doc)}")
    verdicts = [json.load(open(p, encoding="utf8")) for p in paths]
    out = adjudicate(verdicts)
    dest = os.path.join(AUDIT, doc, "adjudicated.json")
    json.dump(out, open(dest, "w"), indent=1)
    print(f"{doc}: {out['verdict']} (coverage {out['coverage']}, "
          f"{out['n_fatal']} fatal, {out['n_major']} major, {out['n_minor']} minor)")
    print(f"-> {dest}")


if __name__ == "__main__":
    main()
