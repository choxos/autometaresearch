#!/usr/bin/env bash
# Run the external reviewers over one document.
#
# Two reviewers from different providers, each given the same document and instructed to
# refute it, each blind to the other. Output is one JSON verdict per reviewer under
# data/audit/<document_id>/, validated against build/audit/schema.json and adjudicated by
# build/audit/adjudicate.py.
#
# These are deliberately NOT subagents. Each call takes minutes, a foreground Bash call is
# capped, and the two providers are independent processes that should run at the same time.
# Detached shell jobs are the right shape for this and the sibling project reached the same
# conclusion for the same reason.
#
# Restartable: a reviewer whose verdict file is already non-empty is skipped, so rerunning
# after a failure or a quota block only redoes what is missing. That matters here, because
# the ChatGPT reviewer is quota-blocked until 2026-09-20 and the intended usage is to run
# this now for whatever answers and again afterwards.
#
# Usage: build/audit/review.sh <document_path> <document_id> [chatgpt|grok|all]

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOC_PATH="${1:?usage: review.sh <document_path> <document_id> [reviewer]}"
DOC_ID="${2:?usage: review.sh <document_path> <document_id> [reviewer]}"
WHICH="${3:-all}"
OUTDIR="$ROOT/data/audit/$DOC_ID"
mkdir -p "$OUTDIR"

if [ ! -f "$ROOT/$DOC_PATH" ] && [ ! -f "$DOC_PATH" ]; then
  echo "document not found: $DOC_PATH" >&2; exit 1
fi
[ -f "$DOC_PATH" ] || DOC_PATH="$ROOT/$DOC_PATH"

PROMPT="$OUTDIR/prompt.txt"
python3 "$ROOT/build/audit/make_prompt.py" "$DOC_PATH" "$DOC_ID" > "$PROMPT" || exit 1
echo "prompt: $(wc -c < "$PROMPT") bytes"

run_one() {
  # Two statements, not one. `local a="$1" b="...$a..."` expands every argument before it
  # assigns any of them, so $a is still unset in b; under `set -u` that aborts the function
  # before it does anything. Both reviewers failed identically on the first run because of it.
  local who="$1"
  local out="$OUTDIR/verdict-$who.json"
  if [ -s "$out" ]; then echo "$who: already has a verdict, skipping"; return 0; fi
  local raw="$OUTDIR/raw-$who.txt"
  # Both CLIs constrain output to the schema and emit only the final message. The first
  # version scraped the transcript instead, and that failed for a reason worth recording:
  # codex echoes the prompt into its transcript, so the first balanced JSON object in the
  # output was the SCHEMA the prompt carries, not the verdict. Asking the tool for structured
  # output removes the parsing problem rather than making the parser cleverer.
  #
  # Both reviewers read the repository while they work, which is wanted: a reviewer that
  # checks a pinned instrument against its source is doing the job. It also makes each call
  # take many minutes, which is why these run detached.
  local schema="$ROOT/build/audit/schema.json"
  case "$who" in
    chatgpt)
      codex exec -m gpt-6-astra -c model_reasoning_effort=max \
        --sandbox read-only --output-schema "$schema" \
        --output-last-message "$raw" < "$PROMPT" > "$OUTDIR/transcript-$who.txt" 2>&1
      ;;
    grok)
      grok --model grok-4.6 --reasoning-effort xhigh --always-approve \
        --json-schema "$(cat "$schema")" -p "$(cat "$PROMPT")" > "$raw" 2>&1
      ;;
    *) echo "unknown reviewer: $who" >&2; return 1 ;;
  esac
  if python3 "$ROOT/build/audit/collect.py" "$raw" "$who" "$DOC_ID" > "$out" 2>"$OUTDIR/err-$who.txt"; then
    echo "$who: verdict written"
  else
    rm -f "$out"
    echo "$who: FAILED, see $OUTDIR/err-$who.txt and $OUTDIR/raw-$who.txt" >&2
  fi
}

case "$WHICH" in
  chatgpt) run_one chatgpt ;;
  grok)    run_one grok ;;
  # Both at once. They are independent providers and neither waits on the other.
  all)     run_one grok & run_one chatgpt & wait ;;
  *)       echo "usage: $0 <document_path> <document_id> [chatgpt|grok|all]" >&2; exit 1 ;;
esac

echo
ls -la "$OUTDIR"/verdict-*.json 2>/dev/null || echo "no verdicts yet"
