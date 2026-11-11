#!/bin/bash
# Install Ubuntu packages on a GitHub runner, sturdy against short outages of the
# package servers: retries, a failing extra repository in the runner image does not
# stop it, and when it still fails the reason is shown as an annotation (readable
# on the run's page without logging in; the log itself needs an account).
#   .github/scripts/apt-install.sh [--no-install-recommends] package...
set -u
extra=()
if [ "${1:-}" = "--no-install-recommends" ]; then
    extra=(--no-install-recommends)
    shift
fi
log=$(mktemp)
for attempt in 1 2 3; do
    # a broken extra repository (not Ubuntu's) makes "update" fail: go on with the lists we got
    sudo apt-get update -o Acquire::Retries=5 >>"$log" 2>&1 \
        || echo "::warning title=apt-get update (attempt $attempt)::$(grep -E '^(E|W|Err):' "$log" | tail -3 | tr '\n' ' ')"
    if sudo apt-get install -y "${extra[@]}" -o Acquire::Retries=5 "$@" >>"$log" 2>&1; then
        echo "installed: $*"
        exit 0
    fi
    echo "apt-get install failed (attempt $attempt), waiting before the next one"
    tail -n 15 "$log"
    sleep $((attempt * 30))
done
echo "::error title=apt-get install::$(grep -E '^(E|Err):' "$log" | tail -6 | tr '\n' ' ' | sed 's/%/%25/g')"
cat "$log"
exit 1
