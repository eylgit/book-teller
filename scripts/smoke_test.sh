#!/usr/bin/env bash
# The smoke test: builds the image, starts it, and asks it a few questions.
# The pipeline runs it on every pull request. To run it on your own machine:
#
#     bash scripts/smoke_test.sh
#
# It needs Docker and curl, and the ports 8000 and 8001 must be free: stop
# your own "docker compose up" first. It ends with "The smoke test passed",
# or it stops at the first question that fails.

# Stop at the first command that fails, and at a name that was never set.
set -euo pipefail

# Work from the top folder of the repository, wherever the script is called from.
cd "$(dirname "$0")/.."

IMAGE="book-teller:smoke-test"
CONTAINER="book-teller-smoke-test"
# Docker Compose under a name of its own. So the clean-up at the end can
# never take down the app that you started yourself with "docker compose up".
COMPOSE=(docker compose --project-name book-teller-smoke-test)
PAGE="backend/src/book_teller/static/index.html"
PAGE_COPY="$(mktemp)"
cp "$PAGE" "$PAGE_COPY"

# Runs when the script ends, also after a failure: nothing stays running,
# and the page gets its own text back.
clean_up() {
    docker rm --force "$CONTAINER" > /dev/null 2>&1 || true
    "${COMPOSE[@]}" down > /dev/null 2>&1 || true
    cp "$PAGE_COPY" "$PAGE" || true
    rm -f "$PAGE_COPY"
}
trap clean_up EXIT

fail() {
    echo "FAILED: $1" >&2
    exit 1
}

# Asks the health address once a second, for at most 30 seconds.
# If the app never answers, it prints what the app wrote, and fails.
wait_for() {
    for _ in $(seq 30); do
        if curl --silent --fail --max-time 2 "$1/health" > /dev/null; then
            return 0
        fi
        sleep 1
    done
    echo "-- The last lines that the app wrote --" >&2
    if [ "$PART" = "1" ]; then
        docker logs --tail 30 "$CONTAINER" >&2 || true
    else
        "${COMPOSE[@]}" logs --tail 30 >&2 || true
    fi
    fail "the app at $1 did not start in 30 seconds"
}

# Gives the answer of one address. curl ends before the answer is looked at.
get() {
    curl --silent --fail --max-time 10 "$1"
}

echo "== Part 1: the image alone, as the cloud will run it =="
PART=1

docker build --tag "$IMAGE" backend
docker run --detach --name "$CONTAINER" --publish 127.0.0.1:8001:8000 "$IMAGE" > /dev/null
wait_for http://127.0.0.1:8001

health="$(get http://127.0.0.1:8001/health)"
[ "$health" = '{"status":"ok"}' ] || fail "/health answered: $health"
echo "ok: /health answers $health"

page="$(get http://127.0.0.1:8001/)"
grep --quiet "Book Teller" <<< "$page" \
    || fail "the page does not hold the words Book Teller"
echo "ok: the page holds the words Book Teller"

# The user number 0 is root, whatever its name is.
user_number="$(docker exec "$CONTAINER" id -u)"
[ "$user_number" != "0" ] || fail "the app runs as root"
echo "ok: the app does not run as root (user number $user_number)"

docker rm --force "$CONTAINER" > /dev/null

echo "== Part 2: with Docker Compose, the volume line =="
PART=2

if curl --silent --max-time 2 http://127.0.0.1:8000/health > /dev/null; then
    fail "something already answers on port 8000: stop your own app first"
fi

"${COMPOSE[@]}" up --build --detach
wait_for http://127.0.0.1:8000

# A word that is not in the image. It can reach the app only through the volume.
word="smoke-test-word-$$"
echo "<!-- $word -->" >> "$PAGE"
page="$(get http://127.0.0.1:8000/)"
grep --quiet "$word" <<< "$page" \
    || fail "a change to the page on this machine does not show in the app"
echo "ok: a change to the page on this machine shows in the app"

echo "The smoke test passed."
