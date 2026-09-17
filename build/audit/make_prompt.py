#!/usr/bin/env python3
"""Build the reviewer prompt for one document.

The instruction is adversarial by design. A reviewer asked whether a document is good will
find it good; a reviewer asked to refute it has to go and look. The sibling project reached
the same conclusion and its catalog carries the disagreements that produced.

Usage: python3 build/audit/make_prompt.py <document_path> <document_id>
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, "schema.json")

INSTRUCTION = """You are reviewing a research document as an adversarial peer reviewer.

Your job is to refute it. Assume it is wrong somewhere and find where. A review that returns
no findings is a valid answer, but return it only after having genuinely tried to break the
document, not as a default.

What to attack, in rough order of how much damage each does if you are right:

1. Does the design measure what it says it measures? Look hardest at the instruments: how the
   exposure is defined, how the outcome is extracted, and whether either could be capturing
   an artifact of the data source rather than the thing of interest.
2. Is the sample what the document says it is? Check for overlap with a sample it claims to
   be independent of, for selection that differs between arms, and for exclusions applied
   after the data were seen.
3. Are stated numbers computed or asserted? A number that appears in prose and in no code is
   a number nobody checked. Say which ones you cannot verify.
4. Does the analysis answer the stated hypothesis? Look for a model whose coefficient does
   not mean what the prose says it means, for adjustment that absorbs the effect being
   measured, and for a null that could not have been detected at the stated sample size.
5. Is anything claimed as preregistered that was actually decided later?
6. Is the prior literature represented fairly, and is the novelty claim true? If you can name
   published work that already does this, that is the single most valuable finding you can
   return.

Rules that decide whether your findings count:

- **Name the section** each finding is against. A finding with no section is downgraded to
  minor by the adjudication rule, because an objection that does not attach to text cannot be
  acted on.
- **State what would fix it** for anything you mark fatal or major. Same downgrade otherwise.
- **Quote the document verbatim** where you can. A quote is what distinguishes an evidenced
  objection from an opinion, and under the adjudication rule an evidenced fatal finding blocks
  the document even if the other reviewer votes it sound.
- Do not invent a citation. If you believe prior work exists but cannot name it precisely,
  say that in the rationale rather than inventing a reference.

Return ONLY a JSON object matching this schema. No prose before or after, no markdown fence.

"""


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: make_prompt.py <document_path> <document_id>")
    path, doc_id = sys.argv[1], sys.argv[2]
    schema = json.load(open(SCHEMA, encoding="utf8"))
    body = open(path, encoding="utf8").read()

    print(INSTRUCTION)
    print(json.dumps(schema, indent=1))
    print()
    print(f'Set "document_id" to exactly: {doc_id}')
    print()
    print("=" * 78)
    print("THE DOCUMENT UNDER REVIEW")
    print("=" * 78)
    print()
    print(body)


if __name__ == "__main__":
    main()
