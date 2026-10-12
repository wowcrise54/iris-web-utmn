#!/bin/bash

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




set -euo pipefail

target=${1:-iriswebapp}
LOG_LEVEL=${LOG_LEVEL:-info}

printf 'Running %s ...\n' "$target"

# The in-place updater deliberately stops and replaces the service process.
# Retain the container supervisor while that happens, and forward Docker stop.
shutdown() {
    trap - TERM INT
    pkill -TERM -P "$$" || true
    wait || true
    exit 0
}
trap shutdown TERM INT

if [[ "$target" == iris-worker ]]; then
    if [[ -n "${NUMBER_OF_CHILD:-}" ]]; then
        celery -A app.celery worker -c "$NUMBER_OF_CHILD" -E -B -l "$LOG_LEVEL" &
    else
        celery -A app.celery worker -E -B -l "$LOG_LEVEL" &
    fi
else
    uvicorn run:app --host 0.0.0.0 --port 8000 --workers 1 --timeout-keep-alive 180 --log-level "$LOG_LEVEL" &
fi

while true; do
    sleep 2 &
    wait $! || true
done

