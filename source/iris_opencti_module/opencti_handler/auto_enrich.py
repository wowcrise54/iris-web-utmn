#!/usr/bin/env python3
"""
Auto-enrichment module for OpenCTI alert enrichment.

Provides Celery-based async enrichment tasks that trigger automatically
when alerts are created, allowing non-blocking enrichment of alerts with
OpenCTI data.
"""
import logging
from typing import Dict, Any, Optional
from celery import shared_task

logger = logging.getLogger(__name__)


def normalize_module_config(raw):
    """Normalize a raw ``iris_module.module_config`` value into a dict.

    The column is stored as a JSON *list* of parameter dicts
    (``[{"param_name": ..., "value": ...}, ...]``) -- that is what
    ``register_module``/``preset_init_mod_config`` write -- but
    ``OpenCTIHandler`` expects a ``param_name -> value`` *dict*.

    A value that is already a dict is returned unchanged; a list is folded
    into a dict (non-dict entries are ignored); anything else yields ``{}``.

    :param raw: the raw value read from ``IrisModule.module_config``
    :return: a ``param_name -> value`` dict (possibly empty), never a list
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {p.get("param_name"): p.get("value") for p in raw if isinstance(p, dict)}
    return {}


def get_opencti_module_config() -> Dict[str, Any]:
    """Return the OpenCTI module config as a canonical ``param_name -> value`` dict.

    ``iris_module.module_config`` is stored in the DB as a JSON *list* of
    ``{"param_name": ..., "value": ..., ...}`` dicts (that is what
    ``register_module`` writes). ``OpenCTIHandler`` expects a *dict*. The
    previous inline code redeclared the ``iris_module`` table on
    ``db.Model.metadata`` -- colliding with the already-mapped ``IrisModule``
    model and raising ``sqlalchemy.exc.InvalidRequestError`` -- and then passed
    the raw list to the handler.

    This helper queries the ORM model directly (no ``Table`` redefinition) and
    normalizes whatever shape the column holds into a dict, so the enrichment
    path receives a usable configuration.
    """
    from app.models.models import IrisModule

    row = IrisModule.query.filter_by(module_name="iris_opencti_module").first()
    if row is None or row.module_config is None:
        # Fall back to the default config declared by the module so the handler
        # can still construct a client (endpoints default, etc.).
        import iris_opencti_module.IrisOpenCTIConfig as interface_conf
        return {
            p["param_name"]: p.get("value", p.get("default"))
            for p in interface_conf.module_configuration
        }

    return normalize_module_config(row.module_config)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def enrich_alert_task(self, alert_id: int) -> Dict[str, Any]:
    """
    Celery task for asynchronous alert enrichment with OpenCTI data.

    This task is triggered automatically when alerts are created and the
    auto-enrichment feature is enabled. It performs the following steps:
    1. Fetches the alert from the database
    2. Validates that the alert has IOCs
    3. Calls OpenCTIHandler.handle_alerts() to perform enrichment
    4. Commits changes to the database
    5. Returns a status report

    Args:
        alert_id: The ID of the alert to enrich

    Returns:
        Dict containing:
            - status: 'success', 'failed', or 'skipped'
            - alert_id: The ID of the processed alert
            - iocs_processed: Number of IOCs processed
            - reason: (only if skipped) Why enrichment was skipped

    Raises:
        Exception: Re-raised for Celery retry logic
    """
    try:
        from app import db, socket_io
        from app.models.alerts import Alert
        from iris_opencti_module.opencti_handler.opencti_handler import OpenCTIHandler

        # Fetch the alert
        alert = Alert.query.get(alert_id)
        if not alert:
            logger.warning(f"Alert {alert_id} not found, skipping enrichment")
            # Emit completion event via SocketIO
            socket_io.emit('enrichment_progress', {
                'alert_id': alert_id,
                'status': 'error',
                'progress': {'status': 'error', 'error': 'alert_not_found'}
            }, room=f'enrichment_{alert_id}', namespace='/opencti')
            return {"status": "skipped", "reason": "alert_not_found", "alert_id": alert_id}

        if not alert.iocs:
            logger.info(f"Alert {alert_id} has no IOCs, skipping enrichment")
            # Emit completion event via SocketIO
            socket_io.emit('enrichment_progress', {
                'alert_id': alert_id,
                'status': 'skipped',
                'progress': {'status': 'skipped', 'reason': 'no_iocs'}
            }, room=f'enrichment_{alert_id}', namespace='/opencti')
            return {"status": "skipped", "reason": "no_iocs", "alert_id": alert_id}

        # Get module configuration as a canonical param_name->value dict.
        # The raw DB value of iris_module.module_config is a *list* of parameter
        # dicts, while OpenCTIHandler expects a *dict*. The previous code also
        # redeclared the iris_module table on db.Model.metadata, which collides
        # with the already-mapped IrisModule model and raises
        # InvalidRequestError. Querying the ORM model instead (and normalizing
        # the list->dict) fixes both issues at once.
        mod_config = get_opencti_module_config()
        server_config = {
            "http_proxy": None,
            "https_proxy": None
        }

        # Create handler and perform enrichment
        handler = OpenCTIHandler(mod_config, server_config, logger)
        
        # Set up progress callback for SocketIO emission
        def emit_progress(progress_data):
            """Emit progress update via SocketIO to alert-specific room."""
            try:
                socket_io.emit('enrichment_progress', {
                    'alert_id': alert_id,
                    'progress': progress_data
                }, room=f'enrichment_{alert_id}', namespace='/opencti')
            except Exception as e:
                logger.warning(f"Failed to emit progress for alert {alert_id}: {e}")
        
        handler.set_progress_callback(emit_progress)
        status = handler.handle_alerts([alert])

        db.session.commit()

        result = {
            "status": "success" if status.is_success() else "failed",
            "alert_id": alert_id,
            "iocs_processed": len(alert.iocs)
        }

        if not status.is_success():
            # IIStatus exposes get_message() (not get_msg()) - calling the
            # wrong name would raise AttributeError here, which the outer
            # except would swallow and turn into spurious Celery retries that
            # mask the real enrichment error.
            fail_msg = status.get_message()
            result["error"] = fail_msg
            logger.error(f"Auto-enrichment failed for alert {alert_id}: {fail_msg}")
            # Emit final error event
            socket_io.emit('enrichment_progress', {
                'alert_id': alert_id,
                'status': 'error',
                'progress': {'status': 'error', 'error': fail_msg}
            }, room=f'enrichment_{alert_id}', namespace='/opencti')
        else:
            logger.info(f"Auto-enrichment completed for alert {alert_id}: {len(alert.iocs)} IOCs processed")
            # Emit final success event
            socket_io.emit('enrichment_progress', {
                'alert_id': alert_id,
                'status': 'completed',
                'progress': {'status': 'success', 'completed': True}
            }, room=f'enrichment_{alert_id}', namespace='/opencti')

        return result

    except Exception as exc:
        logger.error(f"Auto-enrichment failed for alert {alert_id}: {exc}")
        # Emit error event via SocketIO
        try:
            socket_io.emit('enrichment_progress', {
                'alert_id': alert_id,
                'status': 'error',
                'progress': {'status': 'error', 'error': str(exc)}
            }, room=f'enrichment_{alert_id}', namespace='/opencti')
        except Exception:
            pass
        # Retry with exponential backoff
        raise self.retry(exc=exc)


def should_auto_enrich(config: Dict[str, Any], alert: Optional[Any] = None) -> bool:
    """
    Determine if an alert should be auto-enriched based on configuration.

    Args:
        config: Module configuration dictionary
        alert: Optional alert object to check for IOCs

    Returns:
        True if the alert should be auto-enriched, False otherwise

    Conditions for auto-enrichment:
        1. opencti_auto_enrich_alerts must be True in config
        2. If alert is provided, it must have at least one IOC
        3. If opencti_min_iocs is configured, alert must have >= that many IOCs
    """
    # Check if auto-enrichment is enabled
    if not config.get("opencti_auto_enrich_alerts", False):
        return False

    # If no alert provided, just check config flag
    if alert is None:
        return True

    # Check if alert has IOCs
    if not hasattr(alert, 'iocs') or not alert.iocs:
        return False

    # Check minimum IOC threshold if configured
    min_iocs = config.get("opencti_auto_enrich_min_iocs", 1)
    if len(alert.iocs) < min_iocs:
        logger.debug(f"Alert has {len(alert.iocs)} IOCs, minimum is {min_iocs}")
        return False

    return True


def trigger_auto_enrichment(alert, config: Dict[str, Any]) -> Optional[str]:
    """
    Trigger asynchronous enrichment for an alert.

    This function checks if auto-enrichment should be performed and,
    if so, launches the Celery task to enrich the alert in the background.

    Args:
        alert: Alert object to enrich
        config: Module configuration dictionary

    Returns:
        Task ID string if enrichment was triggered, None otherwise

    Example:
        from iris_opencti_module.opencti_handler.auto_enrich import trigger_auto_enrichment

        # In alert creation flow:
        module_config = get_module_config('iris_opencti_module')
        if module_config:
            task_id = trigger_auto_enrichment(new_alert, module_config)
            if task_id:
                logger.info(f"Auto-enrichment triggered: {task_id}")
    """
    if not should_auto_enrich(config, alert):
        logger.debug(f"Auto-enrichment not triggered for alert {getattr(alert, 'alert_id', 'unknown')}")
        return None

    alert_id = getattr(alert, 'alert_id', None)
    if not alert_id:
        logger.warning("Cannot trigger auto-enrichment: alert has no alert_id")
        return None

    logger.info(f"Triggering auto-enrichment for alert {alert_id}")
    task = enrich_alert_task.delay(alert_id)
    return task.id
