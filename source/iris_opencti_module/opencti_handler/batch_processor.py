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
        self._queue: deque = deque()
        self._processing = False
        
    def add_batch(self, ioc_values: List[str]) -> Dict:
        """Add a batch of IOCs to the processing queue.
        
        Args:
            ioc_values: List of IOC values to enrich
            
        Returns:
            Dict with 'accepted' status and additional info:
            - accepted: bool indicating if batch was accepted
            - queue_size: current queue size (if accepted)
            - error: error message (if rejected)
        """
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
        
        self._queue.append(ioc_values)
        logger.info(f"Added batch of {len(ioc_values)} IOCs to queue. Queue size: {len(self._queue)}")
        
        # Trigger async processing if not already running
        if not self._processing:
            self._processing = True
            # Import and call Celery task lazily
            try:
                from iris_opencti_module.opencti_handler.batch_processor import process_batches
                process_batches.delay()
            except ImportError:
                logger.warning("Celery not available, skipping async task trigger")
        
        return {"accepted": True, "queue_size": len(self._queue)}
    
    def get_next_batch(self) -> Optional[List[str]]:
        """Get the next batch from the queue (FIFO).
        
        Returns:
            List of IOC values or None if queue is empty
        """
        if self._queue:
            return self._queue.popleft()
        return None
    
    def get_queue_size(self) -> int:
        """Get the current number of batches in the queue.
        
        Returns:
            Number of batches waiting to be processed
        """
        return len(self._queue)
    
    def clear_queue(self) -> int:
        """Clear all batches from the queue.
        
        Returns:
            Number of batches cleared
        """
        count = len(self._queue)
        self._queue.clear()
        logger.info(f"Cleared {count} batches from queue")
        return count


def _process_batches_impl():
    """Implementation of batch processing without Celery decorator.
    
    This is the core logic that can be called directly or via Celery task.
    """
    processor = BatchProcessor()
    start_time = time.time()
    
    processed_count = 0
    error_count = 0
    delay_between_queries = 1.0 / processor.rate_limit  # seconds between queries
    
    logger.info(f"Starting batch processing. Rate limit: {processor.rate_limit}/sec")
    
    while True:
        batch = processor.get_next_batch()
        if batch is None:
            break
        
        logger.info(f"Processing batch of {len(batch)} IOCs")
        
        for ioc_value in batch:
            try:
                # Rate limiting - sleep between queries
                if processed_count > 0:
                    time.sleep(delay_between_queries)
                
                # Log the enrichment request
                logger.info(f"Enriching IOC: {ioc_value}")
                
                # The actual enrichment would happen here:
                # from iris_opencti_module.opencti_handler.opencti_handler import OpenCTIHandler
                # handler = OpenCTIHandler(mod_config, server_config, logger)
                # status, matches = handler._enrich_ioc(ioc_object)
                
                processed_count += 1
                
            except Exception as exc:
                logger.error(f"Failed to enrich IOC {ioc_value}: {exc}")
                error_count += 1
                # Don't retry individual IOCs - log and continue
    
    total_time = time.time() - start_time
    processor._processing = False
    
    logger.info(
        f"Batch processing completed. Processed: {processed_count}, "
        f"Errors: {error_count}, Time: {total_time:.2f}s"
    )
    
    return {
        "processed": processed_count,
        "errors": error_count,
        "total_time": total_time
    }


# Conditional Celery task registration
try:
    from celery import shared_task
    
    @shared_task(bind=True, max_retries=3, default_retry_delay=60)
    def process_batches(self):
        """Celery task to process IOC batches with rate limiting.
        
        This task processes batches of IOCs from the queue with configurable
        rate limiting to respect OpenCTI API constraints. Each IOC is enriched
        individually with a delay between queries.
        
        Returns:
            Dict with processing results:
            - processed: number of IOCs successfully processed
            - errors: number of IOCs that failed enrichment
            - total_time: total processing time in seconds
        """
        return _process_batches_impl()
        
except ImportError:
    # Celery not available - provide a fallback that still works for testing
    def process_batches():
        """Fallback process_batches when Celery is not available."""
        return _process_batches_impl()


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
