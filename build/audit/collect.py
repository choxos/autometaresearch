#!/usr/bin/env python3
"""Turn one reviewer's raw output into a schema-valid verdict, or fail loudly.

Reviewers wrap JSON in fences, prepend reasoning, and append a summary, whatever the prompt
says. This unwraps the first balanced JSON object and validates it against the schema by hand,
since the repository has no JSON Schema dependency and the schema is small enough that adding
one would be the heavier option.

A failure here is a real failure. It exits non-zero, `review.sh` removes the empty verdict, and
the reviewer is rerun. A malformed verdict silently coerced into a valid-looking one is the
failure mode this exists to prevent.

Usage: python3 build/audit/collect.py <raw_output_path> <reviewer> <document_id>
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = json.load(open(os.path.join(HERE, "schema.json"), encoding="utf8"))

VOTES = set(SCHEMA["properties"]["overall_vote"]["enum"])
SEVERITIES = {"fatal", "major", "minor"}


def first_json_object(text):
    """The first balanced {...} in the text, ignoring braces inside strings."""
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def validate(v, reviewer, doc_id):
    errs = []
    for k in SCHEMA["required"]:
        if k not in v:
            errs.append(f"missing required key: {k}")
    if v.get("overall_vote") not in VOTES:
        errs.append(f"overall_vote {v.get('overall_vote')!r} not in {sorted(VOTES)}")
    c = v.get("confidence")
    if not isinstance(c, (int, float)) or not 0 <= c <= 1:
        errs.append(f"confidence {c!r} is not a number in [0, 1]")
    if not isinstance(v.get("findings"), list):
        errs.append("findings is not an array")
    else:
        for i, f in enumerate(v["findings"]):
            if not isinstance(f, dict):
                errs.append(f"findings[{i}] is not an object")
                continue
            if f.get("severity") not in SEVERITIES:
                errs.append(f"findings[{i}].severity {f.get('severity')!r} invalid")
            for k in ("section", "problem"):
                if not isinstance(f.get(k), str):
                    errs.append(f"findings[{i}].{k} missing or not a string")
            if "what_would_fix_it" not in f:
                errs.append(f"findings[{i}].what_would_fix_it absent; use null if none")
    # The reviewer does not get to relabel itself or the document.
    v["reviewer"] = reviewer
    v["document_id"] = doc_id
    return errs


def main():
    if len(sys.argv) != 4:
        sys.exit("usage: collect.py <raw_output_path> <reviewer> <document_id>")
    raw_path, reviewer, doc_id = sys.argv[1:4]
    text = open(raw_path, encoding="utf8", errors="ignore").read()
    # Strip a fence if there is one; first_json_object handles the rest.
    text = re.sub(r"```(?:json)?", "", text)
    v = first_json_object(text)
    if v is None:
        sys.exit(f"no parseable JSON object in {raw_path} ({len(text)} bytes)")
    errs = validate(v, reviewer, doc_id)
    if errs:
        sys.exit("verdict failed validation:\n  " + "\n  ".join(errs))
    json.dump(v, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
