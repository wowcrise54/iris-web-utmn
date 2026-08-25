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
        from app import db
        from app.models.alerts import Alert
        from iris_opencti_module.opencti_handler.opencti_handler import OpenCTIHandler

        # Fetch the alert
        alert = Alert.query.get(alert_id)
        if not alert:
            logger.warning(f"Alert {alert_id} not found, skipping enrichment")
            return {"status": "skipped", "reason": "alert_not_found", "alert_id": alert_id}

        if not alert.iocs:
            logger.info(f"Alert {alert_id} has no IOCs, skipping enrichment")
            return {"status": "skipped", "reason": "no_iocs", "alert_id": alert_id}

        # Get module configuration
        from sqlalchemy import select, func, Table, Column, Integer, String, JSON
        from sqlalchemy.orm import class_mapper

        # Query the iris_module table for module config
        iris_module_table = Table(
            'iris_module',
            db.Model.metadata,
            Column('module_id', Integer, primary_key=True),
            Column('module_name', String),
            Column('module_config', JSON)
        )

        result = db.session.execute(
            select(iris_module_table.c.module_config)
            .where(iris_module_table.c.module_name == 'iris_opencti_module')
        )
        row = result.first()

        mod_config = row[0] if row else {}
        server_config = {
            "http_proxy": None,
            "https_proxy": None
        }

        # Create handler and perform enrichment
        handler = OpenCTIHandler(mod_config, server_config, logger)
        status = handler.handle_alerts([alert])

        db.session.commit()

        result = {
            "status": "success" if status.is_success() else "failed",
            "alert_id": alert_id,
            "iocs_processed": len(alert.iocs)
        }

        if not status.is_success():
            result["error"] = status.get_msg()
            logger.error(f"Auto-enrichment failed for alert {alert_id}: {status.get_msg()}")
        else:
            logger.info(f"Auto-enrichment completed for alert {alert_id}: {len(alert.iocs)} IOCs processed")

        return result

    except Exception as exc:
        logger.error(f"Auto-enrichment failed for alert {alert_id}: {exc}")
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
