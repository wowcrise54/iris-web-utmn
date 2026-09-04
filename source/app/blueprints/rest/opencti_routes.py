#!/usr/bin/env python3
"""
OpenCTI WebSocket routes for real-time progress updates.

This module provides SocketIO event handlers for joining/leaving enrichment
progress rooms and REST endpoints to trigger enrichment tasks.
"""
import logging
from flask import Blueprint, jsonify, request, render_template
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room

from app import db, socket_io
from app.models.alerts import Alert
from app.util import ac_api_requires, response_success, response_error
from app.business.errors import BusinessProcessingError
from iris_opencti_module.opencti_handler.auto_enrich import enrich_alert_task, get_opencti_module_config
from iris_opencti_module.opencti_handler.metrics import metrics

log = logging.getLogger(__name__)

opencti_routes_blueprint = Blueprint('opencti', __name__)


# SocketIO Namespace for OpenCTI enrichment events
from flask_socketio import Namespace

class OpenCTINamespace(Namespace):
    """SocketIO namespace handler for OpenCTI enrichment progress events."""
    
    namespace = '/opencti'
    
    def on_join_enrichment(self, data):
        """
        Handle client joining an enrichment progress room.
        
        Args:
            data: Dictionary containing 'alert_id' key
            
        Returns:
            None, emits 'enrichment_progress' event with current status
        """
        alert_id = data.get('alert_id')
        if not alert_id:
            emit('error', {'message': 'alert_id is required'})
            return
        
        try:
            # Join the room for this specific alert
            room = f'enrichment_{alert_id}'
            join_room(room)
            log.info(f"Client joined enrichment room {room}")
            
            # Get current progress from alert context
            alert = Alert.query.get(alert_id)
            if not alert:
                emit('error', {'message': f'Alert {alert_id} not found'})
                return
            
            progress = None
            opencti_context = (alert.alert_context or {}).get('opencti', {})
            if opencti_context:
                progress = opencti_context.get('progress')
            
            # Emit current progress state
            emit('enrichment_progress', {
                'alert_id': alert_id,
                'progress': progress,
                'status': 'joined'
            })
            
        except Exception as e:
            log.error(f"Error joining enrichment room for alert {alert_id}: {e}")
            emit('error', {'message': str(e)})
    
    def on_leave_enrichment(self, data):
        """
        Handle client leaving an enrichment progress room.
        
        Args:
            data: Dictionary containing 'alert_id' key
            
        Returns:
            None
        """
        alert_id = data.get('alert_id')
        if not alert_id:
            return
        
        try:
            room = f'enrichment_{alert_id}'
            leave_room(room)
            log.info(f"Client left enrichment room {room}")
        except Exception as e:
            log.error(f"Error leaving enrichment room for alert {alert_id}: {e}")


# Register the namespace with socket_io.
# The JS client (opencti_enrichment.js) connects to the /opencti namespace and
# joins per-alert enrichment rooms here, so the namespace must be registered
# for real-time progress to reach the browser (progress still works via the
# REST /opencti/progress polling path as a fallback).
opencti_namespace = OpenCTINamespace()
socket_io.on_namespace(opencti_namespace)


@opencti_routes_blueprint.route('/opencti/enrich/<int:alert_id>', methods=['POST'])
@ac_api_requires()
def trigger_enrichment(alert_id):
    """
    REST endpoint to trigger OpenCTI enrichment for an alert.
    
    ---
    tags:
      - OpenCTI
    
    parameters:
      - name: alert_id
        in: path
        type: integer
        required: true
        description: Alert ID to enrich
    
    responses:
      200:
        description: Enrichment task triggered successfully
      404:
        description: Alert not found
      400:
        description: Invalid request
    """
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return response_error(f'Alert {alert_id} not found'), 404
        
        # Check if alert has IOCs
        if not alert.iocs:
            return response_error('Alert has no IOCs to enrich'), 400
        
        # Get module configuration as a canonical param_name->value dict.
        # Reuse the shared helper (it queries the ORM model and normalizes the
        # DB's list-of-params into a dict). The previous inline code redeclared
        # Table('iris_module') on db.Model.metadata, which collides with the
        # already-mapped IrisModule model and raises InvalidRequestError.
        mod_config = get_opencti_module_config()
        
        # Check if auto-enrichment is already enabled (will run automatically)
        if mod_config.get('opencti_auto_enrich_alerts'):
            return response_success(
                'Auto-enrichment is enabled; task will run automatically',
                data={'alert_id': alert_id, 'auto_enrich': True}
            )
        
        # Trigger manual enrichment task
        task = enrich_alert_task.delay(alert_id)
        
        log.info(f"Manual enrichment triggered for alert {alert_id}, task_id: {task.id}")
        
        return response_success(
            'Enrichment task triggered',
            data={
                'alert_id': alert_id,
                'task_id': task.id,
                'auto_enrich': False
            }
        )
        
    except Exception as e:
        log.error(f"Failed to trigger enrichment for alert {alert_id}: {e}")
        return response_error(f'Failed to trigger enrichment: {str(e)}'), 500


@opencti_routes_blueprint.route('/opencti/progress/<int:alert_id>', methods=['GET'])
@ac_api_requires()
def get_enrichment_progress(alert_id):
    """
    REST endpoint to get current enrichment progress for an alert.
    
    ---
    tags:
      - OpenCTI
    
    parameters:
      - name: alert_id
        in: path
        type: integer
        required: true
        description: Alert ID to get progress for
    
    responses:
      200:
        description: Current enrichment progress
      404:
        description: Alert not found
    """
    try:
        alert = Alert.query.get(alert_id)
        if not alert:
            return response_error(f'Alert {alert_id} not found'), 404
        
        opencti_context = (alert.alert_context or {}).get('opencti', {})
        progress = opencti_context.get('progress')
        
        if not progress:
            return response_success(
                'No enrichment progress available',
                data={
                    'alert_id': alert_id,
                    'progress': None,
                    'status': 'not_started'
                }
            )
        
        return response_success(
            'Enrichment progress retrieved',
            data={
                'alert_id': alert_id,
                'progress': progress,
                'status': progress.get('status', 'unknown')
            }
        )
        
    except Exception as e:
        log.error(f"Failed to get progress for alert {alert_id}: {e}")
        return response_error(f'Failed to get progress: {str(e)}'), 500


@opencti_routes_blueprint.route('/opencti/metrics', methods=['GET'])
@ac_api_requires()
def get_opencti_metrics(caseid=None):
    """
    REST endpoint to get OpenCTI module metrics.
    
    ---
    tags:
      - OpenCTI
    
    parameters:
      - name: time_range
        in: query
        type: string
        enum: [all, 1h, 6h, 24h]
        description: Time range for historical data
    
    responses:
      200:
        description: Metrics data retrieved successfully
    """
    try:
        time_range = request.args.get('time_range', 'all')
        
        # Validate time_range parameter
        if time_range not in ['all', '1h', '6h', '24h']:
            return response_error('Invalid time_range parameter. Use: all, 1h, 6h, 24h'), 400
        
        # Get metrics from collector
        if time_range == 'all':
            metrics_data = metrics.get_summary()
        else:
            metrics_data = metrics.get_metrics(time_range=time_range)
        
        return response_success(
            'OpenCTI metrics retrieved',
            data=metrics_data
        )
        
    except Exception as e:
        log.error(f"Failed to get OpenCTI metrics: {e}")
        return response_error(f'Failed to get metrics: {str(e)}'), 500


@opencti_routes_blueprint.route('/opencti/metrics/dashboard')
@ac_api_requires()
def opencti_metrics_dashboard(caseid=None):
    """
    Render OpenCTI metrics dashboard.
    
    ---
    tags:
      - OpenCTI
    
    responses:
      200:
        description: Metrics dashboard rendered
    """
    try:
        return render_template('admin/opencti_metrics.html')
        
    except Exception as e:
        log.error(f"Failed to render metrics dashboard: {e}")
        return response_error(f'Failed to render dashboard: {str(e)}'), 500
