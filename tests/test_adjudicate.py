#!/usr/bin/env python3
"""Golden cases for the adjudication rule.

A rule edit is only kept when a case here fails under the old rule and passes under the new
one, and both directions have been checked. Bump RULE_VERSION with any change.

Usage: python3 tests/test_adjudicate.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "build", "audit"))
from adjudicate import adjudicate, ROSTER  # noqa: E402


def v(reviewer, vote, findings=(), confidence=0.8):
    return {"document_id": "D", "reviewer": reviewer, "overall_vote": vote,
            "confidence": confidence, "rationale": "", "findings": list(findings)}


def f(severity, section="4.2", fix="do X", quote=None):
    return {"section": section, "severity": severity, "problem": "p",
            "what_would_fix_it": fix, "quote": quote}


CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("both sound and no findings is sound")
def _():
    r = adjudicate([v("chatgpt", "sound"), v("grok", "sound")])
    assert r["verdict"] == "sound", r["verdict"]
    assert r["coverage"] == "complete"


@case("one reviewer alone is never complete coverage")
def _():
    r = adjudicate([v("grok", "sound")])
    assert r["coverage"] == "partial", r["coverage"]
    assert r["verdict"] == "sound"  # the vote stands; the coverage caveat carries the warning


@case("a major finding forces changes even when both vote sound")
def _():
    r = adjudicate([v("chatgpt", "sound", [f("major")]), v("grok", "sound")])
    assert r["verdict"] == "changes-required", r["verdict"]


@case("a fatal finding with no fix stated is downgraded to minor")
def _():
    r = adjudicate([v("chatgpt", "sound", [f("fatal", fix=None)]), v("grok", "sound")])
    assert r["n_fatal"] == 0, r["n_fatal"]
    assert r["n_minor"] == 1
    assert len(r["downgraded"]) == 1
    assert r["downgraded"][0]["downgraded_because"] == "no fix stated"
    assert r["verdict"] == "sound", r["verdict"]


@case("a major finding naming no section is downgraded to minor")
def _():
    r = adjudicate([v("chatgpt", "sound", [f("major", section="  ")]), v("grok", "sound")])
    assert r["n_major"] == 0
    assert r["downgraded"][0]["downgraded_because"] == "no section named"


@case("an evidenced fatal finding blocks even against a sound majority")
def _():
    # The lone-dissenter-with-a-quote case. Two reviewers voting sound do not outvote a
    # verbatim quote from the document itself.
    r = adjudicate([v("chatgpt", "sound"),
                    v("grok", "unsound", [f("fatal", quote="the text says otherwise")])])
    assert r["verdict"] == "blocked", r["verdict"]


@case("an unevidenced fatal finding does not block, it contests")
def _():
    r = adjudicate([v("chatgpt", "sound"), v("grok", "unsound", [f("fatal")])])
    assert r["verdict"] == "contested", r["verdict"]


@case("both unsound is unsound, not contested")
def _():
    r = adjudicate([v("chatgpt", "unsound", [f("major")]),
                    v("grok", "unsound", [f("major")])])
    assert r["verdict"] == "unsound", r["verdict"]


@case("all abstentions produce no verdict rather than agreement")
def _():
    r = adjudicate([v("chatgpt", "abstain"), v("grok", "abstain")])
    assert r["verdict"] == "no-verdict", r["verdict"]


@case("an abstention does not dilute the reviewer that did vote")
def _():
    r = adjudicate([v("chatgpt", "abstain"), v("grok", "sound")])
    assert r["verdict"] == "sound", r["verdict"]
    assert r["coverage"] == "complete"  # both returned; one chose not to vote


@case("roster is published so partial coverage is visible")
def _():
    r = adjudicate([v("grok", "sound")])
    assert set(r["roster"]) == set(ROSTER)
    assert r["reviewers_returned"] == ["grok"]


@case("a minor finding never forces changes")
def _():
    r = adjudicate([v("chatgpt", "sound", [f("minor", fix=None)]), v("grok", "sound")])
    assert r["verdict"] == "sound", r["verdict"]
    assert r["n_minor"] == 1


def main():
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {name}: {e}")
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
