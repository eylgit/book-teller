# Book Teller

Book Teller turns a book into a podcast series: the book told well by one voice, about 30 minutes an episode, in English.

Every script will be checked against the book, and for each fault the checker will show the line of the book that proves it.

**Status:** the skeleton and its pipeline. The app shows one page and answers one health address; it tells no book yet. See [the plan of milestone 1](docs/plans/2026-11-14-milestone_1_the_whole_path_once/plan.md). Before the app there was a probe, a small early test: can the model find faults that were planted in a script? See [its plan](docs/plans/2026-11-13-probe_planted_faults/plan.md) and [its code](experiments/2026-11-13-probe_planted_faults/).

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
| `scripts/` | Scripts for the whole repository. Today one: the smoke test of the image |
| `docs/plans/` | One plan for each piece of work |
| `experiments/` | One-time experiments, kept as they were run. Each folder has the name of its plan folder in `docs/plans/` |

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

The smoke test needs Docker and curl, and the ports 8000 and 8001 free. It builds the image, starts it, and asks it a few questions: does it answer, and does it run as a user with no special rights? Run it from the top folder:

```
bash scripts/smoke_test.sh
```

## How a change gets in

Every change reaches `main` by a pull request. A pipeline, [azure-pipelines.yml](azure-pipelines.yml), runs on it: the tests, the three checks and the smoke test, on a fresh machine in Azure Pipelines. A ruleset on GitHub refuses the merge while a step fails, and refuses a push straight to `main`, also from the owner. The repository takes no pull requests from outside.

The pipeline runs in a private project of Azure DevOps, because Microsoft no longer offers public ones. So a visitor sees on each pull request whether the run passed, but cannot open its full log.

## How it is built

The project is built with a coding agent. How a change is made, and the merge rule: [CLAUDE.md](CLAUDE.md). What the agent may do: [.claude/settings.json](.claude/settings.json).

Licence: [MIT](LICENSE).
