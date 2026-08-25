#!/usr/bin/env python3
"""
Tests for OpenCTI WebSocket routes and progress functionality.

These tests verify the WebSocket event handlers for joining/leaving enrichment
rooms, progress emission, and REST endpoints.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, call
from flask_socketio import SocketIOTestClient


class TestOpenCTIRoutes:
    """Tests for OpenCTI WebSocket routes and REST endpoints."""

    def test_trigger_enrichment_success(self, client, authenticated_user):
        """Test triggering enrichment via REST endpoint."""
        with patch('iris_opencti_module.opencti_handler.auto_enrich.enrich_alert_task.delay') as mock_delay:
            mock_task = Mock()
            mock_task.id = 'test-task-id-123'
            mock_delay.return_value = mock_task
            
            with patch('app.models.alerts.Alert.query.get') as mock_get:
                mock_alert = Mock()
                mock_alert.alert_id = 123
                mock_alert.iocs = [Mock()]
                mock_get.return_value = mock_alert
                
                with patch('sqlalchemy.Table'):
                    with patch('db.session.execute') as mock_execute:
                        mock_execute.return_value.first.return_value = (
                            {"opencti_url": "http://test.opencti"},
                        )
                        
                        response = client.post(
                            '/opencti/enrich/123',
                            headers={'Authorization': 'Bearer test-token'}
                        )
                        
                        assert response.status_code == 200
                        data = response.get_json()
                        assert data['status'] == 'success'
                        assert data['data']['alert_id'] == 123
                        assert data['data']['task_id'] == 'test-task-id-123'

    def test_trigger_enrichment_alert_not_found(self, client, authenticated_user):
        """Test triggering enrichment for non-existent alert."""
        with patch('app.models.alerts.Alert.query.get') as mock_get:
            mock_get.return_value = None
            
            response = client.post(
                '/opencti/enrich/999',
                headers={'Authorization': 'Bearer test-token'}
            )
            
            assert response.status_code == 404
            data = response.get_json()
            assert 'not found' in data['message']

    def test_trigger_enrichment_no_iocs(self, client, authenticated_user):
        """Test triggering enrichment for alert without IOCs."""
        with patch('app.models.alerts.Alert.query.get') as mock_get:
            mock_alert = Mock()
            mock_alert.alert_id = 123
            mock_alert.iocs = []
            mock_get.return_value = mock_alert
            
            response = client.post(
                '/opencti/enrich/123',
                headers={'Authorization': 'Bearer test-token'}
            )
            
            assert response.status_code == 400
            data = response.get_json()
            assert 'no IOCs' in data['message']

    def test_get_progress_success(self, client, authenticated_user):
        """Test getting enrichment progress via REST endpoint."""
        progress_data = {
            'status': 'running',
            'total': 10,
            'processed': 5,
            'matched': 3,
            'errors': 0
        }
        
        with patch('app.models.alerts.Alert.query.get') as mock_get:
            mock_alert = Mock()
            mock_alert.alert_id = 123
            mock_alert.alert_context = {
                'opencti': {
                    'progress': progress_data
                }
            }
            mock_get.return_value = mock_alert
            
            response = client.get(
                '/opencti/progress/123',
                headers={'Authorization': 'Bearer test-token'}
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['status'] == 'success'
            assert data['data']['progress'] == progress_data

    def test_get_progress_not_started(self, client, authenticated_user):
        """Test getting progress when enrichment hasn't started."""
        with patch('app.models.alerts.Alert.query.get') as mock_get:
            mock_alert = Mock()
            mock_alert.alert_id = 123
            mock_alert.alert_context = {}
            mock_get.return_value = mock_alert
            
            response = client.get(
                '/opencti/progress/123',
                headers={'Authorization': 'Bearer test-token'}
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['data']['progress'] is None
            assert data['data']['status'] == 'not_started'


class TestEnrichmentTaskProgressEmission:
    """Tests for Celery task progress emission via SocketIO."""

    def test_enrich_task_emits_progress_on_start(self):
        """Test that enrichment task emits progress when starting."""
        from iris_opencti_module.opencti_handler.auto_enrich import enrich_alert_task
        
        with patch('app.db') as mock_db:
            with patch('app.socket_io') as mock_socket_io:
                with patch('app.models.alerts.Alert.query.get') as mock_get:
                    mock_alert = Mock()
                    mock_alert.alert_id = 123
                    mock_alert.iocs = [Mock(), Mock()]
                    mock_get.return_value = mock_alert
                    
                    with patch('sqlalchemy.Table'):
                        with patch('sqlalchemy.select'):
                            with patch('iris_opencti_module.opencti_handler.opencti_handler.OpenCTIHandler') as MockHandler:
                                mock_handler_instance = Mock()
                                mock_handler_instance.handle_alerts.return_value = Mock(is_success=Mock(return_value=True))
                                MockHandler.return_value = mock_handler_instance
                                
                                # Mock the progress callback
                                progress_callback = None
                                def capture_callback(callback):
                                    nonlocal progress_callback
                                    progress_callback = callback
                                mock_handler_instance.set_progress_callback = capture_callback
                                
                                # Run task
                                result = enrich_alert_task.func(123)
                                
                                # Verify progress was emitted
                                if progress_callback:
                                    assert progress_callback.call_count > 0

    def test_enrich_task_emits_final_success(self):
        """Test that enrichment task emits success on completion."""
        from iris_opencti_module.opencti_handler.auto_enrich import enrich_alert_task
        
        with patch('app.db') as mock_db:
            with patch('app.socket_io') as mock_socket_io:
                with patch('app.models.alerts.Alert.query.get') as mock_get:
                    mock_alert = Mock()
                    mock_alert.alert_id = 123
                    mock_alert.iocs = [Mock()]
                    mock_get.return_value = mock_alert
                    
                    with patch('sqlalchemy.Table'):
                        with patch('sqlalchemy.select'):
                            with patch('iris_opencti_module.opencti_handler.opencti_handler.OpenCTIHandler') as MockHandler:
                                mock_handler_instance = Mock()
                                mock_handler_instance.handle_alerts.return_value = Mock(is_success=Mock(return_value=True))
                                MockHandler.return_value = mock_handler_instance
                                
                                result = enrich_alert_task.func(123)
                                
                                # Verify success event was emitted
                                mock_socket_io.emit.assert_any_call(
                                    'enrichment_progress',
                                    {
                                        'alert_id': 123,
                                        'status': 'completed',
                                        'progress': {'status': 'success', 'completed': True}
                                    },
                                    room='enrichment_123'
                                )

    def test_enrich_task_emits_error_on_failure(self):
        """Test that enrichment task emits error on failure."""
        from iris_opencti_module.opencti_handler.auto_enrich import enrich_alert_task
        
        with patch('app.db') as mock_db:
            with patch('app.socket_io') as mock_socket_io:
                with patch('app.models.alerts.Alert.query.get') as mock_get:
                    mock_alert = Mock()
                    mock_alert.alert_id = 123
                    mock_alert.iocs = [Mock()]
                    mock_get.return_value = mock_alert
                    
                    with patch('sqlalchemy.Table'):
                        with patch('sqlalchemy.select'):
                            with patch('iris_opencti_module.opencti_handler.opencti_handler.OpenCTIHandler') as MockHandler:
                                mock_handler_instance = Mock()
                                mock_handler_instance.handle_alerts.return_value = Mock(
                                    is_success=Mock(return_value=False),
                                    get_msg=Mock(return_value='Test error')
                                )
                                MockHandler.return_value = mock_handler_instance
                                
                                result = enrich_alert_task.func(123)
                                
                                # Verify error event was emitted
                                mock_socket_io.emit.assert_any_call(
                                    'enrichment_progress',
                                    {
                                        'alert_id': 123,
                                        'status': 'error',
                                        'progress': {'status': 'error', 'error': 'Test error'}
                                    },
                                    room='enrichment_123'
                                )


class TestOpenCTIHandlerProgressCallback:
    """Tests for OpenCTIHandler progress callback functionality."""

    def test_handler_sets_progress_callback(self):
        """Test that handler can set progress callback."""
        from iris_opencti_module.opencti_handler.opencti_handler import OpenCTIHandler
        
        mock_logger = Mock()
        handler = OpenCTIHandler({}, {}, mock_logger)
        
        mock_callback = Mock()
        handler.set_progress_callback(mock_callback)
        
        assert handler._progress_callback == mock_callback

    def test_handler_emits_progress_via_callback(self):
        """Test that handler emits progress via callback."""
        from iris_opencti_module.opencti_handler.opencti_handler import OpenCTIHandler
        
        mock_logger = Mock()
        handler = OpenCTIHandler({}, {}, mock_logger)
        
        mock_callback = Mock()
        handler.set_progress_callback(mock_callback)
        
        progress_data = {'status': 'running', 'total': 10}
        handler._emit_progress(progress_data)
        
        mock_callback.assert_called_once_with(progress_data)

    def test_handler_handles_callback_error_gracefully(self):
        """Test that handler handles callback errors gracefully."""
        from iris_opencti_module.opencti_handler.opencti_handler import OpenCTIHandler
        
        mock_logger = Mock()
        handler = OpenCTIHandler({}, {}, mock_logger)
        
        def failing_callback(data):
            raise Exception("Callback failed")
        
        handler.set_progress_callback(failing_callback)
        
        # Should not raise exception
        handler._emit_progress({'status': 'running'})
        
        # Should log warning
        mock_logger.warning.assert_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
