#!/bin/bash
# Run in a disposable container with the production entrypoint passed as $1.
set -euo pipefail
work=$(mktemp -d)
mkdir "$work/bin"
cat > "$work/bin/uvicorn" <<'SCRIPT'
#!/bin/bash
trap 'echo terminated > "$PROBE_DIRECTORY/terminated"; exit 0' TERM INT
echo "$$" > "$PROBE_DIRECTORY/started"
while true; do sleep 0.1; done
SCRIPT
chmod +x "$work/bin/uvicorn"
export PROBE_DIRECTORY="$work"
PATH="$work/bin:$PATH" bash "$1" iriswebapp > "$work/supervisor.log" 2>&1 &
supervisor=$!
for attempt in $(seq 1 50); do
    [[ -f "$work/started" ]] && break
    sleep 0.1
done
service=$(cat "$work/started")
kill -TERM "$service"
sleep 0.3
kill -0 "$supervisor"
echo 'PASS: supervisor survives deliberate service stop for the updater'
kill -TERM "$supervisor"
wait "$supervisor"
rm "$work/started" "$work/terminated"
PATH="$work/bin:$PATH" bash "$1" iriswebapp > "$work/supervisor.log" 2>&1 &
supervisor=$!
for attempt in $(seq 1 50); do
    [[ -f "$work/started" ]] && break
    sleep 0.1
done
kill -TERM "$supervisor"
wait "$supervisor"
test -f "$work/terminated"
echo 'PASS: supervisor forwards termination to the service'
