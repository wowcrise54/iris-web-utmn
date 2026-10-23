"""Task-local correlation on the worker's existing logging handlers."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import logging

_context = ContextVar('maxpatrol_log_context', default={})


@contextmanager
def logging_context(**values):
    token = _context.set({**_context.get(), **values})
    try:
        yield
    finally:
        _context.reset(token)


class ContextFilter(logging.Filter):
    _maxpatrol_context_filter = True

    def filter(self, record):
        values = _context.get()
        if values:
            context = ' '.join(f'{key}={json.dumps(value, ensure_ascii=True)}' for key, value in values.items())
            # Format existing arguments first: identifiers must not inject % placeholders.
            record.msg = f'[{context}] {record.getMessage()}'
            record.args = ()
        return True


def context_logger(name):
    logger = logging.getLogger(name)
    for existing in list(logger.filters):
        if getattr(existing, '_maxpatrol_context_filter', False):
            logger.removeFilter(existing)
    logger.addFilter(ContextFilter())
    return logger
