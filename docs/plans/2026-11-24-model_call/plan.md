# Task 4: the model call

**State:** planned on 2026-11-24. The maintainer said yes to the plan on the same day, with the three answers below. The bug report was then tested, and the maintainer chose on 2026-11-25 not to code around it. The tests are written.

It is the fourth task of [milestone 1](../2026-11-14-milestone_1_the_whole_path_once/plan.md).

## The goal

One small file in the app makes every call to the model. It asks for an answer in a fixed shape (structured output), sets how much the model thinks, gives up after a fixed time, and turns every way a call can fail into one clear error. The tests need no network and cost nothing.

After this task the app still does not call the model for a visitor. The two steps that use the call come in task 5, and the route that starts them in task 9.

## What is built

| File | What it holds |
|---|---|
| `backend/src/book_teller/model_call.py` | `make_model`: builds LangChain's model class `ChatOpenAI` from the settings. `ask_model`: sends instructions and a text, and returns the answer in the shape that the caller named, with the token counts and the seconds. `ModelCallError`: the one error, with its reason |
| `backend/src/book_teller/settings.py` | Reads the settings from environment variables: the address of the model service, the name of the deployment, the thinking setting, the timeout, the cap on output tokens |
| `backend/src/book_teller/measure.py` | A script for the maintainer, started by hand. It makes one real call for each thinking setting that is named, with the chapter and the script of the [probe](../2026-11-13-probe_planted_faults/plan.md), and prints a table: tokens in, tokens out, thinking tokens, seconds |
| `backend/tests/test_model_call.py` | The tests below, with a fake model service |
| `backend/pyproject.toml`, `backend/uv.lock` | Three libraries: see "New libraries" |
| `README.md` | How to run the measuring script, and which settings it needs |

**The call, in plain sight.** LangChain's model class has defaults that hide choices. This file names each one:

- **The Responses API,** by name (`use_responses_api=True`). OpenAI has two addresses that take a request, Chat Completions and the newer Responses. The class moves to Responses by itself once a thinking setting is given. Naming it means the code says what happens.
- **The strict shape,** by name (`method="json_schema"`, `strict=True`). The default of the class is another method, function calling, which does not force the shape.
- **The thinking setting** (`reasoning.effort`). Most output tokens of the probe were thinking: 4,992 of 5,913. So it is the first lever on cost and on time. It starts at `low`, and the measuring script shows what `low` and `medium` cost.
- **A timeout and the number of retries,** both written out: two retries, so at most three requests for one call. The library retries by itself on "too many requests" (status 429) and on server errors, with a growing wait.
- **A cap on output tokens.** A call cannot cost more than the cap. An answer that hits the cap is cut off. It is half a JSON text, so it fails the check of the shape and never passes as an answer.

**One error with a reason.** Whatever goes wrong, the caller gets a `ModelCallError` with one of these reasons: `timeout` · `too many requests` · `no permission` · `refused` (the model would not answer) · `wrong shape` · `service error`. The words of the library stay inside the error, so nothing is hidden.

**The login has no key.** The class receives a function that fetches a short-lived token from Azure when one is needed. On the maintainer's machine the token comes from the login of the Azure CLI. In the cloud it will come from the app's managed identity. No address and no name of a resource is written into this repository: both come from environment variables. They are read when a model is made, not when the app starts: the app in the cloud has none of them yet and must still start.

**The fake model service.** The tests hand the model class a fake HTTP layer: plain Python that takes the request which the library would send, keeps it, and gives a fixed answer back. So the tests read the real request, and the library's own code for retries and for reading the answer runs in the tests. Later tasks do not need it: they receive `ask_model` as a function and replace it with a function of a few lines.

## Checked first: the two bug reports

The plan of the milestone named two bug reports on LangChain's model classes.

| Report | What it says | On our path? |
|---|---|---|
| [41688](https://github.com/langchain-ai/langchain/issues/41688), open | With the Responses API and a strict shape given as a Pydantic class, an answer that is cut off by the token cap raises "Invalid JSON", and the fact "cut off" is lost | **Yes, and it is real.** Tested on 2026-11-25 with `langchain-openai` 1.8.5 and `openai` 3.58.0, with a fake answer and no network |
| [41807](https://github.com/langchain-ai/langchain/issues/41807), closed as not planned | With an older output format, streaming, and thinking items sent back to the model in a second request, the second request fails | **No.** One call sends nothing back |

**What is done about 41688: nothing in the code** (the maintainer, 2026-11-25). The reasons:

- **The impact is small.** The call fails either way. With the strict shape, the service promises valid JSON for every finished answer, so "Invalid JSON" means in practice that the answer was not finished.
- **The way around is worse than the bug.** It hands the shape over as a JSON schema and reads the status of the answer first. Tested: the library then repairs the half JSON and returns it as if it were whole, with no error. A cut-off answer could pass as a good one. On the normal path it cannot.
- **It would lean on an inner part of the `openai` library,** which can change without notice.

So a cut-off answer is a `wrong shape`, and the error keeps the library's words "Invalid JSON". One test holds this, with a comment that names the report. When the library is fixed, that test fails and says so. **One loss, accepted:** the token counts of a cut-off call are not returned, because the library raises before it gives them.

## Decided by the maintainer

| # | Question | Options | Chosen |
|---|---|---|---|
| 1 | Where does the fake sit in the tests of this file? | **A.** At the HTTP layer. The tests see the real request, so a hidden default of the library cannot pass unseen. Costs: the tests are longer, and it is not checked yet that the fake works with the current `openai` library · **B.** In place of the model object. Short and plain. Costs: no test sees the request; the strict shape and the thinking setting are checked by eye, once | **A** for this one file, and B if A does not work. Later tasks use B: they replace `ask_model` with a small function |
| 2 | Which API? | **A.** Responses, by name. What Microsoft's and OpenAI's pages name for thinking models. Costs: bug report 41688 is on this path · **B.** Chat Completions, as the probe used. Costs: the class leaves it by itself when the thinking setting is given as `reasoning` | **A** |
| 3 | When does the app in the cloud get its right to call the model? | **A.** In the task that first calls the model from the cloud. Costs: a missing right shows late · **B.** Now, as a role assignment in the Terraform file. Costs: nothing in the cloud uses it yet, so nothing can show that it works | **A** |

**Both kinds of fake are common.** LangChain's own pages teach a fake model object for unit tests, and a recorded HTTP call for integration tests (read on 2026-11-24). The usual recording tool saves a real request and its answer in a file. That file would hold the address of the Azure resource, so this task writes its fixed answers by hand. **They are then corrected from a real one** (the maintainer's idea): after the first real call, its answer is printed, the maintainer looks at it, and the hand-written answers of the tests are made to match its form. Nothing from it is saved unseen. The cases that cannot be made on demand, such as "too many requests", stay written from the documentation.

## New libraries

The maintainer installs them. Each is asked for here.

| Library | Why |
|---|---|
| `langchain-openai` (1.8.5 on 2026-11-24) | LangChain's model class for OpenAI models. It brings `langchain-core` and `openai` |
| `azure-identity` | The login with no key: it fetches the token |
| `pydantic` | Already installed, because FastAPI needs it. Now the app's own code names shapes with it, so it is named in `pyproject.toml` |

## What costs money, and what touches a permission

- **The measuring script makes real calls.** The one call of the probe cost about 1.3 US cents. Four to six calls: under 10 cents.
- **The maintainer's own login needs the right to call the model.** Being the owner of the resource does not give it. One role assignment, made once by hand with the Azure CLI. The command goes into [the setup guide](../../guides/setup-from-zero.md).

## Exit criteria

1. `uv run pytest` passes with no network, and the new tests were seen to fail first.
2. `ruff` and `mypy` pass, and a warning still fails the test run.
3. The maintainer saw one real call answer in the fixed shape, logged in with no key. The fixed answers of the tests have the form of that real answer.
4. The maintainer saw the real request once, as the library logs it: the Responses address, the strict shape, the thinking setting.
5. The measuring table exists for at least `low` and `medium`, and its numbers are written into this plan. The thinking setting and the timeout get their values from it.
6. The maintainer saw a real answer cut off, with the cap set to 200 tokens: the error said `wrong shape`, with the words "Invalid JSON" inside.
7. The app starts without any of the new settings: the page and `/health` answer, and the pipeline deploys as before.
8. No key, no address and no name of an Azure resource is in the repository.

## Test cases

In `backend/tests/test_model_call.py`, run by `pytest`, with the fake model service of `backend/tests/fake_model_service.py`:

1. The request goes to the Responses address, not to Chat Completions.
2. The request asks for the strict shape: the type is `json_schema`, `strict` is true, and the schema holds the fields of the shape that the caller named.
3. The request holds the thinking setting and the cap on output tokens from the settings.
4. The request holds the name of the deployment, the instructions and the text.
5. The token in a request is the one that the token function gave, and the function is asked again for the next request: a token is never fetched once and kept.
6. A good answer comes back as an object of the named shape, with tokens in, tokens out and thinking tokens as the service counted them, and the seconds.
7. An answer that was cut off raises `wrong shape`, with "Invalid JSON" in its words (bug report 41688).
8. An answer that is JSON but not in the shape raises `wrong shape`.
9. An answer in which the model refuses raises `refused`, with the model's words.
10. "Too many requests" on every try raises `too many requests`, after exactly three requests.
11. "Too many requests" once, then a good answer: the caller gets the answer, and two requests were made.
12. No answer within the timeout raises `timeout`, after three requests.
13. A refused login (401 or 403) raises `no permission`, and is not tried again.
14. An error of the service (500) raises `service error`, after three requests.
15. A request that the service does not accept (400) raises `service error`, with the service's words, and is not tried again.
16. The settings are read from the environment.
17. A missing setting stops with a sentence that names the environment variable. So does a setting that should be a number and is not.
18. The app's own tests still pass with none of the settings present.

Seen once by the maintainer, with the real model:

19. One real call, with the login of the Azure CLI.
20. The real request in the log of the library.
21. The measuring table.
22. A real answer cut off at 200 tokens.

## The order of the work

1. A branch for this task. First commit: this plan.
2. The maintainer installs the three libraries.
3. A test shows whether bug report 41688 is in the installed version. Done: it is.
4. The tests and the fake model service. They fail: the file does not exist.
5. `model_call.py` and `settings.py`. The tests pass.
6. The role assignment for the maintainer's login. The first real call, then the real request in the log.
7. `measure.py`, the table, and the values for the thinking setting and the timeout.
8. The review by a second agent, the fixes, the README.
9. The pull request and the merge.

## What could go wrong

- **A call that hangs is tried three times.** The library also tries again after a timeout. So one call can hold its caller for three times the timeout, and the timeout must be set with that in mind.
- **A warning from a new library fails every test,** because the test run treats a warning as an error. It happened: `langsmith`, which LangChain brings, uses a function that Python 3.14 calls outdated. That one warning is named in `pyproject.toml` and let through, with the reason beside it.
- **`mypy` in strict mode and the types of LangChain.** Some may need one line that tells `mypy` what a value is.
- **The token for the login can be asked for two audiences,** and Microsoft's pages and LangChain's page name different ones. The first real call shows which one the service takes.
- **Which thinking settings `gpt-5-mini` takes** is not checked. The measuring script reports a setting that the service refuses, and goes on with the next.
- **Azure's content filter** can stop a text before the model sees it. An old book can hold words that trip it. That would be a `refused` with its own sentence; it is not built until it is seen.
- **Retries multiply.** The library tries three times. A graph can try a step again too. Task 5 must count both.
- **The agent cannot reach Azure.** The maintainer runs every real call, and the agent reads the output.

## How it is undone

Take the four new files and the three libraries out again. The role assignment is deleted with one command. Nothing in the cloud changes in this task.
