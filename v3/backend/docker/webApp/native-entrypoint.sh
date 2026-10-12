#!/bin/sh
set -eu
if [ "${1:-app}" = "worker" ]; then
    exec celery -A app.celery worker -c "${NUMBER_OF_CHILD:-2}" -E -B -l "${LOG_LEVEL:-info}"
fi
python -m scripts.run_post_init
exec uvicorn native_run:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips '*' --timeout-keep-alive 180
