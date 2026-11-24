# Task 4: the model call

**State:** planned on 2026-11-24. The maintainer said yes to the plan on the same day, with the three answers below. Nothing is built.

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
- **The shape is checked in two steps.** The service gets the shape as a JSON schema, made from the Pydantic class that the caller named. When the answer comes, the file reads its status first. Only a finished answer is then checked by Pydantic, and the caller gets an object of that class.
- **A cap on output tokens.** A call cannot cost more than the cap. An answer that hits the cap is cut off and must not be read as an answer.

**One error with a reason.** Whatever goes wrong, the caller gets a `ModelCallError` with one of these reasons: `timeout` · `too many requests` · `no permission` · `refused` (the model would not answer) · `cut off` (the cap on output tokens was reached) · `wrong shape` · `service error`.

**The login has no key.** The class receives a function that fetches a short-lived token from Azure when one is needed. On the maintainer's machine the token comes from the login of the Azure CLI. In the cloud it will come from the app's managed identity. No address and no name of a resource is written into this repository: both come from environment variables. They are read when a model is made, not when the app starts: the app in the cloud has none of them yet and must still start.

**The fake model service.** The tests hand the model class a fake HTTP layer: plain Python that takes the request which the library would send, keeps it, and gives a fixed answer back. So the tests read the real request, and the library's own code for retries and for reading the answer runs in the tests. Later tasks do not need it: they receive `ask_model` as a function and replace it with a function of a few lines.

## Checked first: the two bug reports

The plan of the milestone named two open bug reports on LangChain's model classes. Both were read on 2026-11-24.

| Report | What it says | On our path? |
|---|---|---|
| [41688](https://github.com/langchain-ai/langchain/issues/41688), open | With the Responses API, a strict shape given as a Pydantic class, and an answer cut off by the token cap, the library raises "Invalid JSON" and the fact "cut off" is lost | **Yes.** The way around named in the report: hand the shape over as a JSON schema, read the status of the answer first, and only then check the shape with Pydantic. Test case 6 holds this |
| [41807](https://github.com/langchain-ai/langchain/issues/41807), closed as not planned | With an older output format (`v0`), streaming, and thinking items sent back to the model in a second request, the second request fails | **No.** One call sends nothing back. The file names the newer format (`responses/v1`) all the same |

## Decided by the maintainer

| # | Question | Options | Chosen |
|---|---|---|---|
| 1 | Where does the fake sit in the tests of this file? | **A.** At the HTTP layer. The tests see the real request, so a hidden default of the library cannot pass unseen. Costs: the tests are longer, and it is not checked yet that the fake works with the current `openai` library · **B.** In place of the model object. Short and plain. Costs: no test sees the request; the strict shape and the thinking setting are checked by eye, once | **A** for this one file, and B if A does not work. Later tasks use B: they replace `ask_model` with a small function |
| 2 | Which API? | **A.** Responses, by name. What Microsoft's and OpenAI's pages name for thinking models. Costs: bug report 41688 is on this path · **B.** Chat Completions, as the probe used. Costs: the class leaves it by itself when the thinking setting is given as `reasoning` | **A.** The bug report is checked first, by a test, once the library is installed. If the bug is there, the maintainer decides again |
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
6. The maintainer saw a real answer cut off, with the cap set to 200 tokens, and the error said `cut off`.
7. The app starts without any of the new settings: the page and `/health` answer, and the pipeline deploys as before.
8. No key, no address and no name of an Azure resource is in the repository.

## Test cases

In `backend/tests/test_model_call.py`, run by `pytest`, with the fake model service:

1. The request goes to the Responses address, not to Chat Completions.
2. The request asks for the strict shape: the type is `json_schema`, `strict` is true, and the schema holds the fields of the shape that the caller named.
3. The request holds the thinking setting and the cap on output tokens from the settings.
4. The request holds the name of the deployment, the instructions and the text.
5. A good answer comes back as an object of the named shape, with tokens in, tokens out and thinking tokens as the service counted them, and the seconds.
6. An answer that was cut off raises `cut off`, not "Invalid JSON" (bug report 41688).
7. An answer in which the model refuses raises `refused`.
8. An answer that is JSON but not in the shape raises `wrong shape`.
9. "Too many requests" on every try raises `too many requests`, after exactly three requests.
10. "Too many requests" once, then a good answer: the caller gets the answer, and two requests were made.
11. No answer within the timeout raises `timeout`.
12. A refused login (401 or 403) raises `no permission`, and is not tried again.
13. The token in the request is the one that the token function gave, and the function is asked again for a later call: a token is never fetched once and kept.
14. A missing setting stops `make_model` with a sentence that names the environment variable.
15. The app's own tests still pass with none of the settings present.

Seen once by the maintainer, with the real model:

16. One real call, with the login of the Azure CLI.
17. The real request in the log of the library.
18. The measuring table.
19. A real answer cut off at 200 tokens.

## The order of the work

1. A branch for this task. First commit: this plan.
2. The maintainer installs the three libraries.
3. A test shows whether bug report 41688 is in the installed version: a fake answer that is cut off, with no way around.
4. The tests and the fake model service. They fail: the file does not exist.
5. `model_call.py` and `settings.py`. The tests pass.
6. The role assignment for the maintainer's login. The first real call, then the real request in the log.
7. `measure.py`, the table, and the values for the thinking setting and the timeout.
8. The review by a second agent, the fixes, the README.
9. The pull request and the merge.

## What could go wrong

- **The fake HTTP layer and the current `openai` library.** The library changed its HTTP library in version 3. If the fake cannot be handed in, question 1 falls back to B.
- **A warning from a new library fails every test,** because the test run treats a warning as an error. Then the one warning is named and let through, with the reason beside it.
- **`mypy` in strict mode and the types of LangChain.** Some may need one line that tells `mypy` what a value is.
- **The token for the login can be asked for two audiences,** and Microsoft's pages and LangChain's page name different ones. The first real call shows which one the service takes.
- **Which thinking settings `gpt-5-mini` takes** is not checked. The measuring script reports a setting that the service refuses, and goes on with the next.
- **Azure's content filter** can stop a text before the model sees it. An old book can hold words that trip it. That would be a `refused` with its own sentence; it is not built until it is seen.
- **Retries multiply.** The library tries three times. A graph can try a step again too. Task 5 must count both.
- **The agent cannot reach Azure.** The maintainer runs every real call, and the agent reads the output.

## How it is undone

Take the four new files and the three libraries out again. The role assignment is deleted with one command. Nothing in the cloud changes in this task.
