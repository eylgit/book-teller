# Task 5: the graph of two steps

**State:** planned on 2026-11-25. The maintainer said yes to the plan on the same day, with the three answers below. Nothing is built.

It is the fifth task of [milestone 1](../2026-11-14-milestone_1_the_whole_path_once/plan.md).

## The goal

One chapter goes in. Two steps run in a fixed order: the first writes the script of an episode from the chapter, the second checks that script against the chapter. Each step is one model call, made through the model call of [task 4](../2026-11-24-model_call/plan.md). LangGraph runs the two steps and carries the data from one to the next. The tests need no network and cost nothing.

After this task the app still does not call the model for a visitor. The guard on the checker's answer comes in task 6, and the route that starts a run in task 9.

## What is built

| File | What it holds |
|---|---|
| `backend/src/book_teller/write_step.py` | The instructions for the writer, and the shape of its answer, `Script`: a list of sentences. One sentence is one item, because the checker points at a sentence by its number |
| `backend/src/book_teller/check_step.py` | The instructions for the checker, and the shape of its answer, `Flags`: a list of faults. They move here from the measuring script and are completed: see "The checker's answer says what it means". Also the function that numbers the paragraphs of the chapter and the sentences of the script |
| `backend/src/book_teller/episode.py` | The graph: the state, the two nodes, the edges, and `build_graph`, which puts them together |
| `backend/src/book_teller/tell.py` | A script for the maintainer, started by hand. It reads a chapter from a file, runs the graph with the real model, and prints the script, the faults that the checker flagged, and what each step cost |
| `backend/src/book_teller/measure.py` | Changed: it takes the instructions and the shape from `check_step.py`. It keeps no copy of its own |
| `backend/tests/test_episode.py`, `test_check_step.py`, `test_tell.py` | The tests below |
| `backend/pyproject.toml`, `backend/uv.lock` | One library: see "New library" |
| `README.md` | A section "The two steps": the picture of the graph, and how to run `tell.py` |

## The words of LangGraph, and how this task uses each

LangGraph writes a program as boxes and arrows. This task uses five of its words.

| Word | What it is | Here |
|---|---|---|
| **State** | The data that all steps share. Every step reads it, and returns only the part that it changes | The chapter, the script, the flags, and the cost of each call |
| **Node** | One step: a plain Python function. It gets the state and returns its changes | Two nodes: `write` and `check` |
| **Edge** | An arrow: which node runs next | `START → write → check → END`. All fixed. No arrow with a condition |
| **Retry policy** | A rule on a node: after which errors it runs again, and how often | The same rule on both nodes |
| **Reducer** | The rule for how a node's result goes into the state. The usual rule: the new value replaces the old one. A reducer can add to the old value instead | One: the list of costs. Each step adds its own line, so the second step does not wipe the first one's |

`build_graph` describes the nodes and the edges, and `compile()` turns the description into the thing that can run. `invoke` runs it once, from `START` to `END`, and returns the last state.

**Each choice, written out:**

- **The state is a `TypedDict`:** a Python dictionary whose keys and types are named. It is the form that LangGraph's own pages use first.
- **The model is handed in, not held in the state.** `build_graph` receives one function, "ask the model". The real one is `ask_model` of task 4 with the model already inside. A test hands in a function of a few lines that gives fixed answers. No test of this task reaches the HTTP layer, except one: see test case 9.
- **Nothing is saved between the steps.** LangGraph can save the state after every step (its word: a checkpointer), so that a run can go on after a failure. That belongs to milestone 2. Here, when the second step fails, the script of the first step is lost, and the run must start again.
- **The graph tries a failed step once more** (the maintainer, 2026-11-25). A node gets a second try only when a retry rule is given for it (`retry_policy=` in `add_node`; LangGraph's page "Fault tolerance", read on 2026-11-25). Both nodes get the same rule, written out:
  - **Two tries, not three.** The model call already makes up to three requests by itself, so one step can make up to six. With three tries on the node it would be nine.
  - **Our own answer to "is this error worth a second try?".** Left alone, LangGraph tries again after almost every kind of error, so also after `no permission`, where a second try gives the same answer. Our function says yes for three reasons of `ModelCallError`: `timeout`, `too many requests`, `service error`. It says no for `no permission`, `refused` and `wrong shape`.
  - **Only the failed node runs again.** When the checker fails, the writer is not asked a second time.
- **After the last try, a failed call ends the run.** The `ModelCallError` of the step leaves `invoke`, with its reason. No step swallows it.

## The checker's answer says what it means

Two gaps were found when the code of task 4 was read line by line.

1. **The fields of a flag have no description.** The model learns what `sentence`, `paragraph`, `quote` and `reason` mean from the names alone: the list that explained them in the [probe](../2026-11-13-probe_planted_faults/plan.md) was lost on the way. Now each field gets its meaning as `Field(description=…)`. Pydantic puts that text into the JSON schema, and the schema travels to the model inside the request. So the meaning stands beside the field, in one place.
2. **The kinds are bare numbers,** 1 to 6. A reader of the code or of an answer must look them up in the instructions. See question 1 below.

One test reads the real request and holds that the descriptions are in it.

## The writer

The instructions are short: tell the chapter for a listener, say only what the author said, add nothing, one sentence in each item. The length is a part of them; the script of the probe has about 900 words for a chapter of about 3,200.

**No test can say whether a script is good.** The tests hold that the writer is asked, with the chapter, for the right shape. The maintainer reads the script of the first real run. How well the checker finds faults is measured in task 11; nothing in milestone 1 measures the writer.

## Decided by the maintainer

| # | Question | Options | Chosen |
|---|---|---|---|
| 1 | How does the checker name the kind of a fault? | **A.** By a name, as text: the model answers `"wrong_fact"`, and the code has an enum with the six names. An answer, a saved row and a log line can be read with no table beside them. Costs: the probe measured the model with numbers, so the catch rate can move, and nobody knows before task 11 measures it again; the answer key of the probe uses numbers, so the planted-fault test needs a small table from number to name; the milestone's table of faults said "kind (1 to 6)" · **B.** By a number, as today, with an enum in the code that gives each number a name. The request stays as it was measured. Costs: the answer and every saved row still hold a bare number, and the model reads the meaning only in the instructions · **C.** No change. Costs: the gap stays | **A** |
| 2 | Does the graph try a failed step again? | **A.** No. The three tries of the model call are the only ones. Costs: a failure that outlasts those three tries ends the run, and the maintainer starts it again by hand · **B.** Yes, a retry rule on each node. Costs: up to nine requests for one step, and with the timeout of 60 seconds a step that hangs can hold the run for about nine minutes | **B**, with two tries in place of three: up to six requests, and about six minutes for a step that hangs. The agent had proposed A. The maintainer's reason: the project should use the retry rule of LangGraph, not only name it |
| 3 | May the library be installed, and may one real run be made? | See "New library" and "What costs money" | Yes to both |

## New library

The maintainer installs it.

| Library | Why |
|---|---|
| `langgraph` (1.2.24 on 2026-11-25, released on 2026-11-20) | It runs the steps and carries the state. By its own list on PyPI it brings `langgraph-checkpoint`, `langgraph-prebuilt`, `langgraph-sdk` and `xxhash`; what those bring is seen at the install. It does not bring the package `langchain` |

## What costs money

- **`tell.py` makes real calls:** two for one run. One call of the checker in task 4 took 5,446 tokens in and 1,639 out. The writer reads the chapter and writes about 900 words. One run stays under 5 US cents; the first run shows the real number.

Nothing in the cloud changes in this task, and no permission is touched.

## Exit criteria

1. `uv run pytest` passes with no network, and the new tests were seen to fail first.
2. `ruff` and `mypy` pass, and a warning still fails the test run.
3. The maintainer saw one real run: a chapter went in, and a script, a list of flags and the cost of each of the two calls came out.
4. The picture of the graph in the README is printed by the library from the code, not drawn by hand, and it shows `write`, then `check`.
5. The numbers of the real run are written into this plan: tokens and seconds of each step.
6. The app starts without any setting of the model: the page and `/health` answer, and the pipeline builds the image with the new library and deploys as before.
7. No key, no address and no name of an Azure resource is in the repository.

## Test cases

Run by `pytest`. The model is a function of a few lines that keeps what it was asked and gives fixed answers.

In `backend/tests/test_episode.py`:

1. One run asks the model twice: first the writer, then the checker.
2. The writer gets the chapter, and is asked for the shape `Script`.
3. The checker gets the chapter with numbered paragraphs, and the script that the writer returned, with numbered sentences. It is asked for the shape `Flags`.
4. The last state holds the chapter, the script and the flags.
5. The last state holds the cost of both calls, in their order, each with the name of its step. The second does not replace the first.
6. The checker fails once with `timeout`, then answers: the run ends well. The checker was asked twice, and the writer once.
7. The writer fails every time with `service error`: the run ends with that `ModelCallError`, after exactly two tries. The checker is never asked.
7a. A failure with `too many requests` gets a second try too.
7b. A failure with `no permission`, `refused` or `wrong shape` gets no second try: the step was asked once, and the run ends with that error.
7c. After a second try that worked, the list of costs holds one line for each step, not a line for the failed try.

In `backend/tests/test_check_step.py`:

8. Every field of a flag has a description in the JSON schema of `Flags`.
9. Through the fake model service of task 4: the request that leaves for the model holds those descriptions.
10. Every kind of fault that the enum names is explained in the instructions, and the instructions explain no other. So the two cannot drift apart.
11. The paragraphs of a chapter are split at blank lines and numbered from 1, and so are the sentences of a script. This test moves here from the tests of the measuring script.

In `backend/tests/test_tell.py`:

12. A run prints the script, each flag and the cost of each step.
13. A call that fails prints one line with the reason, and the script ends with exit code 1.
14. A missing setting is named, and no call is made.

Kept as they are:

15. The five tests of the measuring script pass with the shape and the instructions of `check_step.py`.
16. The app's own tests pass with none of the settings present.

Seen once by the maintainer, with the real model:

17. One real run of `tell.py` with the chapter of the probe.
18. The picture of the graph, as the library prints it.

## The order of the work

1. A branch for this task. First commit: this plan.
2. The maintainer installs the library. The old tests must still pass: a new library can bring a new warning.
3. The tests. They fail: the three files do not exist.
4. `write_step.py`, `check_step.py`, `episode.py`; the change in `measure.py`. The tests pass.
5. `tell.py` and its tests. The first real run; its numbers go into this plan.
6. The review by a second agent, the fixes, the README.
7. The pull request and the merge.

## What could go wrong

- **A warning from the new library fails every test.** It happened in task 4 with `langsmith`. If it happens again, the one warning is named and let through, with the reason beside it, and the maintainer is asked first.
- **`mypy` in strict mode and the types of LangGraph.** A node returns a part of the state, and the type checker may need help to accept that.
- **Retries multiply.** Two tries of the node, each with up to three requests: a step that hangs holds the run for about six minutes. And a second try of the writer pays for the chapter again.
- **The retry rule waits before the second try** (half a second by its default). The tests must not wait, so they hand in the same rule with the wait set to nothing. That this can be done is not verified.
- **How a failed node ends a run is read from the documentation, not seen yet.** Test cases 6 to 7b prove it after the install. If LangGraph wraps the error in one of its own, the plan is corrected and the maintainer decides.
- **The picture.** That the library prints the graph as text for a diagram, with no further library, is not verified. If it cannot, the README gets no picture, and exit criterion 4 is taken out with the maintainer's yes.
- **The writer may need more than the timeout.** One try has 60 seconds. The checker took 14.6 seconds for 1,639 tokens out. The first real run shows what the writer takes.
- **The checker's request changes** (descriptions, and names for the kinds if question 1 is A). The table of task 4 was measured with the old request. Its numbers stay as history.
- **The agent cannot reach Azure.** The maintainer runs the real run, and the agent reads the output.

## How it is undone

Take the four new files and their tests out, put the instructions and the shape back into `measure.py`, and take the library out of `pyproject.toml` and `uv.lock`. Nothing in the cloud changes in this task.
