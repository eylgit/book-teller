# The build of the image gets a step of its own

**State:** planned on 2026-11-27. The maintainer said yes on the same day, and then made the design stricter: see "Decided by the maintainer". The change is made, and a second agent has reviewed its first form: see "What the review changed". Merged on 2026-11-27, by a pull request, and deployed: see "What was seen". A second, small pull request followed the merge, with this final state.

A small change after [task 8](../2026-11-26-database/plan.md) of [milestone 1](../2026-11-14-milestone_1_the_whole_path_once/plan.md).

## The goal

Before this change, the image that goes to production was built inside the smoke test: a line of `scripts/smoke_test.sh` ran `docker build`, and two steps later the pipeline pushed that image to the registry. The pipeline had no step with the word "build" in it. A reader who looked for the place where the image is made did not find it, and nobody expects a test script to make the thing that is deployed.

After this change:

- the pipeline has a step "Build the image", before the smoke test;
- that step reads the id of the image, the fingerprint of its content, and hands it to the later steps;
- the smoke test is told which image to test, by that id, and does not build it;
- after a merge, the push step takes the image by the same id. So the image that was tested is the image that is deployed, and nothing is built twice for production.

## What changes

| File | The change |
|---|---|
| `azure-pipelines.yml` | A new step, "Build the image": `docker build --tag book-teller:candidate backend`, then the id of that image goes into the variable `imageId`. The smoke test is called with `$(imageId)`. The push step tags the image by `$(imageId)` |
| `scripts/smoke_test.sh` | The line `docker build` goes. The image under test is the first word after the name of the script. With no image named, or one that is not on the machine, the script stops at once. It prints the id of the image and when it was made |
| `backend/tests/test_build_files.py` | The tests below |
| `README.md` | "Run the checks": build the image, then run the smoke test with its name. "How a change gets in": the build is named as a step |

The name `candidate`: an image that was built and is not yet tested.

**A name and an id.** A name, such as `book-teller:candidate`, can be moved to another image by a later build. The id cannot: it is made from the content of the image. In this pipeline the name would be safe too, because the machine is fresh and one job runs the steps in order. The id makes the same thing true without that reasoning, and it is what the base images of the Dockerfile already do with their digests.

**What the id does not cover.** The id is the image's id on the build machine. The registry gives a pushed image a second fingerprint of its own, and the app on Azure is told to run the image by its name in the registry: the id of the merge commit. So the chain "tested, then pushed" is held by the id, and the chain "pushed, then run" by a name that this run has just made.

Part 2 of the smoke test stays as it is. There Docker Compose builds an image of its own, for the app beside its database. That image is thrown away and never pushed.

## Decided by the maintainer

| Question | Options, and what each costs | Chosen |
|---|---|---|
| **The smoke test on the maintainer's machine, when no image was built:** what does it do? | **A. It stops.** The script has one job. Costs: two commands by hand, not one; and an image that was built before the last change is tested as it is. · **B. It builds the image itself when none is there.** Costs: the script builds again after all, on one of its two paths | **A** |

After the review, the maintainer asked for two more things, and both are built:

- **The image is an argument of the smoke test,** not a name written inside it. The script cannot run without being told what to test, and the line of the pipeline that calls it shows which image is meant.
- **The build step records the id of the image, and the later steps use the id,** not the name.

## Exit criteria

1. On a pull request, the run of the pipeline shows the step "Build the image", and then the smoke test passes with the image of that id.
2. After the merge, the run on `main` pushes and deploys that same image, and the live app answers.
3. `scripts/smoke_test.sh` holds no build of the image under test, and no image name of its own.
4. On the maintainer's machine: with no image named, and with a name that does not exist, the smoke test stops with a message; with a built image, it passes.
5. `uv run pytest`, `ruff` and `mypy` pass.

## Test cases

In `backend/tests/test_build_files.py`, by reading the two files:

1. The smoke test does not build the image under test: without its comments and messages, it holds no `docker build`, in any of Docker's three spellings.
2. The smoke test is told which image to test: the image is its first argument, and the script has no image name to fall back on.
3. In the pipeline: one build; the id of that image is read and handed on; the smoke test gets that id; the push step takes the image by that id; in that order.
4. The helper that drops comments and messages from a script is tested itself.

Seen once by the maintainer: exit criteria 1, 2 and 4.

## What could go wrong

- **The syntax of the new step is wrong for Azure Pipelines,** or the variable does not reach the later steps. The run on the pull request shows it, before anything can be pushed.
- **An id is not taken where a name was.** `docker run` and `docker tag` both take an id; seen first in that same run.
- **The agent cannot reach Docker.** The maintainer runs the smoke test, and the pull request shows the pipeline.

## What the review changed

A second agent reviewed the first form of this change, in which the smoke test still held the name of the image. It read the files and ran the one test file. It could reach no Docker.

- **Three sentences said "the smoke test builds nothing".** Not true: its second part lets Docker Compose build a throwaway image. They now say that the script does not build the image under test.
- **The first test could be got around:** it saw only a line that starts with `docker build`. It now reads every command of the script.
- **An image from last week would be tested without a word** on the maintainer's machine. The plan had named this as a cost of option B only; it holds for A too. The script now prints the id of the image and when it was made, and the README says to build again after each change. The pipeline is not touched: its machine is fresh.
- **Stale sentences** in the first lines of the test file and in this plan. Corrected.
- **Not taken:** a test that holds the build command in the README.

After these changes the agent tried five small breakages on copies of the two files: the smoke test builds when no image is there · the smoke test has an image name to fall back on · the push takes the name · the smoke test gets the name · the id is read from another image. The tests noticed all five.

## What was seen

On 2026-11-27, in the run of the pull request:

- **The step "Build the image"** built the image, named it `book-teller:candidate`, and printed its id: the id that Docker itself had printed two lines before.
- **The step "Smoke test of the image"** was called with that id, printed the same id as "the image under test", and passed.

After the merge, the run on `main` passed too: the push step took the image by its id, and the live app ran the new image and answered. The maintainer ran the smoke test on the own machine as well.

## How it is undone

Put the line `docker build` and the name back into the smoke test, and take the step out of the pipeline.
