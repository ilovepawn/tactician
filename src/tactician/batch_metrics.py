"""Pushgateway-pushed metrics for the daily batch.

The batch is a one-shot job — Prometheus pull doesn't fit. We accumulate
counters/gauges in a dedicated CollectorRegistry during the run, then push
the whole registry to a pushgateway at the end (success or failure). The
dedicated registry keeps these out of the default registry used elsewhere.
"""
import logging

from prometheus_client import CollectorRegistry, Counter, Gauge, push_to_gateway

REGISTRY = CollectorRegistry()
JOB = "tactician-batch"

RUN_DURATION = Gauge(
    "tactician_batch_run_duration_seconds",
    "Wall-clock duration of the batch run, broken down by stage.",
    ["stage"],
    registry=REGISTRY,
)

LAST_RUN_TIMESTAMP = Gauge(
    "tactician_batch_last_run_timestamp_seconds",
    "Unix timestamp at which the last batch run completed.",
    registry=REGISTRY,
)

RUN_SUCCESS = Gauge(
    "tactician_batch_run_success",
    "1 if the run completed without raising, 0 otherwise.",
    registry=REGISTRY,
)

S3_FILES_DOWNLOADED = Counter(
    "tactician_batch_s3_files_downloaded_total",
    "PGN files pulled from S3 for the daily batch.",
    registry=REGISTRY,
)

GAMES_PROCESSED = Counter(
    "tactician_batch_games_processed_total",
    "Games handed to the generator's analyze_game().",
    registry=REGISTRY,
)

PUZZLES_CREATED = Counter(
    "tactician_batch_puzzles_created_total",
    "Puzzles emitted by the generator (analyze_game returned non-None).",
    registry=REGISTRY,
)

ANALYZE_GAME_SECONDS = Counter(
    "tactician_batch_analyze_game_seconds_total",
    "Cumulative wall time spent in generator analyze_game (dominated by Stockfish).",
    registry=REGISTRY,
)

PUZZLES_TAGGED = Counter(
    "tactician_batch_puzzles_tagged_total",
    "Puzzles passed through the tagger.",
    registry=REGISTRY,
)

THEMES_EMITTED = Counter(
    "tactician_batch_themes_emitted_total",
    "Sum of themes emitted across all tagged puzzles.",
    registry=REGISTRY,
)

TAGGER_SECONDS = Counter(
    "tactician_batch_tagger_seconds_total",
    "Cumulative wall time spent in tagger cook().",
    registry=REGISTRY,
)


def push(gateway_url: str | None, logger: logging.Logger) -> None:
    """Best-effort push. Never raises — metrics infra must not break the batch."""
    if not gateway_url:
        logger.debug("PUSHGATEWAY_URL unset, skipping metrics push")
        return
    try:
        push_to_gateway(gateway_url, job=JOB, registry=REGISTRY)
        logger.info(f"pushed batch metrics to {gateway_url}")
    except Exception as e:
        logger.warning(f"failed to push metrics to {gateway_url}: {e}")
