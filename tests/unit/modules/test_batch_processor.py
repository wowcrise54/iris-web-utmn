#!/usr/bin/env python3
"""
Test suite for BatchProcessor class.
Tests the batch processing functionality with rate limiting and FIFO queue.
"""

import pytest
from collections import deque
import time
import sys
import os
from unittest.mock import patch, MagicMock

# Add source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'source'))


class TestBatchProcessor:
    """Tests for BatchProcessor class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        # Mock celery before importing
        self.mock_celery = MagicMock()
        self.mock_shared_task = MagicMock()
        self.mock_celery.shared_task = self.mock_shared_task
        sys.modules['celery'] = self.mock_celery
        
        # Clear any cached imports
        modules_to_clear = [k for k in sys.modules.keys() if 'iris_opencti' in k]
        for mod in modules_to_clear:
            del sys.modules[mod]
    
    def test_batch_processor_initialization(self):
        """Test BatchProcessor initialization with defaults"""
        from iris_opencti_module.opencti_handler.batch_processor import BatchProcessor
        
        processor = BatchProcessor()
        assert processor.max_batch_size == 50
        assert processor.rate_limit == 10
        assert processor.get_queue_size() == 0
    
    def test_batch_processor_custom_params(self):
        """Test BatchProcessor with custom parameters"""
        from iris_opencti_module.opencti_handler.batch_processor import BatchProcessor
        
        processor = BatchProcessor(max_batch_size=100, rate_limit=20)
        assert processor.max_batch_size == 100
        assert processor.rate_limit == 20
    
    def test_add_batch_within_limit(self):
        """Test adding batch within size limit"""
        from iris_opencti_module.opencti_handler.batch_processor import BatchProcessor
        
        processor = BatchProcessor(max_batch_size=10)
        result = processor.add_batch(["ioc" + str(i) for i in range(10)])
        
        assert result["accepted"] is True
        assert result["queue_size"] == 1
    
    def test_add_batch_over_limit(self):
        """Test adding batch over size limit is rejected"""
        from iris_opencti_module.opencti_handler.batch_processor import BatchProcessor
        
        processor = BatchProcessor(max_batch_size=10)
        result = processor.add_batch(["ioc" + str(i) for i in range(11)])
        
        assert result["accepted"] is False
        assert "error" in result
        assert "exceeds limit" in result["error"]
    
    def test_add_empty_batch(self):
        """Test adding empty batch is rejected"""
        from iris_opencti_module.opencti_handler.batch_processor import BatchProcessor
        
        processor = BatchProcessor(max_batch_size=50)
        result = processor.add_batch([])
        
        assert result["accepted"] is False
        assert "empty" in result["error"].lower()
    
    def test_fifo_order(self):
        """Test that batches are processed in FIFO order"""
        from iris_opencti_module.opencti_handler.batch_processor import BatchProcessor
        
        processor = BatchProcessor(max_batch_size=5)
        processor.add_batch(["ioc1", "ioc2"])
        processor.add_batch(["ioc3", "ioc4"])
        
        first = processor.get_next_batch()
        second = processor.get_next_batch()
        
        assert first == ["ioc1", "ioc2"]
        assert second == ["ioc3", "ioc4"]
    
    def test_get_next_batch_empty_queue(self):
        """Test get_next_batch returns None when queue is empty"""
        from iris_opencti_module.opencti_handler.batch_processor import BatchProcessor
        
        processor = BatchProcessor()
        result = processor.get_next_batch()
        
        assert result is None
    
    def test_queue_size_tracking(self):
        """Test queue size is tracked correctly"""
        from iris_opencti_module.opencti_handler.batch_processor import BatchProcessor
        
        processor = BatchProcessor(max_batch_size=50)
        
        assert processor.get_queue_size() == 0
        
        processor.add_batch(["ioc1"])
        assert processor.get_queue_size() == 1
        
        processor.add_batch(["ioc2", "ioc3"])
        assert processor.get_queue_size() == 2
        
        processor.get_next_batch()
        assert processor.get_queue_size() == 1
    
    def test_clear_queue(self):
        """Test clearing the queue"""
        from iris_opencti_module.opencti_handler.batch_processor import BatchProcessor
        
        processor = BatchProcessor(max_batch_size=50)
        processor.add_batch(["ioc1"])
        processor.add_batch(["ioc2"])
        
        cleared = processor.clear_queue()
        
        assert cleared == 2
        assert processor.get_queue_size() == 0
    
    def test_single_ioc_batch(self):
        """Test batch with single IOC"""
        from iris_opencti_module.opencti_handler.batch_processor import BatchProcessor
        
        processor = BatchProcessor(max_batch_size=50)
        result = processor.add_batch(["8.8.8.8"])
        
        assert result["accepted"] is True
        assert result["queue_size"] == 1
    
    def test_batch_with_duplicates(self):
        """Test batch processing allows duplicate IOCs"""
        from iris_opencti_module.opencti_handler.batch_processor import BatchProcessor
        
        processor = BatchProcessor(max_batch_size=50)
        result = processor.add_batch(["8.8.8.8", "8.8.8.8", "1.1.1.1"])
        
        assert result["accepted"] is True


class TestBatchEnrichFunction:
    """Tests for batch_enrich_iocs convenience function"""
    
    def setup_method(self):
        """Set up test fixtures"""
        # Mock celery before importing
        self.mock_celery = MagicMock()
        sys.modules['celery'] = self.mock_celery
        
        # Clear any cached imports
        modules_to_clear = [k for k in sys.modules.keys() if 'iris_opencti' in k]
        for mod in modules_to_clear:
            del sys.modules[mod]
    
    def test_batch_enrich_iocs_basic(self):
        """Test batch_enrich_iocs function"""
        from iris_opencti_module.opencti_handler.batch_processor import batch_enrich_iocs
        
        result = batch_enrich_iocs(["8.8.8.8", "1.1.1.1"])
        
        assert "accepted" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
