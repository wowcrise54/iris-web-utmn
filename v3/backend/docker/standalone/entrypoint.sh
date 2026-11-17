#!/bin/sh
set -eu

if [ "${1:-app}" = init ]; then
    exec python /usr/local/lib/iris-standalone-init.py
fi
set -a
. /runtime/iris.env
set +a
exec /iriswebapp/native-entrypoint.sh "${1:-app}"
