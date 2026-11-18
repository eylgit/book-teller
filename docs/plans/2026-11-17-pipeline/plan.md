# Task 2: the pipeline

**State:** planned on 2026-11-17. The maintainer said yes to the plan on the same day, with the three answers below. The pipeline is built and reviewed, and `main` is protected. What the review changed is at the end.

It is the second task of [milestone 1](../2026-11-14-milestone_1_the_whole_path_once/plan.md).

## The goal

From this task on, no change reaches the main branch unseen and untested. Every change comes as a pull request (a change offered for merging), a machine in the cloud runs the tests and the checks on it, and GitHub refuses the merge while they fail.

The pipeline only tests. Building the image for the cloud and deploying it belong to task 3.

## What is built

| File or setting | What it holds |
|---|---|
| `azure-pipelines.yml` | The pipeline: the list of steps that Azure Pipelines runs on every pull request to `main`, and on `main` after a merge |
| `scripts/smoke_test.sh` | The smoke test: a short script that builds the image, starts it and asks it a few questions. The pipeline runs it, and the maintainer can run it too |
| `backend/tests/test_build_files.py` | Tests that read the Dockerfile: is every image named by its digest? |
| `backend/Dockerfile` | The two base images are named by their digest. Left by the review of [task 1](../2026-11-16-app_skeleton/plan.md) |
| `CLAUDE.md`, `README.md` | The merge rule, and how a change gets in |
| A project in Azure DevOps | It holds the pipeline and is joined to this repository. Made by hand, once |
| A ruleset on GitHub | The protection of `main`. Made by hand, once |

**The steps of the pipeline,** in this order. The first step that fails stops the run.

1. Install the tool `uv`, at the version that wrote the lockfile.
2. `uv sync --locked`: Python and the libraries, at the exact versions of the lockfile.
3. `uv run pytest`: the tests.
4. `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`: the three checks.
5. `scripts/smoke_test.sh`: the smoke test.

**The build machine.** Microsoft lends a fresh virtual machine for each run and throws it away after. The pipeline names it `ubuntu-24.04`, not `ubuntu-latest`: the label "latest" moves to a newer Ubuntu on a day that Microsoft chooses, and a run could then fail with no change in this repository. Ubuntu 24.04 is one below the newest, as with Python.

**The smoke test** asks the questions that the maintainer answered by hand in task 1:

- The image alone, as the cloud will run it: does `/health` answer `{"status":"ok"}`, does `/` hold the words "Book Teller", and is the user inside the container not `root`?
- With Docker Compose: does a word written into the page on the machine show in the running app? That proves the volume line of `compose.yaml`. The script takes the word out again when it ends.

**The digests.** `python:3.14-slim` is a tag: a name that its owner can move to another image. A digest is the fingerprint of one exact image. The Dockerfile keeps the tag for the reader and adds the digest, which is what Docker follows: `python:3.14-slim@sha256:…`. The same for the image of `uv`. The price: a pinned image gets no security fix until the digest is changed by hand.

**The protection of `main`,** as a ruleset on GitHub (a set of rules for a branch, which every visitor of a public repository can read):

- A change needs a pull request.
- The run of the pipeline must have passed, on a branch that holds the newest `main`.
- No push by force, and the branch cannot be deleted.
- Nobody is on the list of people who may pass the rules, also not the owner.

## The merge rule

1. **Every change goes in by a pull request,** also a plan and a spelling mistake. The pipeline must pass.
2. **Before the merge,** the change went through the steps of [CLAUDE.md](../../../CLAUDE.md): the plan check, the test first, the review by a second agent, the code-review check.
3. **A pull request that changes anything about secrets, or the code that checks the model's answer,** is read line by line by the maintainer before the merge.
4. **A pull request is merged with a merge commit,** not squashed into one commit. So the history keeps each step: the plan, the failing test, the code.

A plan is the first commit on the branch of its task, so it is still committed before the code. In this task it was not: the plan went in together with the first tests, in one commit. It was left so, because the fix would have been a push by force.

**No pull request from outside.** The repository is public to read. Only a collaborator, somebody whom the owner invited, can open a pull request, and issues and the wiki are off.

## Decided by the maintainer

| # | Question | Options | Chosen |
|---|---|---|---|
| 1 | Does every change need a pull request? | **A.** Every change. Costs about three minutes for each small change, and a run of the pipeline · **B.** Code by pull request; plans and documents straight to `main`. Then the owner must be allowed to pass the rules, and the protection is weaker | **A** |
| 2 | Which Ubuntu? | `ubuntu-24.04`, which "latest" means today · `ubuntu-26.04`, available since 2026-09-29 | `ubuntu-24.04` |
| 3 | How is a pull request merged? | A merge commit: every commit stays · A squash: one commit for each pull request, and the failing test is no longer in the history | A merge commit |

## New tools on the build machine

No new library in the project. On the build machine, the pipeline installs `uv` with `pipx`, a tool that the machine already has. Docker is already there too.

## Exit criteria

1. A pull request to `main` starts the pipeline, and GitHub shows its result on the page of the pull request.
2. The pipeline runs the five steps above, on `ubuntu-24.04`, with `uv` at a fixed version.
3. The history of the first pull request holds a failed run and then a passed one: the tests for the digests are pushed before the digests.
4. Both images of the Dockerfile are named by a digest, and `docker compose up --build` still works on the maintainer's machine.
5. The smoke test passes in the pipeline and on the maintainer's machine. It was seen to fail once: with the line `USER app` taken out of the Dockerfile, it must say no.
6. `main` is protected. The maintainer sees GitHub refuse two things: a push straight to `main`, and the merge of a pull request whose run failed.
7. `CLAUDE.md` and the README hold the merge rule.
8. The pipeline holds no secret and needs none. A stranger cannot start it: GitHub takes a pull request only from a collaborator, and Azure Pipelines builds no pull request from a fork (a copy of the repository under another account).

## Test cases

In `backend/tests/test_build_files.py`, run by `pytest`:

1. Every image that the Dockerfile names, after `FROM` and after `COPY --from=`, has a digest: `@sha256:` and 64 characters.
2. The Dockerfile names exactly two images. Without this case, case 1 could pass by finding nothing.
3. The code that finds the images catches a name with only a tag, and a digest that is too short.

In `scripts/smoke_test.sh`, run by the pipeline:

4. The image builds from the lockfile.
5. A container from the image alone answers `/health` with 200 and `{"status":"ok"}`.
6. The same container gives a page with the words "Book Teller".
7. `whoami` in that container does not answer `root`.
8. With Docker Compose, a word written into `index.html` on the machine is in the answer of `/`.

Seen once by the maintainer, on GitHub:

9. A push straight to `main` is refused.
10. A pull request with a failed run cannot be merged.

## The order of the work

1. The maintainer pushes `main` as it is. It is the last push straight to `main`.
2. A branch for this task. First commit: this plan.
3. The tests for the digests, the smoke test and the pipeline file. The tests for the digests fail on the maintainer's machine.
4. Push, and open the pull request. The maintainer makes the project in Azure DevOps and joins it to the repository. First run: failed.
5. The maintainer makes the ruleset. The merge button is locked.
6. The digests go into the Dockerfile. Second run: passed.
7. The review by a second agent, the fixes, the merge rule in `CLAUDE.md` and the README.
8. The merge. Then one try to push straight to `main`: refused.

## What could go wrong

- **The logs are not public.** Microsoft has retired public projects in Azure DevOps, so the project is private. A visitor sees on GitHub whether a run passed or failed, with a summary, but cannot open the full log.
- **A pull request from a fork would run a stranger's steps on the build machine,** and could use up the free minutes. Task 3 brings the login to Azure, so this door is closed now, twice. On GitHub, the setting "Pull requests" is "Collaborators only". In Azure DevOps, the setting "Limit building pull requests from forked GitHub repositories" is on, with "Disable building pull requests from forked repositories". Both settings are made by hand and are not in a file of this repository.
- **A required check that never reports locks every merge.** That happens when a pipeline leaves out some changes, e.g. changes to documents only. So this pipeline runs on every pull request, with no filter on paths.
- **The free runs.** 1,800 minutes a month, one run at a time. A run is expected to take a few minutes; that is not measured yet.
- **One image for two kinds of machine.** The maintainer's machine and the build machine have different processors. The digest must be the one of the list that holds both forms of the image, not of one form.
- **The agent cannot run Docker or reach GitHub.** Then the maintainer runs the smoke test and makes the settings, and the agent reads the output.
- **Only the maintainer can now break `main`, and only through a pull request.** A wrong rule could lock the maintainer out too. The owner can always change or delete the ruleset.

## How it is undone

Delete the ruleset on GitHub and the pipeline in Azure DevOps; take the four new files and the changed lines back. Nothing costs money: the runs are inside the free 1,800 minutes.

## What was seen

- **The first run failed** at the step "Tests": `1 failed, 9 passed`. GitHub then refused the merge: "Required checks failing".
- **The second run passed,** after the digests went into the Dockerfile. It took 54 seconds.
- **The smoke test said no once:** with the line `USER app` taken out of the Dockerfile, it stopped with "FAILED: the app runs as root".

## What the review changed

A second agent reviewed the change in a fresh session. The maintainer decided on each finding.

- **The smoke test could take down the maintainer's own running app.** It now runs Docker Compose under a name of its own, and stops with a clear sentence when port 8000 is taken.
- **The code that finds the images did not see three ways to name one:** lower case, an instruction over two lines, and an image inside `RUN --mount=`. A test case for the three is new.
- **A check of the page could fail by chance** once the page grows: `curl` was still sending while `grep` had already stopped. The script now lets `curl` end first.
- **A run that hangs** is stopped after 10 minutes, not after 60.
- **When the app does not start,** the smoke test prints the last lines that the app wrote. And it asks for the number of the user, not the name: the number 0 is root under any name.
- **Left for its own pull request, the next one:** the pinned version of `uv`, 0.12.6, has a security notice (GHSA-hq85-5cpj-mr62), fixed in 0.13.4. Done on 2026-11-18: `uv` is 0.13.8, in the pipeline and in the Dockerfile.
- **Left for task 3:** when the Dockerfile gets a second stage, the code that finds the images must learn the name of a stage, which is not an image.
- **Not taken:** a test that the version of `uv` is the same in the pipeline and in the Dockerfile. No mistake has happened there yet.
