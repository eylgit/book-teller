# Milestone 1: the whole path once

**State:** planned on 2026-11-14. Task 1 is built: [its plan](../2026-11-16-app_skeleton/plan.md).

## The goal

One pasted chapter of a book in the public domain becomes a checked episode script on a public page. It is the whole path of the product, once, thin: from the browser to the model and back, shipped by a pull request and running on Azure.

This file is the plan of the milestone. Each task below gets its own plan folder when it starts, as [CLAUDE.md](../../../CLAUDE.md) says.

## Exit criteria

1. A public page takes one pasted chapter and shows a script that tells it.
2. Under the script, the page lists each fault that the checker found, with the line of the chapter that proves it.
3. Plain code has checked that every such proof line is found in the chapter. A fault whose proof line is not found is marked, not shown as proven.
4. The page shows four numbers: faults caught and false alarms on a test with planted faults, and the cost and the time of one run.
5. The run happens in the background, and the page shows its progress.
6. One play button plays the script as sound.
7. Only the owner can start a run.
8. Every change after the first reaches the main branch by a pull request, and the pipeline runs the tests on it. A merge deploys.
9. No key of the model, the queue, the database or the image store is stored anywhere: the app uses a managed identity.
10. The README links to the running page.

## The path of one run

```
 Browser              Web app              Queue               Worker                  Model
     |-- chapter ------->|                    |                   |                       |
     |                   |-- new run -----> DATABASE              |                       |
     |                   |-- message -------->|                   |                       |
     |<-- run id --------|                    |-- starts -------->|                       |
     |                   |                    |                   |-- write the script -->|
     |                   |                    |                   |-- check the script -->|
     |                   |                    |                   |-- the guard (plain code)
     |                   |                    |                   |-- result -----> DATABASE
     |-- "how far?" ---->|-- reads the DATABASE                   |                       |
```

## What is used, and why

| Part | Choice | Why |
|---|---|---|
| Page | Plain HTML, Bootstrap, a little JavaScript | One form and one result. A front-end framework would add nothing yet |
| Web app | FastAPI | Typed requests and answers with Pydantic, which the guard uses too |
| Background run | Azure Service Bus, and a worker that runs as a Container Apps job | A run takes about 40 seconds, too long for one page request. Azure runs the queue, and it works with a managed identity |
| The two steps | LangGraph: write, then check, with one shared state | Two steps do not need a graph. The whole book of milestone 2 does: it must go on after a failure |
| Model | `gpt-5-mini` on Azure AI Foundry, called through LangChain's model classes | The probe of 2026-11-13 found it good enough to go on. The same model interface serves the tools of a later milestone |
| The guard | Pydantic for the shape of the answer; plain code for "the quote is in the chapter" | A model can make a quote up. A check in code gives the same answer every time |
| Database | PostgreSQL, with SQLAlchemy and Alembic | A later milestone searches by meaning, with pgvector |
| Tracing | OpenTelemetry, to Langfuse for the model calls and to Application Insights for the service | Cost and time of each run, and one request ID from the page to the model call |
| Ship path | Docker image · Azure Pipelines · Azure Container Registry · Azure Container Apps, with zero copies when idle | Nothing is paid when nobody visits. The first visitor then waits while the app starts |
| The cloud | One Terraform file | The cloud can be made again, and a change to it is a change in git |
| Login to Azure services | A managed identity | No key to store or to leak |
| On the maintainer's machine | Docker Compose: the app and a database | A change can be tried without the cloud |

## Known limits

- **A point that the script leaves out** (fault kind 6) is looked for and not measured. The probe missed both planted cases, and code cannot score this kind well. The four numbers count kinds 1 to 5.
- **English only.**
- **At most 10 minutes of sound** for an episode: the limit of one request to the speech service.
- **One chapter, not a book.** Retries, and going on after a failure, belong to milestone 2.
- **Two secrets still exist,** in Azure Key Vault: the owner's key for the run route, until there is a login, and the key of the tracing service.

## The tasks, in order

The order is by risk. The cloud is the risky part, so the ship path comes first, with an empty page. The model call already worked in the probe.

| # | Task |
|---|---|
| 1 | The skeleton: a FastAPI app with one page, its tests, the lockfile, the linter and the type checker. It runs with Docker Compose |
| 2 | The pipeline: the tests on every pull request, a fixed version of the build machine, a protected main branch, the full merge rule |
| 3 | The cloud as a Terraform file, and deploy on merge. The empty page is live, and the app has its managed identity |
| 4 | The model call: structured output, the thinking setting, a timeout, a fake model for the tests |
| 5 | The graph of two steps: write, then check |
| 6 | The guard: the shape check and the quote check, and what happens when the guard says no |
| 7 | ~~Streaming: one answer sent piece by piece, in a small script~~ Left out (the maintainer, 2026-11-26). No part of the product needs it: the two model steps ask for an answer in a fixed shape, and the run happens in the background |
| 8 | The database: the tables for runs and faults, and the first migration |
| 9a | The run, without a queue: the routes, the page with its progress line, the owner's key, the limit on the pasted text, the cap of the day. The web app does the run itself. Split from task 9 on 2026-11-27: [its plan](../2026-11-27-run_without_queue/plan.md) |
| 9b | The queue and the worker: the run moves out of the web app |
| 10 | Tracing: one request ID from the page to the model call |
| 11 | The planted-fault test and the four numbers on the page, with their limits said |
| 12 | The sound: one play button |

**If time runs out,** these are left for milestone 2, in this order: the sound · the queue (the web app starts the worker directly) · the second tracing tool.

## What could go wrong

- **A permission.** Each managed identity needs its role on each service. A missing role is the most likely place for the build to stop.
- **The queue and the job.** That a Container Apps job can be started from Service Bus with a managed identity is not checked yet. Task 9b checks it first.
- **Structured output together with the thinking setting** through LangChain's model classes: bug reports are open. Task 4 checks it first.
- **Cost.** The database runs all the time and is the largest part. A cap on the runs of one day stops a loop of model calls.
