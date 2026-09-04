#!/usr/bin/env python3
"""
Batch IOC enrichment processor with rate limiting for OpenCTI integration.

This module provides batch processing capabilities for enriching multiple IOCs
efficiently with rate limiting to respect OpenCTI API limits.
"""

import logging
import time
from typing import List, Dict, Optional
from collections import deque

logger = logging.getLogger(__name__)

# Module-level queue shared between the BatchProcessor API and the Celery
# task: previously each BatchProcessor instance had its own deque and
# _process_batches_impl() created a *brand new* BatchProcessor whose queue
# was always empty, so no batch was ever processed.
_QUEUE: deque = deque()
# Module-level (not per-instance) flag: True while a processing task is
# running. A per-instance flag was dead code - add_batch set it on one
# BatchProcessor but the task's finally cleared a *different* instance's flag,
# so it was always False when checked.
_processing = False


class BatchProcessor:
    """Batch IOC enrichment processor with rate limiting.
    
    This class manages a FIFO queue of IOC batches and processes them with
    configurable rate limiting to respect OpenCTI API constraints.
    
    Attributes:
        max_batch_size: Maximum number of IOCs per batch (default: 50)
        rate_limit: Maximum queries per second (default: 10)
    """
    
    def __init__(self, max_batch_size: int = 50, rate_limit: int = 10):
        """Initialize the batch processor.
        
        Args:
            max_batch_size: Maximum number of IOCs allowed in a single batch
            rate_limit: Maximum number of IOC queries per second
        """
        self.max_batch_size = max_batch_size
        self.rate_limit = rate_limit  # queries per second
        
    def add_batch(self, ioc_values: List[str]) -> Dict:
        """Add a batch of IOCs to the processing queue.

        Args:
            ioc_values: List of IOC values to enrich

        Returns:
            Dict with 'accepted' status and additional info:
            - accepted: bool indicating if batch was accepted
            - async: bool - True if dispatched to the Celery broker
            - queue_size: local queue size (batches awaiting inline processing)
            - error: error message (if rejected)
        """
        global _processing

        if not ioc_values:
            return {
                "accepted": False,
                "error": "Batch cannot be empty"
            }

        if len(ioc_values) > self.max_batch_size:
            return {
                "accepted": False,
                "error": f"Batch size {len(ioc_values)} exceeds limit {self.max_batch_size}"
            }

        # Dispatch: the module-level _QUEUE is per-process, so a Celery worker
        # can never read it - the batch must travel as a task *argument* (the
        # broker serializes it). On success the broker owns the work, so the
        # local _QUEUE is not touched and queue_size stays honest. If Celery
        # is unavailable or the broker is down, enqueue and process inline so
        # the batch is actually enriched instead of silently never running.
        try:
            process_batches.delay(list(ioc_values))
        except Exception as exc:
            logger.warning(f"Async batch task unavailable ({exc}); processing inline")
            _QUEUE.append(list(ioc_values))
            if not _processing:
                _processing = True
                try:
                    # Local queue drain (default argument) processes every
                    # batch in the shared queue, including one a concurrent
                    # caller may have enqueued between its _processing check
                    # and its append - so no batch is stranded.
                    _process_batches_impl()
                finally:
                    _processing = False
            else:
                # A drain is already running (concurrent add_batch, broker
                # down): our batch may not have been picked up yet - drain
                # the remainder so nothing is left in the local queue.
                _process_batches_impl()
            return {
                "accepted": True,
                "async": False,
                "queue_size": len(_QUEUE),
                "note": f"celery unavailable ({exc}); processed inline",
            }

        return {
            "accepted": True,
            "async": True,
            "queue_size": len(_QUEUE),
        }
    
    def get_next_batch(self) -> Optional[List[str]]:
        """Get the next batch from the queue (FIFO).
        
        Returns:
            List of IOC values or None if queue is empty
        """
        if _QUEUE:
            return _QUEUE.popleft()
        return None
    
    def get_queue_size(self) -> int:
        """Get the current number of batches in the queue.
        
        Returns:
            Number of batches waiting to be processed
        """
        return len(_QUEUE)
    
    def clear_queue(self) -> int:
        """Clear all batches from the queue.
        
        Returns:
            Number of batches cleared
        """
        count = len(_QUEUE)
        _QUEUE.clear()
        logger.info(f"Cleared {count} batches from queue")
        return count


def _process_batches_impl(batches: Optional[List[List[str]]] = None):
    """Implementation of batch processing without Celery decorator.

    This is the core logic that can be called directly or via Celery task.

    Args:
        batches: Optional explicit list of IOC batches to process. When
            provided, exactly those batches are processed (this is how the
            Celery task transports batches across processes, since the module
            _QUEUE is per-process). When omitted, the local module queue is
            drained (direct-call / non-Celery fallback path).
    """
    processor = BatchProcessor()
    start_time = time.time()

    processed_count = 0
    matched_count = 0
    error_count = 0
    delay_between_queries = 1.0 / processor.rate_limit  # seconds between queries

    logger.info(f"Starting batch processing. Rate limit: {processor.rate_limit}/sec")

    handler = None

    from iris_opencti_module.opencti_handler.auto_enrich import get_opencti_module_config
    from iris_opencti_module.opencti_handler.opencti_handler import OpenCTIHandler
    from iris_opencti_module.opencti_handler.opencti_mapping import (
        canonicalize_ioc_value,
        infer_ioc_type,
        is_exact_ioc_match,
        normalize_search_results,
    )

    if batches is not None:
        pending = list(batches)
    else:
        # Local queue: drain it (same-process fallback / direct call).
        pending = []
        while True:
            batch = _QUEUE.popleft() if _QUEUE else None
            if batch is None:
                break
            pending.append(batch)

    for batch in pending:
        logger.info(f"Processing batch of {len(batch)} IOCs")
        for ioc_value in batch:
            try:
                # Rate limiting - sleep between queries
                if processed_count > 0:
                    time.sleep(delay_between_queries)

                # The actual enrichment: search OpenCTI for the IOC value
                # and keep only exact matches.
                if handler is None:
                    mod_config = get_opencti_module_config()
                    handler = OpenCTIHandler(
                        mod_config,
                        {"http_proxy": None, "https_proxy": None},
                        logger,
                    )

                ioc_type = infer_ioc_type(value=ioc_value)
                raw_results = handler.client.search_ioc(
                    value=ioc_value,
                    first=int(mod_config.get("opencti_max_results") or 20),
                )
                matches = normalize_search_results(
                    raw_results,
                    min_score=int(mod_config.get("opencti_min_score") or 0),
                    query_value=ioc_value,
                    query_type=ioc_type,
                    base_url=handler._display_base_url(),
                )
                matched_count += len(matches)
                logger.info(
                    f"Enriched IOC {ioc_value}: {len(matches)} exact match(es)"
                )

                processed_count += 1

            except Exception as exc:
                logger.error(f"Failed to enrich IOC {ioc_value}: {exc}")
                error_count += 1
                # Don't retry individual IOCs - log and continue

    total_time = time.time() - start_time
    logger.info(
        f"Batch processing completed. Processed: {processed_count}, "
        f"Matched: {matched_count}, Errors: {error_count}, Time: {total_time:.2f}s"
    )
    
    return {
        "processed": processed_count,
        "matched": matched_count,
        "errors": error_count,
        "total_time": total_time
    }


# Conditional Celery task registration
try:
    from celery import shared_task
    
    @shared_task(bind=True, max_retries=3, default_retry_delay=60)
    def process_batches(self, ioc_values: Optional[List[str]] = None):
        """Celery task to process IOC batches with rate limiting.

        The IOC list travels as a task *argument* (broker-serialized) rather
        than being read from the module _QUEUE, because that deque is
        per-process and a worker can never see a batch appended by the web
        process. Each IOC is enriched individually with a delay between
        queries.

        Returns:
            Dict with processing results:
            - processed: number of IOCs successfully processed
            - errors: number of IOCs that failed enrichment
            - total_time: total processing time in seconds
        """
        return _process_batches_impl([list(ioc_values)] if ioc_values else None)

except ImportError:
    # Celery not available - provide a fallback that still works for testing
    def process_batches(ioc_values: Optional[List[str]] = None):
        """Fallback process_batches when Celery is not available."""
        return _process_batches_impl([list(ioc_values)] if ioc_values else None)


def batch_enrich_iocs(ioc_values: List[str], max_batch_size: int = 50, rate_limit: int = 10) -> Dict:
    """Convenience function to enrich a list of IOCs via batch processing.
    
    Args:
        ioc_values: List of IOC values to enrich
        max_batch_size: Maximum batch size (default: 50)
        rate_limit: Rate limit in queries per second (default: 10)
        
    Returns:
        Dict with submission status and queue info
    """
    processor = BatchProcessor(max_batch_size=max_batch_size, rate_limit=rate_limit)
    return processor.add_batch(ioc_values)
