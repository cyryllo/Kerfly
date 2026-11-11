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
# the runner image usually has them already: ask the package servers only for what is missing
missing=()
for pkg in "$@"; do
    dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed" || missing+=("$pkg")
done
if [ ${#missing[@]} -eq 0 ]; then
    echo "already installed: $*"
    exit 0
fi
echo "to install: ${missing[*]}"
set -- "${missing[@]}"
for attempt in 1 2 3; do
    # a broken extra repository (not Ubuntu's) makes "update" fail: go on with the lists we got
    # time limits: a package server that does not answer must not hold the job for an hour
    sudo timeout 300 apt-get update -o Acquire::Retries=3 -o Acquire::http::Timeout=30 >>"$log" 2>&1 \
        || echo "::warning title=apt-get update (attempt $attempt)::$(grep -E '^(E|W|Err):' "$log" | tail -3 | tr '\n' ' ')"
    if sudo timeout 600 apt-get install -y "${extra[@]}" -o Acquire::Retries=3 -o Acquire::http::Timeout=30 \
            "$@" >>"$log" 2>&1; then
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
