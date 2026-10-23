__iris_module_interface = 'IrisOpenCTIInterface'

import logging
import os

# Configure only this package; keep IRIS/Celery handlers and global levels intact.
_level = os.environ.get('IRIS_OPENCTI_LOG_LEVEL', 'INFO').upper()
if _level == 'TRACE' or os.environ.get('IRIS_OPENCTI_LOG_PAYLOADS', '').lower() == 'true':
    _level = 'DEBUG'
logging.getLogger(__name__).setLevel(_level if _level in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL') else 'INFO')
