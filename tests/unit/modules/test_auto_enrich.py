#!/usr/bin/env python3
"""
Tests for auto-enrichment module.

These tests verify the auto-enrichment functionality for OpenCTI alert enrichment,
including configuration checks, task triggering, and edge cases.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, PropertyMock
from datetime import datetime

from iris_opencti_module.opencti_handler.auto_enrich import (
    enrich_alert_task,
    should_auto_enrich,
    trigger_auto_enrichment
)


class TestShouldAutoEnrich:
    """Tests for should_auto_enrich() function"""

    def test_auto_enrich_disabled_by_default(self):
        """Auto-enrichment should be disabled by default"""
        config = {"opencti_auto_enrich_alerts": False}
        assert should_auto_enrich(config) is False

    def test_auto_enrich_enabled(self):
        """Auto-enrichment should trigger when enabled"""
        config = {"opencti_auto_enrich_alerts": True}
        assert should_auto_enrich(config) is True

    def test_auto_enrich_missing_config_key(self):
        """Auto-enrichment should be disabled when config key is missing"""
        config = {}
        assert should_auto_enrich(config) is False

    def test_auto_enrich_skips_empty_alerts(self):
        """Auto-enrichment should skip alerts without IOCs"""
        config = {"opencti_auto_enrich_alerts": True}
        alert = Mock()
        alert.iocs = []
        assert should_auto_enrich(config, alert) is False

    def test_auto_enrich_with_iocs(self):
        """Auto-enrichment should process alerts with IOCs"""
        config = {"opencti_auto_enrich_alerts": True}
        alert = Mock()
        alert.iocs = [Mock(), Mock()]
        assert should_auto_enrich(config, alert) is True

    def test_auto_enrich_with_min_iocs_threshold(self):
        """Auto-enrichment should respect min_iocs threshold"""
        config = {
            "opencti_auto_enrich_alerts": True,
            "opencti_auto_enrich_min_iocs": 3
        }
        
        # Alert with fewer IOCs than threshold
        alert = Mock()
        alert.iocs = [Mock(), Mock()]  # 2 IOCs
        assert should_auto_enrich(config, alert) is False

        # Alert with exactly threshold IOCs
        alert.iocs = [Mock(), Mock(), Mock()]  # 3 IOCs
        assert should_auto_enrich(config, alert) is True

        # Alert with more IOCs than threshold
        alert.iocs = [Mock(), Mock(), Mock(), Mock()]  # 4 IOCs
        assert should_auto_enrich(config, alert) is True

    def test_auto_enrich_min_iocs_default_is_1(self):
        """Default min_iocs threshold should be 1"""
        config = {"opencti_auto_enrich_alerts": True}
        
        alert = Mock()
        alert.iocs = []
        assert should_auto_enrich(config, alert) is False

        alert.iocs = [Mock()]
        assert should_auto_enrich(config, alert) is True

    def test_auto_enrich_no_alert_provided(self):
        """should_auto_enrich should return True when no alert provided and enabled"""
        config = {"opencti_auto_enrich_alerts": True}
        assert should_auto_enrich(config, None) is True

    def test_auto_enrich_disabled_no_alert(self):
        """should_auto_enrich should return False when disabled and no alert"""
        config = {"opencti_auto_enrich_alerts": False}
        assert should_auto_enrich(config, None) is False


class TestTriggerAutoEnrichment:
    """Tests for trigger_auto_enrichment() function"""

    def test_trigger_skips_when_disabled(self):
        """Auto-enrichment should not trigger when disabled"""
        config = {"opencti_auto_enrich_alerts": False}
        alert = Mock(alert_id=123)

        with patch('iris_opencti_module.opencti_handler.auto_enrich.enrich_alert_task') as mock_task:
            result = trigger_auto_enrichment(alert, config)
            mock_task.delay.assert_not_called()
            assert result is None

    def test_trigger_skips_empty_alerts(self):
        """Auto-enrichment should not trigger for alerts without IOCs"""
        config = {"opencti_auto_enrich_alerts": True}
        alert = Mock(alert_id=123, iocs=[])

        with patch('iris_opencti_module.opencti_handler.auto_enrich.enrich_alert_task') as mock_task:
            result = trigger_auto_enrichment(alert, config)
            mock_task.delay.assert_not_called()
            assert result is None

    def test_trigger_success(self):
        """Test that auto-enrichment triggers Celery task correctly"""
        config = {"opencti_auto_enrich_alerts": True}
        alert = Mock(alert_id=123, iocs=[Mock(ioc_value="8.8.8.8")])

        with patch('iris_opencti_module.opencti_handler.auto_enrich.enrich_alert_task') as mock_task:
            mock_task.delay.return_value.id = "task-abc-123"
            result = trigger_auto_enrichment(alert, config)
            
            mock_task.delay.assert_called_once_with(123)
            assert result == "task-abc-123"

    def test_trigger_skips_alert_without_id(self):
        """Auto-enrichment should skip alerts without alert_id"""
        config = {"opencti_auto_enrich_alerts": True}
        alert = Mock(alert_id=None, iocs=[Mock()])

        with patch('iris_opencti_module.opencti_handler.auto_enrich.enrich_alert_task') as mock_task:
            result = trigger_auto_enrichment(alert, config)
            mock_task.delay.assert_not_called()
            assert result is None

    def test_trigger_with_min_iocs(self):
        """Auto-enrichment should respect min_iocs when triggering"""
        config = {
            "opencti_auto_enrich_alerts": True,
            "opencti_auto_enrich_min_iocs": 2
        }
        alert = Mock(alert_id=456, iocs=[Mock()])  # Only 1 IOC

        with patch('iris_opencti_module.opencti_handler.auto_enrich.enrich_alert_task') as mock_task:
            result = trigger_auto_enrichment(alert, config)
            mock_task.delay.assert_not_called()
            assert result is None


class TestEnrichAlertTask:
    """Tests for enrich_alert_task Celery task - basic smoke tests only"""

    def test_enrich_alert_task_is_callable(self):
        """Test that the task is properly decorated and callable"""
        from iris_opencti_module.opencti_handler.auto_enrich import enrich_alert_task
        # Verify it's a Celery task
        assert hasattr(enrich_alert_task, 'delay')
        assert hasattr(enrich_alert_task, 'run')

    def test_enrich_alert_task_has_correct_max_retries(self):
        """Test that the task has correct retry configuration"""
        from iris_opencti_module.opencti_handler.auto_enrich import enrich_alert_task
        assert enrich_alert_task.max_retries == 3
        assert enrich_alert_task.default_retry_delay == 60


class TestIntegrationScenarios:
    """Integration-style tests for common scenarios"""

    def test_full_workflow_disabled(self):
        """Test full workflow when auto-enrichment is disabled"""
        config = {"opencti_auto_enrich_alerts": False}
        alert = Mock(alert_id=1, iocs=[Mock()])

        # Should not trigger
        assert should_auto_enrich(config, alert) is False
        
        with patch('iris_opencti_module.opencti_handler.auto_enrich.enrich_alert_task') as mock_task:
            result = trigger_auto_enrichment(alert, config)
            assert result is None
            mock_task.delay.assert_not_called()

    def test_full_workflow_enabled(self):
        """Test full workflow when auto-enrichment is enabled"""
        config = {"opencti_auto_enrich_alerts": True}
        alert = Mock(alert_id=2, iocs=[Mock(), Mock()])

        # Should trigger
        assert should_auto_enrich(config, alert) is True
        
        with patch('iris_opencti_module.opencti_handler.auto_enrich.enrich_alert_task') as mock_task:
            mock_task.delay.return_value.id = "task-xyz"
            result = trigger_auto_enrichment(alert, config)
            assert result == "task-xyz"
            mock_task.delay.assert_called_once_with(2)

    def test_edge_case_zero_iocs(self):
        """Test edge case with zero IOCs"""
        config = {"opencti_auto_enrich_alerts": True}
        alert = Mock(alert_id=3, iocs=[])

        assert should_auto_enrich(config, alert) is False

    def test_edge_case_single_ioc(self):
        """Test edge case with single IOC"""
        config = {"opencti_auto_enrich_alerts": True}
        alert = Mock(alert_id=4, iocs=[Mock(ioc_value="1.2.3.4")])

        assert should_auto_enrich(config, alert) is True

    def test_edge_case_many_iocs(self):
        """Test with many IOCs"""
        config = {"opencti_auto_enrich_alerts": True}
        alert = Mock(alert_id=5, iocs=[Mock() for _ in range(100)])

        assert should_auto_enrich(config, alert) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
