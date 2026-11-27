#!/usr/bin/env bash
# The smoke test: starts one image of the app, and asks it a few questions.
#
#     bash scripts/smoke_test.sh IMAGE
#
# IMAGE is the image under test, by its name or by its id. The script does
# not build it: whoever calls the script says which image is meant. In the
# pipeline, the step "Build the image" builds it and hands its id over. On
# your own machine, from the top folder of the repository, after each change:
#
#     docker build --tag book-teller:candidate backend
#     bash scripts/smoke_test.sh book-teller:candidate
#
# Part 1 tests that image alone. Part 2 tests the app beside its database:
# there Docker Compose builds a second image of its own, which is thrown
# away and never pushed.
#
# It needs Docker and curl, and the ports 8000, 8001 and 5432 must be free:
# stop your own "docker compose up" first, also when only the database runs.
# It ends with "The smoke test passed", or it stops at the first question
# that fails.

# Stop at the first command that fails, and at a name that was never set.
set -euo pipefail

# Work from the top folder of the repository, wherever the script is called from.
cd "$(dirname "$0")/.."

# The image under test: the first word after the name of the script. Empty
# when none was given; that is checked below.
IMAGE="${1:-}"
CONTAINER="book-teller-smoke-test"
# Docker Compose under a name of its own. So the clean-up at the end can
# never take down the app that you started yourself with "docker compose up",
# and never throw away the rows of your own database: its volume carries the
# name of your project, not this one.
COMPOSE=(docker compose --project-name book-teller-smoke-test)
PAGE="backend/src/book_teller/static/index.html"
PAGE_COPY="$(mktemp)"
cp "$PAGE" "$PAGE_COPY"

# Runs when the script ends, also after a failure: nothing stays running,
# and the page gets its own text back.
clean_up() {
    docker rm --force "$CONTAINER" > /dev/null 2>&1 || true
    # "--volumes": the database of this test is thrown away with its rows.
    "${COMPOSE[@]}" down --volumes > /dev/null 2>&1 || true
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

echo "== Part 1: the image alone, with no database =="
PART=1

[ -n "$IMAGE" ] \
    || fail "name the image to test: bash scripts/smoke_test.sh IMAGE"
# Prints which image is tested: its id, the fingerprint of its content, and
# when it was made. An image from last week shows here.
docker image inspect --format 'The image under test: {{.Id}}, made at {{.Created}}' "$IMAGE" 2> /dev/null \
    || fail "there is no image $IMAGE on this machine. See the first lines of this script."
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

echo "== Part 2: with Docker Compose: the volume line, and the database =="
PART=2

if curl --silent --max-time 2 http://127.0.0.1:8000/health > /dev/null; then
    fail "something already answers on port 8000: stop your own app first"
fi
# Opens a connection to the port and closes it at once. bash does this
# itself, through the name /dev/tcp.
if (exec 3<> /dev/tcp/127.0.0.1/5432) 2> /dev/null; then
    fail "something already listens on port 5432: stop your own database first"
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

# The app's container ran the migrations at its start, on a database that
# was empty. So the tables must be there now. psql, the client of
# PostgreSQL, is asked inside the container of the database.
# "-At": only the value, with no frame around it.
tables="$("${COMPOSE[@]}" exec -T db psql --username postgres --dbname book_teller -At \
    --command "SELECT string_agg(tablename, ',' ORDER BY tablename) FROM pg_tables WHERE schemaname = 'public'")"
[ "$tables" = "alembic_version,faults,runs" ] \
    || fail "the tables of the database are: ${tables:-none}"
echo "ok: the migrations made the tables $tables"

echo "The smoke test passed."
