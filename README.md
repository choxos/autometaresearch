# Automated meta-research

Meta-research studies designed, run and reviewed by language models, published in full: the
search, the map derived from it, the studies proposed against it, the code, the independent
reviews, and the disagreements between them.

Site: [choxos.github.io/autometaresearch](https://choxos.github.io/autometaresearch/)

## Where this stands

The literature has been harvested and described. No study has been proposed, run or reviewed
yet.

| stage | state |
|---|---|
| Search the literature | done, tier A only. 1830 records |
| Map what the field studies | done |
| Propose studies against the gaps | not started |
| Run them in R | not started |
| Independent review by two models | not started |
| Publish results with the reviews | not started |

## The corpus

1830 unique PubMed and PMC records that name themselves meta-research, metascience, research on
research, or meta-epidemiological, harvested 2026-09-16. 1716 carry an abstract and 1315 carry
MeSH indexing. Every query, every count, and the two queries that turned out to be wrong are
recorded in `methods.qmd`.

Topic blocks by subject matter, such as data sharing and retraction, have been sized but not
harvested; a subject query retrieves studies that performed a practice alongside studies of it,
and separating those is a classification problem rather than a query to tune.

## Building

```bash
python3 build/lit/search.py --check     # assert the parser still works, 5 records
python3 build/lit/search.py --counts    # size every block, download nothing
python3 build/lit/search.py --tier A    # harvest, resumable, cached
python3 build/lit/describe.py           # derive map.json, MAP.md, records-labelled.jsonl
python3 build/render_site.py            # write landscape.qmd and corpus.qmd
quarto render                           # -> docs/
quarto preview                          # live preview
```

Rendering needs Quarto 1.8 or later. The harvest needs Python 3 and nothing else; it uses only
the standard library and no NCBI API key. Analyses in proposed studies are written in R.

`data/lit/records.jsonl` is tracked, so everything after the harvest rebuilds on a fresh clone
without touching NCBI. Pushing to `main` regenerates the derived pages, fails if they no longer
follow from the tracked corpus, then renders and publishes to `gh-pages`.

## Layout

| Path | What it is |
|---|---|
| `build/lit/search.py` | PubMed and PMC harvester. Owns the search blocks and the phrase set |
| `build/lit/describe.py` | Corpus to map. Vocabulary labelling, counts, co-occurrence |
| `build/render_site.py` | Map to Quarto source. Writes `landscape.qmd` and `corpus.qmd` |
| `data/lit/records.jsonl` | The corpus, tracked |
| `data/lit/search-log.json` | Every query issued, with hit counts and any truncation |
| `data/lit/counts.json` | Block sizes measured before harvesting |
| `methods.qmd` | The published search protocol, including what went wrong |

## Provenance

The searching, the analysis code, the drafting and the reviewing are done by language models.
The research questions, the scope decisions and the responsibility for everything published are
the author's. Where a model produced an artifact, the page says which model and when.

## License

MIT. See `LICENSE`.
