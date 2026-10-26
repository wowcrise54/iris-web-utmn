#  IRIS Source Code
#  Copyright (C) 2021 - Airbus CyberSecurity (SAS)
#  ir@cyberactionlab.net
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3 of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

from celery import Celery
from celery import signals
from celery.exceptions import Retry
import logging
import time
from app.observability_logging import configure_logging, current_context, logging_context, request_id
from app.configuration import CeleryConfig


def make_celery(name):
    return Celery(
        name,
        config_source=CeleryConfig
    )


@signals.setup_logging.connect
def configure_worker_logging(**kwargs):
    configure_logging()


@signals.worker_process_init.connect
def configure_worker_child_logging(**kwargs):
    configure_logging()


@signals.before_task_publish.connect
def carry_logging_context(headers=None, **kwargs):
    if headers is not None:
        context = current_context()
        headers['iris_log_context'] = {key: context[key] for key in
                                      ('request_id', 'user_id', 'customer_id', 'case_id', 'alert_id')
                                      if key in context}


@signals.worker_ready.connect
def worker_ready(**kwargs):
    logging.getLogger('iris.worker').info('service_started')


@signals.worker_shutdown.connect
def worker_shutdown(**kwargs):
    logging.getLogger('iris.worker').info('service_stopped')


def set_celery_flask_context(celery: Celery, app):
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            headers = self.request.headers or {}
            context = headers.get('iris_log_context', {})
            if not isinstance(context, dict):
                context = {}
            context = {key: value for key, value in context.items()
                       if key in ('user_id', 'customer_id', 'case_id', 'alert_id')
                       and isinstance(value, int) and not isinstance(value, bool)} | {
                           'request_id': request_id(context.get('request_id')),
                           'task_id': request_id(self.request.id), 'task': self.name}
            started = time.monotonic()
            log = logging.getLogger('iris.worker')
            with logging_context(**context), app.app_context():
                log.info('task_started')
                try:
                    result = self.run(*args, **kwargs)
                except Retry:
                    log.warning('task_retry', extra={'duration_ms': round((time.monotonic() - started) * 1000, 2)})
                    raise
                except Exception:
                    log.exception('task_failed')
                    raise
                else:
                    log.info('task_completed', extra={'duration_ms': round((time.monotonic() - started) * 1000, 2)})
                    return result

    celery.Task = ContextTask
