"""Shared logging policy. No application/database imports at module load."""
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import math
import os
import re
import sys
import threading
import time
import traceback
import uuid
from urllib.parse import urlsplit

TRACE = 5
logging.addLevelName(TRACE, 'TRACE')
_context = ContextVar('iris_log_context', default={})
_request_identity = ContextVar('iris_log_request_identity', default=None)
_ID = re.compile(r'[A-Za-z0-9_.:-]{1,128}\Z')
_SENSITIVE = re.compile(r'password|passwd|secret|token|cookie|authorization|credential|api.?key|dsn', re.I)
_CONTENT = re.compile(r'^(body|payload|prompt|response|content|arguments|headers|alert_source_content|attachment|ioc|evidence)$', re.I)
_FIELDS = frozenset(('request_id', 'task_id', 'user_id', 'customer_id', 'object_id', 'case_id',
                     'alert_id', 'duration_ms', 'status', 'result', 'error_type', 'source',
                     'method', 'path', 'task', 'stage', 'count', 'namespace', 'metadata'))
_LEVELS = {'TRACE': TRACE, 'DEBUG': 10, 'INFO': 20, 'WARNING': 30, 'WARN': 30,
           'ERROR': 40, 'CRITICAL': 50, 'FATAL': 50}
_APP_NAMES = ('app', 'iris', 'iris_maxpatrol_module', 'iris_opencti_module', 'celery', 'uvicorn')


def request_id(value=None):
    return value if isinstance(value, str) and _ID.fullmatch(value) else uuid.uuid4().hex


def current_context():
    return {**_context.get(), **(_request_identity.get() or {})}


def bind_request_identity(**values):
    identity = _request_identity.get()
    if identity is not None:
        identity.update({key: value for key, value in values.items()
                         if key in ('user_id', 'customer_id', 'case_id', 'alert_id')
                         and isinstance(value, int) and not isinstance(value, bool)})


@contextmanager
def _request_identity_scope():
    token = _request_identity.set({})
    try:
        yield
    finally:
        _request_identity.reset(token)


@contextmanager
def observed_operation(logger_name, stage):
    log = logging.getLogger(logger_name)
    started = time.monotonic()
    with logging_context(stage=stage):
        log.log(TRACE, 'operation_started')
        try:
            yield
        except Exception as exc:
            log.warning('operation_completed', extra={'result': 'error', 'error_type': type(exc).__name__,
                'duration_ms': round((time.monotonic() - started) * 1000, 2)})
            raise
        else:
            log.info('operation_completed', extra={'result': 'ok',
                'duration_ms': round((time.monotonic() - started) * 1000, 2)})


@contextmanager
def logging_context(**values):
    token = _context.set({**_context.get(), **{k: v for k, v in values.items() if k in _FIELDS}})
    try:
        yield
    finally:
        _context.reset(token)


def clean_text(value):
    text = str(value)[:8192]
    text = re.sub(r'(?i)\b(Bearer|Basic)\s+[^\s,;\'\"]+', r'\1 [Filtered]', text)
    text = re.sub(r'''(?is)((?:password|passwd|secret|token|cookie|authorization|credential|api[_-]?key|dsn)[\w-]*["']?\s*[:=]\s*)(["'])(.*?)(?:\2|$)''', r'\1[Filtered]', text)
    text = re.sub(r'(?i)((?:password|passwd|secret|token|cookie|authorization|credential|api[_-]?key|dsn)[\w-]*[\"\']?\s*[:=]\s*)[^\s,;&\"\']+', r'\1[Filtered]', text)
    # URLs in messages/stack traces never retain credentials, queries or fragments.
    text = re.sub(r'https?://[^\s<>\"\']+', lambda m: safe_url(m.group()), text)
    return text.replace('\r', '\\r').replace('\n', '\\n')[:2048]


def safe_url(value):
    try:
        parts = urlsplit(value)
        host = parts.hostname or ''
        return f'{parts.scheme}://{host}{parts.path}' if parts.scheme else parts.path
    except ValueError:
        return '[Filtered URL]'


def clean(value, depth=0, seen=None):
    if depth > 4:
        return '[truncated]'
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return clean_text(value)
    seen = set() if seen is None else seen
    if id(value) in seen:
        return '[circular]'
    seen.add(id(value))
    if isinstance(value, dict):
        return {str(k)[:64]: '[Filtered]' if _SENSITIVE.search(str(k)) or _CONTENT.search(str(k))
                else clean(v, depth + 1, seen) for k, v in list(value.items())[:20]}
    if isinstance(value, (list, tuple)):
        return [clean(v, depth + 1, seen) for v in value[:20]]
    # Arbitrary repr() often contains incident data or HTTP response bodies.
    return f'[{type(value).__name__}]'


class SafeFormatter(logging.Formatter):
    def __init__(self, service, output_format):
        super().__init__()
        self.service, self.output_format = service, output_format

    def format(self, record):
        try:
            def argument(value):
                return clean(value) if value is None or isinstance(value, (str, bool, int, float)) else f'[{type(value).__name__}]'
            args = ({key: '[Filtered]' if _SENSITIVE.search(str(key)) or _CONTENT.search(str(key)) else argument(value)
                     for key, value in record.args.items()} if isinstance(record.args, dict)
                    else tuple(argument(value) for value in record.args))
            if isinstance(record.args, dict) and not (isinstance(record.msg, str) and re.search(r'%\([^)]+\)', record.msg)):
                args = (argument(record.args),)
            message = record.msg if isinstance(record.msg, str) else f'diagnostic_{type(record.msg).__name__}'
            if record.args:
                message = message % args
        except (TypeError, ValueError, KeyError):
            message = 'log_message_format_failed'
        active_error = record.exc_info or sys.exc_info()
        if active_error[1] is not None:
            try:
                error_value = str(active_error[1])
                if error_value:
                    message = message.replace(error_value, f'[{type(active_error[1]).__name__}]')
            except Exception:
                message = 'operation_failed'
        fields = {**current_context(), **{k: getattr(record, k) for k in _FIELDS if hasattr(record, k)}}
        row = {'time': datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
               'level': record.levelname, 'service': self.service, 'logger': record.name,
               'event': clean_text(getattr(record, 'event', message.split(' ', 1)[0]))[:96],
               'message': clean_text(message), **clean(fields)}
        if record.exc_info and record.exc_info[0] is not None:
            row['error_type'] = record.exc_info[0].__name__
            # Stack locations only: neither exception values, locals nor source lines.
            row['stack'] = [{'file': os.path.basename(f.filename), 'line': f.lineno, 'function': f.name}
                            for f in traceback.extract_tb(record.exc_info[2])[-12:]]
        if self.output_format == 'json':
            return json.dumps(row, ensure_ascii=True, allow_nan=False, default=lambda _: '[Filtered]')
        return ' '.join(f'{key}={json.dumps(value, ensure_ascii=True)}' for key, value in row.items())


class _ApplicationEvents(logging.Filter):
    def filter(self, record):
        # Sentry's logging integration inspects the original LogRecord after
        # handlers run; keep correlation fields there as well as in stdout JSON.
        for key, value in current_context().items():
            if key in _FIELDS and not hasattr(record, key):
                setattr(record, key, clean(value))
        # Celery trace prints results and SQLAlchemy engine prints bound case
        # contents. Application lifecycle/error events cover these safely.
        return record.name != 'celery.app.trace' and not record.name.startswith('sqlalchemy.engine')


def _level(value):
    if not isinstance(value, str) or value.upper() not in _LEVELS:
        raise ValueError('Invalid logging level')
    return _LEVELS[value.upper()]


def configure_logging(environ=None, *, stream=None):
    env = os.environ if environ is None else environ
    level = _level(env.get('LOG_LEVEL', 'INFO'))
    output_format = env.get('IRIS_LOG_FORMAT', 'json' if env.get('DOCKERIZED') else 'text')
    if output_format not in ('json', 'text'):
        raise ValueError('Invalid IRIS_LOG_FORMAT')
    try:
        overrides = json.loads(env.get('IRIS_LOG_LEVELS', '{}'))
        if not isinstance(overrides, dict) or len(overrides) > 100:
            raise ValueError()
        if any(not isinstance(name, str) or not re.fullmatch(r'[\w.-]{1,160}', name) for name in overrides):
            raise ValueError()
        overrides = {name: _level(value) for name, value in overrides.items()}
    except (ValueError, TypeError):
        raise ValueError('Invalid IRIS_LOG_LEVELS') from None
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    handler.addFilter(_ApplicationEvents())
    handler.setFormatter(SafeFormatter('worker' if env.get('IRIS_WORKER') else 'app', output_format))
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    for name in _APP_NAMES:
        logging.getLogger(name).setLevel(level)
    for name, logger in list(root.manager.loggerDict.items()):
        if not isinstance(logger, logging.Logger):
            continue
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(level if name in _APP_NAMES else logging.NOTSET)
    for name in ('urllib3', 'requests', 'httpx', 'httpcore', 'sqlalchemy', 'kombu', 'amqp', 'asyncio'):
        logging.getLogger(name).setLevel(logging.WARNING)
    # Descendants of a configured prefix inherit its threshold.
    for name, threshold in overrides.items():
        logging.getLogger(name).setLevel(threshold)
    return handler


class LoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        kind = scope['type']
        log = logging.getLogger('iris.api')
        if kind not in ('http', 'websocket'):
            async def lifecycle_send(message):
                events = {'lifespan.startup.complete': 'service_started', 'lifespan.shutdown.complete': 'service_stopped'}
                if message['type'] in events:
                    log.info(events[message['type']])
                if message['type'].endswith('.failed'):
                    log.critical('service_lifecycle_failed')
                await send(message)
            return await self.app(scope, receive, lifecycle_send)
        identifier = request_id(dict(scope.get('headers', [])).get(b'x-request-id', b'').decode('latin1'))
        scope = dict(scope)
        scope['headers'] = [(k, v) for k, v in scope.get('headers', []) if k.lower() != b'x-request-id'] + [(b'x-request-id', identifier.encode())]
        started, status = time.monotonic(), 500

        async def correlated_send(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
                message = {**message, 'headers': [(k, v) for k, v in message.get('headers', []) if k.lower() != b'x-request-id'] + [(b'x-request-id', identifier.encode())]}
            elif message['type'] == 'websocket.accept':
                status = 101
            await send(message)
        with _request_identity_scope(), logging_context(request_id=identifier, method=scope.get('method'), path=scope.get('path')):
            try:
                await self.app(scope, receive, correlated_send)
            except Exception as exc:
                # app.web owns request tracebacks; this covers outer transport failures.
                log.error('transport_failed', extra={'error_type': type(exc).__name__})
                raise
            finally:
                event = 'http_completed' if kind == 'http' else 'websocket_closed'
                threshold = logging.WARNING if status >= 400 else logging.INFO
                if status < 400 and scope.get('path') in ('/health', '/healthz', '/api/v2/manage/server/authentication-settings'):
                    threshold = logging.DEBUG
                log.log(threshold, event, extra={'status': status, 'duration_ms': round((time.monotonic() - started) * 1000, 2)})


class ClientEvents:
    """Bounded, atomic per-process intake; never stores client event contents."""
    def __init__(self):
        self.history = {}
        self.lock = threading.Lock()

    def validate(self, body):
        if not isinstance(body, dict) or set(body) != {'events'}:
            raise ValueError('Expected events')
        events = body['events']
        if not isinstance(events, list) or not 1 <= len(events) <= 20:
            raise ValueError('Expected 1 to 20 events')
        allowed = {'level', 'event', 'message', 'request_id', 'path', 'stack'}
        result = []
        for event in events:
            if not isinstance(event, dict) or set(event) - allowed or event.get('level') not in ('WARNING', 'ERROR', 'CRITICAL'):
                raise ValueError('Invalid event')
            if not all(isinstance(v, str) and len(v) <= 4096 for v in event.values()):
                raise ValueError('Invalid event fields')
            if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,96}', event.get('event', '')):
                raise ValueError('Invalid event name')
            if 'request_id' in event and not _ID.fullmatch(event['request_id']):
                raise ValueError('Invalid request ID')
            if 'path' in event and (not event['path'].startswith('/') or event['path'].startswith('//')):
                raise ValueError('Invalid path')
            cleaned = clean(event)
            cleaned['path'] = event.get('path', '').split('?', 1)[0].split('#', 1)[0][:512]
            # Keep only JS frame lines, never exception text or source snippets.
            cleaned['stack'] = [clean_text(line) for line in event.get('stack', '').splitlines()
                                if re.match(r'\s*(at |[^\s@]+@)', line)][:12]
            result.append(cleaned)
        return result

    def allow(self, user_id, count, *, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            for key in list(self.history):
                history = self.history[key]
                while history and history[0] <= now - 60:
                    history.popleft()
                if not history:
                    del self.history[key]
            history = self.history.setdefault(user_id, deque())
            if len(history) + count > 60:
                return False
            history.extend([now] * count)
            return True
