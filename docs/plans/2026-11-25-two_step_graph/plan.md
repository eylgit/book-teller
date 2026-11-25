# Task 5: the graph of two steps

**State:** planned on 2026-11-25. The maintainer said yes to the plan on the same day, with the three answers below. The code is built, two real runs are made, and a second agent has reviewed the change. What was seen and what the review changed are at the end. Merged on 2026-11-25: the pipeline built the image with the new library and deployed it, and all seven exit criteria are met. A second, small pull request followed the merge, with this final state.

It is the fifth task of [milestone 1](../2026-11-14-milestone_1_the_whole_path_once/plan.md).

## The goal

One chapter goes in. Two steps run in a fixed order: the first writes the script of an episode from the chapter, the second checks that script against the chapter. Each step is one model call, made through the model call of [task 4](../2026-11-24-model_call/plan.md). LangGraph runs the two steps and carries the data from one to the next. The tests need no network and cost nothing.

After this task the app still does not call the model for a visitor. The guard on the checker's answer comes in task 6, and the route that starts a run in task 9.

## What is built

| File | What it holds |
|---|---|
| `backend/src/book_teller/write_step.py` | The instructions for the writer, and the shape of its answer, `Script`: a list of sentences. One sentence is one item, because the checker points at a sentence by its number |
| `backend/src/book_teller/check_step.py` | The instructions for the checker, and the shape of its answer, `Flags`: a list of faults. They move here from the measuring script and are completed: see "The checker's answer says what it means". Also the function that numbers the paragraphs of the chapter and the sentences of the script |
| `backend/src/book_teller/episode.py` | The graph: the state, the two nodes, the edges, the retry rule, and `build_graph`, which puts them together. `run_episode` runs it once. `picture` gives the graph as the text of a diagram |
| `backend/src/book_teller/tell.py` | A script for the maintainer, started by hand. It reads a chapter from a file, runs the graph with the real model, and prints the script, the faults that the checker flagged, and what each step cost. With `--picture` it asks no model and prints the picture of the graph |
| `backend/src/book_teller/measure.py` | Changed: it takes the instructions and the shape from `check_step.py`. It keeps no copy of its own |
| `backend/tests/test_episode.py`, `test_check_step.py`, `test_tell.py`, `fake_ask.py` | The tests below, and the fake "ask the model" that they hand in |
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

`build_graph` describes the nodes and the edges, and `compile()` turns the description into the thing that can run. `invoke` runs it once, from `START` to `END`, and returns the last state. LangGraph gives that answer the type "a dictionary of anything". So one function, `run_episode`, calls `invoke` and says that the answer is our state; the script and the tests use it.

**Each choice, written out:**

- **The state is a `TypedDict`:** a Python dictionary whose keys and types are named. It is the form that LangGraph's own pages use first.
- **The model is handed in, not held in the state.** `build_graph` receives one function, "ask the model". The real one is `ask_model` of task 4 with the model already inside. A test hands in a function of a few lines that gives fixed answers. No test of this task reaches the HTTP layer, except one: see test case 9.
- **Nothing is saved between the steps.** LangGraph can save the state after every step (its word: a checkpointer), so that a run can go on after a failure. That belongs to milestone 2. Here, when the second step fails, the script of the first step is lost, and the run must start again.
- **The graph tries a failed step once more** (the maintainer, 2026-11-25). A node gets a second try only when a retry rule is given for it (`retry_policy=` in `add_node`; LangGraph's page "Fault tolerance", read on 2026-11-25). Both nodes get the same rule, written out:
  - **Two tries, not three.** The model call already makes up to three requests by itself, so one step can make up to six. With three tries on the node it would be nine.
  - **Our own answer to "is this error worth a second try?".** Left alone, LangGraph tries again after every `ModelCallError`, so also after `no permission`, where a second try gives the same answer. (It refuses only a list of Python's own kinds of error, such as `ValueError` and `OSError`.) Our function says yes for three reasons of `ModelCallError`: `timeout`, `too many requests`, `service error`. It says no for `no permission`, `refused` and `wrong shape`.
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
| 2 | Does the graph try a failed step again? | **A.** No. The three tries of the model call are the only ones. Costs: a failure that outlasts those three tries ends the run, and the maintainer starts it again by hand · **B.** Yes, a retry rule on each node. Costs: up to nine requests for one step, and with the timeout of 60 seconds a step that hangs can hold the run for about nine minutes | **B**, with two tries in place of three: up to six requests, and about six minutes for a step that hangs. The agent had proposed A. The maintainer's reason: the graph should show LangGraph's own retry rule at work |
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
7d. The retry rule gives two tries.
7e. The picture that the library prints shows `write`, then `check`.

In `backend/tests/test_check_step.py`:

8. Every field of a flag has a description in the JSON schema of `Flags`.
9. Through the fake model service of task 4: the request that leaves for the model holds those descriptions.
10. Every kind of fault that the enum names is explained in the instructions, and the instructions explain no other. So the two cannot drift apart.
11. The paragraphs of a chapter are split at blank lines and numbered from 1, and so are the sentences of a script. The older test of the same thing, in the tests of the measuring script, stays beside it.

In `backend/tests/test_tell.py`:

12. A run prints the script, each flag and the cost of each step.
13. A call that fails prints one line with the reason, and the script ends with exit code 1.
14. A missing setting is named, and no call is made.

Kept as they are:

15. The five tests of the measuring script pass with the shape and the instructions of `check_step.py`. One fixed answer in them changed: its kind is a name now, not a number.
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
- **The retry rule waits before the second try** (by its default half a second, plus a random part of up to one second). The tests must not wait, so they hand in the same rule with the wait set to nothing.
- **How a failed node ends a run is read from the documentation, not seen yet.** Test cases 6 to 7b prove it after the install. If LangGraph wraps the error in one of its own, the plan is corrected and the maintainer decides.
- **The picture.** That the library prints the graph as text for a diagram, with no further library, is not verified. If it cannot, the README gets no picture, and exit criterion 4 is taken out with the maintainer's yes.
- **The writer may need more than the timeout.** One try has 60 seconds. The checker took 14.6 seconds for 1,639 tokens out. The first real run shows what the writer takes.
- **The checker's request changes** (descriptions, and names for the kinds if question 1 is A). The table of task 4 was measured with the old request. Its numbers stay as history.
- **The agent cannot reach Azure.** The maintainer runs the real run, and the agent reads the output.

## What was seen

**After the install,** with the installed library and no network: the error of a node leaves `invoke` as the same object, and LangGraph only adds a note that names the node · with the retry rule only the failed node runs again · a test can copy the rule with its wait set to nothing · the library prints the picture of the graph with no further library. No new warning came with the library.

**The first real run** (2026-11-25), with the chapter of the probe, about 3,200 words:

| Step | Tokens in | Tokens out | Of them thinking | Seconds |
|---|---|---|---|---|
| `write` | 4,024 | 1,787 | 64 | 18.2 |
| `check` | 6,182 | 718 | 704 | 6.2 |

Both steps answered at the first try, in the fixed shape. The writer gave 46 sentences. The checker flagged nothing.

What the run shows, and what it does not:

- **The writer is far inside the timeout** of 60 seconds for one try.
- **The writer hardly thinks** at the setting `low`: 64 of its 1,787 output tokens. Almost all of its output is the script. The checker is the other way round: 704 of 718.
- **The script reads badly aloud.** Nearly every sentence starts with "The author says" or "He says", and many sentences are long. The instructions asked for this by their own words: "Say whose ideas they are, such as 'the author says'". No test can see it.
- **"No flag" proves little.** The writer followed the chapter closely, and one model checked the work of the same model. Whether the checker finds real faults is measured with planted faults in task 11.

**The writer's instructions were mended once, and a second real run was made** (2026-11-25). The sentence that asked to say whose ideas they are went out. In came: short sentences of at most about 25 words, and the author named only now and then.

| Step | Tokens in | Tokens out | Of them thinking | Seconds |
|---|---|---|---|---|
| `write` | 4,069 | 2,041 | 64 | 16.9 |
| `check` | 6,647 | 979 | 832 | 7.8 |

- **The sentences are short now:** 116 of them. Few start with "the author says"; some now end with it.
- **The script is still not a short telling.** It follows the chapter nearly sentence by sentence, so it is not "a quarter to a third" of the chapter, as the instructions ask. Its words were not counted.
- **The checker flagged one fault,** of the kind `wrong_strength`: the script says "may injure" where the author says "may possibly be injurious". Its quote is in the chapter word for word, in the paragraph that it names.
- **Left so** (the maintainer chose one try). A good script needs its own work, with a way to measure it. This task is about the graph.

## How it is undone

Take the four new files and their tests out, put the instructions and the shape back into `measure.py`, and take the library out of `pyproject.toml` and `uv.lock`. Nothing in the cloud changes in this task.

## What the review changed

A second agent reviewed the change in a fresh session. It found no bug in the graph. It also changed the code in 53 small ways on a copy, to see which changes a test notices: 20 went unnoticed. The maintainer decided on each finding.

- **`service error` is wider than "a second try can help".** The model call gives that reason to everything else that goes wrong: also to a request that the service does not accept, and to a login that did not work. The node tries those again, for nothing. **Left so, and said** in the code and in the README (the maintainer). The other way, a reason of its own for such a request, changes the model call of task 4 and belongs to a later task.
- **No test ran the graph with its real retry rule.** Every test handed in the copy that does not wait. With LangGraph's own rule in its place, all tests passed. One test is new: it hands in nothing and switches off only the waiting.
- **The function that joins the graph to the real model had no test.** It is now `ask_with` in `tell.py`, and a test reads the request that it sends. `--picture` has a test too.
- **The picture in the README lacked five lines that the library prints.** It is now the whole output, and a test compares the two.
- **Three sentences promised too much:** what LangGraph tries again by itself, how long the rule waits, and the length of the second script. Corrected above.
- **The cost leaves out a try that failed.** Said in the code, in the script and in the README.
- **A line that holds only spaces did not end a paragraph.** It does now, with a test. The chapter of the probe has no such line, so its numbering is the same.
- **A chapter file that is not there** gave a long Python error. Now one line.
- **Two types were wider than needed.**
- **Tests added for what went unnoticed:** the descriptions of the two lists, the "0" for a fault with no sentence, the lines that `tell.py` prints for a flag, an error that is not of the model call.
- **Not taken:** a newer form of `invoke` that needs no `cast`. The plain form is the one in LangGraph's first examples. And no test for the wording of the instructions: a test cannot judge it.
