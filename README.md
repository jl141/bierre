# bierre

A free, profile-driven tool for literature search and triage. Given a research
question, it searches free scholarly sources (OpenAlex, CrossRef, PubMed, Europe
PMC, Semantic Scholar), deduplicates and ranks the results, classifies them into
relevance buckets, and runs transparent rule-based extraction over abstracts.

## Quick start

```bash
pip install -r requirements.txt

# Command line
python cli.py --offline                   # no network — uses built-in mock data
python cli.py -q "antimicrobial hydrogel wound dressing"
python cli.py -q "graphene supercapacitor electrodes" --profile generic --json out.json

# Local web UI
python webapp/server.py                   # then open http://127.0.0.1:8765
```

The optional ranking libraries (`scikit-learn`, `rank-bm25`, `rapidfuzz`) improve
relevance scoring; if they are absent the pipeline falls back to token-overlap
scoring and still runs.

## Domain profiles (the key idea)

Everything domain-specific — query expansion, relevance buckets, down-weighted
terms, extraction fields — lives in a YAML **profile**:

- `generic` has no concepts or buckets, so papers rank purely on
  lexical/semantic relevance to the question. It works for any field.

Swap profiles with `--profile <name>` (CLI), the dropdown (web), or `profile:`
in `config.yaml`. Add a new domain by copying `generic.yaml`; no code changes.

## Tests

```bash
python -m pytest tests/
```

## HTTP helper

The shared `core/http.py` `request_json(...)` helper uses a reusable Session
with bounded retries for transient GET failures (429/5xx and timeout/connection
errors), exponential backoff with jitter, Retry-After support, and redacted
error URLs for sensitive query parameters. The function signature remains
backward-compatible with existing source adapters, and it accepts tuple
timeouts and returns any valid JSON top-level shape (object/array/scalar).
