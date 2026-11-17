# Book Teller

Book Teller turns a book into a podcast series: the book told well by one voice, about 30 minutes an episode, in English.

Every script will be checked against the book, and for each fault the checker will show the line of the book that proves it.

**Status:** the skeleton. The app shows one page and answers one health address; it tells no book yet. See [the plan of milestone 1](docs/plans/2026-11-14-milestone_1_the_whole_path_once/plan.md). Before the app there was a probe, a small early test: can the model find faults that were planted in a script? See [its plan](docs/plans/2026-11-13-probe_planted_faults/plan.md).

## Run it

You need [Docker](https://docs.docker.com/get-docker/).

```
docker compose up --build
```

Then open <http://localhost:8000>. The address <http://localhost:8000/health> answers `{"status":"ok"}`.

A change to the page, `backend/src/book_teller/static/index.html`, shows after a reload of the browser, with no new build: `compose.yaml` puts the folder `backend/src` into the running container. A change to the Python code needs a restart: `docker compose restart`.

## The folders

| Folder | What it holds |
|---|---|
| `backend/` | The Python project: the web app, its tests, its lockfile and its Dockerfile |
| `docs/plans/` | One plan for each piece of work |
| `probes/` | Small early tests, kept as they were run |

## Run the checks

You need [uv](https://docs.astral.sh/uv/). It installs Python and the libraries at the exact versions of the lockfile, `backend/uv.lock`. Run the commands inside the folder `backend`.

```
cd backend
uv sync --locked
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy
```

The tests need no network. `ruff` is the linter and the formatter; `mypy` is the type checker.

## How it is built

The project is built with a coding agent. How a change is made: [CLAUDE.md](CLAUDE.md). What the agent may do: [.claude/settings.json](.claude/settings.json).

Licence: [MIT](LICENSE).
