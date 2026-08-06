"""Run the full search → dedup → rank → extract pipeline for one question.

This is a pure orchestrator: it holds no module-level state, takes its inputs as
arguments, and returns a :class:`RunResult`. The web and CLI layers are thin
adapters over ``run_pipeline``.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable

from . import dedup, extraction, planner, ranking
from .config import Settings
from .models import Paper, RunResult
from .profiles import DomainProfile, load_profile
from .util.journal_rankings import impact_factor_for_journal
from .sources import REGISTRY, SearchContext, SourceDispatchState, policy_for
from .sources import unpaywall

# progress(step, total, label) — optional UI/CLI hook.
ProgressCallback = Callable[[int, int, str], None]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _mock_papers() -> list[Paper]:
    """Offline fixtures used by ``--offline`` / the UI's offline checkbox.

    Mirrors the buckets the default profile distinguishes: a strict on-topic
    coating, a transferable-substrate example, a background dressing, and an
    off-topic control.
    """
    return [
        Paper(
            title="Hydantoin N-halamine polyurethane coating with rechargeable antibacterial activity",
            authors="Offline Mock",
            year="2024",
            journal="Mock Polymer Coatings",
            doi="10.0000/bierre.mock1",
            abstract=(
                "A 5,5-dimethylhydantoin precursor was covalently grafted to a polyurethane coating and "
                "chlorinated with sodium hypochlorite to form N-halamine active chlorine. Active chlorine "
                "reached 0.42 wt% and antibacterial activity was retained after 10 recharge cycles. E. coli "
                "and S. aureus showed 4 log reduction. Nonleaching behaviour and fibroblast viability were evaluated."
            ),
            sources=["OfflineMock"],
            search_queries=["offline"],
        ),
        Paper(
            title="N-halamine cotton textile with rechargeable active chlorine",
            authors="Offline Mock",
            year="2021",
            journal="Mock Textile Chemistry",
            doi="10.0000/bierre.mock2",
            abstract=(
                "Cotton textile was grafted with hydantoin and chlorinated with bleach to form N-halamine "
                "active chlorine, showing rechargeable antibacterial activity after washing. The substrate was "
                "cotton textile rather than a polyurethane or epoxy coating."
            ),
            sources=["OfflineMock"],
            search_queries=["offline"],
        ),
        Paper(
            title="Biocompatible chitosan hydrogel wound dressing with broad antimicrobial performance",
            authors="Offline Mock",
            year="2020",
            journal="Mock Hydrogel Biomaterials",
            doi="10.0000/bierre.mock3",
            abstract=(
                "A chitosan hydrogel wound dressing showed swelling, hemostatic behaviour and biocompatibility. "
                "It did not report N-halamine chemistry, active chlorine, recharge cycles, or chlorination."
            ),
            sources=["OfflineMock"],
            search_queries=["offline"],
        ),
        Paper(
            title="Silver nanoparticle photothermal peptide hydrogel wound dressing",
            authors="Offline Mock",
            year="2019",
            journal="Mock Nanomedicine",
            doi="10.0000/bierre.mock4",
            abstract=(
                "A silver nanoparticle and CuO photothermal peptide hydrogel dressing using graphene oxide and "
                "carbon dots. It did not report N-halamine, active chlorine, or recharge evidence."
            ),
            sources=["OfflineMock"],
            search_queries=["offline"],
        ),
    ]


def _plan_search_tasks(queries: list[str], settings: Settings) -> tuple[list, list, list[str]]:
    """Split (source, query) work into concurrent and serial task lists."""
    search = settings.search
    dispatch_state = SourceDispatchState()

    concurrent: list[tuple[str, str]] = []
    serial: list[tuple[str, str]] = []
    apis: list[str] = []
    for query in queries:
        for source in search.enabled_sources:
            if source not in REGISTRY:
                continue
            policy = policy_for(source)
            if not policy.allow_dispatch(settings, dispatch_state):
                continue
            run_serial = policy.force_serial(settings, dispatch_state)
            (serial if run_serial else concurrent).append((source, query))
            if source not in apis:
                apis.append(source)
    return concurrent, serial, apis


def run_pipeline(
    question: str,
    settings: Settings | None = None,
    profile: DomainProfile | None = None,
    offline: bool = False,
    progress: ProgressCallback | None = None,
) -> RunResult:
    """Execute one run and return a structured :class:`RunResult`."""
    settings = settings or Settings()
    profile = profile or load_profile(settings.profile)
    question = question.strip() or profile.default_question
    run_id = f"run_{uuid.uuid4().hex[:10]}"

    queries = planner.generate_queries(question, profile)[: max(settings.search.max_queries_per_run, 1)]

    errors: list[dict] = []
    if offline:
        papers, apis = _mock_papers(), ["OfflineMock"]
        if progress:
            progress(1, 4, "Loaded offline mock records")
    else:
        papers, apis = _search(queries, settings, errors, progress)

    if progress:
        progress(2, 4, "Deduplicating and ranking")
    deduped = dedup.deduplicate(papers)
    for paper in deduped:
        if paper.impact_factor is None:
            paper.impact_factor = impact_factor_for_journal(paper.journal)
    ranked = ranking.rank_and_select(deduped, question, profile, settings)

    selected = [r for r in ranked if r.selected]
    if not offline and settings.use_unpaywall and selected:
        if progress:
            progress(3, 4, "Checking open-access PDFs")
        ctx = SearchContext(
            timeout=settings.search.timeout_seconds,
            email=settings.contact_email,
            http_overrides=settings.search.source_http_overrides,
            errors=errors,
        )
        unpaywall.enrich([r.paper for r in selected], ctx)
        if "unpaywall" not in apis and settings.contact_email:
            apis.append("unpaywall")

    evidence = extraction.extract(selected, profile)
    if progress:
        progress(4, 4, "Done")

    return RunResult(
        run_id=run_id,
        timestamp=_now(),
        mode="offline" if offline else "online",
        profile=profile.name,
        question=question,
        queries=queries,
        apis_used=apis,
        ranked=ranked,
        evidence=evidence,
        errors=errors,
    )


def _search(
    queries: list[str],
    settings: Settings,
    errors: list[dict],
    progress: ProgressCallback | None,
) -> tuple[list[Paper], list[str]]:
    concurrent, serial, apis = _plan_search_tasks(queries, settings)
    ctx = SearchContext(
        max_results=settings.search.max_results_per_query,
        timeout=settings.search.timeout_seconds,
        email=settings.contact_email,
        api_keys=settings.api_keys,
        http_overrides=settings.search.source_http_overrides,
        errors=errors,
    )
    total = len(concurrent) + len(serial) + 3
    done = 0
    papers: list[Paper] = []

    def tick(label: str) -> None:
        nonlocal done
        done += 1
        if progress:
            progress(done, total, label)

    if concurrent:
        workers = max(1, min(settings.search.concurrent_workers, len(concurrent)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(REGISTRY[s], ctx, q): (s, q) for s, q in concurrent}
            for future in as_completed(futures):
                source, query = futures[future]
                try:
                    papers.extend(future.result())
                except Exception as exc:  # a single source failing must not abort the run
                    errors.append({"stage": source, "error_type": "workflow_error", "message": str(exc)})
                tick(f"{source}: {query[:40]}")

    for source, query in serial:
        try:
            papers.extend(REGISTRY[source](ctx, query))
        except Exception as exc:
            errors.append({"stage": source, "error_type": "workflow_error", "message": str(exc)})
        tick(f"{source}: {query[:40]}")

    return papers, apis
