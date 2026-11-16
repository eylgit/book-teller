# Task 1: the skeleton of the app

**State:** planned on 2026-11-16. The maintainer said yes to the plan and to the six dependencies on the same day. No code yet.

It is the first task of [milestone 1](../2026-11-14-milestone_1_the_whole_path_once/plan.md).

## The goal

A web app that does almost nothing, built with care: one page, one health address, its tests, its checks, and one command that runs it on the maintainer's machine. Every later task copies its shape, so the shape must be right.

Nothing here talks to a model, a database or the cloud.

## What is built

| File | What it holds |
|---|---|
| `pyproject.toml` | The name of the project, the Python version, the libraries, and the settings of the checks |
| `uv.lock` | The lockfile: the exact version of every library, written by the tool `uv` |
| `.python-version` | The Python version: 3.13 |
| `src/book_teller/main.py` | The app: two routes (a route is one address with its code) |
| `src/book_teller/static/index.html` | The page: the name of the product and one line that says what will come. Plain HTML with Bootstrap |
| `tests/test_app.py` | The tests |
| `Dockerfile` | The recipe for the image: the app and everything it needs, packed in one file |
| `compose.yaml` | Docker Compose: one command starts the app on the maintainer's machine |
| `.dockerignore` | What stays out of the image |
| `README.md` | Two new parts: how to run it, and how to run the checks |

**The two routes.**

- `GET /` gives the page.
- `GET /health` gives `{"status": "ok"}`. A machine asks this address to learn whether the app is alive. The pipeline and Azure use it in the next tasks.

**The checks.** Three programs read the code without running it:

- `ruff check`: a linter. It finds likely mistakes.
- `ruff format --check`: a formatter. It keeps one style.
- `mypy`, in strict mode: a type checker. It finds a value of the wrong kind, such as text where a number is expected.

**On the maintainer's machine.** `docker compose up --build` builds the image and starts the app at `http://localhost:8000`. One line of `compose.yaml` is a volume: it puts the folder `src` of the machine into the running container, so a change to the page shows after a reload, with no new build. The image itself still holds its own copy of the code: the cloud runs the image without that line.

**The container does not run as root.** The Dockerfile makes a user with no special rights, and the app runs as that user.

## New dependencies

Each one needs the maintainer's yes, as [CLAUDE.md](../../../CLAUDE.md) says.

| Library | For | Why this one |
|---|---|---|
| `fastapi` | The web app | Chosen for the milestone |
| `uvicorn` | The server program that runs the app | The server that FastAPI's own pages use |
| `pytest` | The tests | The standard test tool in Python. Only for development |
| `httpx` | The tests call the app through it, with no network | FastAPI's test client needs it. Only for development |
| `ruff` | Linter and formatter | One fast tool for both. Only for development |
| `mypy` | Type checker | The most used one. Only for development |

The tool `uv` installs them and writes the lockfile. Bootstrap is not installed: the page loads one fixed version from a public address, with a checksum, so the browser refuses a changed file.

**Left out on purpose:** a template library. The page is one fixed file. A database in `compose.yaml`: it joins in task 8, when something uses it.

## Exit criteria

1. `uv run pytest` passes, with no network. Each test was seen to fail first.
2. `uv run ruff check`, `uv run ruff format --check` and `uv run mypy` pass.
3. `uv sync --locked` works on a clean copy: the lockfile and `pyproject.toml` agree.
4. `docker compose up --build` shows the page at `http://localhost:8000`, and `http://localhost:8000/health` answers `{"status": "ok"}`. The maintainer sees both.
5. A change to `index.html` shows after a reload of the browser, with no new build.
6. Inside the container, `whoami` does not answer `root`.
7. The README says how to run the app and the checks.
8. No key is in the repository.

## Test cases

1. `GET /health` answers 200, and the body is `{"status": "ok"}`.
2. `GET /` answers 200, the content type is HTML, and the page holds the words "Book Teller".
3. `GET /` holds no address of a script or a style without a checksum.
4. An address that does not exist answers 404.
5. `POST /health` answers 405: the route takes only `GET`.

Criteria 4 to 6 are checked by hand, once, by the maintainer. A test for them comes with the pipeline in task 2, which builds the image on every change.

## What could go wrong

- **The agent cannot run Docker.** Its sandbox may not reach Docker on this machine. Then the maintainer runs the three Docker checks, and the agent reads the output.
- **The versions.** The agent's memory of these libraries may be old. The lockfile holds what `uv` really chose, and the checks run against that.
- **Strict type checking is strict.** It may ask for more words in the code than a small app needs. If it gets in the way, the plan says so, and the maintainer decides.

## How it is undone

Every file of this task is new, except the README. Deleting them and taking the README change back removes the task. Nothing is made in the cloud, and nothing costs money.
