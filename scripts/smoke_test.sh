#!/usr/bin/env bash
# The smoke test: builds the image, starts it, and asks it a few questions.
# The pipeline runs it on every pull request. To run it on your own machine:
#
#     bash scripts/smoke_test.sh
#
# It needs Docker and curl. It ends with "The smoke test passed", or it stops
# at the first question that fails.

# Stop at the first command that fails, and at a name that was never set.
set -euo pipefail

# Work from the top folder of the repository, wherever the script is called from.
cd "$(dirname "$0")/.."

IMAGE="book-teller:smoke-test"
CONTAINER="book-teller-smoke-test"
PAGE="backend/src/book_teller/static/index.html"
PAGE_COPY="$(mktemp)"
cp "$PAGE" "$PAGE_COPY"

# Runs when the script ends, also after a failure: the page gets its own
# text back, and nothing stays running.
clean_up() {
    cp "$PAGE_COPY" "$PAGE"
    rm -f "$PAGE_COPY"
    docker rm --force "$CONTAINER" > /dev/null 2>&1 || true
    docker compose down > /dev/null 2>&1 || true
}
trap clean_up EXIT

fail() {
    echo "FAILED: $1" >&2
    exit 1
}

# Asks the health address once a second, for at most 30 seconds.
wait_for() {
    for _ in $(seq 30); do
        if curl --silent --fail "$1/health" > /dev/null; then
            return 0
        fi
        sleep 1
    done
    fail "the app at $1 did not start in 30 seconds"
}

echo "== Part 1: the image alone, as the cloud will run it =="

docker build --tag "$IMAGE" backend
docker run --detach --name "$CONTAINER" --publish 127.0.0.1:8001:8000 "$IMAGE" > /dev/null
wait_for http://127.0.0.1:8001

health="$(curl --silent --fail http://127.0.0.1:8001/health)"
[ "$health" = '{"status":"ok"}' ] || fail "/health answered: $health"
echo "ok: /health answers $health"

curl --silent --fail http://127.0.0.1:8001/ | grep --quiet "Book Teller" \
    || fail "the page does not hold the words Book Teller"
echo "ok: the page holds the words Book Teller"

user="$(docker exec "$CONTAINER" whoami)"
[ "$user" != "root" ] || fail "the app runs as root"
echo "ok: the app runs as the user $user"

docker rm --force "$CONTAINER" > /dev/null

echo "== Part 2: with Docker Compose, the volume line =="

docker compose up --build --detach
wait_for http://127.0.0.1:8000

# A word that is not in the image. It can reach the app only through the volume.
word="smoke-test-word-$$"
echo "<!-- $word -->" >> "$PAGE"
curl --silent --fail http://127.0.0.1:8000/ | grep --quiet "$word" \
    || fail "a change to the page on this machine does not show in the app"
echo "ok: a change to the page on this machine shows in the app"

echo "The smoke test passed."
