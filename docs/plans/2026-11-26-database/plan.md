# Task 8: the database

**State:** planned on 2026-11-26. The maintainer said yes to the plan on the same day, with the five answers below. The code is built, the database server on Azure is made, and a second agent has reviewed the change: see "What was seen" and "What the review changed". Not merged yet, so the app on Azure has not used its database.

It is the eighth task of [milestone 1](../2026-11-14-milestone_1_the_whole_path_once/plan.md).

## The goal

Today a run lives only as long as the script `tell.py` runs: the script, the faults and the cost are printed, and then they are gone. In [task 9](../2026-11-14-milestone_1_the_whole_path_once/plan.md) a worker makes the run in the background, and the page asks "how far?". The two are different programs, so the run must be kept where both can reach it: in a database.

After this task:

- two tables exist, `runs` and `faults`, made by a migration (a file that changes the tables, kept in git);
- a small file of functions saves a run and reads it back;
- the database runs on the maintainer's machine, beside the app, and on Azure;
- on Azure the app logs in to it with its managed identity. No password exists.

The app still has no route that starts a run. That is task 9. In this task the tables are used by `tell.py --save` and by the tests.

## The words

| Word | What it is |
|---|---|
| **PostgreSQL** | The database. A relational database with SQL, like MySQL |
| **psycopg** | The driver: the library that speaks PostgreSQL's network language for Python |
| **SQLAlchemy** | The ORM (object-relational mapper): a library that maps a table to a Python class and a row to an object, and writes the SQL. Each table is written once, as a class, and the type checker then knows every column |
| **Alembic** | The migration tool of SQLAlchemy's makers. Each change of the tables is one numbered file with two functions: one makes the change, one takes it back. A table in the database, `alembic_version`, holds the number of the last file that ran |

## The tables

Written here as the SQL that the first migration runs. The ORM classes in `tables.py` say the same, and a test compares the two.

```sql
CREATE TABLE runs (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status          text        NOT NULL DEFAULT 'waiting'
                    CHECK (status IN ('waiting', 'writing', 'checking', 'done', 'failed')),
    chapter         text        NOT NULL,
    -- The script, as a JSON list of its sentences: ["First.", "Second."].
    -- NULL until the writer has answered.
    script          jsonb,
    -- Why a failed run failed, in the words of the model call, such as
    -- 'timeout'. NULL for every other status.
    failure         text,
    -- The sums over the model calls of the run that answered.
    tokens_in       integer     NOT NULL DEFAULT 0,
    tokens_out      integer     NOT NULL DEFAULT 0,
    thinking_tokens integer     NOT NULL DEFAULT 0,
    model_seconds   double precision NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now(),
    -- When the run became 'done' or 'failed'.
    finished_at     timestamptz
);

CREATE TABLE faults (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          bigint  NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    -- The place in the checker's list, from 1.
    position        integer NOT NULL,
    -- What the checker said.
    sentence        integer NOT NULL,   -- 0: no sentence holds the fault
    kind            text    NOT NULL
                    CHECK (kind IN ('wrong_fact', 'wrong_concept', 'wrong_example',
                                    'wrong_conclusion', 'wrong_strength', 'left_out')),
    paragraph       integer NOT NULL,
    quote           text    NOT NULL,
    reason          text    NOT NULL,
    -- What the guard said.
    found_in        integer NOT NULL,   -- the paragraph that holds the quote; 0: none
    sentence_exists boolean NOT NULL,
    UNIQUE (run_id, position)
);
```

A fault is proven when `found_in > 0 AND sentence_exists`. It is not stored a second time.

**Why these choices:**

- **The script is one `jsonb` value, not a table of sentences.** It is always written whole and read whole. A fault names a sentence by its number in the list.
- **The token counts are sums on the run, not a table with a row for each model call.** The page shows the cost of a run, and the daily money cap of task 9 adds up the runs of a day. The detail of each call goes to the tracing of task 10.
- **`status` and `kind` are `text` with a `CHECK`, not PostgreSQL's own `ENUM` type.** A new value is then one changed line in a migration. The database still refuses a value that is not in the list, and a test holds the two lists against the lists in the code.
- **`UNIQUE (run_id, position)`** also gives the index for "the faults of this run". PostgreSQL makes no index for a foreign key by itself.
- **The cost in money is not stored.** It is counted from the tokens and a price when it is shown, so a new price does not make old rows wrong.

**Not in the tables yet, on purpose:** the owner of a run (one owner until there is a login) · the request ID (task 10) · the results of the planted-fault test (task 11). Each comes as a migration of its own.

## What is built

| File | What it holds |
|---|---|
| `backend/src/book_teller/tables.py` | New. The two tables as ORM classes |
| `backend/src/book_teller/database.py` | New. It makes the connection to the database, from the settings. With the Azure login, a fresh token is asked for every new connection and handed over as the password |
| `backend/src/book_teller/runs.py` | New. A new run · set its status · save the result of a finished run (the script, each fault with the guard's answer, the sums) · mark a run as failed, with the reason · read a run with its faults |
| `backend/src/book_teller/settings.py` | The settings of the database: host, name of the database, user, and which login |
| `backend/alembic.ini`, `backend/src/book_teller/migrations/` | New. Alembic's settings and the first migration. The migrations are a part of the app's code, so they are in the image wherever the code is |
| `backend/src/book_teller/migrate.py` | New. Run the migrations, take them back, and compare the tables with the ORM classes. The start of a container and the tests both use it |
| `backend/src/book_teller/tell.py` | A new option, `--save`: the run is also written to the database, and its number is printed. Without it, the script touches no database |
| `backend/src/book_teller/start.py`, `backend/Dockerfile` | New: what a container runs at its start. When the settings of the database are there, it runs the migrations first and then starts the app. Without them the app starts as before. If a migration fails, the app does not start. The Dockerfile names this file as its start command |
| `compose.yaml` | A second service, `db`: PostgreSQL 18, named by its digest, with one volume for its data. It takes no password and listens only on this machine |
| `azure-pipelines.yml`, `scripts/smoke_test.sh` | The pipeline starts a PostgreSQL before the tests. The smoke test starts the app with its database and asks whether the tables are there |
| `infra/main.tf`, `infra/tests/cloud.tftest.hcl` | The database server on Azure, one database, its logins, one firewall rule, and the settings that the app gets |
| `backend/tests/` | The tests below |
| `README.md`, `docs/guides/setup-from-zero.md` | How to start the database, how to run the tests, what is made by hand |

## The database on Azure

Azure Database for PostgreSQL, flexible server, in UK South: PostgreSQL 18, the smallest size (B1ms, burstable), 32 GB, backups kept for 7 days.

- **No password.** The login with a password is switched off; only logins of Microsoft Entra work. The app asks Azure for a token as its managed identity and sends it where a password would go. A token lives for a limited time, so the code asks for a fresh one for every new connection.
- **The network.** The server has a public address and one firewall rule: "allow Azure services". The app has no fixed address of its own, and a private network starts a monthly fee, so the rule cannot be narrower. The price: a machine of any Azure customer can reach the login door. The login is the wall.
- **Where the settings are.** None of them is a secret: the address of the server, the name of the database, the name of the login. On the maintainer's machine they are in `backend/.env`, which git does not see. On Azure there is no such file: Terraform writes them into the description of the app, and Azure hands them to the container as environment variables.
- **Nothing private in the file.** The maintainer's own login name is a Terraform variable that comes from the shell, like the subscription id. The address of the server reaches the app as a setting, from Terraform.

## Decided by the maintainer

On 2026-11-26. Every question was answered as the agent had proposed. Questions 3 and 4 take the simple form on purpose: the app is an administrator of its database and runs its own migrations. The usual practice of a team is narrower: one login for the app that may only read and write rows, and a second one, used only at a deploy, that may change tables. A later milestone narrows it.

| # | Question | Options, and what each costs | Chosen |
|---|---|---|---|
| 1 | **Are the tables right?** | See "The tables", and the three choices under it that could go the other way: the script as `jsonb` or as a table of sentences · sums on the run or a row for each model call · `text` with `CHECK` or `ENUM` | As written |
| 2 | **Which database do the tests use?** | **A. A real PostgreSQL,** the `db` service of Docker Compose; the pipeline starts the same image. The tests run the real migration on it. Costs: `uv run pytest` needs a running database, so "run the tests" gets a step before it; a test run without the database fails, it does not skip; the agent cannot reach a database from its sandbox, so the maintainer runs these tests. · **B. SQLite in memory,** a small database that ships with Python. Costs: the tests then prove the code on a database that the product never uses. SQLite has no `jsonb`, takes a wrong type without a word, and cannot run the migration as PostgreSQL does. The first real proof would be the deploy | **A** |
| 3 | **Who may log in to the database on Azure?** | **A. Two administrators, both written in the Terraform file:** the app's identity and the maintainer. Nothing is made by hand. Costs: the app can do more than it needs: an administrator can drop the database and make other logins. A later milestone narrows it. · **B. The maintainer is the administrator; the app gets a login of its own with only the rights that it needs.** That login is made with one SQL statement, by hand, by the administrator. Costs: a step that is not in the files; the maintainer needs a firewall rule for the own address first; and the app then may not change tables, so see question 4 | **A** |
| 4 | **When do the migrations run on Azure?** | **A. Each time a container starts,** before the app. A migration that already ran is skipped. Costs: a start from zero copies takes a little longer; the app's login must be allowed to change tables; with two copies at once, two could start the same migration (today: at most one copy). A migration that fails stops the new version from starting, the deploy step sees it, and the old version keeps the visits. · **B. By hand, from the maintainer's machine,** before a merge that needs it. Costs: a step that can be forgotten, and then the new code meets the old tables. · **C. As a step of the pipeline.** Costs: the pipeline's login needs rights in the database too, and a second place holds the settings of the database | **A** |
| 5 | **Three yeses** | The new libraries: `sqlalchemy` 2.1.9, `alembic` 1.20.1 and `psycopg` 3.3.9 with its ready-built part (`psycopg[binary]`) · the cost of the server: about £13.64 a month from the day of the first `terraform apply`, used or not: about £10.44 for the machine (730 hours at £0.0143) and £3.20 for the disk (32 GB at £0.10), from Azure's price list, read on 2026-11-14 · one real run of `tell.py --save`, under 5 US cents | Yes |

**Taken by the agent, because they are small. Say so if one is wrong:**

- The local database takes no password (`trust`). It listens only on the maintainer's machine. So this repository still holds no password, not even one for development.
- A run gets a whole number as its id, counted up by the database. A later milestone, with more than one user, may want an id that cannot be guessed.
- One pull request. The cloud part is applied by the maintainer before the merge, as in task 3.

## Exit criteria

1. `uv run pytest` passes with the local database running, and the new tests were seen to fail first. Without the database, the tests that need it fail; they do not skip.
2. `ruff` and `mypy` pass, and a warning still fails the test run.
3. `docker compose up` starts the app and the database. The maintainer saw the two tables there, and they are still there after `docker compose down` and a new start: the volume line.
4. The maintainer made one real run with `tell.py --save`, read its rows with plain SQL, and saw the SQL that the ORM wrote for one query.
5. The migration can be taken back: after `downgrade`, the two tables are gone.
6. On Azure: `terraform apply` made the server, and a second `terraform plan` says "No changes".
7. After the merge, the deployed app ran the migration, logged in as its managed identity. The maintainer saw the line "The migrations ran" in the log of the app. The tables themselves are not looked at: the firewall lets only Azure's own services in, not the maintainer's machine.
8. The login with a password is off on the server.
9. The image alone, with no setting of a database, still starts: part 1 of the smoke test.
10. No password, no token, no address of the server and no login name of a person is in the repository.

## Test cases

Run by `pytest`. Cases 1 to 13, 16 to 18 need the local database; the others need nothing. The tests use a database of their own on the local server, `book_teller_test`, and make it when it is not there. So a test run never touches the runs that `tell.py --save` wrote.

When the tests were written, a few cases were added to the list: a second run of the migrations changes nothing · the defaults of a new run · a run does not show the faults of another · writing to a run that does not exist is an error, not a silent loss · a wrong value of a setting is an error.

In `backend/tests/test_migrations.py`:

1. On an empty database, the migration makes `runs` and `faults`.
2. `downgrade` removes both.
3. After the migration, Alembic's own comparison finds no difference between the tables and the ORM classes.
4. The database refuses a status that is not in the list, a kind that is not in the list, and a fault for a run that does not exist.
5. The statuses of the `CHECK` are the statuses of the code, and the kinds of the `CHECK` are the six kinds of `check_step.py`.
6. Two faults of one run cannot have the same position.
7. Deleting a run deletes its faults.

In `backend/tests/test_runs.py`:

8. A new run has the status `waiting`, holds the chapter, and has no script.
9. The status can be set to `writing` and to `checking`.
10. A saved result can be read back as it went in: the sentences of the script in order, each fault in the checker's order with the guard's answer, the sums of the tokens and the seconds. The status is `done`, and `finished_at` is set. Curly quote marks and letters with accents come back unchanged.
11. A result with no fault is saved and read back with an empty list.
12. A failed run has the status `failed` and its reason. The function that saves it takes what the steps before the failure cost. (`tell.py` cannot hand that over: see "What the review changed".)
13. Reading a run that does not exist gives nothing, not an error.

In `backend/tests/test_database.py`:

14. A missing setting gives an error that names its environment variable.
15. Making the engine opens no connection, also with a wrong address. (That the app starts with no setting of a database is held by part 1 of the smoke test.)
16. With the Azure login, the token function is asked once for each new connection, and its token is what goes out as the password. The token is asked for the audience of Azure's PostgreSQL service.
17. With the local login, no token is asked.

In `backend/tests/test_tell.py`:

18. With `--save`, a run is written and its number is printed. Without it, the database is never asked.

In `backend/tests/test_build_files.py`:

19. Every image that `compose.yaml` names has a digest.

In `infra/tests/cloud.tftest.hcl`, run by `terraform test`:

20. The login with a password is off, and the login with Microsoft Entra is on.
21. The server is the smallest size, with 32 GB, PostgreSQL 18, in UK South.
22. The firewall rule is the one for Azure services. A test of Terraform cannot count: it cannot show that no second rule exists.
23. The two administrators are the app's identity and the maintainer. For the same reason, the test cannot show that there is no third.
24. The app gets the settings of the database, and still holds no secret.

In `scripts/smoke_test.sh`:

25. Part 1, the image alone: it starts with no database, as before.
26. Part 2, with Docker Compose: after the start, the database holds the two tables.

Kept as they are: all tests of tasks 1 to 6.

Seen once by the maintainer: exit criteria 3, 4, 6 and 7.

## The order of the work

1. A branch for this task. First commit: this plan.
2. The maintainer installs the three libraries, and starts the local database.
3. The tests. They fail: the new modules do not exist.
4. The tables, the migration, `database.py`, `runs.py`, `tell.py --save`, Docker Compose. The tests pass.
5. The pipeline and the smoke test.
6. The cloud: the tests of `main.tf` first, then the file, then `terraform apply` by the maintainer.
7. The review by a second agent, the fixes, the README and the guide.
8. The pull request and the merge. The first deploy runs the migration on Azure.

## What could go wrong

- **Azure refuses the server.** A young subscription can be closed for new database servers in a region. Then: another size, or a request to Azure. The apply shows it, before any code depends on it.
- **A missing right, or a wrong name.** The name of the login in the database must be the name of the identity, letter for letter. The identity also needs its id as a setting of the app, so that the code knows which identity to ask for.
- **The firewall rule does not let the app in.** Not checked before the first deploy.
- **Terraform and Azure disagree after the apply,** as with the workload profile in task 3. A likely place: the zone that Azure picks for the server.
- **No ready-built `psycopg` for Python 3.14,** or a new warning from one of the three libraries. Seen at the install.
- **The data folder of the PostgreSQL 18 image** is not where older versions had it. A wrong volume line loses the data at every restart; exit criterion 3 catches it.
- **The start gets slower,** or fails when the database is down, though no page needs the database yet.
- **The agent cannot reach a database or Azure.** The maintainer runs the tests of cases 1 to 13, the apply and the real run, and the agent reads the output.

## What was seen

On 2026-11-26. First on the maintainer's machine; the part on Azure is at the end.

**The tables.** `docker compose up` started the database and the app, and the app's container ran the migration at its start: `runs`, `faults` and `alembic_version` were there.

**One real run with `tell.py --save`,** with the chapter of the probe. It was saved as run 1.

| Step | Tokens in | Tokens out | Of them thinking | Seconds |
|---|---|---|---|---|
| `write` | 4,069 | 2,146 | 512 | 21.3 |
| `check` | 6,263 | 946 | 896 | 8.5 |

The row of the run, read with plain SQL: status `done`, 10,332 tokens in, 3,092 out, 1,408 of them thinking, 29.9 seconds, 86 sentences in the `jsonb` list. The checker flagged nothing, so `faults` has no row of a real run yet; the tests hold that table.

**The SQL of the ORM.** With SQLAlchemy's log switched on, reading run 1 sent two statements: one `SELECT` on `runs` by its id, and one on `faults` by `run_id`, ordered by `position`.

**The volume line.** After `docker compose down` and a new start, the run was still there.

**The smoke test** passed, with its new line: the migrations made the three tables on an empty database.

**On Azure.** The first plan listed five things to add and two to change. The second change was not expected: Terraform wanted to remove a label (a tag) from the registry, which had been added by hand in the portal and was not in `main.tf`. The maintainer chose to keep the label, so it is written into the file now. Then: a saved plan with five to add and one to change, the apply of that plan, and a new plan that says "No changes". Nothing has logged in to that database yet: the first deploy after the merge does.

## What the review changed

A second agent reviewed the change in a fresh session. It read every changed file, ran the tests that need no database and the checks, and tried four small changes of the code on a copy; no test noticed them. It could reach no database, no Docker and no Azure. The maintainer decided on each finding.

- **The health check of the local database could say "healthy" too early,** at the very first start, before the server listens on the network. Then the tests or the smoke test in the pipeline could fail by chance. The check now asks over the network.
- **No test held the join between the setting "the login is azure" and the token.** The reviewer broke it on a copy, and every test passed. Two tests hold it now.
- **A failed run that `tell.py --save` saves has a cost of 0,** also when the writer had answered: the graph hands nothing back when a step fails for good. **Left so, and said** in the code. The worker of task 9 saves a run step by step.
- **The maintainer cannot look into the database on Azure:** the firewall lets only Azure's services in. Exit criterion 7 said "saw the tables"; it now names the line in the log of the app.
- **Sentences that were stale or promised too much:** "nothing is built yet", "exactly one firewall rule", "nobody else", and "the two cannot drift apart" for the tables and their classes. Corrected.
- **Two functions had the name `azure_login`,** one for the model and one for the database. The new one is `azure_database_login`.
- **Kept, though nothing runs them yet:** `alembic.ini`, the template for a new migration, and the second way through `migrations/env.py`. They are for the command `alembic`, which the second migration will need.
- **Left as it is:** with `--save` against Azure, a login that fails ends in the long words of the library, not in one line.
- **The connection to Azure is encrypted, and the server's certificate is not checked** (`sslmode=require`). The stricter setting, `verify-full`, is what Microsoft's pages advise. **Left so, and said** in the code (the maintainer). The ready-built driver does not find the certificates of the system by itself, by the reports of other projects, so the stricter setting needs one more library and a try against the real server.
- **Not taken, because neither mistake has happened:** a limit of 10 seconds for opening a connection (a firewall that is closed shows only after about two minutes, the limit of the driver) · a check in the smoke test that the migration files are inside the image (Docker Compose runs the code of the folder, not of the image; the Dockerfile copies the whole folder of code). If the first deploy hangs: wait two minutes, then read the log of the app.

## How it is undone

Take the new files and the option `--save` out, and the `db` service out of `compose.yaml`. Take the server out of `main.tf` and apply: Azure deletes the server and its data, and the cost ends. Only test runs are lost.
