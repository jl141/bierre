from sentry_sdk import metrics

def run_start(run_id):
    metrics.distribution(
        "run.start",
        1,
        attributes={
          "run_id": run_id
        }
    )

def papers_retrieved(source: str, count: int):
    metrics.distribution(
        "papers.received",
        count,
        unit="papers",
        attributes={
          "source": source
        },
    )

def papers_deduped(count: int):
    metrics.distribution(
        "papers.deduped",
        count,
        unit="papers",
    )
