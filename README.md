# bierre

A free, profile-driven tool for literature search and triage. Given a research
question, it searches free scholarly sources (OpenAlex, CrossRef, PubMed, Europe
PMC, Semantic Scholar), deduplicates and ranks the results, classifies them into
relevance buckets, and runs transparent rule-based extraction over abstracts.

This is **Phase 0** of the refactor: a clean extraction of the original
`LiuLabAgentResearchWorkflow` into a reusable core library, with the domain
logic pulled out into swappable profiles. It is the foundation the desktop tool
(Phase 1) and hosted service (Phase 2+) build on.

## Quick start

```bash
pip install -r requirements.txt          # only `requests` + `PyYAML` are required

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

## Layout

```
bierre/
  core/                 # pure, reusable library — no globals, structured I/O
    text.py             #   shared text helpers (tokenise, normalise, negation-aware match)
    models.py           #   Paper / RankedPaper / EvidenceRow / RunResult dataclasses
    config.py           #   Settings (loaded from optional YAML)
    profiles.py         #   DomainProfile loader — the de-hardcoded domain logic
    planner.py          #   question -> search queries (profile-driven)
    dedup.py            #   merge duplicate papers by DOI/title
    ranking.py          #   hybrid relevance scoring + bucket classification
    extraction.py       #   rule-based evidence extraction
    pipeline.py         #   orchestrator: run_pipeline(...) -> RunResult
    http.py             #   the single network dependency, isolated
    sources/            #   one adapter per scholarly source (+ unpaywall)
  profiles/
    generic.yaml        #   no domain bias; documents the profile schema
    n_halamine.yaml     #   the original Liu Lab domain, now expressed as data
  webapp/               #   thin JSON-API + static-file server (vanilla HTML/CSS/JS)
  cli.py                #   command-line adapter
  tests/                #   offline smoke tests (no network)
  config.example.yaml   #   copy to config.yaml to override defaults
```

## Domain profiles (the key idea)

The original ranked every query against hard-coded N-halamine term lists, so it
only worked for one research program. Here, everything domain-specific —
query expansion, relevance buckets, down-weighted terms, extraction fields —
lives in a YAML **profile**:

- `generic` has no concepts or buckets, so papers rank purely on
  lexical/semantic relevance to the question. It works for any field.
- `n_halamine` reproduces the original behaviour as data.

Swap profiles with `--profile <name>` (CLI), the dropdown (web), or `profile:`
in `config.yaml`. Add a new domain by copying `generic.yaml`; no code changes.

## What changed from the original (Phase 0 scope)

**Extracted / cleaned up**
- One pure `core` library with dataclasses instead of dicts threaded everywhere.
- Removed module-level run state (`LAST_MANIFEST`/`LAST_ERROR`) and the duplicate
  function definitions; the web server returns results directly per request.
- Domain logic moved from Python into `profiles/*.yaml`.
- The web layer is now a JSON API + static files — the seam a React SPA / hosted
  API plugs into later — and shows an honest "working" indicator rather than a
  fake progress bar. The results table lists every paper found *and why it was or
  wasn't selected* (a first step toward the "view what was removed" feature).

**Intentionally deferred (not in Phase 0)**
- PDF download/parsing — brittle (publishers block direct PDF access) and not
  needed for abstract-based ranking/extraction.
- LLM extraction, AI overview, and discussion partner — these belong to the
  hosted service tier, not the offline core.
- Excel exports, the N-halamine-specific deliverables (shortlists, evidence
  ledgers, supervisor brief) — domain outputs that a profile-aware exporter can
  add later. The core emits structured JSON via `RunResult.to_dict()`.
- Persistence, accounts, subscriptions/notifications — Phase 2/3.

## Tests

```bash
python tests/test_pipeline_offline.py     # or: python -m pytest tests/
```
