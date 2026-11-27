# Task 9a: the run, without a queue

**State:** planned on 2026-11-27. The maintainer answered the six questions on the same day: see "Decided by the maintainer". The app's code is built, and the cloud part is applied: see "What was seen". Not merged yet: the review by a second agent is next.

It is the first half of task 9 of [milestone 1](../2026-11-14-milestone_1_the_whole_path_once/plan.md). Task 9 was split on 2026-11-27: this half makes the page work, and task 9b moves the run out of the web app, behind a queue.

## The goal

Today a chapter is told only by a script that the maintainer starts by hand, `tell.py`. The page shows one sentence and can do nothing.

After this task:

- the owner pastes a chapter into the page, gives the owner's key, and presses "Tell";
- the web app answers at once with the number of the run, and does the run itself after that answer, in the background;
- the page asks "how far?" every two seconds and shows a progress line: waiting, writing, checking, done or failed;
- then it shows the script, each fault with the words of the chapter that prove it, the faults that are not proven, and the tokens and the seconds;
- three guards stand in front of a run: the owner's key, a limit on the length of the pasted text, and a cap on the runs of one day;
- only the owner can read a run: "how far?" needs the key too;
- the app on Azure may call the model: until now only the maintainer's own login may.

**No queue and no worker yet.** The web app does the work. This has one known weakness until task 9b: a run dies with the web app. After a deploy or a crash in the middle of a run, the run stays "writing" or "checking" for ever.

## The path of one run, in this task

```
 Browser                     Web app (FastAPI)                         Model
     |-- 1. chapter + key ------>|                                        |
     |                           |-- 2. the three guards                  |
     |                           |-- 3. new run ------> DATABASE          |
     |<-- 4. "run 17" -----------|                                        |
     |                           |-- 5. write the script ---------------->|
     |                           |-- 6. status "checking" --> DATABASE    |
     |                           |-- 7. check the script ---------------->|
     |                           |-- 8. the guard of the faults (plain code)
     |                           |-- 9. result -------> DATABASE          |
     |-- 10. "how far?" + key -->|-- reads the DATABASE                   |
     |<-- the status, then the result                                     |
```

Steps 5 to 9 happen after answer 4 has left. Step 10 happens many times, beside them.

## The words

| Word | What it is |
|---|---|
| **Route** | One address of the web app together with one function: a request to that address runs that function. Today the app has two: `/` and `/health` |
| **Status code** | The number at the start of every HTTP answer that says how it went: 200 is "fine", 404 is "not found". This task uses six more, listed under "The routes" |
| **Background task** | FastAPI's way to do work after the answer has been sent. The route hands FastAPI a function, the answer leaves, and then FastAPI runs the function, in a thread of the same program |
| **The owner's key** | A long random text that only the owner knows. It stands in for a login until a later milestone has one. The page sends it with the request, and the app compares it with its own copy |
| **Azure Key Vault** | Azure's safe for secrets. A secret has a name and a value; who may read it is decided by role assignments, like everything else in this cloud |
| **Key Vault reference** | A setting of the app on Azure that holds no value, only the address of a secret in the vault. Azure fetches the value with the app's managed identity and hands it to the container as an environment variable. So the code reads the key as it reads every other setting |

## The routes

| Route | What it does | It answers |
|---|---|---|
| `POST /runs` | Starts a run. The body is JSON with one field, `chapter`. The key travels in the header `Authorization: Bearer …`, the usual place | **202** "accepted", with the number of the run: the work is not done yet · **401** no key, or a wrong one · **422** the chapter is empty or too long · **429** the cap of the day is reached · **503** the app is not set up: it has no key, no settings of the model, or no database |
| `GET /runs/{number}` | "How far?" It reads the run from the database. It needs the key too | **200** with the status, and with the script, the faults and the sums when they are there · **401** no key, or a wrong one · **404** no run has this number · **503** the app has no key or no database |

The app checks in this order: is a key set up at all, is the key right, is the chapter within the limit, is the cap free, are the model and the database set up. Only then a row is written.

## The three guards

- **The owner's key.** The app holds its copy in the environment variable `BOOK_TELLER_OWNER_KEY`. The two keys are compared with `secrets.compare_digest`, a function of Python that takes the same time for a right and for a wrong key, so the time of the answer tells an attacker nothing. **With no key set up, every start of a run is refused:** the app never falls open. On Azure the key lives in Key Vault: see "The key on Azure".
- **The limit on the pasted text.** At most 5,000 words, counted as the pieces between spaces, and at most 40,000 characters, so that one endless "word" cannot pass. The chapter of the probe has 3,190 words and 18,114 characters. It is the cheapest guard: a long text is refused before it costs anything.
- **The cap of the day.** Before a run starts, the app counts the runs that were started on this day, and refuses the new run when there are 20. Every row counts, also a run that failed: it has cost money too. The day is the day of the clock UTC. The number is a setting, `BOOK_TELLER_RUNS_A_DAY`. A count is simple, and nothing slips past it. It is not money: 20 runs of the size of the probe's chapter cost about 20 to 40 US cents, and a run of the longest text that the limit allows costs more. An Azure budget cannot do this job: it only sends a notice, and its numbers are 8 to 24 hours late.

## The key on Azure

The usual practice is that a secret is not written into a file of settings, and not into the description of the app. It rests in a store that is made for secrets, and the app is given the right to read it.

1. **Terraform makes the key:** 48 random characters, from the plug-in `hashicorp/random`. Terraform itself has no way to make a random secret, and a key that a person types must be handed to Terraform again at every later plan.
2. **Terraform puts it into Azure Key Vault,** as the secret `owner-key`.
3. **The app's settings hold only the address of that secret:** a Key Vault reference. Azure fetches the value with the app's managed identity, which has the role "Key Vault Secrets User" on the vault, and hands it to the container as the environment variable `BOOK_TELLER_OWNER_KEY`.
4. **The owner reads the key** from the vault with one `az` command. The person who runs Terraform has the role "Key Vault Secrets Officer" there, which may write and read secrets.

**What this does not solve:** the key is also in Terraform's state file, which stays on the maintainer's machine and never goes into git. And the vault has a public address, like the database: the login is the wall.

## What is built

| File | What it holds |
|---|---|
| `backend/src/book_teller/job.py` | New. One function, `do_run`: "do run number N". It reads the chapter of the run, runs the graph, saves the status after each step, and saves the result or the failure. It knows nothing of the web. The worker of task 9b calls this same function |
| `backend/src/book_teller/episode.py` | The graph is asked to report each step when it ends (LangGraph's stream of updates), so `do_run` can save "checking" between the writer and the checker. The graph itself does not change |
| `backend/src/book_teller/main.py` | The routes above. One small function decides how a run is started: today as a background task, in task 9b as a message. The parts that the routes need (the database, "ask the model", the settings) are handed in when the app is made, so a test hands in its own |
| `backend/src/book_teller/runs.py` | One more read: how many runs were started on this day |
| `backend/src/book_teller/settings.py` | The owner's key, and the cap of the day |
| `backend/src/book_teller/static/index.html` | The form, the progress line and the result. Plain HTML, Bootstrap, and a short script inside the page. The page asks for the key when it has none, keeps it in the browser for two days, and forgets it at once when the app answers 401. Every text of the model is put into the page as text, never as HTML: a script that came in with such a text could read the key |
| `infra/main.tf`, `infra/tests/cloud.tftest.hcl` | The app's right to call the model · the two settings of the model · the vault, the key in it, the two roles on it, and the Key Vault reference of the app |
| `scripts/smoke_test.sh` | One more question: without a key, the start of a run is refused |
| `backend/tests/` | The tests below |
| `README.md`, `docs/guides/setup-from-zero.md`, the plan of the milestone | How to make a run on the page, the guards and their limits, what is made by hand, and task 9 as 9a and 9b |

**On the maintainer's machine,** a real run is made with the web app started on the machine itself, beside the database of Docker Compose. The app inside Docker Compose has no Azure login, so there "Tell" answers 503.

**The model resource** was made by hand, before this repository had a Terraform file, and it stays so. Terraform only gives the app a role on it. Its id, its address and the name of its deployment reach Terraform as variables that are not in git.

## Decided by the maintainer

On 2026-11-27.

| # | Question | Options, and what each costs | Chosen |
|---|---|---|---|
| 1 | **Where does the owner's key live on Azure?** | **A. In Azure Key Vault:** see "The key on Azure". Costs: five more things in the Terraform file · a role needs minutes to take effect, so the first apply can stop with "forbidden" and must be run again · the key is also in Terraform's state file · one more plug-in of Terraform. · **B. As a secret of the app itself,** in Azure Container Apps. Costs: two things in the file, not five; but Microsoft's page on secrets advises against it for production, and task 10 brings a second secret | **A** |
| 2 | **Who may read a run?** | **A. Only the owner:** "how far?" needs the key too. Costs: somebody who opens the link sees the form and nothing of the product at work. · **B. Everybody,** and the page shows the newest finished run to every visitor. Costs: whatever the owner pastes becomes public · anybody can make the app read its database · run numbers count up, so a visitor can read every run | **A.** Not the agent's proposal, which was B |
| 3 | **How does the cap of the day count?** | **A. In money:** the tokens of the day, times a price, against a cap in US dollars. Costs: two prices as settings · a run that is still running counts as 0 · a try that failed is not counted. · **B. In runs:** at most 20 starts a day. Costs: the cap is not in money | **B:** "keep it simple". Not the agent's proposal, which was A |
| 4 | **"Service error" stays wide?** | Since task 5, `service error` is the reason for everything that has no reason of its own. So a request that the service does not accept, and a login that did not work, are tried a second time for nothing. **A. Leave it, and keep saying it in the README.** · **B. Narrow it now:** two more reasons, with their tests | **A** |
| 5 | **How does the page remember the key?** Asked by the maintainer: the page should ask for the key once, and then not again for about two days | **A. Typed at each visit.** The page holds the key only while it is open. Costs: typed again after every reload. · **B. The page keeps the key in the browser,** in `localStorage`, the small store that a browser gives each site, together with the date; after two days the page throws it away. Costs: the key itself rests in the browser, where any script that runs in the page could read it · the two days are kept by the page, not by the server: the key itself stays valid. · **C. A login route that sets a cookie** with a signed ticket and an end time, which scripts cannot read. Costs: a login route, a logout and their tests, for a key that the login of a later milestone replaces | **B.** The key guards little: 20 runs a day, and the reading of scripts |
| 6 | **Four yeses** | The plug-in `hashicorp/random` for Terraform · the role "Cognitive Services OpenAI User" on the model resource for the app's identity, and a `terraform apply` by the maintainer · real runs: one on the maintainer's machine and one or two on Azure, under 5 US cents together · the vault | Yes |


**Taken by the agent, because they are small. Say so if one is wrong:**

- No new Python library. FastAPI brings the background task.
- The pages that document the API (`/docs`) stay off, as since task 1.
- One pull request. The cloud part is applied by the maintainer before the merge, as in tasks 3 and 8: the old code does not read the new settings, so nothing breaks in between.

## Exit criteria

1. `uv run pytest` passes with the local database running, and the new tests were seen to fail first.
2. `ruff` and `mypy` pass, and a warning still fails the test run.
3. On the maintainer's machine: one real run from the page. The maintainer saw the progress line change, and then the script, the faults and the sums.
4. On the maintainer's machine: without the key, and with a wrong key, "Tell" is refused. With the cap set to 0, it is refused with the words of the cap.
5. On Azure: `terraform apply` ran, and a second `terraform plan` says "No changes".
6. After the merge: one real run on the live page, started with the key from the vault. So the app called the model as its managed identity, with no key of the model anywhere.
7. On the live page, a start without the key is refused.
8. The maintainer has read line by line, before the merge: the check of the key in `main.py`, and the parts of `main.tf` that hold the key. This is the merge rule for a change to secrets.
9. No key, no token and no address of the model or of the app is in the repository.

## Test cases

Run by `pytest`. The tests call the app in memory and hand it a fake "ask the model", so no test asks a model. Cases 1 to 17 need the local database.

In `backend/tests/test_web_runs.py`:

1. With the right key and a chapter, `POST /runs` answers 202 with a number, and a run with this chapter is in the database.
2. After the background work, `GET /runs/{number}` gives the status `done`, the sentences of the script in order, each fault with "proven" or with what is wrong with it, and the sums of the tokens and the seconds.
3. With no key, and with a wrong key: 401, no row is written, and the model is never asked.
4. When the app has no key set up: 503 for every start, whatever key is sent.
5. An empty chapter, and one of only spaces: 422.
6. A chapter of 5,000 words passes. One of 5,001 words is refused with 422, and the answer names the limit. A chapter of over 40,000 characters is refused too.
7. When 20 runs were started on this day: 429, no row, and the model is never asked. With 19, the run starts. The runs of yesterday do not count. A cap of 0 refuses every run.
8. Without the settings of the model: 503, and no row is written.
9. `GET` for a number that no run has: 404. For a number that is no number: 422.
10. A run whose checker fails for good: the status is `failed`, the answer holds the reason, and the cost of the writer is saved.
11. `GET /runs/{number}` with no key, and with a wrong key: 401, and the answer holds nothing of the run. A wrong key gets 401 for a number that no run has too, so the answer does not tell which numbers exist.
12. No answer of the app holds the owner's key.

In `backend/tests/test_job.py`:

13. While the writer is asked, the status in the database is `writing`. While the checker is asked, it is `checking`. The fake "ask the model" reads the row at the moment it is asked.
14. A finished run is saved as `tell.py --save` saves it: the same script, faults and sums.
15. A failure that is not a failed model call, such as a bug in our own code, marks the run as `failed`. The run does not stay `writing`.
16. `do_run` for a number that no run has is an error, and asks no model.

In `backend/tests/test_runs.py`:

17. The count of the day holds every run that was started today: waiting, running, done or failed. It holds none of an earlier day.

In `backend/tests/test_episode.py`:

18. The steps are reported in their order: write, check, guard. The last state is the same as before this task.

In `backend/tests/test_database.py` (the settings):

19. The cap has a default, 20. A value that is no whole number is an error that names its environment variable. An owner's key of only spaces counts as no key.

In `backend/tests/test_app.py`:

20. The page has the form: a field for the chapter, a field for the key, and the button. It still loads nothing without a checksum.

In `infra/tests/cloud.tftest.hcl`, run by `terraform test`:

21. The app's identity has the role "Cognitive Services OpenAI User" on the model resource.
22. The app gets the address of the model and the name of the deployment as settings.
23. The owner's key reaches the app by the name of a secret, never as a plain value. The secret is a Key Vault reference that uses the app's identity. The vault gives rights by roles, and the app's identity has the role "Key Vault Secrets User" on it.

In `scripts/smoke_test.sh`:

24. The image alone, with no setting: `POST /runs` is refused, and the app still answers `/health`.

Kept as they are: all tests of tasks 1 to 8.

Seen once by the maintainer: exit criteria 3 to 8. The script inside the page has no test of its own: the maintainer sees it work.

## The order of the work

1. A branch for this task. First commit: this plan, and task 9 as 9a and 9b in the plan of the milestone.
2. The tests of the app. They fail: the new modules do not exist.
3. `job.py`, the routes, the guards, the page. The tests pass.
4. One real run on the maintainer's machine.
5. The cloud: the tests of `main.tf` first, then the file, then `terraform apply` by the maintainer.
6. The review by a second agent, the fixes, the README and the guide.
7. The pull request and the merge. Then one real run on the live page.

## What could go wrong

- **Azure stops the app in the middle of a run.** With zero copies when idle, Azure stops the last copy 300 seconds after the last request (Microsoft's page on scaling, dated 2026-05-19). The page asks every two seconds, so an open page keeps the app alive, and a run takes about 30 seconds. Not verified: whether work in the background alone, with no request, keeps a copy alive. If the owner closes the page and the run is slow, the run can die. Task 9b ends this.
- **A run that dies stays "writing".** The known weakness above. The page shows it as running for ever.
- **The first apply stops with "forbidden"** at the secret, because the maintainer's new role on the vault has not taken effect yet. A second apply goes on from there.
- **The Key Vault reference fails,** and the new version of the app does not start. Then the old version keeps the visits, as with a failed migration. The names of the fields were read in the plug-in's pages of today, not of the version 5.13.0 that this repository uses; `terraform validate` shows it.
- **The app's role on the model has not taken effect** at the first run on Azure: the run fails with "no permission". Wait a few minutes and start a new run.
- **The key rests in the owner's browser** for two days: question 5. On a shared computer, the owner presses "Forget the key".
- **A very large request** is read whole before the limit on the text is checked. Nothing limits the size of a request yet.
- **The agent cannot reach a database, Docker or Azure.** The maintainer runs the tests of cases 1 to 17, the real runs and the apply, and the agent reads the output.

## What was seen

On 2026-11-27.

**On the maintainer's machine.** All tests passed with the local database, and the new ones had failed first: four test files could not be loaded, because the names that they import did not exist. The maintainer made a real run from the page, with the web app started on the machine itself, and tried the wrong key.

**Not as the plan said:**

- The tests of the settings are in a file of their own, `test_settings.py`.
- Two tests were written with the code, not before it: two keys are compared without an error when they hold a letter outside ASCII, and a database that cannot be reached answers 503 without its address.
- The real "ask the model", `ask_with`, moved from `tell.py` to `job.py`, so that the web app does not load a script.
- The subscription id is a variable of `main.tf` now, and every value of the maintainer's own is in one file, `infra/terraform.tfvars`. Before, two of them were variables of the shell that had to be set again in every new terminal.
- Two older checks of the cloud tests were rewritten. "The app holds no secret" became "the app has one secret, with no value, that points to the vault". "Exactly five settings, none from a secret" became "seven plain settings, and one that names the secret".

**On Azure.** The plan listed six things to add and one to change, and nothing to destroy. The apply made them at the first try, and a new plan said "No changes". The app got its new settings while it still ran the code of before this task, which does not read them.

## How it is undone

Take the routes, `job.py` and the form out; the page is the one sentence again. Take the vault, the roles and the new settings out of `main.tf` and apply. No table changes in this task, so the database needs nothing. The rows of the runs that were made stay.
