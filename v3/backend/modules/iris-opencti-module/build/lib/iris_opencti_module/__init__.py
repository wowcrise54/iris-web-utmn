__iris_module_interface = 'IrisOpenCTIInterface'

import logging
import os
import json

# Configure only this package; keep IRIS/Celery handlers and global levels intact.
_level = os.environ.get('IRIS_OPENCTI_LOG_LEVEL', '').upper()
try:
    _overrides = json.loads(os.environ.get('IRIS_LOG_LEVELS', '{}'))
except ValueError:
    _overrides = {}
if _level and not any(__name__ == name or __name__.startswith(name + '.') for name in _overrides):
    logging.getLogger(__name__).setLevel(5 if _level == 'TRACE' else
        _level if _level in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL') else 'INFO')
